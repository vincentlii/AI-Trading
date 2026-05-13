from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeframeProfile:
    key: str
    name: str
    entry_timeframe: str
    structure_timeframe: str
    trend_timeframe: str
    use_case: str
    judgment: str
    asset_priority: dict[str, int]

    @property
    def timeframes(self) -> tuple[str, str, str]:
        return (self.entry_timeframe, self.structure_timeframe, self.trend_timeframe)

    def priority_for_asset(self, symbol: str) -> int:
        asset = symbol.split("/", 1)[0].upper()
        return self.asset_priority.get(asset, self.asset_priority["DEFAULT"])


@dataclass(frozen=True)
class BacktestResultSummary:
    profile_key: str
    symbol: str
    gross_profit: float
    net_profit: float
    total_fees: float
    trade_count: int
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    profit_factor: float = 0.0
    average_holding_time: str = ""
    expectancy_per_trade: float = 0.0

    @property
    def fee_to_gross_profit_ratio(self) -> float:
        if self.gross_profit <= 0:
            return 1.0
        return self.total_fees / self.gross_profit


@dataclass(frozen=True)
class ProfileDecision:
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RankedProfileResult:
    result: BacktestResultSummary
    decision: ProfileDecision
    score: float


_DEFAULT_PROFILES = (
    TimeframeProfile(
        key="B",
        name="standard_swing",
        entry_timeframe="15m",
        structure_timeframe="1h",
        trend_timeframe="4h",
        use_case="Primary BTC/ETH/XAUT backtest layer with balanced signal quality and frequency.",
        judgment="Recommended primary candidate.",
        asset_priority={"BTC": 1, "ETH": 1, "XAUT": 1, "DEFAULT": 1},
    ),
    TimeframeProfile(
        key="C",
        name="slow_trend",
        entry_timeframe="1h",
        structure_timeframe="4h",
        trend_timeframe="1d",
        use_case="Low-frequency trend capture for XAUT and major BTC/ETH trends.",
        judgment="Lower costs and better tail capture, but sample size must be checked.",
        asset_priority={"BTC": 2, "ETH": 2, "XAUT": 2, "DEFAULT": 2},
    ),
    TimeframeProfile(
        key="A",
        name="fast_intraday",
        entry_timeframe="5m",
        structure_timeframe="15m",
        trend_timeframe="1h",
        use_case="High-liquidity BTC/ETH sessions for sweeps and OB/FVG retests.",
        judgment="Most cost-sensitive; reject when fees consume too much gross profit.",
        asset_priority={"BTC": 3, "ETH": 3, "XAUT": 4, "DEFAULT": 3},
    ),
)


def list_default_profiles() -> tuple[TimeframeProfile, ...]:
    return _DEFAULT_PROFILES


def get_profile(key: str) -> TimeframeProfile:
    normalized_key = key.upper()
    for profile in _DEFAULT_PROFILES:
        if profile.key == normalized_key:
            return profile
    raise KeyError(f"Unknown timeframe profile: {key}")


def required_backtest_metrics() -> tuple[str, ...]:
    return (
        "net_profit",
        "max_drawdown",
        "win_rate",
        "profit_loss_ratio",
        "profit_factor",
        "average_holding_time",
        "expectancy_per_trade",
        "fee_to_gross_profit_ratio",
    )


def evaluate_profile_result(
    result: BacktestResultSummary,
    *,
    fast_profile_fee_reject_threshold: float = 0.25,
    min_trades_for_primary: int = 30,
) -> ProfileDecision:
    profile = get_profile(result.profile_key)
    reasons: list[str] = []

    if profile.key == "A" and result.fee_to_gross_profit_ratio > fast_profile_fee_reject_threshold:
        reasons.append(
            f"cost ratio {result.fee_to_gross_profit_ratio:.2%} is above "
            f"{fast_profile_fee_reject_threshold:.0%} for fast intraday trading"
        )
        return ProfileDecision(status="rejected", reasons=tuple(reasons))

    if profile.key == "C" and result.trade_count < min_trades_for_primary:
        reasons.append(
            f"sample size {result.trade_count} is below {min_trades_for_primary}; "
            "use slow trend as a supporting layer only"
        )
        return ProfileDecision(status="supporting_only", reasons=tuple(reasons))

    reasons.append(f"profile {profile.key} passed initial timeframe-layer gates")
    return ProfileDecision(status="candidate", reasons=tuple(reasons))


def rank_profile_results(
    results: tuple[BacktestResultSummary, ...] | list[BacktestResultSummary],
    *,
    fast_profile_fee_reject_threshold: float = 0.25,
    min_trades_for_primary: int = 30,
) -> tuple[RankedProfileResult, ...]:
    ranked: list[RankedProfileResult] = []

    for result in results:
        decision = evaluate_profile_result(
            result,
            fast_profile_fee_reject_threshold=fast_profile_fee_reject_threshold,
            min_trades_for_primary=min_trades_for_primary,
        )
        ranked.append(RankedProfileResult(result=result, decision=decision, score=_score_result(result)))

    status_rank = {"candidate": 0, "supporting_only": 1, "rejected": 2}
    ranked.sort(
        key=lambda item: (
            status_rank[item.decision.status],
            -item.score,
            get_profile(item.result.profile_key).priority_for_asset(item.result.symbol),
        )
    )
    return tuple(ranked)


def _score_result(result: BacktestResultSummary) -> float:
    drawdown_penalty = result.max_drawdown if result.max_drawdown > 0 else 0.01
    profit_factor_boost = result.profit_factor if result.profit_factor > 0 else 1.0
    expectancy_boost = max(result.expectancy_per_trade, 0.0)
    return (result.net_profit / drawdown_penalty) + (profit_factor_boost * 100.0) + expectancy_boost
