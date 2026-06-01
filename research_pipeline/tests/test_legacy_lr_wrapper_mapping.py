import io
import json
import unittest
from contextlib import redirect_stdout

from research_pipeline.cli.research import main


class LegacyLiquidityReversalWrapperMappingTest(unittest.TestCase):
    def test_legacy_list_cli_outputs_mapping_without_running_legacy_logic(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["legacy-list"])

        payload = json.loads(stdout.getvalue())
        readonly_aliases = {"stage6e-aggregate", "stage7-smoke-plan"}
        self.assertEqual(exit_code, 0)
        self.assertGreaterEqual(len(payload["mappings"]), 7)
        self.assertTrue(
            all(
                (not row["calls_old_logic"] if row["pipeline_command_alias"] in readonly_aliases else row["calls_old_logic"])
                for row in payload["mappings"]
            )
        )
        self.assertTrue(all(not row["migrated_to_core"] for row in payload["mappings"]))

    def test_legacy_run_cli_dry_run_echoes_command(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["legacy-run", "--name", "fresh-lr-scan", "--", "--max-windows", "200"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["mapping"]["legacy_script_name"], "run_fresh_lr_scanner.py")
        self.assertIn("--max-windows", payload["legacy_args"])


if __name__ == "__main__":
    unittest.main()
