import unittest

from research_pipeline.core.audit.proposal_boundary import build_proposal_boundary_rows


class AuditProposalBoundaryTest(unittest.TestCase):
    def test_unexecuted_proposal_rows_do_not_fail_when_unclosed(self) -> None:
        rows = build_proposal_boundary_rows(
            selected_rows=[{"closed_trade": False, "sizing_policy": "quality_aware_capped_sizing"}],
            variant_rows=[],
            diagnostic_combos=[],
        )
        check = next(row for row in rows if row["check_name"] == "proposal_only_unexecuted_enters_closed_trades")

        self.assertTrue(check["passed"])
        self.assertEqual(check["affected_rows"], 1)


if __name__ == "__main__":
    unittest.main()
