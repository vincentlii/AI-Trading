import unittest
from pathlib import Path

from research_pipeline.runners.research_flow_audit import run_research_flow_audit


ARTIFACT_DIR = Path("storage/backtest_cache/lr_combined_fix_pr11g")


class ResearchFlowLineageAuditTest(unittest.TestCase):
    def test_lineage_marks_performance_metrics_as_closed_trade_only(self) -> None:
        result = run_research_flow_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            artifact_index=None,
            registry=None,
            output_dir=None,
        )
        lineage = {row["metric_name"]: row for row in result.as_dict()["lineage_rows"]}

        self.assertEqual(lineage["net_R_avg"]["source_row_type"], "closed_trade")
        self.assertTrue(lineage["net_R_avg"]["can_enter_performance_metrics"])
        self.assertEqual(lineage["selected_trades"]["source_row_type"], "selected_candidate")
        self.assertFalse(lineage["selected_trades"]["can_enter_performance_metrics"])


if __name__ == "__main__":
    unittest.main()
