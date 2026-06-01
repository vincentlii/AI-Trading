import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path

from research_pipeline.legacy.registry import get_legacy_mapping
from scripts.run_stage6e_aggregator import main as aggregate_main
from scripts.run_stage7_smoke_plan import main as smoke_main


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class LegacyAggregationWrappersTest(unittest.TestCase):
    def test_stage6e_wrapper_calls_readonly_pipeline_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = aggregate_main(
                    [
                        "--summary-dir",
                        str(SUMMARY_DIR),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "stage6e_aggregated_comparison.csv").exists())
            self.assertTrue((output_dir / "stage6e_aggregator_final_report.md").exists())
            self.assertIn("displacement_after_reclaim", (output_dir / "stage6e_aggregator_final_report.md").read_text(encoding="utf-8"))

    def test_stage7_smoke_wrapper_calls_readonly_pipeline_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            aggregate_dir = Path(temp_dir) / "agg"
            smoke_dir = Path(temp_dir) / "smoke"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                aggregate_main(["--summary-dir", str(SUMMARY_DIR), "--output-dir", str(aggregate_dir)])

                exit_code = smoke_main(
                    [
                        "--aggregation-result",
                        str(aggregate_dir / "aggregation_result.json"),
                        "--output-dir",
                        str(smoke_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            plan = (smoke_dir / "stage7_smoke_plan.md").read_text(encoding="utf-8")
            self.assertIn("CHOCH true", plan)
            self.assertIn("displacement_after_reclaim", plan)
            self.assertIn("formal_conclusion_enabled: false", plan)

    def test_registry_marks_readonly_wrappers_without_core_strategy_migration(self) -> None:
        aggregation = get_legacy_mapping("stage6e-aggregate")
        smoke = get_legacy_mapping("stage7-smoke-plan")

        self.assertFalse(aggregation.calls_old_logic)
        self.assertFalse(smoke.calls_old_logic)
        self.assertFalse(aggregation.migrated_to_core)
        self.assertFalse(smoke.migrated_to_core)
        self.assertTrue(aggregation.readonly_wrapper_to_core)
        self.assertTrue(smoke.readonly_wrapper_to_core)


if __name__ == "__main__":
    unittest.main()
