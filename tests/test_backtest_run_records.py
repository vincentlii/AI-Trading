import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_btc_eth_p4_4_backtest import parse_args as parse_p44_args
from scripts.run_btc_eth_swap_proposal import parse_args as parse_swap_args
from trading_system.config import load_backtest_preset
from trading_system.reports.backtest_runs import record_backtest_run


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SWAP_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_swap_proposal.toml"


class BacktestRunRecordTests(unittest.TestCase):
    def test_backtest_scripts_default_to_recording_run_artifacts(self):
        swap_args = parse_swap_args([])
        p44_args = parse_p44_args([])

        self.assertEqual(swap_args.output_dir, "storage/backtest_runs")
        self.assertEqual(p44_args.output_dir, "storage/backtest_runs")
        self.assertFalse(swap_args.no_record)
        self.assertFalse(p44_args.no_record)

    def test_backtest_scripts_can_disable_or_redirect_recording(self):
        swap_args = parse_swap_args(["--no-record", "--output-dir", "storage/custom_runs"])
        p44_args = parse_p44_args(["--no-record", "--output-dir", "storage/custom_runs"])

        self.assertTrue(swap_args.no_record)
        self.assertTrue(p44_args.no_record)
        self.assertEqual(swap_args.output_dir, "storage/custom_runs")
        self.assertEqual(p44_args.output_dir, "storage/custom_runs")

    def test_records_summary_rows_preset_snapshot_and_index_entry(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        rows = (
            {
                "cost_tier": "base",
                "symbol": "BTC/USDT",
                "inst_id": "BTC-USDT-SWAP",
                "inst_type": "SWAP",
                "contract_mode": "usdt_swap",
                "allow_short": True,
                "timeframe_group": "B",
                "setup_type": "liquidity_reversal",
                "direction": "long",
                "trade_count": 2,
                "net_profit": 123.45,
                "expectancy_R": 0.6,
                "max_drawdown": 0.01,
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = record_backtest_run(
                output_dir=Path(temp_dir),
                script_name="scripts/run_btc_eth_swap_proposal.py",
                command_args={
                    "db": "storage/history.duckdb",
                    "preset": "configs/presets/btc_eth_swap_proposal.toml",
                    "cost_tiers": ("base",),
                    "max_entry_windows": 200,
                },
                preset=preset,
                rows=rows,
                project_root=PROJECT_ROOT,
                git_metadata={
                    "branch": "test-branch",
                    "commit": "abc123",
                    "dirty": False,
                },
            )

            self.assertTrue(paths.run_id)
            self.assertTrue(paths.summary_path.exists())
            self.assertTrue(paths.rows_csv_path.exists())
            self.assertTrue(paths.preset_snapshot_path.exists())
            self.assertTrue(paths.index_path.exists())

            summary = json.loads(paths.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["run_id"], paths.run_id)
            self.assertEqual(summary["script_name"], "scripts/run_btc_eth_swap_proposal.py")
            self.assertEqual(summary["command_args"]["max_entry_windows"], 200)
            self.assertEqual(summary["config_fingerprint"], preset.config_fingerprint)
            self.assertEqual(summary["strategy"]["name"], "trend_price_volume")
            self.assertEqual(summary["assets"]["contract_mode"], "usdt_swap")
            self.assertEqual(summary["assets"]["targets"][0]["inst_type"], "SWAP")
            self.assertEqual(summary["risk"]["max_total_gross_leverage"], 1.0)
            self.assertEqual(summary["costs"]["fee_rate"], 0.001)
            self.assertEqual(summary["row_count"], 1)

            preset_snapshot = json.loads(paths.preset_snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(preset_snapshot["strategy"]["parameters"], summary["strategy"]["parameters"])
            self.assertEqual(preset_snapshot["risk"], summary["risk"])

            with paths.rows_csv_path.open("r", encoding="utf-8", newline="") as file:
                csv_rows = tuple(csv.DictReader(file))
            self.assertEqual(len(csv_rows), 1)
            self.assertEqual(csv_rows[0]["symbol"], "BTC/USDT")
            self.assertEqual(csv_rows[0]["cost_tier"], "base")
            self.assertEqual(csv_rows[0]["trade_count"], "2")

            index_rows = [
                json.loads(line)
                for line in paths.index_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(index_rows), 1)
            self.assertEqual(index_rows[0]["run_id"], paths.run_id)
            self.assertEqual(index_rows[0]["row_count"], 1)
            self.assertEqual(index_rows[0]["config_fingerprint"], preset.config_fingerprint)

    def test_recording_multiple_runs_appends_index_without_overwriting(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        with tempfile.TemporaryDirectory() as temp_dir:
            first = record_backtest_run(
                output_dir=Path(temp_dir),
                script_name="first.py",
                command_args={},
                preset=preset,
                rows=({"symbol": "BTC/USDT", "trade_count": 1},),
                project_root=PROJECT_ROOT,
                git_metadata={"branch": "test", "commit": "", "dirty": True},
            )
            second = record_backtest_run(
                output_dir=Path(temp_dir),
                script_name="second.py",
                command_args={},
                preset=preset,
                rows=({"symbol": "ETH/USDT", "trade_count": 3},),
                project_root=PROJECT_ROOT,
                git_metadata={"branch": "test", "commit": "", "dirty": True},
            )

            self.assertNotEqual(first.run_id, second.run_id)
            self.assertTrue(first.run_dir.exists())
            self.assertTrue(second.run_dir.exists())

            index_rows = [
                json.loads(line)
                for line in first.index_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([row["script_name"] for row in index_rows], ["first.py", "second.py"])

    def test_records_cache_manifest_and_extra_artifacts_when_provided(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = record_backtest_run(
                output_dir=Path(temp_dir),
                script_name="scripts/run_btc_eth_swap_proposal.py",
                command_args={"mode": "filter_replay"},
                preset=preset,
                rows=(),
                project_root=PROJECT_ROOT,
                git_metadata={"branch": "test", "commit": "abc123", "dirty": True},
                extra_artifacts={"funnel_summary": Path(temp_dir) / "funnel_summary.csv"},
                cache_manifest={"context_cache_status": "reused", "raw_candidate_cache_status": "created"},
            )

            summary = json.loads(paths.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["command_args"]["mode"], "filter_replay")
            self.assertEqual(summary["extra_artifacts"]["funnel_summary"], str(Path(temp_dir) / "funnel_summary.csv"))
            self.assertEqual(summary["cache_manifest"]["context_cache_status"], "reused")


if __name__ == "__main__":
    unittest.main()
