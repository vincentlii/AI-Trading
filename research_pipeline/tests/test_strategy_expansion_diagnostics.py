from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_pipeline.registry.strategy_registry import default_strategy_registry
from research_pipeline.runners.strategy_expansion_diagnostics import (
    BaselineReuseError,
    build_baseline_reuse_manifest,
    diagnostic_rows_for_adapter,
    classify_trend_gate_rejection,
    load_reusable_baseline_artifacts,
    run_strategy_expansion_diagnostics,
    _run_diagnostic_pass,
    summarize_diagnostic_funnel,
    _numeric_distribution_summary,
    summarize_trend_gate_diagnostics,
    write_expansion_diagnostics_artifacts,
)


class StrategyExpansionDiagnosticsTests(unittest.TestCase):
    def test_numeric_distribution_summary_keeps_non_empty_numeric_values(self) -> None:
        summary = _numeric_distribution_summary(
            [{"score": 0.1}, {"score": 0.3}, {"score": None}],
            ("score",),
        )

        self.assertEqual(summary["score"]["count"], 2)
        self.assertAlmostEqual(summary["score"]["avg"], 0.2)

    def test_breakout_pullback_adapter_declares_setup_contract(self) -> None:
        adapter = default_strategy_registry().get("breakout_pullback")
        audit_profile = adapter.audit_profile()
        candidate_schema = adapter.candidate_schema()

        self.assertEqual(adapter.name, "breakout_pullback")
        self.assertEqual(adapter.metadata()["implementation_setup"], "breakout_pullback")
        self.assertEqual(adapter.metadata()["strategy_family"], "breakout_pullback_continuation")
        self.assertEqual(adapter.setup_filter(), ("breakout_pullback",))
        self.assertEqual(adapter.parameter_namespace(), "breakout_pullback")
        self.assertIn("pullback_end_time", audit_profile.required_time_fields)
        self.assertIn("relaunch_time", audit_profile.required_time_fields)
        for field in ("level_id", "breakout_event_id", "lifecycle_event_id"):
            self.assertIn(field, audit_profile.required_lineage_fields)
            self.assertIn(field, candidate_schema)
        self.assertIn("zone_confirmed_time", audit_profile.required_time_fields)
        self.assertIn("zone_confirmed_time", candidate_schema)

    def test_breakout_pullback_adapter_declares_state_machine_stages(self) -> None:
        adapter = default_strategy_registry().get("breakout_pullback")

        names = [stage.name for stage in adapter.diagnostic_stages()]

        self.assertEqual(
            names,
            [
                "window_ready",
                "structure_zone_discovery",
                "breakout_event_seed",
                "breakout_lifecycle",
                "pullback_observation",
                "pullback_health",
                "relaunch_confirmation",
                "structural_stop",
                "target_tradeability",
                "risk_engine_approval",
            ],
        )
        self.assertFalse(next(stage for stage in adapter.diagnostic_stages() if stage.name == "breakout_lifecycle").hard_gate)

    def test_breakout_pullback_adapter_declares_limited_variants(self) -> None:
        adapter = default_strategy_registry().get("breakout_pullback")

        variant_ids = [variant.variant_id for variant in adapter.proposal_expansion_variants()]

        self.assertEqual(
            variant_ids,
            [
                "bp_lifecycle_level_zone_retest_v2",
                "bp_lifecycle_boundary_midpoint_v2",
                "bp_lifecycle_shallow_momentum_v2",
                "bp_lifecycle_weak_break_watch_v2",
            ],
        )
        self.assertTrue(all(variant.proposal_only for variant in adapter.proposal_expansion_variants()))

    def test_compression_expansion_adapter_declares_setup_contract(self) -> None:
        adapter = default_strategy_registry().get("compression_expansion")

        self.assertEqual(adapter.name, "compression_expansion")
        self.assertEqual(adapter.metadata()["implementation_setup"], "compression_expansion")
        self.assertEqual(adapter.metadata()["strategy_family"], "compression_expansion_breakout")
        self.assertEqual(adapter.setup_filter(), ("compression_expansion",))
        self.assertEqual(adapter.parameter_namespace(), "compression_expansion")
        self.assertIn("compression_end_time", adapter.audit_profile().required_time_fields)
        self.assertIn("breakout_time", adapter.audit_profile().required_time_fields)

    def test_compression_expansion_adapter_declares_diagnostic_stages(self) -> None:
        adapter = default_strategy_registry().get("compression_expansion")

        names = [stage.name for stage in adapter.diagnostic_stages()]

        self.assertEqual(
            names,
            [
                "window_ready",
                "compression_detected",
                "compression_quality_valid",
                "breakout_detected",
                "breakout_displacement_valid",
                "breakout_volume_valid",
                "failed_breakout_absent",
                "midpoint_hold",
                "retest_hold",
                "continuation_ready",
                "subtype_selected",
                "risk_precheck_pass",
            ],
        )

    def test_compression_expansion_adapter_declares_limited_variants(self) -> None:
        adapter = default_strategy_registry().get("compression_expansion")

        variant_ids = [variant.variant_id for variant in adapter.proposal_expansion_variants()]

        self.assertEqual(
            variant_ids,
            [
                "ce_semantic_acceptance_opposite_stop_v2",
                "ce_semantic_acceptance_breakout_extreme_stop_v2",
                "ce_acceptance_then_retest_entry_v2",
            ],
        )
        self.assertTrue(all(variant.proposal_only for variant in adapter.proposal_expansion_variants()))

    def test_diagnostic_rows_use_adapter_evaluator_for_compression_expansion(self) -> None:
        adapter = default_strategy_registry().get("compression_expansion")
        rows = diagnostic_rows_for_adapter(
            adapter=adapter,
            repository=None,
            preset=None,
            context_rows=[],
            variant_id="baseline_strict",
            parameter_overrides=None,
        )

        self.assertEqual(rows, ())

    def test_variant_replay_reuses_context_but_recomputes_raw_candidates(self) -> None:
        adapter = default_strategy_registry().get("compression_expansion")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            layered = SimpleNamespace(
                context_path=output_dir / "context_features.jsonl",
                raw_candidates_count=2,
            )
            with patch(
                "research_pipeline.runners.strategy_expansion_diagnostics.run_layered_proposal",
                return_value=layered,
            ) as run_layered, patch(
                "research_pipeline.runners.strategy_expansion_diagnostics.diagnostic_rows_for_adapter",
                return_value=(
                    {
                        "row_type": "diagnostic_only",
                        "profile": "B",
                        "candidate_ready": True,
                        "first_failed_stage": "",
                    },
                ),
            ):
                artifacts = _run_diagnostic_pass(
                    strategy=adapter.name,
                    adapter=adapter,
                    repository=object(),
                    preset=object(),
                    dataset_window="fixture_window",
                    output_dir=output_dir,
                    max_entry_windows=10,
                    force=False,
                    variant_id="box_atr_max_1_75",
                    parameter_overrides={"compression_expansion": {"compression_box_atr_max": 1.75}},
                    context_rows=({"symbol": "BTC/USDT", "profile": "B"},),
                    config_fingerprint="config-a",
                    source_command="fixture",
                )

        self.assertEqual(artifacts.summary["raw_candidates"], 2)
        self.assertEqual(run_layered.call_args.kwargs["setup_filter"], ("compression_expansion",))
        self.assertFalse(run_layered.call_args.kwargs["force_context"])
        self.assertTrue(run_layered.call_args.kwargs["force_candidates"])

    def test_run_top_variants_passes_requested_cost_tiers(self) -> None:
        def diagnostic_side_effect(**kwargs):
            output_dir = Path(kwargs["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            if kwargs["variant_id"] == "baseline_strict":
                (output_dir / "context_features.jsonl").write_text("{}\n", encoding="utf-8")
            return SimpleNamespace(
                summary={
                    "candidate_ready_windows": 1,
                    "raw_candidates": 1,
                    "first_failed_stage_counts": {},
                    "profile_summary": {},
                }
            )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "research_pipeline.runners.strategy_expansion_diagnostics._run_diagnostic_pass",
            side_effect=diagnostic_side_effect,
        ), patch(
            "research_pipeline.runners.strategy_expansion_diagnostics._run_one_pass",
            return_value={"summary": {"closed_trades": 0, "candidate_rows": 1, "formal_approved": 0}},
        ) as run_one, patch(
            "research_pipeline.runners.strategy_expansion_diagnostics.run_full_pipeline_audit",
            return_value=SimpleNamespace(audit_passed=True, blocking_issues=[]),
        ), patch(
            "research_pipeline.runners.strategy_expansion_diagnostics._preset_with_override",
            side_effect=lambda preset, overrides: preset,
        ):
            run_strategy_expansion_diagnostics(
                strategy="compression_expansion",
                repository=object(),
                preset=SimpleNamespace(config_fingerprint="cfg"),
                dataset_window="fixture_window",
                output_root=Path(tmp),
                run_top_variants=True,
                variants=("ce_semantic_acceptance_opposite_stop_v2",),
                cost_tiers=("base", "stress", "harsh"),
            )

        self.assertEqual(run_one.call_args.kwargs["cost_tiers"], ("base", "stress", "harsh"))

    def test_trend_continuation_adapter_declares_ordered_diagnostic_stages(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")

        names = [stage.name for stage in adapter.diagnostic_stages()]

        self.assertEqual(
            names,
            [
                "window_ready",
                "trend_gate",
                "volume_baseline_available",
                "breakout_rvol",
                "pullback_rvol",
                "displacement_range",
                "displacement_body",
                "BOS",
                "close_location",
                "pullback_direction",
                "pullback_midpoint",
                "restart_price",
                "restart_rvol",
                "entry_volume_confirmation",
            ],
        )
        self.assertTrue(all(stage.hard_gate for stage in adapter.diagnostic_stages()))

    def test_trend_continuation_adapter_declares_trend_definition_variants(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")

        variant_ids = {variant.variant_id for variant in adapter.proposal_expansion_variants()}

        self.assertIn("fresh_trend_b_v1", variant_ids)
        self.assertIn("transition_trend_b_v1", variant_ids)
        self.assertIn("compression_expansion_watchlist_v1", variant_ids)
        self.assertIn("profile_c_structure_proxy_v1", variant_ids)
        self.assertIn("near_threshold_mature_trend_v1", variant_ids)

    def test_trend_gate_rejection_classifies_indicator_failures(self) -> None:
        reasons = classify_trend_gate_rejection(
            {
                "status": "MEAN_REVERTING_TRANSITION",
                "direction": "long",
                "fast_ema": 101.0,
                "slow_ema": 100.0,
                "atr": 20.0,
                "adx": 18.0,
                "efficiency_ratio": 0.42,
                "choppiness": 55.0,
                "ttm_squeeze": False,
                "dmi_plus": 30.0,
                "dmi_minus": 20.0,
            }
        )

        self.assertEqual(reasons["primary_reason"], "adx_below_25")
        self.assertIn("er_below_0_60", reasons["reasons"])
        self.assertIn("chop_above_38_2", reasons["reasons"])
        self.assertIn("ema_gap_below_0_1_atr", reasons["reasons"])

    def test_trend_gate_summary_counts_reasons_by_profile(self) -> None:
        rows = [
            {"row_type": "diagnostic_only", "profile": "B", "trend_gate_primary_reason": "adx_below_25"},
            {"row_type": "diagnostic_only", "profile": "B", "trend_gate_primary_reason": "adx_below_25"},
            {"row_type": "diagnostic_only", "profile": "C", "trend_gate_primary_reason": "compression_pending_breakout"},
        ]

        summary = summarize_trend_gate_diagnostics(rows)

        self.assertEqual(summary["reason_counts"]["adx_below_25"], 2)
        self.assertEqual(summary["profile_summary"]["B"]["reason_counts"]["adx_below_25"], 2)
        self.assertEqual(summary["profile_summary"]["C"]["reason_counts"]["compression_pending_breakout"], 1)

    def test_funnel_summary_counts_first_failing_stage_by_profile(self) -> None:
        rows = [
            {"row_type": "diagnostic_only", "profile": "B", "first_failed_stage": "trend_gate"},
            {"row_type": "diagnostic_only", "profile": "B", "first_failed_stage": "BOS"},
            {"row_type": "diagnostic_only", "profile": "C", "first_failed_stage": "BOS"},
            {"row_type": "diagnostic_only", "profile": "C", "first_failed_stage": "", "candidate_ready": True},
        ]

        summary = summarize_diagnostic_funnel(rows)

        self.assertEqual(summary["total_windows"], 4)
        self.assertEqual(summary["candidate_ready_windows"], 1)
        self.assertEqual(summary["first_failed_stage_counts"]["BOS"], 2)
        self.assertEqual(summary["profile_summary"]["B"]["first_failed_stage_counts"]["trend_gate"], 1)
        self.assertEqual(summary["profile_summary"]["C"]["candidate_ready_windows"], 1)

    def test_funnel_summary_does_not_count_event_lifecycle_rows_as_windows(self) -> None:
        rows = [
            {"row_type": "diagnostic_only", "diagnostic_scope": "context_window", "profile": "B", "candidate_ready": True},
            {"row_type": "diagnostic_only", "diagnostic_scope": "event_lifecycle", "profile": "B", "breakout_class": "weak_but_watch"},
            {"row_type": "diagnostic_only", "diagnostic_scope": "event_lifecycle", "profile": "B", "breakout_class": "accepted_breakout"},
        ]

        summary = summarize_diagnostic_funnel(rows)

        self.assertEqual(summary["total_windows"], 1)
        self.assertEqual(summary["candidate_ready_windows"], 1)
        self.assertEqual(summary["breakout_event_seeds"], 2)

    def test_artifact_writer_keeps_diagnostic_rows_out_of_performance_contract(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            artifacts = write_expansion_diagnostics_artifacts(
                output_dir=output_dir,
                strategy=adapter.name,
                adapter=adapter,
                dataset_window="fixture",
                run_id="tc-diagnostic-fixture",
                max_entry_windows=4,
                diagnostic_rows=[
                    {
                        "row_type": "diagnostic_only",
                        "profile": "B",
                        "first_failed_stage": "BOS",
                        "candidate_ready": False,
                    }
                ],
                near_miss_rows=[
                    {
                        "row_type": "diagnostic_only",
                        "near_miss_stage": "BOS",
                        "distance_to_threshold": 0.1,
                    }
                ],
                variant_rows=[
                    {
                        "row_type": "diagnostic_only",
                        "variant_id": "bos_buffer_0_35",
                        "proposal_only": True,
                    }
                ],
                summary={"total_windows": 1, "candidate_ready_windows": 0},
                source_command="fixture",
            )

            manifest = artifacts.manifest
            self.assertEqual(manifest["artifact_paths"]["diagnostic_rows"], str(output_dir / "diagnostic_funnel_rows.jsonl"))
            self.assertEqual(manifest["artifact_paths"]["core_event_rows"], str(output_dir / "core_event_rows.jsonl"))
            self.assertEqual(manifest["artifact_contract"]["performance_row_type"], "closed_trade")
            self.assertIn("diagnostic_only", manifest["artifact_contract"]["excluded_performance_row_types"])
            self.assertTrue((output_dir / "artifact_index.json").exists())
            self.assertTrue((output_dir / "research_run_registry.json").exists())

    def test_builds_and_validates_baseline_reuse_manifest(self) -> None:
        adapter = default_strategy_registry().get("compression_expansion")
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp)
            _write_text(baseline_dir / "context_features.jsonl", '{"row_type":"context"}\n')
            _write_text(baseline_dir / "raw_candidates.jsonl", "")
            _write_text(baseline_dir / "diagnostic_funnel_rows.jsonl", '{"row_type":"diagnostic_only"}\n')
            _write_text(baseline_dir / "diagnostic_summary_rows.jsonl", '{"row_type":"summary_row"}\n')
            _write_text(baseline_dir / "near_miss_rows.jsonl", "")
            _write_text(baseline_dir / "cache_manifest.json", '{"data_hash":"fixture-data"}')
            _write_text(baseline_dir / "run_manifest.json", "{}")
            _write_text(baseline_dir / "artifact_index.json", "{}")
            _write_text(baseline_dir / "research_run_registry.json", "{}")

            manifest = build_baseline_reuse_manifest(
                baseline_dir=baseline_dir,
                strategy=adapter.name,
                adapter=adapter,
                dataset_window="fixture_window",
                max_entry_windows=10,
                config_fingerprint="config-a",
                setup_filter=("compression_expansion",),
            )

            loaded = load_reusable_baseline_artifacts(
                baseline_dir=baseline_dir,
                strategy=adapter.name,
                adapter=adapter,
                dataset_window="fixture_window",
                max_entry_windows=10,
                config_fingerprint="config-a",
                setup_filter=("compression_expansion",),
            )

        self.assertEqual(loaded["strategy"], manifest["strategy"])
        self.assertIn("context_features", loaded["artifact_paths"])
        self.assertIn("diagnostic_funnel_rows", loaded["artifact_paths"])

    def test_reuse_manifest_rejects_hash_mismatch(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp)
            _write_text(baseline_dir / "context_features.jsonl", '{"row_type":"context"}\n')
            _write_text(baseline_dir / "raw_candidates.jsonl", "")
            _write_text(baseline_dir / "diagnostic_funnel_rows.jsonl", "")
            _write_text(baseline_dir / "diagnostic_summary_rows.jsonl", "")
            _write_text(baseline_dir / "near_miss_rows.jsonl", "")
            _write_text(baseline_dir / "cache_manifest.json", "{}")
            _write_text(baseline_dir / "run_manifest.json", "{}")
            _write_text(baseline_dir / "artifact_index.json", "{}")
            _write_text(baseline_dir / "research_run_registry.json", "{}")
            build_baseline_reuse_manifest(
                baseline_dir=baseline_dir,
                strategy=adapter.name,
                adapter=adapter,
                dataset_window="fixture_window",
                max_entry_windows=10,
                config_fingerprint="config-a",
                setup_filter=("trend_continuation",),
            )
            _write_text(baseline_dir / "context_features.jsonl", '{"row_type":"changed"}\n')

            with self.assertRaisesRegex(BaselineReuseError, "hash mismatch"):
                load_reusable_baseline_artifacts(
                    baseline_dir=baseline_dir,
                    strategy=adapter.name,
                    adapter=adapter,
                    dataset_window="fixture_window",
                    max_entry_windows=10,
                    config_fingerprint="config-a",
                    setup_filter=("trend_continuation",),
                )

    def test_reuse_manifest_rejects_config_mismatch(self) -> None:
        adapter = default_strategy_registry().get("trend_continuation")
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp)
            _write_text(baseline_dir / "context_features.jsonl", "")
            _write_text(baseline_dir / "raw_candidates.jsonl", "")
            _write_text(baseline_dir / "diagnostic_funnel_rows.jsonl", "")
            _write_text(baseline_dir / "diagnostic_summary_rows.jsonl", "")
            _write_text(baseline_dir / "near_miss_rows.jsonl", "")
            _write_text(baseline_dir / "cache_manifest.json", "{}")
            _write_text(baseline_dir / "run_manifest.json", "{}")
            _write_text(baseline_dir / "artifact_index.json", "{}")
            _write_text(baseline_dir / "research_run_registry.json", "{}")
            build_baseline_reuse_manifest(
                baseline_dir=baseline_dir,
                strategy=adapter.name,
                adapter=adapter,
                dataset_window="fixture_window",
                max_entry_windows=10,
                config_fingerprint="config-a",
                setup_filter=("trend_continuation",),
            )

            with self.assertRaisesRegex(BaselineReuseError, "config_fingerprint mismatch"):
                load_reusable_baseline_artifacts(
                    baseline_dir=baseline_dir,
                    strategy=adapter.name,
                    adapter=adapter,
                    dataset_window="fixture_window",
                    max_entry_windows=10,
                    config_fingerprint="config-b",
                    setup_filter=("trend_continuation",),
                )


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
