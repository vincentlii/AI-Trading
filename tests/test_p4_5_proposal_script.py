import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.validate_p4_5_proposal import main, parse_args
from trading_system.config import ProposalChange, load_backtest_preset, make_parameter_proposal, save_parameter_proposal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"


class ValidateP45ProposalScriptTests(unittest.TestCase):
    def test_parse_args_accepts_project_safe_defaults(self):
        args = parse_args(["--proposal", "configs/proposals/example.json"])

        self.assertEqual(args.db, "storage/history.duckdb")
        self.assertEqual(args.preset, "configs/presets/btc_eth_p4_4.toml")
        self.assertEqual(args.proposal, "configs/proposals/example.json")

    def test_main_validates_proposal_file_without_applying_formal_config(self):
        preset = load_backtest_preset(PRESET_PATH)
        proposal = make_parameter_proposal(
            proposal_id="p4_5_script_smoke",
            title="Script smoke proposal",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.min_trades_for_primary",
                    before=30,
                    after=40,
                    reason="Smoke test validation entry.",
                ),
            ),
            evidence={"window": "synthetic"},
            expected_impact="Only proposed preset changes in memory.",
            risks=("No production config should change.",),
            validation_plan=("Run script smoke.",),
        )

        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            proposal_path = save_parameter_proposal(proposal, Path(temp_dir))
            db_path = Path(temp_dir) / "history.duckdb"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--proposal", str(proposal_path), "--db", str(db_path)])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("proposal_id=p4_5_script_smoke", output)
        self.assertIn("auto_apply=false", output)
        self.assertIn("proposed_config_fingerprint=", output)
        reloaded = load_backtest_preset(PRESET_PATH)
        self.assertEqual(reloaded.config_fingerprint, preset.config_fingerprint)


if __name__ == "__main__":
    unittest.main()
