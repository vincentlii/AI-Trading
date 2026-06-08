import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.reports.trend_continuation_core_rebuild import (
    REPORT_FILENAME,
    render_trend_continuation_core_rebuild_report,
    write_trend_continuation_core_rebuild_report,
)


class TrendContinuationCoreRebuildReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "run_id": "bp-core-rebuild-test",
            "total_windows": 8000,
            "structure_zones_found": 4200,
            "breakout_event_seeds": 1800,
            "breakout_class_distribution": {
                "strong_breakout": 120,
                "accepted_breakout": 440,
                "weak_but_watch": 810,
                "failed_breakout": 430,
            },
            "candidate_ready_windows": 510,
            "failure_taxonomy": {
                "pullback_health_failed": 260,
                "no_relaunch_observed": 180,
            },
            "previous_round": {
                "old_true_breakout_failed": 7169,
                "old_candidate_ready_windows": 194,
                "old_raw_candidates": 49,
            },
        }
        self.variants = {
            "bp_lifecycle_level_zone_retest_v2": {
                "raw_candidates": 80,
                "formal_approved": 42,
                "closed_trades": 38,
                "base_net_R_avg": 0.12,
                "stress_net_R_avg": 0.08,
                "harsh_net_R_avg": 0.05,
                "PF": 1.28,
                "median_R": 0.03,
                "full_audit_gate": "passed",
                "no_lookahead": "passed",
                "metric_recompute": "passed",
                "regression_baseline": "passed",
                "interpretation": "Level/zone retest is the strongest bounded variant.",
            },
            "bp_lifecycle_weak_break_watch_v2": {
                "raw_candidates": 31,
                "formal_approved": 12,
                "closed_trades": 10,
                "base_net_R_avg": -0.01,
                "stress_net_R_avg": -0.03,
                "harsh_net_R_avg": -0.06,
                "PF": 0.94,
                "interpretation": "Weak break watch adds events but not robust edge.",
            },
        }
        self.metadata = {
            "run_id": "bp-core-rebuild-test",
            "artifact_paths": ["run_manifest.json", "closed_trade_rows.jsonl"],
            "manifest_summary": "breakout_pullback lifecycle core v2; proposal-only",
            "known_limitations": ["Limited BTC/ETH sample."],
        }

    def test_render_contains_all_required_sections_and_hard_boundaries(self) -> None:
        report = render_trend_continuation_core_rebuild_report(
            baseline_summary=self.baseline,
            variant_summaries=self.variants,
            metadata=self.metadata,
        )

        required_sections = (
            "1. Executive Summary",
            "2. Why Previous TC / CE / BP Failed",
            "3. Research Scope and Constraints",
            "4. Rebuilt Shared Engine Design",
            "5. Structure Zone Diagnostics",
            "6. Breakout Lifecycle Diagnostics",
            "7. Pullback Health Diagnostics",
            "8. Relaunch Confirmation Diagnostics",
            "9. Structural Stop and Risk Diagnostics",
            "10. Target and Cost-Adjusted Tradeability",
            "11. Variant Results",
            "12. Subtype Analysis",
            "13. Return Quality and Robustness",
            "14. Asset / Profile / Direction Split",
            "15. Decision",
            "16. Next Action Plan",
            "17. Appendix / Reproducibility Notes",
        )
        for section in required_sections:
            self.assertIn(f"## {section}", report)

        self.assertIn("proposal-only", report)
        self.assertIn("No formalization", report)
        self.assertIn("No P6", report)
        self.assertIn("LR final evidence remains untouched", report)
        self.assertIn("row_type=closed_trade", report)
        self.assertIn("bp_lifecycle_level_zone_retest_v2", report)
        self.assertIn("7169", report)
        self.assertIn("weak_but_watch", report)
        self.assertIn("passed", report)

    def test_render_does_not_mutate_machine_readable_inputs(self) -> None:
        baseline_before = repr(self.baseline)
        variants_before = repr(self.variants)
        metadata_before = repr(self.metadata)

        render_trend_continuation_core_rebuild_report(
            baseline_summary=self.baseline,
            variant_summaries=self.variants,
            metadata=self.metadata,
        )

        self.assertEqual(repr(self.baseline), baseline_before)
        self.assertEqual(repr(self.variants), variants_before)
        self.assertEqual(repr(self.metadata), metadata_before)

    def test_writer_uses_concentrated_report_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_trend_continuation_core_rebuild_report(
                output_dir=Path(temp_dir),
                baseline_summary=self.baseline,
                variant_summaries=self.variants,
                metadata=self.metadata,
            )

            self.assertEqual(path.name, REPORT_FILENAME)
            self.assertTrue(path.exists())
            self.assertIn("## 15. Decision", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
