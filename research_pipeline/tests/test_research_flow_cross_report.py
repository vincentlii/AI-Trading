import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.research_flow_audit import run_research_flow_audit


from research_pipeline.tests.fixture_paths import COMBINED_FIX_DIR as ARTIFACT_DIR


class ResearchFlowCrossReportAuditTest(unittest.TestCase):
    def test_cross_report_records_pr11g_fix_definition_change(self) -> None:
        result = run_research_flow_audit(
            strategy="liquidity_reversal",
            artifact_dir=ARTIFACT_DIR,
            artifact_index=None,
            registry=None,
            output_dir=None,
        )
        rows = result.as_dict()["cross_report_rows"]

        self.assertTrue(any(row["scope"] == "Variant B" for row in rows))
        self.assertTrue(any(row["metric_changed_reason"] for row in rows))

    def test_flow_audit_cli_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "flow-audit",
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
                "research_flow_audit_result.json",
                "research_flow_audit_report.md",
                "research_flow_lineage_rows.jsonl",
                "research_flow_join_audit_rows.jsonl",
                "research_flow_invariant_rows.jsonl",
                "research_flow_metric_recompute_rows.jsonl",
                "research_flow_cross_report_rows.jsonl",
            ):
                self.assertTrue((output_dir / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
