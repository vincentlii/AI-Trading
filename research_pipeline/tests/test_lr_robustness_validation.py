import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_robustness_validation import run_lr_robustness_validation


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _closed_row(candidate_id: str, combo_name: str, tier: str, priority: int, net_r: float, cost_tier: str) -> dict:
    penalty = {"base": 0.0, "stress": 0.05, "harsh": 0.12}[cost_tier]
    adjusted = net_r - penalty
    return {
        "asset": "ETH",
        "profile": "C",
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
        "entry_time": 1000 if candidate_id.endswith("1") else 2000,
        "exit_time": 2000 if candidate_id.endswith("1") else 3000,
        "bar_confirmed": True,
        "no_lookahead_safe": True,
        "net_R": adjusted,
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


class LRRobustnessValidationTest(unittest.TestCase):
    def test_runner_uses_closed_trade_rows_and_writes_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_dir = root / "lr_combined_fix"
            audit_dir = root / "full_audit"
            artifact_dir.mkdir()
            audit_dir.mkdir()
            rows = []
            for cost_tier in ("base", "stress", "harsh"):
                for idx in range(1, 6):
                    combo_name = (
                        "T1_session_hl_attempt4_fixed_current"
                        if idx <= 3
                        else "T2_session_hl_attempt3_dynamic_quality"
                    )
                    tier = "Tier 1" if idx <= 3 else "Tier 2"
                    priority = 1 if idx <= 3 else 4
                    rows.append(
                        _closed_row(
                            f"event{idx}",
                            combo_name,
                            tier,
                            priority,
                            0.8 if idx <= 3 else 0.4,
                            cost_tier,
                        )
                    )
            _write_jsonl(artifact_dir / "lr_combined_combo_rows.jsonl", rows)
            (audit_dir / "full_pipeline_audit_result.json").write_text(
                json.dumps(
                    {
                        "audit_passed": True,
                        "blocking_issues": [],
                        "non_blocking_warnings": [],
                        "join_integrity_rows": [
                            {
                                "scope": "Variant B - Tier 1 + Positive Tier 2",
                                "missing_execution_row_count": 0,
                                "proposal_only_unexecuted_count": 0,
                                "selected_without_closed_count": 0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output_dir = root / "robustness"
            result = run_lr_robustness_validation(
                artifact_dir=artifact_dir,
                output_dir=output_dir,
                monte_carlo_seeds=20,
            )

            self.assertTrue(result.preflight_passed)
            self.assertIn(result.primary_decision, {"A", "C"})
            self.assertEqual(result.cost_stress_summary[0]["closed_trades"], 5)
            self.assertTrue((output_dir / "lr_robustness_validation_result.json").exists())
            self.assertTrue((output_dir / "lr_robustness_validation_report.md").exists())
            self.assertTrue((output_dir / "lr_robustness_monte_carlo_rows.jsonl").exists())
            self.assertTrue((output_dir / "artifact_index.json").exists())
            self.assertTrue((output_dir / "research_run_registry.json").exists())

    def test_cli_writes_robustness_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_dir = root / "lr_combined_fix"
            audit_dir = root / "full_audit"
            artifact_dir.mkdir()
            audit_dir.mkdir()
            rows = [_closed_row("event1", "T1_session_hl_attempt4_fixed_current", "Tier 1", 1, 0.8, tier) for tier in ("base", "stress", "harsh")]
            _write_jsonl(artifact_dir / "lr_combined_combo_rows.jsonl", rows)
            (audit_dir / "full_pipeline_audit_result.json").write_text(
                json.dumps({"audit_passed": True, "blocking_issues": [], "non_blocking_warnings": []}),
                encoding="utf-8",
            )

            output_dir = root / "robustness"
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "lr-robustness-validation",
                        "--artifact-dir",
                        str(artifact_dir),
                        "--output-dir",
                        str(output_dir),
                        "--monte-carlo-seeds",
                        "10",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "lr_robustness_cost_stress_rows.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
