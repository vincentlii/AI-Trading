import tempfile
import unittest
from pathlib import Path

from trading_system.config import ConfigError, load_backtest_preset
from trading_system.config.proposals import (
    ProposalChange,
    ProposalError,
    apply_parameter_proposal,
    load_parameter_proposal,
    make_parameter_proposal,
    save_parameter_proposal,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"


class ConfigProposalTests(unittest.TestCase):
    def test_parameter_proposal_round_trips_as_json_with_auto_apply_disabled(self):
        preset = load_backtest_preset(PRESET_PATH)
        proposal = make_parameter_proposal(
            proposal_id="p4_5_raise_fast_cost_gate",
            title="Raise A profile cost gate for sensitivity check",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.fast_profile_fee_reject_threshold",
                    before=0.25,
                    after=0.3,
                    reason="Check whether A profile remains viable with a looser cost gate.",
                ),
            ),
            evidence={"window": "synthetic", "summary": "cost sensitivity candidate"},
            expected_impact="A profile may reject fewer setups.",
            risks=("May admit fee-heavy intraday samples.",),
            validation_plan=("Run P4.4 batch backtest before any manual config promotion.",),
        )

        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            saved_path = save_parameter_proposal(proposal, Path(temp_dir))
            loaded = load_parameter_proposal(saved_path)

        self.assertEqual(loaded.proposal_id, proposal.proposal_id)
        self.assertFalse(loaded.auto_apply)
        self.assertEqual(loaded.base_config_version, preset.config_version)
        self.assertEqual(loaded.base_config_fingerprint, preset.config_fingerprint)
        self.assertEqual(loaded.changes[0].path, "ranking.fast_profile_fee_reject_threshold")

    def test_applying_proposal_returns_in_memory_preset_without_mutating_base(self):
        preset = load_backtest_preset(PRESET_PATH)
        proposal = make_parameter_proposal(
            proposal_id="p4_5_min_trade_check",
            title="Tighten minimum sample size",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.min_trades_for_primary",
                    before=30,
                    after=40,
                    reason="Require a larger sample before treating a layer as primary.",
                ),
            ),
            evidence={"window": "synthetic"},
            expected_impact="C profile will more often be marked supporting_only.",
            risks=("May demote otherwise useful low-frequency samples.",),
            validation_plan=("Run P4.4 batch backtest and compare ranking statuses.",),
        )

        proposed = apply_parameter_proposal(preset, proposal)

        self.assertEqual(preset.ranking.min_trades_for_primary, 30)
        self.assertEqual(proposed.ranking.min_trades_for_primary, 40)
        self.assertNotEqual(proposed.config_fingerprint, preset.config_fingerprint)
        self.assertEqual(proposed.config_version, preset.config_version)

    def test_stale_before_value_and_invalid_paths_are_rejected(self):
        preset = load_backtest_preset(PRESET_PATH)
        stale = make_parameter_proposal(
            proposal_id="p4_5_stale",
            title="Stale proposal",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.min_trades_for_primary",
                    before=99,
                    after=40,
                    reason="Stale baseline should fail.",
                ),
            ),
            evidence={"window": "synthetic"},
            expected_impact="None.",
            risks=("None.",),
            validation_plan=("None.",),
        )

        with self.assertRaisesRegex(ProposalError, "before"):
            apply_parameter_proposal(preset, stale)

        invalid = make_parameter_proposal(
            proposal_id="p4_5_invalid_path",
            title="Invalid path",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="include.risk",
                    before="configs/risk/default.toml",
                    after="configs/risk/other.toml",
                    reason="Formal include paths must not be changed by proposal.",
                ),
            ),
            evidence={"window": "synthetic"},
            expected_impact="None.",
            risks=("Would rewrite formal config routing.",),
            validation_plan=("None.",),
        )

        with self.assertRaisesRegex(ProposalError, "not allowed"):
            apply_parameter_proposal(preset, invalid)

    def test_invalid_proposed_values_use_config_error(self):
        preset = load_backtest_preset(PRESET_PATH)
        proposal = make_parameter_proposal(
            proposal_id="p4_5_bad_threshold",
            title="Invalid ranking threshold",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.fast_profile_fee_reject_threshold",
                    before=0.25,
                    after=1.5,
                    reason="Threshold outside percentage range should fail.",
                ),
            ),
            evidence={"window": "synthetic"},
            expected_impact="None.",
            risks=("Invalid config.",),
            validation_plan=("None.",),
        )

        with self.assertRaises(ConfigError):
            apply_parameter_proposal(preset, proposal)


if __name__ == "__main__":
    unittest.main()
