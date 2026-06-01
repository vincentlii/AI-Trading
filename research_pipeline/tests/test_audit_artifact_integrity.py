import tempfile
import unittest
from pathlib import Path

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.core.audit.artifact_integrity import build_artifact_integrity_rows


class AuditArtifactIntegrityTest(unittest.TestCase):
    def test_hash_change_fails_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "x.json"
            artifact.write_text("{}", encoding="utf-8")
            write_artifact_index(
                build_index_for_directory(root, strategy="s", stage="stage", window="w"),
                root,
            )
            artifact.write_text('{"changed": true}', encoding="utf-8")
            rows = build_artifact_integrity_rows(root)

        self.assertTrue(any(row["artifact_name"] == "x.json" and row["blocking"] for row in rows))


if __name__ == "__main__":
    unittest.main()
