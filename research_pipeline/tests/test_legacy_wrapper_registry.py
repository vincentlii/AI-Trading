import unittest

from research_pipeline.legacy.registry import get_legacy_mapping, list_legacy_mappings


class LegacyWrapperRegistryTest(unittest.TestCase):
    def test_liquidity_reversal_registry_lists_primary_legacy_scripts(self) -> None:
        mappings = list_legacy_mappings(strategy="liquidity_reversal")

        self.assertGreaterEqual(len(mappings), 7)
        aliases = {mapping.pipeline_command_alias for mapping in mappings}
        self.assertIn("fresh-lr-scan", aliases)
        self.assertIn("minimal-lr-filter", aliases)
        self.assertIn("stage6e-aggregate", aliases)
        self.assertIn("stage7-smoke-plan", aliases)

        readonly_aliases = {"stage6e-aggregate", "stage7-smoke-plan"}
        for mapping in mappings:
            self.assertEqual(mapping.strategy, "liquidity_reversal")
            self.assertFalse(mapping.migrated_to_core)
            if mapping.pipeline_command_alias in readonly_aliases:
                self.assertFalse(mapping.calls_old_logic)
                self.assertTrue(mapping.readonly_wrapper_to_core)
            else:
                self.assertTrue(mapping.calls_old_logic)
                self.assertFalse(mapping.readonly_wrapper_to_core)

    def test_lookup_by_alias(self) -> None:
        mapping = get_legacy_mapping("stage6e-aggregate")

        self.assertEqual(mapping.legacy_script_name, "run_stage6e_aggregator.py")
        self.assertEqual(mapping.stage, "stage6e_aggregator")


if __name__ == "__main__":
    unittest.main()
