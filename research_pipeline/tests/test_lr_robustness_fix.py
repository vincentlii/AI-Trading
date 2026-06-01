import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_robustness_fix import run_lr_robustness_fix


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _closed_row(
    candidate_id: str,
    combo_name: str,
    tier: str,
    priority: int,
    net_r: float,
    cost_tier: str,
    *,
    profile: str,
    entry_time: int,
    exit_time: int,
) -> dict:
    penalty = {"base": 0.0, "stress": 0.05, "harsh": 0.12}.get(cost_tier, 0.0)
    return {
        "asset": "ETH",
        "profile": profile,
        "direction": "long",
        "candidate_id": candidate_id,
        "event_id": candidate_id,
        "event_key": candidate_id,
        "trade_id": f"trade_{candidate_id}",
        "execution_id": f"exec_{candidate_id}",
        "combo_name": combo_name,
        "tier": tier,
        "priority": priority,
        "cost_tier": cost_tier,
        "row_type": "closed_trade",
        "closed_trade": True,
        "eligible_for_performance": True,
        "eligible_for_robustness": True,
        "invalid_for_robustness": False,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "bar_confirmed": True,
        "no_lookahead_safe": True,
        "net_R": net_r - penalty,
        "mfe_R": 1.2,
        "mae_R": 0.2,
        "fee_cost": 0.01,
        "slippage_cost": 0.0,
        "funding_cost": 0.0,
        "portfolio_heat": 0.005,
        "margin_required": 1000,
        "notional_to_equity_pct": 0.1,
        "time_cut_exit": False,
        "loss_time_cut": False,
        "same_bar_ambiguous": False,
        "forced_pessimistic_exit": False,
        "liquidation_event": False,
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _filter_row(candidate_id: str, profile: str, *, approved: bool, displacement: bool, choch: bool) -> dict:
    return {
        "candidate_id": candidate_id,
        "event_id": candidate_id,
        "profile": profile,
        "asset": "ETH",
        "structure_level_source": "session_high_low" if displacement else "recent_swing",
        "session_high_low_tag": displacement,
        "formal_approved": approved,
        "reject_reason": "" if approved else "margin_required_too_high",
        "sweep_time": 100,
        "reclaim_time": 110,
        "signal_time": 120,
        "entry_time": 130,
        "displacement_direction_valid": displacement,
        "choch_valid_for_direction": choch,
    }


class LRRobustnessFixTest(unittest.TestCase):
    def test_profile_root_cause_and_outputs_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_dir = root / "lr_combined_fix"
            filter_dir = root / "minimal_lr_v0_filter" / "10000w"
            artifact_dir.mkdir()
            filter_dir.mkdir(parents=True)
            rows = []
            for cost_tier in ("base", "stress", "harsh"):
                rows.append(_closed_row("c1", "T1_session_hl_attempt4_fixed_current", "Tier 1", 1, 1.0, cost_tier, profile="C", entry_time=1000, exit_time=3000))
                rows.append(_closed_row("c2", "T2_session_hl_attempt3_dynamic_quality", "Tier 2", 4, 0.4, cost_tier, profile="C", entry_time=1100, exit_time=3100))
                rows.append(_closed_row("b1", "T2_session_hl_attempt3_dynamic_quality", "Tier 2", 4, -0.2, cost_tier, profile="B", entry_time=1200, exit_time=3200))
            _write_jsonl(artifact_dir / "lr_combined_combo_rows.jsonl", rows)
            _write_jsonl(
                filter_dir / "minimal_lr_v0_filter_results.jsonl",
                [
                    _filter_row("c1", "C", approved=True, displacement=True, choch=True),
                    _filter_row("c2", "C", approved=True, displacement=False, choch=True),
                    _filter_row("b1", "B", approved=True, displacement=False, choch=True),
                    _filter_row("b2", "B", approved=False, displacement=False, choch=False),
                ],
            )

            output_dir = root / "fix"
            result = run_lr_robustness_fix(artifact_dir=artifact_dir, output_dir=output_dir, monte_carlo_seeds=20)

            self.assertEqual(result.profile_root_cause["B"]["fresh_candidates"], 2)
            self.assertEqual(result.profile_root_cause["B"]["closed_trades"], 1)
            self.assertGreaterEqual(result.profile_root_cause["B"]["formal_approved"], 1)
            self.assertTrue((output_dir / "lr_profile_concentration_root_cause_report.md").exists())
            self.assertTrue((output_dir / "lr_profile_funnel_rows.jsonl").exists())
            self.assertTrue((output_dir / "lr_exposure_restriction_rows.jsonl").exists())
            self.assertTrue((output_dir / "artifact_index.json").exists())

    def test_cli_runs_and_global_cap_reduces_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_dir = root / "lr_combined_fix"
            artifact_dir.mkdir()
            rows = []
            for cost_tier in ("base", "stress", "harsh"):
                for idx in range(6):
                    rows.append(
                        _closed_row(
                            f"c{idx}",
                            "T1_session_hl_attempt4_fixed_current",
                            "Tier 1",
                            1,
                            0.8,
                            cost_tier,
                            profile="C",
                            entry_time=1000 + idx,
                            exit_time=3000 + idx,
                        )
                    )
            _write_jsonl(artifact_dir / "lr_combined_combo_rows.jsonl", rows)

            output_dir = root / "fix"
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-robustness-fix",
                        "--artifact-dir",
                        str(artifact_dir),
                        "--output-dir",
                        str(output_dir),
                        "--monte-carlo-seeds",
                        "20",
                    ]
                )

            self.assertEqual(code, 0)
            result = json.loads((output_dir / "lr_robustness_fix_result.json").read_text(encoding="utf-8"))
            by_name = {row["restriction_name"]: row for row in result["restriction_summary"] if row["cost_tier"] == "base"}
            self.assertEqual(by_name["global_max_concurrent_3"]["max_concurrent_positions"], 3)
            self.assertLess(
                by_name["global_max_concurrent_3"]["max_concurrent_positions"],
                by_name["variant_b_unrestricted"]["max_concurrent_positions"],
            )


if __name__ == "__main__":
    unittest.main()
