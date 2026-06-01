import unittest
from pathlib import Path

from research_pipeline.runners.edge_analysis import build_edge_analysis


SUMMARY_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class TagComboAnalysisTest(unittest.TestCase):
    def test_tag_combo_analysis_reads_fixture_and_preserves_smoke_ready_combos(self) -> None:
        analysis = build_edge_analysis("liquidity_reversal", summary_dir=SUMMARY_DIR)
        payload = analysis.as_dict()
        combos = {combo["combo_name"]: combo for combo in payload["combo_metrics"]}

        self.assertIn("CHOCH true", combos)
        self.assertIn("displacement_after_reclaim", combos)
        self.assertEqual(combos["displacement_after_reclaim"]["edge_metrics"]["closed_trades"], 137)
        self.assertAlmostEqual(
            combos["displacement_after_reclaim"]["edge_metrics"]["MFE_R_avg"],
            1.043551147771528,
        )
        self.assertEqual(payload["ranked_combos"][0]["combo_name"], "displacement_after_reclaim")
        self.assertIn("CHOCH true", [row["combo_name"] for row in payload["ranked_combos"]])


if __name__ == "__main__":
    unittest.main()
