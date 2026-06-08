import unittest

from trading_system.data.okx_cli import Candle
from trading_system.strategies import get_strategy
from trading_system.strategies.base import StrategyContext
from trading_system.strategies.trend_price_volume_v1.candidates import generate_raw_candidates
from trading_system.strategies.trend_price_volume_v1.features import (
    MarketRegimeContext,
    build_market_regime,
    evaluate_trend_continuation_diagnostics,
)
from trading_system.strategies.trend_price_volume_v1.trend_continuation_core import CORE_ENGINE_VERSION


def _candle(
    index: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
    *,
    confirmed: bool = True,
) -> Candle:
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


def _bullish_trend_candles(count: int = 230) -> tuple[Candle, ...]:
    candles: list[Candle] = []
    for index in range(count):
        close = 100.0 + index * 0.45
        candles.append(
            _candle(
                index,
                close - 0.2,
                close + 0.5,
                close - 0.5,
                close,
                volume=500.0 + index,
            )
        )
    return tuple(candles)


def _trend_continuation_structure() -> tuple[Candle, ...]:
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


def _compression_expansion_structure() -> tuple[Candle, ...]:
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


def _breakout_pullback_structure() -> tuple[Candle, ...]:
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


def _liquidity_reversal_structure() -> tuple[Candle, ...]:
    rows = (
        (110.0, 111.0, 108.0, 109.0, 100.0),
        (109.0, 110.0, 104.0, 105.0, 100.0),
        (105.0, 106.0, 100.0, 101.0, 100.0),
        (101.0, 105.5, 99.4, 104.8, 230.0),
        (104.8, 108.5, 103.8, 108.0, 160.0),
        (108.0, 109.0, 105.5, 107.6, 90.0),
    )
    return tuple(_candle(index, row[0], row[1], row[2], row[3], volume=row[4]) for index, row in enumerate(rows))


def _entry_candles(*, quiet_latest: bool = False) -> tuple[Candle, ...]:
    candles: list[Candle] = []
    for index in range(24):
        close = 105.0 + (index % 3) * 0.1
        candles.append(
            _candle(
                index,
                close - 0.1,
                close + 0.3,
                close - 0.3,
                close,
                volume=100.0,
            )
        )
    latest_volume = 40.0 if quiet_latest else 320.0
    candles.append(_candle(24, 105.2, 107.0, 104.9, 106.6, volume=latest_volume))
    return tuple(candles)


class TrendPriceVolumeStrategySignalTests(unittest.TestCase):
    def test_missing_required_timeframes_returns_no_signals(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={"15m": _entry_candles()},
        )

        self.assertEqual(strategy.generate_signals(context), ())

    def test_generates_trend_continuation_signal_from_three_timeframes(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(),
                "1h": _trend_continuation_structure(),
                "4h": _bullish_trend_candles(),
            },
        )

        signals = strategy.generate_signals(context)

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.setup_type, "trend_continuation")
        self.assertEqual(signal.direction, "long")
        self.assertEqual(signal.strategy_name, "trend_price_volume")
        self.assertEqual(signal.strategy_version, "v1")
        self.assertEqual(signal.symbol, "BTC/USDT")
        self.assertEqual(signal.venue, "okx")
        self.assertEqual(signal.timeframe_group, "B")
        self.assertEqual(signal.price_action_evidence["strategy_family"], "breakout_pullback_continuation")
        self.assertEqual(signal.explanation_payload["strategy_family"], "breakout_pullback_continuation")
        self.assertEqual(signal.volume_price_evidence["status"], "confirm")
        self.assertGreater(signal.target_hint["reward_to_risk"], 1.5)
        self.assertLess(signal.invalidation_level, signal.entry_zone["low"])

    def test_quiet_latest_volume_rejects_otherwise_valid_signal(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(quiet_latest=True),
                "1h": _trend_continuation_structure(),
                "4h": _bullish_trend_candles(),
            },
        )

        self.assertEqual(strategy.generate_signals(context), ())

    def test_strategy_parameter_override_can_tighten_breakout_threshold(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(),
                "1h": _trend_continuation_structure(),
                "4h": _bullish_trend_candles(),
            },
            features={"strategy_parameters": {"breakout_rvol_min": 3.0}},
        )

        self.assertEqual(strategy.generate_signals(context), ())

    def test_generates_liquidity_reversal_signal_when_sweep_choch_and_volume_confirm(self):
        strategy = get_strategy("trend_price_volume", version="v1")
        context = StrategyContext(
            symbol="BTC/USDT",
            venue="okx",
            timeframe_group="B",
            candles_by_timeframe={
                "15m": _entry_candles(),
                "1h": _liquidity_reversal_structure(),
                "4h": _bullish_trend_candles(),
            },
        )

        signals = strategy.generate_signals(context)

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.setup_type, "liquidity_reversal")
        self.assertEqual(signal.direction, "long")
        self.assertEqual(signal.price_action_evidence["sweep_direction"], "down")
        self.assertEqual(signal.price_action_evidence["strategy_family"], "liquidity_sweep_reclaim")
        self.assertEqual(signal.explanation_payload["trend_gate_role"], "soft_context")
        self.assertGreaterEqual(signal.target_hint["reward_to_risk"], 1.5)

    def test_liquidity_reversal_history_event_not_regenerated_after_entry_window_moves_on(self):
        structure = _liquidity_reversal_structure()
        entry_at_next_bar = tuple(_candle(index, 104.0, 106.0, 103.5, 105.5) for index in range(1, 6))
        entry_after_next_bar = (*entry_at_next_bar, _candle(6, 105.5, 106.2, 104.8, 105.8))
        context_features = {
            "asset": "BTC",
            "entry_timeframe": "15m",
            "structure_timeframe": "1h",
            "trend_timeframe": "4h",
        }

        current = generate_raw_candidates(
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT-SWAP",
            inst_type="SWAP",
            profile="B",
            structure_candles=structure,
            entry_candles=entry_at_next_bar,
            trend_candles=_bullish_trend_candles(),
            context_features=context_features,
            setup_filter=("liquidity_reversal",),
        )
        later = generate_raw_candidates(
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT-SWAP",
            inst_type="SWAP",
            profile="B",
            structure_candles=structure,
            entry_candles=entry_after_next_bar,
            trend_candles=_bullish_trend_candles(),
            context_features=context_features,
            setup_filter=("liquidity_reversal",),
        )

        self.assertTrue(current)
        self.assertEqual(later, ())

    def test_trend_continuation_same_breakout_pullback_keeps_single_event_identity(self):
        entry = _entry_candles()
        later_entry = (*entry, _candle(25, 106.8, 108.2, 106.4, 107.8, volume=340.0))
        context_features = {
            "asset": "BTC",
            "entry_timeframe": "15m",
            "structure_timeframe": "1h",
            "trend_timeframe": "4h",
        }

        first = generate_raw_candidates(
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT-SWAP",
            inst_type="SWAP",
            profile="B",
            structure_candles=_trend_continuation_structure(),
            entry_candles=entry,
            trend_candles=_bullish_trend_candles(),
            context_features=context_features,
            setup_filter=("trend_continuation",),
        )
        second = generate_raw_candidates(
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT-SWAP",
            inst_type="SWAP",
            profile="B",
            structure_candles=_trend_continuation_structure(),
            entry_candles=later_entry,
            trend_candles=_bullish_trend_candles(),
            context_features=context_features,
            setup_filter=("trend_continuation",),
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].candidate_id, second[0].candidate_id)
        self.assertEqual(first[0].event_id or first[0].sweep_event_id, second[0].event_id or second[0].sweep_event_id)

    def test_compression_expansion_setup_filter_generates_isolated_candidate(self):
        context_features = {
            "asset": "BTC",
            "entry_timeframe": "15m",
            "structure_timeframe": "1h",
            "trend_timeframe": "4h",
            "timeframe_group": "B",
            "market_regime": MarketRegimeContext(
                status="COMPRESSION_PENDING_BREAKOUT",
                direction="long",
                last_close=102.85,
                fast_ema=101.4,
                slow_ema=101.0,
                atr=2.0,
                efficiency_ratio=0.25,
                choppiness=64.0,
                dmi_plus=22.0,
                dmi_minus=18.0,
                adx=14.0,
                ttm_squeeze=True,
            ),
        }

        rows = generate_raw_candidates(
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT-SWAP",
            inst_type="SWAP",
            profile="B",
            structure_candles=_compression_expansion_structure(),
            entry_candles=_entry_candles(),
            trend_candles=_bullish_trend_candles(),
            context_features=context_features,
            setup_filter=("compression_expansion",),
        )

        self.assertEqual(len(rows), 1)
        row = rows[0].to_row()
        self.assertEqual(row["setup"], "compression_expansion")
        self.assertEqual(row["strategy_family"], "compression_expansion_breakout")
        self.assertEqual(row["compression_start_time"], _compression_expansion_structure()[0].timestamp_ms)
        self.assertEqual(row["compression_end_time"], _compression_expansion_structure()[7].timestamp_ms)
        self.assertEqual(row["breakout_time"], _compression_expansion_structure()[8].timestamp_ms)
        self.assertEqual(row["confirmation_time"], _compression_expansion_structure()[9].timestamp_ms)
        self.assertAlmostEqual(row["compression_box_height"], 1.0)
        self.assertAlmostEqual(row["compression_box_atr"], 0.5)
        self.assertAlmostEqual(row["compression_midpoint"], 100.3)
        self.assertAlmostEqual(row["breakout_displacement_atr"], 1.6)
        self.assertAlmostEqual(row["breakout_close_location"], 0.90625)
        self.assertAlmostEqual(row["breakout_body_pct"], row["breakout_body_ratio"])
        self.assertTrue(row["midpoint_hold"])
        self.assertTrue(row["boundary_hold"])
        self.assertTrue(row["retest_hold"])
        self.assertEqual(row["stop_anchor_type"], "breakout_midpoint_or_box_edge")
        self.assertGreater(row["entry_to_stop"], 0)
        self.assertGreater(row["target_space"], 0)
        self.assertGreater(row["gross_RR"], 0)
        self.assertEqual(row["signal_time"], _compression_expansion_structure()[9].timestamp_ms)
        self.assertTrue(row["no_lookahead_safe"])

    def test_breakout_pullback_setup_filter_generates_isolated_candidate(self):
        structure = _breakout_pullback_structure()
        context_features = {
            "asset": "BTC",
            "entry_timeframe": "15m",
            "structure_timeframe": "1h",
            "trend_timeframe": "4h",
            "timeframe_group": "B",
            "strategy_parameters": {
                "breakout_pullback": {
                    "bp_variant_policy": "level_retest",
                    "bp_min_breakout_score": 0.10,
                    "bp_min_relaunch_score": 0.10,
                }
            },
        }

        rows = generate_raw_candidates(
            symbol="BTC/USDT",
            venue="okx",
            inst_id="BTC-USDT-SWAP",
            inst_type="SWAP",
            profile="B",
            structure_candles=structure,
            entry_candles=_entry_candles(),
            trend_candles=_bullish_trend_candles(),
            context_features=context_features,
            setup_filter=("breakout_pullback",),
        )

        self.assertEqual(len(rows), 1)
        row = rows[0].to_row()
        self.assertEqual(row["setup"], "breakout_pullback")
        self.assertEqual(row["strategy_family"], "breakout_pullback_continuation")
        self.assertEqual(row["breakout_pullback_event_id"], row["event_id"])
        self.assertEqual(row["core_engine_version"], CORE_ENGINE_VERSION)
        self.assertTrue(row["level_id"])
        self.assertTrue(row["breakout_event_id"])
        self.assertIn(row["breakout_class"], {"strong_breakout", "accepted_breakout", "weak_but_watch"})
        self.assertTrue(row["stop_is_structural"])
        self.assertGreater(row["pullback_quality_score"], 0)
        self.assertGreater(row["relaunch_score"], 0)

    def test_trend_continuation_diagnostics_marks_valid_setup_candidate_ready(self):
        trend = _bullish_trend_candles()
        diagnostics = evaluate_trend_continuation_diagnostics(
            _trend_continuation_structure(),
            _entry_candles(),
            build_market_regime(trend),
            context_features={
                "asset": "BTC",
                "entry_timeframe": "15m",
                "structure_timeframe": "1h",
                "trend_timeframe": "4h",
            },
        )

        self.assertTrue(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["first_failed_stage"], "")
        self.assertTrue(diagnostics["stages"]["entry_volume_confirmation"]["passed"])
        self.assertGreater(diagnostics["metrics"]["breakout_rvol"], 2.0)

    def test_trend_continuation_diagnostics_reports_first_failed_stage(self):
        structure = list(_trend_continuation_structure())
        structure[-2] = _candle(6, 103.8, 106.2, 103.2, 105.4, 260.0)

        diagnostics = evaluate_trend_continuation_diagnostics(
            tuple(structure),
            _entry_candles(),
            build_market_regime(_bullish_trend_candles()),
            context_features={
                "asset": "BTC",
                "entry_timeframe": "15m",
                "structure_timeframe": "1h",
                "trend_timeframe": "4h",
            },
        )

        self.assertFalse(diagnostics["candidate_ready"], diagnostics)
        self.assertEqual(diagnostics["first_failed_stage"], "displacement_body")
        self.assertFalse(diagnostics["stages"]["displacement_body"]["passed"])


if __name__ == "__main__":
    unittest.main()
