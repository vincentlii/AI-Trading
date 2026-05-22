import unittest

from trading_system.indicators.external_wrappers import external_atr_check, external_ema_check


class ExternalIndicatorWrapperTests(unittest.TestCase):
    def test_external_ema_check_uses_project_schema_and_never_requires_optional_libraries(self):
        result = external_ema_check([1.0, 2.0, 3.0, 4.0, 5.0], period=3)

        self.assertEqual(result.name, "external.ema")
        self.assertIn(result.status, {"matched", "external_missing", "mismatch"})
        self.assertAlmostEqual(result.internal_value, 4.0625)
        self.assertNotEqual(result.source, "direct_strategy_dependency")

    def test_external_atr_check_uses_project_reference_value_when_library_is_missing(self):
        result = external_atr_check(
            highs=[10.0, 11.0, 15.0],
            lows=[9.0, 10.0, 14.0],
            closes=[9.5, 10.5, 14.5],
            period=2,
        )

        self.assertEqual(result.name, "external.atr")
        self.assertAlmostEqual(result.internal_value, 3.0)
        self.assertIn(result.status, {"matched", "external_missing", "mismatch"})
        if result.status == "external_missing":
            self.assertIn("optional_indicator_library_missing", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
