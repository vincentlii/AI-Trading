from __future__ import annotations

import unittest

from research_pipeline.core.sizing.capped_risk import apply_capped_risk_sizing
from trading_system.config import load_backtest_preset


class CappedRiskSizingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preset = load_backtest_preset("configs/presets/btc_eth_swap_proposal.toml")

    def test_cap_only_lowers_position_and_preserves_formal_approval(self) -> None:
        row = {
            "formal_approved": False,
            "reject_reason": "margin_required_too_high",
            "entry_price": 100.0,
            "stop_price": 99.0,
            "atr_value": 1.0,
            "structural_stop_quality": "valid",
            "cost_adjusted_RR": 1.5,
            "target_space_atr": 2.0,
        }

        result = apply_capped_risk_sizing(row, self.preset)

        self.assertFalse(result["formal_approved"])
        self.assertTrue(result["proposal_approved_after_cap"])
        self.assertLess(result["capped_position_size"], result["theoretical_risk_based_position_size"])
        self.assertLessEqual(result["capped_notional"], self.preset.execution.initial_equity * self.preset.risk.max_single_notional_pct)
        self.assertGreaterEqual(result["actual_risk_after_cap_pct"], 0.001)

    def test_cap_does_not_override_non_sizing_reject(self) -> None:
        row = {
            "formal_approved": False,
            "reject_reason": "structural_stop_too_near",
            "entry_price": 100.0,
            "stop_price": 99.0,
            "atr_value": 1.0,
            "structural_stop_quality": "structural_stop_too_near",
            "cost_adjusted_RR": 1.5,
            "target_space_atr": 2.0,
        }

        result = apply_capped_risk_sizing(row, self.preset)

        self.assertFalse(result["proposal_approved_after_cap"])
        self.assertEqual(result["risk_reject_reason_after_cap"], "structural_stop_too_near")


if __name__ == "__main__":
    unittest.main()
