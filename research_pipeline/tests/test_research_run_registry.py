import tempfile
import unittest
from pathlib import Path

from research_pipeline.runners.build_artifact_index import build_and_write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run
from research_pipeline.core.artifacts.registry import load_research_run_registry


ARTIFACT_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "regression_baselines"
    / "liquidity_reversal"
    / "stage6e_10000w"
)


class ResearchRunRegistryTest(unittest.TestCase):
    def test_registers_research_run_with_stable_id_and_index_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            _, paths = build_and_write_artifact_index(
                artifact_dir=ARTIFACT_DIR,
                output_dir=temp_path,
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
                source_command="fixture",
                legacy_source=True,
            )
            registry_path = temp_path / "research_run_registry.json"

            first = register_research_run(
                registry_path=registry_path,
                artifact_index_path=paths["json"],
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
                proposal_only=True,
                formal_conclusion_enabled=False,
                readonly=True,
                legacy_source=True,
                notes="fixture run",
                tags=["baseline", "aggregation"],
            )
            second = register_research_run(
                registry_path=registry_path,
                artifact_index_path=paths["json"],
                strategy="liquidity_reversal",
                stage="stage6e_aggregation",
                window="10000w",
                proposal_only=True,
                formal_conclusion_enabled=False,
                readonly=True,
                legacy_source=True,
                notes="fixture run",
                tags=["baseline", "aggregation"],
            )

            self.assertEqual(first.run_id, second.run_id)
            self.assertGreaterEqual(first.artifact_count, 6)
            self.assertEqual(len(first.artifact_index_hash), 64)

            registry = load_research_run_registry(registry_path)
            self.assertEqual(len(registry.runs), 2)
            self.assertEqual(registry.runs[0].artifact_count, registry.runs[1].artifact_count)
            self.assertFalse(registry.runs[0].formal_conclusion_enabled)


if __name__ == "__main__":
    unittest.main()
