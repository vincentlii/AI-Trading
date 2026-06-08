from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_pipeline.runners.lineage_repair import run_lineage_repair


from research_pipeline.tests.fixture_paths import COMBINED_FIX_DIR as COMBINED_DIR, EXECUTION_RESULTS, FILTER_RESULTS


class LineageRepairTests(unittest.TestCase):
    def test_missing_execution_identity_rows_are_invalid_for_robustness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_lineage_repair(
                strategy="liquidity_reversal",
                combined_artifact_dir=COMBINED_DIR,
                filter_results=FILTER_RESULTS,
                execution_results=EXECUTION_RESULTS,
                output_dir=Path(temp_dir),
            )
            self.assertEqual(result.primary_decision, "C")
            self.assertEqual(result.robustness_input_count, 0)
            self.assertGreater(result.invalid_for_robustness_count, 0)
            self.assertEqual(result.closed_with_trade_id_count, 0)
            self.assertEqual(result.closed_with_execution_id_count, 0)

            invalid_rows = _read_jsonl(Path(temp_dir) / "invalid_for_robustness_rows.jsonl")
            self.assertTrue(invalid_rows)
            self.assertTrue(all(row["invalid_for_robustness"] for row in invalid_rows))
            self.assertTrue(any("missing_trade_id" in row["invalid_reasons"] for row in invalid_rows))

            full_audit = json.loads((Path(temp_dir) / "full_pipeline_audit_result.json").read_text(encoding="utf-8"))
            self.assertEqual(full_audit["primary_decision"], "C")
            self.assertFalse(full_audit["audit_passed"])

    def test_lineage_repair_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "research_pipeline.cli.research",
                    "lineage-repair",
                    "--strategy",
                    "liquidity_reversal",
                    "--combined-artifact-dir",
                    str(COMBINED_DIR),
                    "--filter-results",
                    str(FILTER_RESULTS),
                    "--execution-results",
                    str(EXECUTION_RESULTS),
                    "--output-dir",
                    temp_dir,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn('"primary_decision": "C"', completed.stdout)
            for filename in (
                "lineage_repair_result.json",
                "lineage_repair_report.md",
                "lineage_backfill_rows.jsonl",
                "robustness_input_candidate_rows.jsonl",
                "invalid_for_robustness_rows.jsonl",
                "fixed_combined_variant_rows.jsonl",
                "fixed_combined_grouped_rows.jsonl",
                "full_pipeline_audit_result.json",
                "full_pipeline_audit_report.md",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((Path(temp_dir) / filename).exists(), filename)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()
