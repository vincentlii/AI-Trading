import unittest
from pathlib import Path

from research_pipeline.core.artifacts.reader import read_artifact


BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ArtifactReaderTest(unittest.TestCase):
    def test_reads_json_artifact(self) -> None:
        artifact = read_artifact(BASELINE_DIR / "key_metrics.json")

        self.assertEqual(artifact.kind, "json")
        self.assertEqual(artifact.data["counts"]["fresh_candidates"], 5652)

    def test_reads_csv_artifact(self) -> None:
        artifact = read_artifact(BASELINE_DIR / "stage6e_aggregated_comparison_snapshot.csv")

        self.assertEqual(artifact.kind, "csv")
        self.assertGreater(len(artifact.data), 0)
        self.assertEqual(artifact.data[0]["label"], "baseline")

    def test_reads_jsonl_artifact(self) -> None:
        artifact = read_artifact(BASELINE_DIR / "stage7_smoke_grouped_rows_snapshot.jsonl")

        self.assertEqual(artifact.kind, "jsonl")
        self.assertGreater(len(artifact.data), 0)
        self.assertIn("combo", artifact.data[0])


if __name__ == "__main__":
    unittest.main()
