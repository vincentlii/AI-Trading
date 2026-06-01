import json
import tempfile
import unittest
from pathlib import Path

from research_pipeline.runners.build_artifact_index import build_and_write_artifact_index
from research_pipeline.runners.validate_artifacts import validate_artifact_index


ARTIFACT_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ArtifactValidationTest(unittest.TestCase):
    def test_validate_artifact_hashes_passes_for_unchanged_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, paths = build_and_write_artifact_index(
                artifact_dir=ARTIFACT_DIR,
                output_dir=Path(temp_dir),
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
            )

            result = validate_artifact_index(paths["json"])

            self.assertTrue(result.passed)
            self.assertEqual(result.errors, [])

    def test_validate_artifact_hashes_fails_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            _, paths = build_and_write_artifact_index(
                artifact_dir=ARTIFACT_DIR,
                output_dir=temp_path,
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
            )
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            payload["records"][0]["path"] = str(temp_path / "missing.json")
            paths["json"].write_text(json.dumps(payload), encoding="utf-8")

            result = validate_artifact_index(paths["json"])

            self.assertFalse(result.passed)
            self.assertIn("missing", result.errors[0])

    def test_validate_artifact_hashes_fails_for_hash_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sample = temp_path / "sample.json"
            sample.write_text('{"a": 1}\n', encoding="utf-8")
            _, paths = build_and_write_artifact_index(
                artifact_dir=temp_path,
                output_dir=temp_path / "index",
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
            )
            sample.write_text('{"a": 2}\n', encoding="utf-8")

            result = validate_artifact_index(paths["json"])

            self.assertFalse(result.passed)
            self.assertIn("hash_changed", result.errors[0])


if __name__ == "__main__":
    unittest.main()
