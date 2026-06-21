import unittest

from research_pipeline.core.audit.no_lookahead import build_no_lookahead_rows


class AuditNoLookaheadTest(unittest.TestCase):
    def test_custom_lt_check_is_strict_while_lte_allows_equality(self) -> None:
        source = {
            "relaunch_time": 10,
            "signal_time": 10,
            "bar_confirmed": True,
            "same_bar_ambiguous": False,
            "no_lookahead_safe": True,
        }

        strict = build_no_lookahead_rows(
            [source],
            time_field_checks=(("relaunch_time_lt_signal_time", "relaunch_time", "signal_time"),),
        )[0]
        inclusive = build_no_lookahead_rows(
            [source],
            time_field_checks=(("relaunch_time_lte_signal_time", "relaunch_time", "signal_time"),),
        )[0]

        self.assertFalse(strict["passed"])
        self.assertTrue(inclusive["passed"])

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

    def test_false_causal_flags_block_audit(self) -> None:
        source = {
            "feature_cutoff_time": 10,
            "structure_confirmed_time": 10,
            "sweep_time": 20,
            "reclaim_time": 30,
            "signal_time": 40,
            "entry_time": 41,
            "exit_time": 50,
            "same_bar_ambiguous": False,
        }

        for field, check_name in (
            ("bar_confirmed", "bar_confirmed_true"),
            ("no_lookahead_safe", "no_lookahead_feature_usage"),
        ):
            checks = build_no_lookahead_rows([{**source, field: False}])
            check = next(row for row in checks if row["check_name"] == check_name)
            self.assertFalse(check["passed"])
            self.assertTrue(check["blocking"])
            self.assertEqual(check["failed_rows"], 1)

    def test_ambiguous_same_bar_requires_pessimistic_resolution(self) -> None:
        base = {
            "feature_cutoff_time": 10,
            "structure_confirmed_time": 10,
            "sweep_time": 20,
            "reclaim_time": 30,
            "signal_time": 40,
            "entry_time": 41,
            "exit_time": 50,
            "bar_confirmed": True,
            "no_lookahead_safe": True,
            "same_bar_ambiguous": True,
        }

        failed = build_no_lookahead_rows([{**base, "forced_pessimistic_exit": False}])
        passed = build_no_lookahead_rows([{**base, "forced_pessimistic_exit": True}])
        failed_check = next(row for row in failed if row["check_name"] == "same_bar_ambiguity_pessimistic")
        passed_check = next(row for row in passed if row["check_name"] == "same_bar_ambiguity_pessimistic")

        self.assertFalse(failed_check["passed"])
        self.assertTrue(failed_check["blocking"])
        self.assertTrue(passed_check["passed"])


if __name__ == "__main__":
    unittest.main()
