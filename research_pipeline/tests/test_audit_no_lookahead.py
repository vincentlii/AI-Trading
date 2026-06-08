import unittest

from research_pipeline.core.audit.no_lookahead import build_no_lookahead_rows


class AuditNoLookaheadTest(unittest.TestCase):
    def test_missing_time_fields_are_unverifiable(self) -> None:
        rows = build_no_lookahead_rows([{"candidate_id": "c1"}])
        check = next(row for row in rows if row["check_name"] == "signal_time_lt_entry_time")

        self.assertFalse(check["passed"])
        self.assertTrue(check["blocking"])
        self.assertEqual(check["unverifiable_rows"], 1)

    def test_time_order_violation_blocks_even_when_fields_exist(self) -> None:
        rows = build_no_lookahead_rows(
            [
                {
                    "feature_cutoff_time": 10,
                    "structure_confirmed_time": 10,
                    "sweep_time": 20,
                    "reclaim_time": 30,
                    "signal_time": 40,
                    "entry_time": 35,
                    "exit_time": 50,
                    "bar_confirmed": True,
                    "same_bar_ambiguous": False,
                    "no_lookahead_safe": True,
                }
            ]
        )
        check = next(row for row in rows if row["check_name"] == "signal_time_lt_entry_time")

        self.assertFalse(check["passed"])
        self.assertTrue(check["blocking"])
        self.assertEqual(check["failed_rows"], 1)


if __name__ == "__main__":
    unittest.main()
