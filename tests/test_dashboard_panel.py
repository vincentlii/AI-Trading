import tempfile
import unittest
from pathlib import Path

from trading_system.config import ProposalChange, load_backtest_preset, make_parameter_proposal, save_parameter_proposal
from trading_system.data.history import CandleRepository
from trading_system.data.okx_cli import Candle
from trading_system.data.quality import bar_duration_ms
from trading_system.simulation import ReviewLogEntry
from trading_system.simulation.review_log import append_review_log_entries
from trading_system.strategies.base import Strategy, StrategyContext, StrategyMetadata, StrategySignal
from trading_system.timeframe_profiles import get_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_PATH = PROJECT_ROOT / "configs" / "presets" / "btc_eth_p4_4.toml"


def _candle(index: int, interval_ms: int, open_price: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * interval_ms,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        volume_currency=100.0,
        volume_currency_quote=100.0 * close,
        is_confirmed=True,
    )


def _repository_with_btc_eth_abc_data() -> CandleRepository:
    repository = CandleRepository()
    for inst_id in ("BTC-USDT", "ETH-USDT"):
        for bar in ("5m", "15m", "1H", "4H", "1D"):
            interval_ms = bar_duration_ms(bar)
            candles = (
                _candle(0, interval_ms, 100.0, 104.0, 99.0, 102.0),
                _candle(1, interval_ms, 102.0, 105.0, 100.0, 104.0),
                _candle(2, interval_ms, 104.0, 106.0, 101.0, 105.0),
                _candle(3, interval_ms, 100.0, 112.0, 99.0, 111.0),
            )
            repository.save_many(inst_id, bar, candles)
    return repository


class OneSignalPerProfileStrategy(Strategy):
    metadata = StrategyMetadata(
        name="trend_price_volume",
        version="v1",
        description="Dashboard test strategy.",
        required_timeframe_profile_keys=("A", "B", "C"),
        required_indicators=(),
        documentation_path="",
        supported_symbols=("BTC/USDT", "ETH/USDT"),
        setup_types=("trend_continuation",),
    )

    def generate_signals(self, context: StrategyContext) -> tuple[StrategySignal, ...]:
        profile = get_profile(context.timeframe_group)
        entry = tuple(context.candles_by_timeframe[profile.entry_timeframe])
        if len(entry) != 3:
            return ()
        return (
            StrategySignal(
                strategy_name=self.metadata.name,
                strategy_version=self.metadata.version,
                setup_type="trend_continuation",
                symbol=context.symbol,
                venue=context.venue,
                timeframe_group=context.timeframe_group,
                direction="long",
                entry_zone={"low": 99.0, "high": 101.0},
                invalidation_level=95.0,
                target_hint={"target_price": 110.0},
                trend_evidence={"atr": 3.0},
                price_action_evidence={},
                volume_price_evidence={"status": "confirm"},
                risk_profile={},
                explanation_payload={"strategy_family": "breakout_pullback_continuation"},
            ),
        )


class DashboardPanelTests(unittest.TestCase):
    def test_snapshot_uses_p4_4_runner_quality_checks_and_read_only_proposals(self):
        from trading_system.dashboard.panel import build_dashboard_snapshot

        preset = load_backtest_preset(PRESET_PATH)
        proposal = make_parameter_proposal(
            proposal_id="dashboard_smoke",
            title="Dashboard smoke proposal",
            source="agent",
            base_preset_path="configs/presets/btc_eth_p4_4.toml",
            base_preset=preset,
            changes=(
                ProposalChange(
                    path="ranking.min_trades_for_primary",
                    before=30,
                    after=40,
                    reason="Check proposal listing in dashboard.",
                ),
            ),
            evidence={"source": "unit_test"},
            expected_impact="No formal config changes.",
            risks=("Dashboard must not apply this proposal.",),
            validation_plan=("List the proposal only.",),
        )

        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            review_log_path = Path(temp_dir) / "review_log.jsonl"
            append_review_log_entries(
                review_log_path,
                (
                    ReviewLogEntry(
                        event_type="position_closed",
                        timestamp_ms=1_700_000_000_000,
                        symbol="BTC/USDT",
                        venue="okx",
                        strategy_name="trend_price_volume",
                        strategy_version="v1",
                        setup_type="trend_continuation",
                        status="time_exit",
                        reason_codes=(),
                        payload={"net_pnl": -10.0, "r_multiple": -0.1, "cost": 1.0},
                    ),
                    ReviewLogEntry(
                        event_type="equity_updated",
                        timestamp_ms=1_700_000_000_000,
                        symbol="BTC/USDT",
                        venue="okx",
                        strategy_name="trend_price_volume",
                        strategy_version="v1",
                        setup_type="trend_continuation",
                        status="updated",
                        reason_codes=(),
                        payload={"equity": 99_990.0, "drawdown_pct": 0.0001},
                    ),
                ),
            )
            proposal_path = save_parameter_proposal(proposal, Path(temp_dir))
            snapshot = build_dashboard_snapshot(
                repository=_repository_with_btc_eth_abc_data(),
                preset=preset,
                strategy=OneSignalPerProfileStrategy(),
                proposals_dir=Path(temp_dir),
                review_log_path=review_log_path,
            )

        self.assertEqual(snapshot.config_version, preset.config_version)
        self.assertEqual(snapshot.config_fingerprint, preset.config_fingerprint)
        self.assertEqual(len(snapshot.ranking_rows), 6)
        self.assertEqual({row["symbol"] for row in snapshot.ranking_rows}, {"BTC/USDT", "ETH/USDT"})
        self.assertEqual({row["timeframe_group"] for row in snapshot.ranking_rows}, {"A", "B", "C"})

        self.assertEqual(len(snapshot.quality_rows), 10)
        self.assertEqual({row["symbol"] for row in snapshot.quality_rows}, {"BTC/USDT", "ETH/USDT"})
        self.assertNotIn("XAUT/USDT", {row["symbol"] for row in snapshot.quality_rows})
        self.assertTrue(all(row["status"] == "pass" for row in snapshot.quality_rows))

        self.assertEqual(len(snapshot.proposal_rows), 1)
        self.assertEqual(snapshot.proposal_rows[0]["proposal_id"], "dashboard_smoke")
        self.assertEqual(snapshot.proposal_rows[0]["status"], "loaded")
        self.assertEqual(snapshot.proposal_rows[0]["auto_apply"], False)
        self.assertEqual(snapshot.proposal_rows[0]["path"], str(proposal_path))

        self.assertEqual(len(snapshot.performance_metric_rows), 6)
        self.assertEqual({row["primary_metric_source"] for row in snapshot.performance_metric_rows}, {"project_backtest_summary"})
        self.assertEqual({row["library"] for row in snapshot.performance_library_rows}, {"quantstats", "empyrical"})
        self.assertEqual(snapshot.performance_artifact_rows[0]["status"], "not_generated")
        self.assertEqual(len(snapshot.data_coverage_rows), 10)
        self.assertEqual({row["bar"] for row in snapshot.data_coverage_rows}, {"5m", "15m", "1H", "4H", "1D"})
        self.assertEqual(len(snapshot.profile_coverage_rows), 6)
        self.assertEqual({row["profile"] for row in snapshot.profile_coverage_rows}, {"A", "B", "C"})
        self.assertEqual(len(snapshot.signal_funnel_rows), 6)
        self.assertTrue(all("approved_signal" in row for row in snapshot.signal_funnel_rows))
        self.assertIsInstance(snapshot.volume_rejection_rows, tuple)
        self.assertIsInstance(snapshot.volume_distribution_rows, tuple)
        self.assertIsInstance(snapshot.risk_rejection_rows, tuple)
        self.assertIsInstance(snapshot.near_miss_rows, tuple)

        self.assertEqual(snapshot.summary["ranked_groups"], 6)
        self.assertEqual(snapshot.summary["quality_failures"], 0)
        self.assertEqual(snapshot.summary["proposals"], 1)
        self.assertEqual(snapshot.summary["performance_runs"], 6)
        self.assertEqual(snapshot.summary["coverage_bars"], 10)
        self.assertEqual(snapshot.summary["signal_funnel_profiles"], 6)
        self.assertIn("volume_rejection_groups", snapshot.summary)
        self.assertIn("risk_rejection_groups", snapshot.summary)
        self.assertIn("near_miss_candidates", snapshot.summary)
        self.assertEqual(len(snapshot.paper_review_log_rows), 2)
        self.assertEqual(len(snapshot.paper_trade_rows), 1)
        self.assertEqual(len(snapshot.paper_equity_rows), 1)
        self.assertEqual(len(snapshot.paper_failure_rows), 1)
        self.assertEqual(snapshot.summary["paper_review_log_events"], 2)
        self.assertEqual(snapshot.summary["dashboard_max_entry_windows"], 200)


if __name__ == "__main__":
    unittest.main()
