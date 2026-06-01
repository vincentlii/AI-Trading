import unittest

from research_pipeline.core.analytics.smoke_readiness import evaluate_smoke_readiness


class SmokeReadinessTest(unittest.TestCase):
    def test_smoke_readiness_requires_sample_edge_and_lower_time_cut(self) -> None:
        baseline = {
            "closed_trades": 100,
            "MFE_R_avg": 0.5,
            "MFE_R_ge_0_5_ratio": 0.3,
            "MFE_R_ge_1_0_ratio": 0.2,
            "net_R_avg": 0.1,
            "net_return_on_notional_avg": 0.01,
            "time_cut_exit_rate": 0.5,
        }
        candidate = {
            "closed_trades": 40,
            "MFE_R_avg": 0.6,
            "MFE_R_ge_0_5_ratio": 0.4,
            "MFE_R_ge_1_0_ratio": 0.2,
            "net_R_avg": 0.1,
            "net_return_on_notional_avg": 0.01,
            "time_cut_exit_rate": 0.4,
        }

        flags = evaluate_smoke_readiness(candidate, baseline)

        self.assertTrue(flags["smoke_ready"])
        self.assertTrue(flags["sample_ok"])
        self.assertTrue(flags["mfe_avg_improved"])
        self.assertTrue(flags["time_cut_lower"])


if __name__ == "__main__":
    unittest.main()
