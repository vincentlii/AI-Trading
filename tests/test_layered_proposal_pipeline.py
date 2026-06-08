import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from scripts.run_btc_eth_swap_proposal import parse_args
from trading_system.backtest.layered_cache import candidate_generation_config_hash, context_config_hash, filter_config_hash
from trading_system.backtest.layered_pipeline import _execution_row, _filter_candidate, run_layered_proposal
from trading_system.config import StrategyConfig, load_backtest_preset
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SWAP_PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_swap_proposal.toml"


def _candle(index: int, open_price: float, high: float, low: float, close: float, volume: float = 100.0, confirmed: bool = True) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * 60_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume * close,
        is_confirmed=confirmed,
    )


def _repository_with_swap_context() -> CandleRepository:
    repository = CandleRepository()
    entry = tuple(_candle(index, 100.0 + index * 0.1, 101.0 + index * 0.1, 99.5 + index * 0.1, 100.4 + index * 0.1) for index in range(1, 18))
    # The unconfirmed candle must never appear in context artifacts.
    entry = (*entry, _candle(99, 200.0, 220.0, 180.0, 210.0, confirmed=False))
    structure = (
        _candle(1, 100.0, 101.0, 99.0, 100.5),
        _candle(2, 100.5, 102.0, 100.0, 101.5),
        _candle(3, 101.5, 103.0, 101.0, 102.0),
        _candle(4, 102.0, 102.5, 98.0, 101.8, volume=120.0),
        _candle(5, 101.8, 103.5, 101.0, 103.0, volume=90.0),
        _candle(6, 103.0, 104.0, 102.5, 103.5, volume=80.0),
    )
    trend = tuple(_candle(index, 90.0 + index * 0.05, 91.0 + index * 0.05, 89.5 + index * 0.05, 90.5 + index * 0.05) for index in range(1, 230))
    for inst_id in ("BTC-USDT-SWAP", "ETH-USDT-SWAP"):
        repository.save_many(inst_id, "15m", entry, inst_type="SWAP")
        repository.save_many(inst_id, "1H", structure, inst_type="SWAP")
        repository.save_many(inst_id, "4H", trend, inst_type="SWAP")
        repository.save_many(inst_id, "1D", trend, inst_type="SWAP")
    return repository


class LayeredProposalPipelineTests(unittest.TestCase):
    def test_breakout_pullback_execution_row_preserves_audit_time_chain(self):
        candidate = {
            "candidate_id": "bp-1",
            "event_id": "event-1",
            "breakout_pullback_event_id": "bp-event-1",
            "core_engine_version": "trend_continuation_core.v1",
            "level_id": "level-1",
            "breakout_event_id": "breakout-1",
            "lifecycle_event_id": "lifecycle-1",
            "zone_confirmed_time": 1005,
            "breakout_class": "accepted_breakout",
            "pullback_health_class": "healthy",
            "relaunch_type": "micro_break_relaunch",
            "relaunch_quality_class": "strong",
            "target_source": "measured_move",
            "target_quality_class": "good",
            "structural_stop_quality": "valid",
            "asset": "BTC",
            "symbol": "BTC-USDT-SWAP",
            "profile": "B",
            "setup": "breakout_pullback",
            "direction": "long",
            "formal_approved": True,
            "entry_price": 101.0,
            "stop_price": 99.0,
            "target_price": 105.0,
            "target_r": 2.0,
            "atr_value": 2.0,
            "portfolio_heat": 0.01,
            "margin_required": 1000.0,
            "notional": 5000.0,
            "feature_cutoff_time": 1000,
            "breakout_time": 1010,
            "acceptance_end_time": 1020,
            "pullback_start_time": 1030,
            "pullback_end_time": 1040,
            "relaunch_time": 1050,
            "signal_time": 1050,
            "bar_confirmed": True,
            "no_lookahead_safe": True,
        }
        fill = SimpleNamespace(
            trade_id="trade-bp-1",
            execution_id="exec-bp-1",
            entry_timestamp_ms=1060,
            exit_timestamp_ms=1120,
            net_pnl=10.0,
            gross_pnl=12.0,
            r_multiple=0.5,
            exit_reason="target",
            holding_bars=4,
            mae_r=0.1,
            mfe_r=0.8,
            bars_to_mae=1,
            bars_to_mfe=2,
            reached_1r=False,
            reached_1_5r=False,
            reached_2r=False,
            moved_to_breakeven=False,
            breakeven_hit=False,
            partial_take_profit_hit=False,
            same_bar_ambiguous=False,
            same_bar_resolution="",
            forced_pessimistic_exit=False,
            cost_estimate=SimpleNamespace(fees=1.0, spread=0.5, expected_slippage=0.25, funding=0.0),
        )

        row = _execution_row(candidate, fill, "base")

        self.assertEqual(row["breakout_pullback_event_id"], "bp-event-1")
        self.assertEqual(row["lifecycle_event_id"], "lifecycle-1")
        self.assertEqual(row["zone_confirmed_time"], 1005)
        self.assertEqual(row["structural_stop_quality"], "valid")
        self.assertEqual(row["breakout_time"], 1010)
        self.assertEqual(row["acceptance_end_time"], 1020)
        self.assertEqual(row["pullback_start_time"], 1030)
        self.assertEqual(row["pullback_end_time"], 1040)
        self.assertEqual(row["relaunch_time"], 1050)
        self.assertEqual(row["signal_time"], 1050)
        self.assertEqual(row["entry_time"], 1060)

    def test_cli_accepts_layered_modes_and_force_flags(self):
        args = parse_args(["--mode", "filter_replay", "--cache-dir", "storage/custom_cache", "--force-candidates"])

        self.assertEqual(args.mode, "filter_replay")
        self.assertEqual(args.cache_dir, "storage/custom_cache")
        self.assertTrue(args.force_candidates)

    def test_context_hash_ignores_filter_threshold_changes(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        changed = replace(
            preset,
            strategy=StrategyConfig(
                name=preset.strategy.name,
                version=preset.strategy.version,
                enabled=preset.strategy.enabled,
                enabled_setups=preset.strategy.enabled_setups,
                parameters={
                    **preset.strategy.parameters,
                    "liquidity_reversal": {
                        **preset.strategy.parameters["liquidity_reversal"],
                        "assets": {
                            **preset.strategy.parameters["liquidity_reversal"]["assets"],
                            "BTC": {
                                **preset.strategy.parameters["liquidity_reversal"]["assets"]["BTC"],
                                "sweep_rvol_min": 9.9,
                            },
                        },
                    },
                },
                parameter_grid=preset.strategy.parameter_grid,
                profile_status=preset.strategy.profile_status,
                volume=preset.strategy.volume,
            ),
        )

        self.assertEqual(context_config_hash(preset), context_config_hash(changed))
        self.assertNotEqual(filter_config_hash(preset), filter_config_hash(changed))

    def test_candidate_hash_includes_setup_filter(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        self.assertNotEqual(
            candidate_generation_config_hash(preset, ("liquidity_reversal",)),
            candidate_generation_config_hash(preset, ("trend_continuation",)),
        )
        self.assertNotEqual(
            candidate_generation_config_hash(preset, ("trend_continuation",)),
            candidate_generation_config_hash(preset, ("compression_expansion",)),
        )

    def test_candidate_hash_includes_setup_semantic_version(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)

        self.assertNotEqual(
            candidate_generation_config_hash(
                preset,
                ("breakout_pullback",),
                setup_semantic_version="breakout_pullback.initial_research.v1",
            ),
            candidate_generation_config_hash(
                preset,
                ("breakout_pullback",),
                setup_semantic_version="trend_continuation_core.v1",
            ),
        )

    def test_candidate_only_writes_context_and_raw_candidate_artifacts(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
            )

            self.assertEqual(result.mode, "candidate_only")
            self.assertTrue(result.context_path.exists())
            self.assertTrue(result.raw_candidates_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertGreater(result.scanned_windows, 0)
            self.assertGreater(result.raw_candidates_count, 0)
            context_rows = _read_jsonl(result.context_path)
            raw_rows = _read_jsonl(result.raw_candidates_path)
            self.assertTrue(all(row["confirmed"] is True for row in context_rows))
            self.assertNotIn(1_700_000_000_000 + 99 * 60_000, {row["timestamp_ms"] for row in context_rows})
            self.assertIn("candidate_generation_reason", raw_rows[0])

    def test_setup_filter_isolates_liquidity_reversal_rows(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
                setup_filter=("liquidity_reversal",),
            )

            raw_rows = _read_jsonl(result.raw_candidates_path)
            self.assertTrue(raw_rows)
            self.assertEqual({row["setup"] for row in raw_rows}, {"liquidity_reversal"})

    def test_setup_filter_isolates_trend_continuation_rows(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
                setup_filter=("trend_continuation",),
            )

            raw_rows = _read_jsonl(result.raw_candidates_path)
            self.assertEqual({row["setup"] for row in raw_rows}, {"trend_continuation"} if raw_rows else set())

    def test_setup_filter_isolates_compression_expansion_rows(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
                setup_filter=("compression_expansion",),
            )

            raw_rows = _read_jsonl(result.raw_candidates_path)
            self.assertEqual({row["setup"] for row in raw_rows}, {"compression_expansion"} if raw_rows else set())
            manifest = _read_json(result.manifest_path)
            self.assertEqual(tuple(manifest["setup_filter"]), ("compression_expansion",))

    def test_candidate_only_applies_execution_invalidation_to_raw_liquidity_stops(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
            )

            raw_rows = _read_jsonl(result.raw_candidates_path)
            liquidity = next(
                row
                for row in raw_rows
                if row["setup"] == "liquidity_reversal"
                and row["candidate_lifecycle_status"] == "active_candidate"
                and row["bars_reclaim_to_signal"] is not None
            )
            expected_buffer = 0.15 * float(liquidity["atr_value"])
            if liquidity["direction"] == "long":
                expected_stop = float(liquidity["sweep_extreme_price"]) - expected_buffer
                self.assertEqual(liquidity["stop_formula_used"], "structure_extreme_buffer_long")
            else:
                expected_stop = float(liquidity["sweep_extreme_price"]) + expected_buffer
                self.assertEqual(liquidity["stop_formula_used"], "structure_extreme_buffer_short")
            self.assertEqual(liquidity["invalidation_mode_config"], "structure_extreme_buffer")
            self.assertEqual(liquidity["invalidation_mode_effective"], "structure_extreme_buffer")
            self.assertEqual(liquidity["stop_formula_fallback_reason"], "")
            self.assertAlmostEqual(float(liquidity["stop_price"]), expected_stop)

    def test_liquidity_candidate_entry_reference_binds_to_reclaim_next_entry_bar(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
            )

            raw_rows = _read_jsonl(result.raw_candidates_path)
            liquidity = next(
                row
                for row in raw_rows
                if row["setup"] == "liquidity_reversal"
                and row["candidate_lifecycle_status"] == "active_candidate"
                and row["bars_reclaim_to_signal"] is not None
            )

            self.assertLessEqual(liquidity["bars_reclaim_to_signal"], 1)
            self.assertLessEqual(liquidity["bars_signal_to_entry"], 1)
            self.assertLessEqual(liquidity["bars_reclaim_to_entry"], 2)
            self.assertEqual(liquidity["candidate_lifecycle_status"], "active_candidate")
            self.assertNotEqual(liquidity["entry_reference_price"], 102.1)
            self.assertEqual(liquidity["entry_reference_price"], liquidity["actual_entry_price_if_simulated"])

    def test_filter_replay_reuses_raw_candidates_and_records_reject_reasons(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="candidate_only",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
            )

            result = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="filter_replay",
                cache_dir=Path(temp_dir),
                max_entry_windows=20,
                cost_tiers=("base",),
            )

            self.assertEqual(result.mode, "filter_replay")
            self.assertTrue(result.filter_results_path.exists())
            self.assertTrue(result.funnel_summary_path.exists())
            filter_rows = _read_jsonl(result.filter_results_path)
            rejected = [row for row in filter_rows if not row["approved"]]
            self.assertTrue(rejected)
            self.assertTrue(all(row["reject_stage"] and row["reject_reason"] for row in rejected))
            self.assertTrue(any(row["reject_reason"] for row in rejected))

    def test_full_backtest_and_gate_ablation_write_diagnostic_artifacts(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            full = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="full_backtest",
                cache_dir=Path(temp_dir),
                max_entry_windows=8,
                cost_tiers=("base", "stress", "harsh"),
            )
            ablation = run_layered_proposal(
                repository=_repository_with_swap_context(),
                preset=preset,
                mode="gate_ablation",
                cache_dir=Path(temp_dir),
                max_entry_windows=8,
                cost_tiers=("base",),
            )

            self.assertTrue(full.execution_results_path.exists())
            self.assertTrue(full.diagnostics_report_path.exists())
            self.assertTrue(ablation.gate_ablation_path.exists())
            with ablation.gate_ablation_path.open("r", encoding="utf-8", newline="") as file:
                stages = {row["stage"] for row in csv.DictReader(file)}
            self.assertIn("raw_structure_only", stages)
            self.assertIn("+execution_and_cost", stages)

    def test_acceptable_reclaim_rvol_is_diagnostic_not_hard_reject(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        row = _raw_liquidity_candidate(reclaim_rvol=1.3)

        result = _filter_candidate(row, preset)

        self.assertEqual(result["reclaim_quality"], "acceptable_reclaim")
        self.assertNotEqual(result["reject_reason"], "high_reclaim_rvol")

    def test_breakout_pullback_rejects_invalid_structural_stop_before_risk_engine(self):
        preset = load_backtest_preset(SWAP_PRESET_PATH)
        row = {
            **_raw_liquidity_candidate(reclaim_rvol=1.0),
            "candidate_id": "bp-structural-stop-too-near",
            "setup": "breakout_pullback",
            "entry_reference_price": 100.0,
            "stop_price": 99.9,
            "target_price": 104.0,
            "atr_value": 1.0,
            "structural_stop_quality": "structural_stop_too_near",
            "stop_is_structural": True,
        }

        result = _filter_candidate(row, preset)

        self.assertEqual(result["reject_stage"], "structural_tradeability_filter")
        self.assertEqual(result["reject_reason"], "structural_stop_too_near")


def _read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_liquidity_candidate(*, reclaim_rvol: float) -> dict[str, object]:
    return {
        "candidate_id": "acceptable-reclaim",
        "timestamp_ms": 1_700_000_000_000,
        "asset": "BTC",
        "symbol": "BTC/USDT",
        "venue": "okx",
        "inst_id": "BTC-USDT-SWAP",
        "inst_type": "SWAP",
        "profile": "B",
        "setup": "liquidity_reversal",
        "direction": "long",
        "long_or_short": "long",
        "structure_level": 99.0,
        "sweep_extreme": 98.0,
        "sweep_extreme_price": 98.0,
        "wick_ratio": 0.8,
        "sweep_atr_multiple": 0.2,
        "rolling_rvol": 3.0,
        "tod_dow_rvol": 3.0,
        "reclaim_bars": 1,
        "reclaim_price": 101.0,
        "reclaim_rvol": reclaim_rvol,
        "choch_detected": True,
        "bos_detected": False,
        "trend_state": "MEAN_REVERTING_TRANSITION",
        "trend_direction": "long",
        "entry_reference_price": 100.0,
        "target_price": 104.0,
        "stop_price": 98.0,
        "atr_value": 1.0,
        "countertrend": False,
        "raw_volume": 100.0,
        "log_volume": 4.6,
        "volume_baseline_mode": "tod_dow_log_ewma",
        "volume_bucket_key": "BTC|15m|1|0",
        "volume_bucket_sample_count": 30,
        "used_fallback_volume_baseline": False,
        "candidate_generation_reason": "downside_sweep_structure_event",
    }


if __name__ == "__main__":
    unittest.main()
