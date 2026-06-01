import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main


ARTIFACT_DIR = Path("storage/backtest_cache/lr_combined_fix_pr11g")


class FullPipelineAuditCliTest(unittest.TestCase):
    def test_full_audit_cli_writes_reusable_gate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "full-audit",
                        "--strategy",
                        "liquidity_reversal",
                        "--artifact-dir",
                        str(ARTIFACT_DIR),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            for name in (
                "full_pipeline_audit_result.json",
                "full_pipeline_audit_report.md",
                "audit_schema_contract_rows.jsonl",
                "audit_lineage_rows.jsonl",
                "audit_join_integrity_rows.jsonl",
                "audit_proposal_boundary_rows.jsonl",
                "audit_no_lookahead_rows.jsonl",
                "audit_metric_recompute_rows.jsonl",
                "audit_report_consistency_rows.jsonl",
                "audit_artifact_integrity_rows.jsonl",
                "audit_code_logic_review_rows.jsonl",
                "artifact_index.json",
                "research_run_registry.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            payload = json.loads((output_dir / "full_pipeline_audit_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["primary_decision"], "C")


if __name__ == "__main__":
    unittest.main()
