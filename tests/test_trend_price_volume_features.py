import importlib
import unittest
from dataclasses import is_dataclass
from typing import NamedTuple


class CandleStub(NamedTuple):
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_currency: float
    volume_currency_quote: float
    is_confirmed: bool = True


def _candle(
    index: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
    *,
    confirmed: bool = True,
) -> CandleStub:
    return CandleStub(
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


def _hourly_candle(index: int, volume: float) -> CandleStub:
    timestamp_ms = 1_700_000_000_000 + index * 3_600_000
    return CandleStub(
        timestamp_ms=timestamp_ms,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=volume,
        volume_currency=volume,
        volume_currency_quote=volume,
        is_confirmed=True,
    )


def _import_features():
    try:
        return importlib.import_module("trading_system.strategies.trend_price_volume_v1.features")
    except ModuleNotFoundError as exc:
        raise AssertionError("trend_price_volume_v1.features module should exist") from exc


def _bullish_regime_candles(count: int = 230) -> tuple[CandleStub, ...]:
    candles = []
    for index in range(count):
        close = 100.0 + index * 0.55
        candles.append(_candle(index, close - 0.2, close + 0.4, close - 0.4, close, volume=500.0))
    return tuple(candles)


def _trend_continuation_structure() -> tuple[CandleStub, ...]:
    rows = (
        (100.0, 101.0, 99.0, 100.5, 100.0),
        (100.5, 103.0, 100.0, 102.5, 100.0),
        (102.5, 105.0, 101.5, 104.5, 100.0),
        (104.5, 104.8, 101.0, 102.0, 100.0),
        (102.0, 103.2, 100.2, 101.5, 100.0),
        (101.5, 104.2, 101.0, 103.8, 100.0),
        (103.8, 110.0, 103.2, 109.4, 260.0),
        (109.4, 109.8, 107.8, 108.4, 65.0),
    )
    return tuple(_candle(index, row[0], row[1], row[2], row[3], volume=row[4]) for index, row in enumerate(rows))


def _compression_expansion_structure() -> tuple[CandleStub, ...]:
    rows = (
        (100.00, 100.80, 99.80, 100.20, 110.0),
        (100.20, 100.70, 99.90, 100.10, 105.0),
        (100.10, 100.60, 99.95, 100.30, 96.0),
        (100.30, 100.65, 100.00, 100.20, 92.0),
        (100.20, 100.55, 99.95, 100.35, 88.0),
        (100.35, 100.70, 100.05, 100.30, 84.0),
        (100.30, 100.62, 100.02, 100.40, 80.0),
        (100.40, 100.58, 100.04, 100.28, 78.0),
        (100.28, 103.40, 100.20, 103.10, 210.0),
        (103.10, 103.45, 101.85, 102.85, 135.0),
    )
    return tuple(_candle(index, row[0], row[1], row[2], row[3], volume=row[4]) for index, row in enumerate(rows))


def _breakout_pullback_structure() -> tuple[CandleStub, ...]:
    rows = (
        (100.00, 100.90, 99.80, 100.20, 110.0),
        (100.20, 101.00, 99.90, 100.30, 108.0),
        (100.30, 101.10, 99.95, 100.50, 104.0),
        (100.50, 101.05, 100.05, 100.40, 98.0),
        (100.40, 101.00, 100.00, 100.35, 96.0),
        (100.35, 101.15, 100.10, 100.80, 100.0),
        (100.80, 104.50, 100.70, 104.10, 260.0),
        (104.10, 104.60, 103.20, 103.80, 140.0),
        (103.80, 104.00, 101.05, 101.55, 95.0),
        (101.55, 103.90, 101.35, 103.70, 170.0),
    )
    return tuple(_candle(index, row[0], row[1], row[2], row[3], volume=row[4]) for index, row in enumerate(rows))


def _liquidity_reversal_structure() -> tuple[CandleStub, ...]:
    rows = (
        (110.0, 111.0, 108.0, 109.0, 100.0),
        (109.0, 110.0, 104.0, 105.0, 100.0),
        (105.0, 106.0, 100.0, 101.0, 100.0),
        (101.0, 105.5, 99.4, 104.8, 230.0),
        (104.8, 108.5, 103.8, 108.0, 160.0),
        (108.0, 109.0, 105.5, 107.6, 90.0),
    )
    return tuple(_candle(index, row[0], row[1], row[2], row[3], volume=row[4]) for index, row in enumerate(rows))


def _entry_candles(*, latest_volume: float = 320.0, latest_confirmed: bool = True) -> tuple[CandleStub, ...]:
    candles = []
    for index in range(24):
        close = 105.0 + (index % 3) * 0.1
        candles.append(_candle(index, close - 0.1, close + 0.3, close - 0.3, close, volume=100.0))
    candles.append(
        _candle(
            24,
            105.2,
            107.0,
            104.9,
            106.6,
            volume=latest_volume,
            confirmed=latest_confirmed,
        )
    )
    return tuple(candles)


class TrendPriceVolumeFeatureTests(unittest.TestCase):
    def test_public_api_uses_dataclasses(self):
        features = _import_features()

        self.assertTrue(is_dataclass(features.MarketRegimeContext))
        self.assertTrue(is_dataclass(features.PriceActionSetup))
        self.assertTrue(is_dataclass(features.VolumePriceConfirmation))

    def test_build_market_regime_uses_confirmed_candles_only(self):
        features = _import_features()
        confirmed = _bullish_regime_candles()
        unconfirmed_spike = _candle(99, 150.0, 151.0, 49.0, 50.0, confirmed=False)

        regime = features.build_market_regime((*confirmed, unconfirmed_spike))

        self.assertIsNotNone(regime)
        self.assertEqual(regime.status, "TREND")
        self.assertEqual(regime.direction, "long")
        self.assertLess(regime.last_close, 230.0)
        self.assertIn("adx", regime.evidence)
        self.assertIn("ttm_squeeze", regime.evidence)

    def test_build_market_regime_returns_none_when_data_is_insufficient(self):
        features = _import_features()

        self.assertIsNone(features.build_market_regime(_bullish_regime_candles(10)))

    def test_detects_trend_continuation_only_with_trend_bos_displacement_and_pullback(self):
        features = _import_features()
        regime = features.build_market_regime(_bullish_regime_candles())

        setup = features.detect_price_action_setup(
            _trend_continuation_structure(),
            _entry_candles(),
            regime,
        )

        self.assertIsNotNone(setup)
        self.assertEqual(setup.setup_type, "trend_continuation")
        self.assertEqual(setup.direction, "long")
        self.assertEqual(setup.evidence["structure"], "BOS_DISPLACEMENT_PULLBACK")
        self.assertEqual(setup.evidence["strategy_family"], "breakout_pullback_continuation")
        self.assertEqual(setup.evidence["trend_gate_role"], "hard_gate")
        self.assertGreaterEqual(setup.evidence["breakout_rvol"], 2.0)
        self.assertLessEqual(setup.evidence["pullback_rvol"], 0.8)
        self.assertTrue(setup.evidence["pullback_holds_midpoint"])
        self.assertLess(setup.invalidation_level, setup.entry_zone["low"])

    def test_rejects_trend_continuation_without_trend_regime(self):
        features = _import_features()
        non_trend_regime = features.MarketRegimeContext(
            status="RANGE",
            direction=None,
            last_close=100.0,
            fast_ema=100.0,
            slow_ema=100.0,
            atr=1.0,
            efficiency_ratio=0.1,
            choppiness=70.0,
            dmi_plus=None,
            dmi_minus=None,
        )

        setup = features.detect_price_action_setup(
            _trend_continuation_structure(),
            _entry_candles(),
            non_trend_regime,
        )

        self.assertIsNone(setup)

    def test_rejects_trend_continuation_when_breakout_volume_is_not_expanded(self):
        features = _import_features()
        regime = features.build_market_regime(_bullish_regime_candles())
        weak_breakout = tuple(
            candle._replace(volume=120.0, volume_currency_quote=120.0 * candle.close) if index == 6 else candle
            for index, candle in enumerate(_trend_continuation_structure())
        )

        setup = features.detect_price_action_setup(
            weak_breakout,
            _entry_candles(),
            regime,
        )

        self.assertIsNone(setup)

    def test_rejects_trend_continuation_when_pullback_loses_breakout_midpoint(self):
        features = _import_features()
        regime = features.build_market_regime(_bullish_regime_candles())
        failed_pullback = tuple(
            candle._replace(close=105.5, low=104.8) if index == 7 else candle
            for index, candle in enumerate(_trend_continuation_structure())
        )

        setup = features.detect_price_action_setup(
            failed_pullback,
            _entry_candles(),
            regime,
        )

        self.assertIsNone(setup)

    def test_compression_expansion_diagnostics_marks_valid_setup_candidate_ready(self):
        features = _import_features()
        non_mature_regime = features.MarketRegimeContext(
            status="COMPRESSION_PENDING_BREAKOUT",
            direction="long",
            last_close=101.0,
            fast_ema=100.5,
            slow_ema=100.2,
            atr=2.0,
            efficiency_ratio=0.25,
            choppiness=64.0,
            dmi_plus=18.0,
            dmi_minus=16.0,
            adx=14.0,
            ttm_squeeze=True,
        )

        diagnostics = features.evaluate_compression_expansion_diagnostics(
            _compression_expansion_structure(),
            _entry_candles(),
            non_mature_regime,
            context_features={"asset": "BTC", "timeframe_group": "B"},
        )

        self.assertTrue(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["first_failed_stage"], "")
        self.assertTrue(diagnostics["stages"]["compression_detected"]["passed"])
        self.assertTrue(diagnostics["stages"]["breakout_volume_valid"]["passed"])
        self.assertTrue(diagnostics["stages"]["midpoint_hold"]["passed"])
        self.assertEqual(diagnostics["metrics"]["direction"], "long")
        self.assertIn("breakout_score", diagnostics["metrics"])
        self.assertIn("breakout_displacement_box_ratio", diagnostics["metrics"])
        self.assertIn("volume_expansion_vs_compression", diagnostics["metrics"])
        self.assertIn("acceptance_window_bars", diagnostics["metrics"])
        self.assertIn("close_back_inside_box", diagnostics["metrics"])
        self.assertIn("primary_failure_reason", diagnostics["metrics"])
        self.assertIn(diagnostics["metrics"]["ce_subtype"], {"impulse_breakout", "acceptance_retest", "ambiguous"})

    def test_compression_expansion_semantic_v2_accepts_wick_retest_without_close_failure(self):
        features = _import_features()
        regime = features.MarketRegimeContext(
            status="COMPRESSION_PENDING_BREAKOUT",
            direction="long",
            last_close=101.0,
            fast_ema=100.5,
            slow_ema=100.2,
            atr=2.0,
            efficiency_ratio=0.25,
            choppiness=64.0,
            dmi_plus=18.0,
            dmi_minus=16.0,
            adx=14.0,
            ttm_squeeze=True,
        )
        semantic_structure = tuple(
            candle._replace(open=101.65, high=102.25, low=100.70, close=101.85, volume=360.0)
            if index == 9
            else candle
            for index, candle in enumerate(_compression_expansion_structure())
        )

        diagnostics = features.evaluate_compression_expansion_diagnostics(
            semantic_structure,
            _entry_candles(),
            regime,
            parameters=features.StrategyParameters(
                compression_breakout_semantic_policy="semantic_v2",
                compression_acceptance_window_bars=3,
                compression_stop_policy="opposite_edge_structural_stop",
                compression_min_breakout_score=0.1,
            ),
            context_features={"asset": "BTC", "timeframe_group": "B"},
        )

        self.assertTrue(diagnostics["candidate_ready"], diagnostics)
        self.assertFalse(diagnostics["metrics"]["close_back_inside_box"])
        self.assertTrue(diagnostics["metrics"]["wick_back_inside_but_close_hold"])
        self.assertEqual(diagnostics["metrics"]["primary_failure_reason"], "")

    def test_compression_expansion_acceptance_retest_entry_uses_retest_reference(self):
        features = _import_features()
        regime = features.MarketRegimeContext(
            status="COMPRESSION_PENDING_BREAKOUT",
            direction="long",
            last_close=101.0,
            fast_ema=100.5,
            slow_ema=100.2,
            atr=2.0,
            efficiency_ratio=0.25,
            choppiness=64.0,
            dmi_plus=18.0,
            dmi_minus=16.0,
            adx=14.0,
            ttm_squeeze=True,
        )
        semantic_structure = tuple(
            candle._replace(open=101.65, high=102.25, low=100.70, close=101.85, volume=360.0)
            if index == 9
            else candle
            for index, candle in enumerate(_compression_expansion_structure())
        )

        diagnostics = features.evaluate_compression_expansion_diagnostics(
            semantic_structure,
            _entry_candles(),
            regime,
            parameters=features.StrategyParameters(
                compression_breakout_semantic_policy="semantic_v2",
                compression_acceptance_window_bars=3,
                compression_entry_policy="acceptance_retest_close",
                compression_stop_policy="acceptance_retest_structural_stop",
                compression_hold_policy="midpoint_or_boundary",
                compression_min_breakout_score=0.1,
            ),
            context_features={"asset": "BTC", "timeframe_group": "B"},
        )

        self.assertTrue(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["metrics"]["entry_policy"], "acceptance_retest_close")
        self.assertEqual(diagnostics["metrics"]["entry_reference_time"], semantic_structure[-1].timestamp_ms)
        self.assertEqual(diagnostics["metrics"]["entry_reference_price"], float(semantic_structure[-1].close))

    def test_compression_expansion_reports_failed_breakout(self):
        features = _import_features()
        regime = features.MarketRegimeContext(
            status="COMPRESSION_PENDING_BREAKOUT",
            direction="long",
            last_close=101.0,
            fast_ema=100.5,
            slow_ema=100.2,
            atr=2.0,
            efficiency_ratio=0.25,
            choppiness=64.0,
            dmi_plus=18.0,
            dmi_minus=16.0,
            adx=14.0,
            ttm_squeeze=True,
        )
        failed = tuple(
            candle._replace(close=100.40, low=100.10) if index == 9 else candle
            for index, candle in enumerate(_compression_expansion_structure())
        )

        diagnostics = features.evaluate_compression_expansion_diagnostics(
            failed,
            _entry_candles(),
            regime,
            context_features={"asset": "BTC", "timeframe_group": "B"},
        )

        self.assertFalse(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["first_failed_stage"], "failed_breakout_absent")
        self.assertFalse(diagnostics["stages"]["failed_breakout_absent"]["passed"])

    def test_breakout_pullback_diagnostics_marks_state_machine_candidate_ready(self):
        features = _import_features()
        regime = features.MarketRegimeContext(
            status="COMPRESSION_PENDING_BREAKOUT",
            direction="long",
            last_close=103.7,
            fast_ema=101.5,
            slow_ema=100.8,
            atr=2.0,
            efficiency_ratio=0.45,
            choppiness=48.0,
            dmi_plus=24.0,
            dmi_minus=16.0,
            adx=18.0,
            ttm_squeeze=False,
        )

        diagnostics = features.evaluate_breakout_pullback_diagnostics(
            _breakout_pullback_structure(),
            _entry_candles(),
            regime,
            parameters=features.StrategyParameters(
                bp_variant_policy="level_retest",
                bp_min_breakout_score=0.10,
                bp_min_relaunch_score=0.10,
            ),
            context_features={"asset": "BTC", "timeframe_group": "B"},
        )

        self.assertTrue(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["first_failed_stage"], "")
        self.assertTrue(diagnostics["stages"]["true_breakout"]["passed"])
        self.assertTrue(diagnostics["stages"]["acceptance_window"]["passed"])
        self.assertTrue(diagnostics["stages"]["healthy_pullback"]["passed"])
        self.assertTrue(diagnostics["stages"]["relaunch_confirmation"]["passed"])
        metrics = diagnostics["metrics"]
        self.assertEqual(metrics["setup_id"], "breakout_pullback")
        self.assertEqual(metrics["bp_subtype"], "level_retest_continuation")
        self.assertGreater(metrics["breakout_score"], 0)
        self.assertGreater(metrics["acceptance_score"], 0)
        self.assertGreater(metrics["pullback_quality_score"], 0)
        self.assertGreater(metrics["relaunch_score"], 0)
        self.assertIn("pullback_depth_ATR", metrics)
        self.assertIn("cost_adjusted_RR", metrics)
        self.assertEqual(metrics["primary_failure_reason"], "")

    def test_breakout_pullback_rejects_fake_breakout_before_pullback(self):
        features = _import_features()
        failed = tuple(
            candle._replace(close=100.55, low=100.20) if index == 7 else candle
            for index, candle in enumerate(_breakout_pullback_structure())
        )

        diagnostics = features.evaluate_breakout_pullback_diagnostics(
            failed,
            _entry_candles(),
            None,
            parameters=features.StrategyParameters(bp_min_breakout_score=0.10),
            context_features={"asset": "BTC", "timeframe_group": "B"},
        )

        self.assertFalse(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["first_failed_stage"], "acceptance_window")
        self.assertEqual(diagnostics["metrics"]["primary_failure_reason"], "close_back_inside_level")

    def test_detects_liquidity_reversal_from_sweep_and_choch(self):
        features = _import_features()
        regime = features.build_market_regime(_bullish_regime_candles())

        setup = features.detect_price_action_setup(
            _liquidity_reversal_structure(),
            _entry_candles(),
            regime,
        )

        self.assertIsNotNone(setup)
        self.assertEqual(setup.setup_type, "liquidity_reversal")
        self.assertEqual(setup.direction, "long")
        self.assertEqual(setup.evidence["sweep_direction"], "down")
        self.assertEqual(setup.evidence["structure"], "SWEEP_CHOCH")
        self.assertEqual(setup.evidence["strategy_family"], "liquidity_sweep_reclaim")
        self.assertEqual(setup.evidence["trend_gate_role"], "soft_context")
        self.assertGreaterEqual(setup.evidence["sweep_rvol"], 1.5)
        self.assertLessEqual(setup.evidence["reclaim_bars"], 5)

    def test_countertrend_liquidity_reversal_requires_stronger_sweep_volume(self):
        features = _import_features()
        bullish_regime = features.build_market_regime(_bullish_regime_candles())
        countertrend_short = (
            _candle(0, 100.0, 102.0, 99.0, 101.0, 100.0),
            _candle(1, 101.0, 104.0, 100.0, 103.0, 100.0),
            _candle(2, 103.0, 106.0, 102.0, 105.0, 100.0),
            _candle(3, 105.0, 106.6, 101.0, 102.0, 170.0),
            _candle(4, 102.0, 103.0, 98.0, 99.0, 160.0),
        )

        setup = features.detect_price_action_setup(
            countertrend_short,
            _entry_candles(),
            bullish_regime,
        )

        self.assertIsNone(setup)

    def test_strategy_parameters_resolve_asset_specific_liquidity_overrides(self):
        features = _import_features()

        btc_params = features.strategy_parameters_from_context(
            {
                "asset": "BTC",
                "timeframe_group": "B",
                "strategy_parameters": {
                    "liquidity_reversal": {
                        "assets": {
                            "BTC": {
                                "sweep_max_atr_multiple": 0.8,
                                "sweep_wick_ratio_min": 0.35,
                                "sweep_rvol_min": 1.8,
                                "countertrend_sweep_rvol_min": 2.5,
                                "reclaim_max_bars": 3,
                                "reclaim_rvol_max": 1.2,
                                "require_choch_for_countertrend": True,
                            },
                            "ETH": {
                                "sweep_wick_ratio_min": 0.40,
                                "sweep_rvol_min": 2.0,
                                "countertrend_sweep_rvol_min": 2.8,
                                "require_choch_for_eth_reversal": True,
                            },
                        }
                    }
                },
            }
        )
        eth_params = features.strategy_parameters_from_context(
            {
                "asset": "ETH",
                "timeframe_group": "B",
                "strategy_parameters": {
                    "liquidity_reversal": {
                        "assets": {
                            "BTC": {"sweep_wick_ratio_min": 0.35},
                            "ETH": {
                                "sweep_wick_ratio_min": 0.40,
                                "sweep_rvol_min": 2.0,
                                "countertrend_sweep_rvol_min": 2.8,
                                "require_choch_for_eth_reversal": True,
                            },
                        }
                    }
                },
            }
        )

        self.assertEqual(btc_params.sweep_max_atr_multiple, 0.8)
        self.assertEqual(btc_params.sweep_wick_ratio_min, 0.35)
        self.assertEqual(btc_params.reclaim_max_bars, 3)
        self.assertEqual(btc_params.reclaim_rvol_max, 1.2)
        self.assertTrue(btc_params.require_choch_for_countertrend)
        self.assertEqual(eth_params.sweep_wick_ratio_min, 0.40)
        self.assertEqual(eth_params.countertrend_sweep_rvol_min, 2.8)
        self.assertTrue(eth_params.require_choch_for_eth_reversal)

    def test_structure_extreme_buffer_invalidation_uses_sweep_extreme_plus_small_atr_buffer(self):
        features = _import_features()
        regime = features.build_market_regime(_bullish_regime_candles())
        params = features.StrategyParameters(
            invalidation_mode="structure_extreme_buffer",
            invalidation_buffer_atr=0.15,
        )

        setup = features.detect_price_action_setup(
            _liquidity_reversal_structure(),
            _entry_candles(),
            regime,
            params,
        )

        self.assertIsNotNone(setup)
        self.assertEqual(setup.evidence["invalidation_mode"], "structure_extreme_buffer")
        self.assertEqual(setup.evidence["invalidation_buffer_atr"], 0.15)
        self.assertAlmostEqual(setup.invalidation_level, setup.evidence["sweep_extreme_price"] - regime.atr * 0.15)

    def test_volume_price_prefers_quote_volume_for_crypto(self):
        features = _import_features()
        candles = tuple(
            candle._replace(volume=100.0, volume_currency_quote=1000.0)
            for candle in _entry_candles(latest_volume=100.0)
        )
        candles = (*candles[:-1], candles[-1]._replace(volume=100.0, volume_currency_quote=2600.0))

        confirmation = features.confirm_volume_price(candles, "long")

        self.assertEqual(confirmation.status, "confirm")
        self.assertEqual(confirmation.evidence["volume_source"], "quote")

    def test_confirm_volume_price_outputs_status_without_direction(self):
        features = _import_features()

        confirmation = features.confirm_volume_price(_entry_candles(), "long")

        self.assertEqual(confirmation.status, "confirm")
        self.assertNotIn("direction", confirmation.evidence)

    def test_confirm_volume_price_rejects_quiet_latest_volume(self):
        features = _import_features()

        confirmation = features.confirm_volume_price(_entry_candles(latest_volume=40.0), "long")

        self.assertEqual(confirmation.status, "reject")

    def test_confirm_volume_price_ignores_unconfirmed_latest_candle(self):
        features = _import_features()
        candles = (*_entry_candles(latest_volume=40.0), _candle(99, 106.6, 109.0, 106.5, 108.8, 900.0, confirmed=False))

        confirmation = features.confirm_volume_price(candles, "long")

        self.assertEqual(confirmation.status, "reject")

    def test_tod_dow_log_ewma_rvol_uses_prior_bucket_only_and_reports_fallback(self):
        features = _import_features()
        matching_history = tuple(_hourly_candle(index * 24 * 7, 100.0) for index in range(30))
        other_bucket_spikes = tuple(_hourly_candle(index * 24 * 7 + 1, 10_000.0) for index in range(30))
        latest = _hourly_candle(30 * 24 * 7, 200.0)
        context_features = {
            "volume": {
                "baseline_mode": "tod_dow_log_ewma",
                "half_life_days": 90,
                "min_bucket_samples": 30,
                "fallback_mode": "rolling_ewma",
                "epsilon": 1e-12,
            },
            "asset": "BTC",
            "entry_timeframe": "1h",
        }

        confirmation = features.confirm_volume_price((*matching_history, *other_bucket_spikes, latest), "long", context_features)

        self.assertEqual(confirmation.evidence["volume_baseline_mode"], "tod_dow_log_ewma")
        self.assertFalse(confirmation.evidence["used_fallback_volume_baseline"])
        self.assertEqual(confirmation.evidence["volume_bucket_sample_count"], 30)
        self.assertAlmostEqual(confirmation.evidence["tod_dow_rvol"], 2.0, places=6)
        self.assertAlmostEqual(confirmation.evidence["rolling_rvol"], 200.0 / 5050.0, places=6)
        self.assertEqual(confirmation.evidence["raw_volume"], 200.0)
        self.assertAlmostEqual(confirmation.evidence["log_volume"], 5.298317366548036, places=6)

    def test_tod_dow_log_ewma_rvol_falls_back_when_bucket_is_too_small(self):
        features = _import_features()
        candles = tuple(_hourly_candle(index, 100.0) for index in range(10))
        latest = _hourly_candle(10, 200.0)

        confirmation = features.confirm_volume_price(
            (*candles, latest),
            "long",
            {
                "volume": {
                    "baseline_mode": "tod_dow_log_ewma",
                    "min_bucket_samples": 30,
                    "fallback_mode": "rolling_ewma",
                    "epsilon": 1e-12,
                },
                "asset": "BTC",
                "entry_timeframe": "1h",
            },
        )

        self.assertTrue(confirmation.evidence["used_fallback_volume_baseline"])
        self.assertEqual(confirmation.evidence["volume_baseline_mode"], "rolling_ewma")
        self.assertEqual(confirmation.evidence["tod_dow_rvol"], None)

    def test_minimum_reward_to_risk_handles_valid_and_invalid_levels(self):
        features = _import_features()

        self.assertEqual(features.minimum_reward_to_risk(100.0, 95.0, 112.5), 2.5)
        self.assertIsNone(features.minimum_reward_to_risk(100.0, 100.0, 112.5))


if __name__ == "__main__":
    unittest.main()
