import unittest

from research_pipeline.core.audit.no_lookahead import build_no_lookahead_rows


class AuditNoLookaheadTest(unittest.TestCase):
    def test_missing_time_fields_are_unverifiable(self) -> None:
        rows = build_no_lookahead_rows([{"candidate_id": "c1"}])
        check = next(row for row in rows if row["check_name"] == "signal_time_lt_entry_time")

        self.assertFalse(check["passed"])
        self.assertTrue(check["blocking"])
        self.assertEqual(check["unverifiable_rows"], 1)


if __name__ == "__main__":
    unittest.main()
