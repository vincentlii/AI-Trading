import shutil
import tempfile
import unittest
from pathlib import Path

from trading_system.backtest.execution import BacktestExecutionConfig
from trading_system.backtest.risk import RiskParameters
from trading_system.config import ConfigError, load_backtest_preset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"
SWAP_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_swap_proposal.toml"


class ConfigLoaderTests(unittest.TestCase):
    def test_loads_btc_eth_p4_4_preset(self):
        preset = load_backtest_preset(PRESET_PATH)

        self.assertEqual(preset.config_version, "btc_eth_p4_4_v1")
        self.assertEqual(preset.strategy.name, "trend_price_volume")
        self.assertEqual(preset.strategy.enabled_setups, ("trend_continuation", "liquidity_reversal"))
        self.assertTrue(preset.config_fingerprint)

    def test_builds_btc_eth_scan_targets_and_profile_order(self):
        preset = load_backtest_preset(PRESET_PATH)
        scan_config = preset.to_scan_config()

        self.assertEqual(scan_config.profile_keys, ("B", "C", "A"))
        self.assertEqual([target.canonical_symbol for target in scan_config.targets], ["BTC/USDT", "ETH/USDT"])
        self.assertEqual([target.inst_id for target in scan_config.targets], ["BTC-USDT", "ETH-USDT"])
        self.assertEqual({target.venue for target in scan_config.targets}, {"okx"})
        self.assertEqual({target.inst_type for target in scan_config.targets}, {"SPOT"})

    def test_loads_swap_proposal_preset_with_bc_primary_profiles_and_contract_metadata(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        scan_config = preset.to_scan_config()

        self.assertEqual(preset.assets.contract_mode, "usdt_swap")
        self.assertTrue(preset.assets.allow_short)
        self.assertEqual(scan_config.profile_keys, ("B", "C"))
        self.assertEqual([target.inst_id for target in scan_config.targets], ["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
        self.assertEqual({target.inst_type for target in scan_config.targets}, {"SWAP"})
        self.assertEqual(preset.strategy.profile_status["A"], "diagnostic_only")
        self.assertEqual(preset.strategy.profile_status["B"], "proposal_enabled")
        self.assertEqual(preset.strategy.volume["baseline_mode"], "tod_dow_log_ewma")
        self.assertEqual(preset.strategy.parameters["liquidity_reversal"]["assets"]["BTC"]["sweep_rvol_min"], 1.8)
        self.assertEqual(preset.strategy.parameters["liquidity_reversal"]["assets"]["ETH"]["require_choch_for_eth_reversal"], True)
        self.assertEqual(preset.execution.invalidation_mode, "structure_extreme_buffer")
        self.assertEqual(preset.execution.invalidation_buffer_atr, 0.15)
        self.assertEqual(preset.execution.shadow_max_stop_atr_multiple_candidates, (5.0, 8.0))
        self.assertEqual(preset.execution.breakeven_after_mfe_r, 1.0)
        self.assertEqual([tier.name for tier in preset.costs.cost_model_tiers], ["base", "stress", "harsh"])
        self.assertTrue(all(tier.fee_rate == 0.001 for tier in preset.costs.cost_model_tiers))

    def test_builds_risk_and_execution_configs(self):
        preset = load_backtest_preset(PRESET_PATH)

        risk = preset.to_risk_parameters()
        execution = preset.to_execution_config()

        self.assertIsInstance(risk, RiskParameters)
        self.assertEqual(risk.risk_pct, 0.005)
        self.assertEqual(risk.max_single_notional_pct, 0.15)
        self.assertIsInstance(execution, BacktestExecutionConfig)
        self.assertTrue(execution.enable_advanced_exits)
        self.assertEqual(execution.partial_take_profit_pct, 0.5)
        self.assertEqual(execution.chandelier_period, 22)

    def test_btc_eth_preset_excludes_xaut_and_nasdaq(self):
        preset = load_backtest_preset(PRESET_PATH)
        symbols = {target.canonical_symbol for target in preset.assets.targets}

        self.assertEqual(symbols, {"BTC/USDT", "ETH/USDT"})
        self.assertNotIn("XAUT/USDT", symbols)
        self.assertNotIn("NASDAQ100/INDEX", symbols)

    def test_config_fingerprint_is_stable_for_same_content(self):
        first = load_backtest_preset(PRESET_PATH)
        second = load_backtest_preset(PRESET_PATH)

        self.assertEqual(first.config_fingerprint, second.config_fingerprint)

    def test_invalid_profile_is_rejected(self):
        with self.config_copy() as root:
            self.replace_text(root / "configs" / "presets" / "btc_eth_p4_4.toml", '["B", "C", "A"]', '["B", "Z"]')

            with self.assertRaisesRegex(ConfigError, "profile"):
                load_backtest_preset(root / "configs" / "presets" / "btc_eth_p4_4.toml", project_root=root)

    def test_invalid_strategy_setup_is_rejected(self):
        with self.config_copy() as root:
            self.replace_text(
                root / "configs" / "strategies" / "trend_price_volume_v1.toml",
                '["trend_continuation", "liquidity_reversal"]',
                '["trend_continuation", "unknown_setup"]',
            )

            with self.assertRaisesRegex(ConfigError, "setup"):
                load_backtest_preset(root / "configs" / "presets" / "btc_eth_p4_4.toml", project_root=root)

    def test_negative_fee_rate_is_rejected(self):
        with self.config_copy() as root:
            self.replace_text(root / "configs" / "costs" / "crypto_spot_research.toml", "fee_rate = 0.001", "fee_rate = -0.1")

            with self.assertRaisesRegex(ConfigError, "fee_rate"):
                load_backtest_preset(root / "configs" / "presets" / "btc_eth_p4_4.toml", project_root=root)

    def test_invalid_risk_percentage_is_rejected(self):
        with self.config_copy() as root:
            self.replace_text(root / "configs" / "risk" / "default.toml", "risk_pct = 0.005", "risk_pct = 1.5")

            with self.assertRaisesRegex(ConfigError, "risk_pct"):
                load_backtest_preset(root / "configs" / "presets" / "btc_eth_p4_4.toml", project_root=root)

    def config_copy(self):
        return _ConfigCopy()

    def replace_text(self, path: Path, old: str, new: str):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")


class _ConfigCopy:
    def __enter__(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=PROJECT_ROOT)
        self.root = Path(self.temp_dir.name)
        shutil.copytree(PROJECT_ROOT / "configs", self.root / "configs")
        return self.root

    def __exit__(self, exc_type, exc, tb):
        self.temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
