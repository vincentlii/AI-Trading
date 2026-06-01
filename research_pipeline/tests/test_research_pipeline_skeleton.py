import unittest


class ResearchPipelineSkeletonTest(unittest.TestCase):
    def test_package_imports_and_candidate_schema_is_serializable(self) -> None:
        import research_pipeline
        from research_pipeline.core.candidates.schema import Candidate

        candidate = Candidate(
            candidate_id="sample",
            strategy_name="liquidity_reversal",
            asset="BTC",
            profile="C",
            direction="long",
            signal_time="2026-01-01T00:00:00Z",
            entry_time="2026-01-01T01:00:00Z",
            setup="liquidity_reversal",
            tags={"high_sweep_rvol": True},
            prices={"entry": 100.0},
            risk={"stop_atr": 1.2},
            status="fresh",
        )

        self.assertEqual(research_pipeline.__all__, ("StrategyAdapter",))
        self.assertEqual(candidate.to_dict()["candidate_id"], "sample")


if __name__ == "__main__":
    unittest.main()
