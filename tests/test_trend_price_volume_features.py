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

    def test_minimum_reward_to_risk_handles_valid_and_invalid_levels(self):
        features = _import_features()

        self.assertEqual(features.minimum_reward_to_risk(100.0, 95.0, 112.5), 2.5)
        self.assertIsNone(features.minimum_reward_to_risk(100.0, 100.0, 112.5))


if __name__ == "__main__":
    unittest.main()
