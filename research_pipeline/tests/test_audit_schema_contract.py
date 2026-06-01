import unittest

from research_pipeline.core.audit.schema_contract import build_schema_contract_rows


class AuditSchemaContractTest(unittest.TestCase):
    def test_missing_fields_are_not_silent(self) -> None:
        rows = build_schema_contract_rows(
            artifact_name="candidate.jsonl",
            rows=[{"candidate_id": "c1"}],
            inferred_row_type="raw_candidate",
            required_fields={"candidate_id", "event_id"},
        )

        self.assertEqual(rows[0]["missing_fields"], ["event_id"])
        self.assertTrue(rows[0]["blocking"])


if __name__ == "__main__":
    unittest.main()
