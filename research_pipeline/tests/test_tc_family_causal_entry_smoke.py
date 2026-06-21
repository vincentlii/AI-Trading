from __future__ import annotations

import unittest
import tempfile
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from research_pipeline.runners.tc_family_causal_entry_smoke import (
    _event_available_time_ms,
    _execution_bar_count,
    _load_candidate_rows,
    _normalize_candidate_availability,
    _render_report,
    _research_variant_summary,
    _scaled_execution_preset,
    _smoke_gate_passes,
)
from trading_system.config import load_backtest_preset
from research_pipeline.cli.research import main

class TcFamilyCausalEntrySmokeTests(unittest.TestCase):
    def test_cli_dispatches_causal_entry_smoke(self) -> None:
        result = type(
            "Result",
            (),
            {"as_dict": lambda self: {"decision": "proceed_to_profile_b"}},
        )()
        stdout = io.StringIO()
        with patch("research_pipeline.cli.research.DuckDbCandleRepository", return_value=object()):
            with patch(
                "research_pipeline.cli.research.run_tc_family_causal_entry_smoke",
                return_value=result,
            ) as runner:
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "tc-family-causal-entry-smoke",
                            "--preset",
                            "configs/presets/btc_eth_swap_tc_formal.toml",
                            "--db",
                            "storage/history_ro_temp_backtest.duckdb",
                            "--source-candidates",
                            "candidate_rows.jsonl",
                            "--profile-b-source-candidates",
                            "profile_b_candidate_rows.jsonl",
                            "--dataset-window",
                            "fixture",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("proceed_to_profile_b", stdout.getvalue())
        runner.assert_called_once()
        self.assertEqual(
            runner.call_args.kwargs["profile_b_source_candidate_rows"],
            Path("profile_b_candidate_rows.jsonl"),
        )

    def test_profile_c_event_is_available_only_after_the_4h_bar_closes(self) -> None:
        candidate = {"profile": "C", "relaunch_time": 12 * 60 * 60_000}

        self.assertEqual(_event_available_time_ms(candidate), 16 * 60 * 60_000)

    def test_candidate_loader_reads_jsonl_artifact_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "candidate_rows.jsonl"
            path.write_text('{"candidate_id":"c1"}\n', encoding="utf-8")

            self.assertEqual(_load_candidate_rows(path), ({"candidate_id": "c1"},))

    def test_candidate_signal_and_feature_cutoff_use_event_availability(self) -> None:
        candidate = {
            "profile": "C",
            "relaunch_time": 12 * 60 * 60_000,
            "signal_time": 15 * 60 * 60_000,
            "timestamp_ms": 15 * 60 * 60_000,
        }

        normalized = _normalize_candidate_availability(candidate)

        self.assertEqual(normalized["event_available_time_ms"], 16 * 60 * 60_000)
        self.assertEqual(normalized["signal_time"], 16 * 60 * 60_000)
        self.assertEqual(normalized["feature_cutoff_time"], 16 * 60 * 60_000)
        self.assertEqual(normalized["timestamp_ms"], 16 * 60 * 60_000)

    def test_bar_count_scaling_preserves_elapsed_time(self) -> None:
        self.assertEqual(_execution_bar_count(20, source_timeframe="1h", target_timeframe="15m"), 80)
        self.assertEqual(_execution_bar_count(8, source_timeframe="1h", target_timeframe="15m"), 32)
        self.assertEqual(_execution_bar_count(22, source_timeframe="1h", target_timeframe="15m"), 88)

    def test_scaled_preset_preserves_elapsed_exit_horizons(self) -> None:
        preset = load_backtest_preset(
            Path(__file__).resolve().parents[2] / "configs" / "presets" / "btc_eth_swap_tc_formal.toml"
        )

        scaled = _scaled_execution_preset(preset, source_timeframe="1h", target_timeframe="15m")

        self.assertEqual(scaled.execution.max_holding_bars, 80)
        self.assertEqual(scaled.execution.reversal_time_cut_bars, 32)
        self.assertEqual(scaled.execution.chandelier_period, 88)

    def test_smoke_gate_requires_cost_stability_and_balanced_subgroups(self) -> None:
        passing = {
            "closed_trades": 84,
            "base_avg_r": 0.08,
            "harsh_avg_r": 0.01,
            "base_median_r": 0.02,
            "base_pf": 1.2,
            "positive_walk_forward_windows": 4,
            "walk_forward_windows": 5,
            "improvement_vs_control_r": 0.13,
            "subgroup_harsh_avg_r": {"BTC": 0.01, "ETH": 0.02, "long": -0.04, "short": 0.03},
        }

        self.assertTrue(_smoke_gate_passes(passing))
        self.assertFalse(_smoke_gate_passes({**passing, "harsh_avg_r": -0.01}))
        self.assertFalse(_smoke_gate_passes({**passing, "closed_trades": 79}))
        self.assertFalse(
            _smoke_gate_passes(
                {**passing, "subgroup_harsh_avg_r": {**passing["subgroup_harsh_avg_r"], "ETH": -0.06}}
            )
        )

    def test_report_is_single_concentrated_stage_summary(self) -> None:
        report = _render_report(
            {
                "decision": "proceed_to_profile_b",
                "source_candidate_count": 84,
                "variants": {
                    "c_4h_next_1h_open_control": {"closed_trades": 84, "base_avg_r": -0.04, "harsh_avg_r": -0.09},
                    "c_4h_next_15m_open": {"closed_trades": 84, "base_avg_r": 0.01, "harsh_avg_r": -0.02},
                },
            }
        )

        self.assertIn("# TC Causal Entry Rescue Smoke v1", report)
        self.assertIn("c_4h_next_15m_open", report)
        self.assertIn("proceed_to_profile_b", report)
        self.assertIn("Base PF", report)
        self.assertIn("## Stop Rule", report)

    def test_research_variant_label_does_not_replace_family_variant_identity(self) -> None:
        summary = _research_variant_summary({"variant_id": "bp_lifecycle_level_zone_v1"}, "c_4h_next_15m_open")

        self.assertEqual(summary["family_variant_id"], "bp_lifecycle_level_zone_v1")
        self.assertEqual(summary["variant_id"], "c_4h_next_15m_open")


if __name__ == "__main__":
    unittest.main()
