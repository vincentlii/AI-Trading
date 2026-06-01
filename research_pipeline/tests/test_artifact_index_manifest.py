import unittest
from pathlib import Path

from research_pipeline.runners.build_artifact_index import build_artifact_index


ARTIFACT_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ArtifactIndexManifestTest(unittest.TestCase):
    def test_builds_index_for_regression_fixture_artifacts(self) -> None:
        index = build_artifact_index(
            artifact_dir=ARTIFACT_DIR,
            strategy="liquidity_reversal",
            stage="stage6e",
            window="10000w",
            source_command="fixture",
            legacy_source=True,
        )
        payload = index.as_dict()
        records = {Path(record["path"]).name: record for record in payload["records"]}

        self.assertEqual(payload["strategy"], "liquidity_reversal")
        self.assertTrue(payload["index_id"])
        self.assertIn("key_metrics.json", records)
        self.assertIn("stage6e_aggregator_final_snapshot.md", records)
        self.assertIn("stage7_smoke_plan_snapshot.md", records)
        self.assertEqual(records["key_metrics.json"]["artifact_type"], "json")
        self.assertEqual(len(records["key_metrics.json"]["file_hash"]), 64)
        self.assertEqual(records["key_metrics.json"]["window"], "10000w")


if __name__ == "__main__":
    unittest.main()
