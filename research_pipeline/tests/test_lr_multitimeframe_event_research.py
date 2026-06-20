from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_pipeline.cli.research import main
from research_pipeline.runners.lr_multitimeframe_event_research import (
    audit_multitimeframe_research,
    build_research_summaries,
    deterministic_rows_hash,
    run_lr_multitimeframe_event_research,
)


class LRMultiTimeframeEventResearchTest(unittest.TestCase):
    def test_runner_is_development_only_and_writes_diagnostic_artifacts(self):
        class EmptyRepository:
            def __init__(self):
                self.calls = []

            def load_range(self, inst_id, bar, start_ms, end_ms, **kwargs):
                self.calls.append((inst_id, bar, start_ms, end_ms, kwargs))
                return ()

        repository = EmptyRepository()
        target = SimpleNamespace(inst_id="BTC-USDT-SWAP", venue="okx", inst_type="SWAP")
        preset = SimpleNamespace(
            config_fingerprint="test-config",
            to_scan_config=lambda: SimpleNamespace(targets=(target,)),
        )
        with tempfile.TemporaryDirectory() as directory:
            result = run_lr_multitimeframe_event_research(
                repository=repository,
                preset=preset,
                output_root=Path(directory),
                start_date="2021-01-01",
                end_date="2021-01-15",
            )
            root = Path(result.run_root)
            manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
            report = (root / "lr_multitimeframe_vpa_causal_event_report.md").read_text(encoding="utf-8")

            self.assertEqual({call[1] for call in repository.calls}, {"15m", "1H", "4H"})
            self.assertTrue(all(call[4]["confirmed_only"] for call in repository.calls))
            self.assertTrue(all(call[3] < 1_733_011_200_000 for call in repository.calls))
            self.assertEqual(manifest["schema_version"], "lr_multitimeframe_event_research.v1")
            self.assertFalse(manifest["holdout_accessed"])
            self.assertIsNone(manifest["selected_variant"])
            self.assertEqual((root / "closed_trade_rows.jsonl").read_text(encoding="utf-8"), "")
            self.assertEqual((root / "execution_rows.jsonl").read_text(encoding="utf-8"), "")
            for name in (
                "event_rows.jsonl",
                "vpa_feature_rows.jsonl",
                "diagnostic_label_rows.jsonl",
                "anatomy_rows.jsonl",
                "summary_rows.jsonl",
                "causality_audit.json",
                "artifact_index.json",
            ):
                self.assertTrue((root / name).exists(), name)
            for heading in (
                "lr_multitimeframe_event_scanner_report",
                "lr_vpa_attribution_report",
                "lr_event_timeframe_anatomy_report",
                "lr_event_causality_audit_report",
                "lr_research_direction_recommendation",
            ):
                self.assertIn(heading, report)
            for question in range(1, 7):
                self.assertIn(f"研究问题 {question}", report)
            self.assertIn("15m / 1H / 4H", report)
            self.assertNotIn("hard winner", report.lower())

        with self.assertRaisesRegex(ValueError, "sealed holdout"):
            run_lr_multitimeframe_event_research(
                repository=repository,
                preset=preset,
                output_root=Path("unused"),
                start_date="2024-11-01",
                end_date="2024-12-01",
            )

    def test_audit_rejects_causality_and_feature_label_contamination(self):
        event = {
            "event_id": "event-1",
            "physical_event_key": "physical-1",
            "bar_confirmed": True,
            "reclaim_time": 100,
            "signal_time": 100,
            "feature_cutoff_time": 100,
        }
        feature = {
            "event_id": "event-1",
            "row_role": "tradable_feature",
            "signal_time": 100,
            "feature_cutoff_time": 100,
            "max_source_time": 100,
        }
        label = {
            "event_id": "event-1",
            "row_role": "diagnostic_label",
            "signal_time": 100,
            "min_source_time": 101,
        }

        passed = audit_multitimeframe_research((event,), (feature,), (label,), holdout_accessed=False)
        self.assertEqual(passed["status"], "pass")
        self.assertEqual(passed["unique_physical_event_count"], 1)

        bad_feature = {**feature, "max_source_time": 101}
        failed = audit_multitimeframe_research(
            ({**event, "bar_confirmed": False},),
            (bad_feature,),
            ({**label, "row_role": "tradable_feature"},),
            holdout_accessed=True,
        )
        self.assertEqual(failed["status"], "fail")
        self.assertGreater(failed["violation_count"], 0)
        self.assertIn("holdout_accessed", failed["violations"])

    def test_core_row_hash_is_order_independent_and_deterministic(self):
        rows = ({"b": 2, "a": 1}, {"a": 3, "b": 4})

        first = deterministic_rows_hash(rows)
        second = deterministic_rows_hash(tuple(reversed(rows)))

        self.assertEqual(first, second)

    def test_summaries_cover_cross_year_stability_and_all_causal_vpa_features(self):
        events = []
        features = []
        anatomy = []
        for index, year_ms in enumerate((1_609_459_200_000, 1_640_995_200_000)):
            event_id = f"event-{index}"
            events.append(
                {
                    "event_id": event_id,
                    "physical_event_key": event_id,
                    "event_timeframe": "1H_sweep_reclaim",
                    "instrument": "BTC-USDT-SWAP",
                    "direction": "long",
                    "signal_time": year_ms,
                    "level_family": "previous_day_high_low",
                }
            )
            features.append(
                {
                    "event_id": event_id,
                    "sweep_volume_bucket": "q4",
                    "reclaim_volume_bucket": "q3",
                    "sweep_relative_volume": 1.6,
                    "reclaim_relative_volume": 1.3,
                    "sweep_range_expansion": 1.7,
                    "reclaim_range_expansion": 1.1,
                    "wick_ratio": 0.6,
                    "close_location_value": 0.8,
                    "combined_volume_ratio": 1.4,
                }
            )
            anatomy.append(
                {
                    "event_id": event_id,
                    "MFE_R": 1.0,
                    "MAE_R": -0.5,
                    "forward_240m_R": 0.5 + index,
                    "follow_through_status": "follow_through",
                    "invalidation_first_status": "not_invalidation_first",
                }
            )

        summaries = build_research_summaries(events, features, anatomy)

        self.assertTrue(any(row["row_type"] == "cross_year_stability_summary" for row in summaries))
        vpa_names = {
            row["feature_name"]
            for row in summaries
            if row["row_type"] == "vpa_bucket_summary"
        }
        self.assertTrue(
            {
                "sweep_relative_volume",
                "reclaim_relative_volume",
                "sweep_range_expansion",
                "reclaim_range_expansion",
                "wick_ratio",
                "close_location_value",
                "combined_volume_ratio",
            }.issubset(vpa_names)
        )

    def test_cli_dispatches_multitimeframe_event_research(self):
        result = SimpleNamespace(as_json=lambda: "{}", run_root="unused")
        with (
            patch("research_pipeline.cli.research.load_backtest_preset", return_value="preset"),
            patch("research_pipeline.cli.research.DuckDbCandleRepository", return_value="repository"),
            patch(
                "research_pipeline.cli.research.run_lr_multitimeframe_event_research",
                return_value=result,
                create=True,
            ) as runner,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = main(
                [
                    "lr-causal-rebuild",
                    "--stage",
                    "multitimeframe-events",
                    "--mode",
                    "development",
                    "--start",
                    "2021-01-01",
                    "--end",
                    "2021-01-15",
                ]
            )

        self.assertEqual(exit_code, 0)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["start_date"], "2021-01-01")
        self.assertEqual(runner.call_args.kwargs["end_date"], "2021-01-15")


if __name__ == "__main__":
    unittest.main()
