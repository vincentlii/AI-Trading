import unittest

from trading_system.dashboard.presentation import (
    DASHBOARD_SECTION_FIELDS,
    FIELD_TOOLTIPS,
    METRIC_DESCRIPTIONS,
    SECTION_DESCRIPTIONS,
    STATUS_TEXT,
    field_label,
    field_tooltip,
    metric_description,
    present_row,
    section_description,
    status_text,
)


class DashboardChinesePresentationTests(unittest.TestCase):
    def test_field_labels_cover_p5_dashboard_sections(self):
        expected_sections = {
            "ranking",
            "data_coverage",
            "signal_funnel",
            "volume_rejection",
            "risk_rejection",
            "near_miss",
            "proposal",
        }

        self.assertTrue(expected_sections.issubset(DASHBOARD_SECTION_FIELDS))
        for section in expected_sections:
            self.assertGreater(len(DASHBOARD_SECTION_FIELDS[section]), 0)

        self.assertEqual(field_label("ranking", "timeframe_group"), "周期组")
        self.assertEqual(field_label("data_coverage", "next_action"), "下一步")
        self.assertEqual(field_label("signal_funnel", "approved_signal"), "通过信号")
        self.assertEqual(field_label("volume_rejection", "volume_ratio_median"), "RVOL 中位数")
        self.assertEqual(field_label("risk_rejection", "stop_atr_median"), "止损/ATR 中位数")
        self.assertEqual(field_label("near_miss", "distance_to_pass"), "距通过阈值")
        self.assertEqual(field_label("proposal", "auto_apply"), "自动应用")

    def test_status_and_reason_text_keeps_unknown_codes_readable(self):
        self.assertEqual(status_text("candidate"), "候选")
        self.assertEqual(status_text("supporting_only"), "辅助观察")
        self.assertEqual(status_text("ready"), "已就绪")
        self.assertEqual(status_text("stop_distance_too_far"), "止损距离过远")
        self.assertEqual(status_text("unknown_new_code"), "unknown_new_code")
        self.assertIn("candidate", STATUS_TEXT)

    def test_metric_descriptions_cover_required_terms(self):
        required_terms = (
            "RVOL",
            "ATR",
            "ADX/DMI",
            "CHOP",
            "ER",
            "TTM Squeeze",
            "Profit Factor",
            "最大回撤",
            "单笔期望",
            "止损/ATR",
            "Near Miss",
        )

        for term in required_terms:
            self.assertIn(term, METRIC_DESCRIPTIONS)
            self.assertGreater(len(metric_description(term)), 10)

    def test_tooltips_and_section_descriptions_are_available_for_display(self):
        self.assertIn("ranking", SECTION_DESCRIPTIONS)
        self.assertIn("risk_rejection", SECTION_DESCRIPTIONS)
        self.assertGreater(len(section_description("signal_funnel")), 10)
        self.assertEqual(field_tooltip("signal_funnel", "volume_price_rejected"), "量价确认未通过的窗口数量。")
        self.assertEqual(field_tooltip("risk_rejection", "estimated_cost_r_median"), "预估交易成本占单笔风险 R 的中位数。")
        self.assertEqual(field_tooltip("unknown", "unknown"), "")
        self.assertIn("near_miss", FIELD_TOOLTIPS)

    def test_present_row_returns_chinese_labels_without_changing_internal_keys(self):
        row = {
            "symbol": "BTC/USDT",
            "status": "candidate",
            "reason_codes": ("stop_distance_too_far",),
            "profit_factor": 1.8,
        }

        presented = present_row("ranking", row)

        self.assertEqual(row["status"], "candidate")
        self.assertIn("交易对", presented)
        self.assertIn("状态", presented)
        self.assertEqual(presented["状态"], "候选")
        self.assertEqual(presented["原因代码"], "止损距离过远")
        self.assertEqual(presented["Profit Factor"], 1.8)


if __name__ == "__main__":
    unittest.main()
