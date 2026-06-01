import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_pipeline.cli.research import main


ARTIFACT_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ArtifactIndexCliTest(unittest.TestCase):
    def test_build_register_list_and_validate_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            index_dir = temp_path / "index"
            registry_path = temp_path / "registry.json"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                build_exit = main(
                    [
                        "build-artifact-index",
                        "--strategy",
                        "liquidity_reversal",
                        "--stage",
                        "stage6e_aggregation",
                        "--window",
                        "10000w",
                        "--artifact-dir",
                        str(ARTIFACT_DIR),
                        "--output-dir",
                        str(index_dir),
                    ]
                )
            self.assertEqual(build_exit, 0)
            artifact_index = index_dir / "artifact_index.json"
            self.assertTrue(artifact_index.exists())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                register_exit = main(
                    [
                        "register-run",
                        "--registry",
                        str(registry_path),
                        "--artifact-index",
                        str(artifact_index),
                        "--strategy",
                        "liquidity_reversal",
                        "--stage",
                        "stage6e_aggregation",
                        "--window",
                        "10000w",
                    ]
                )
            self.assertEqual(register_exit, 0)
            self.assertTrue(registry_path.exists())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["list-artifacts", "--artifact-index", str(artifact_index)]), 0)
            artifact_payload = json.loads(stdout.getvalue())
            self.assertGreaterEqual(len(artifact_payload["artifacts"]), 6)
            self.assertIn("file_hash", artifact_payload["artifacts"][0])

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["validate-artifacts", "--artifact-index", str(artifact_index)]), 0)
            validate_payload = json.loads(stdout.getvalue())
            self.assertTrue(validate_payload["passed"])

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["list-runs", "--registry", str(registry_path)]), 0)
            runs_payload = json.loads(stdout.getvalue())
            self.assertEqual(len(runs_payload["runs"]), 1)
            self.assertEqual(runs_payload["runs"][0]["strategy"], "liquidity_reversal")


if __name__ == "__main__":
    unittest.main()
