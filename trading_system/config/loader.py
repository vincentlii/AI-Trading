from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

from trading_system.backtest.execution import BacktestExecutionConfig
from trading_system.backtest.risk import RiskParameters
from trading_system.backtest.scanner import BacktestScanConfig, BacktestScanTarget


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_PROFILES = {"A", "B", "C"}
TREND_PRICE_VOLUME_SETUPS = {"trend_continuation", "liquidity_reversal", "compression_expansion", "breakout_pullback"}
BTC_ETH_SYMBOLS = {"BTC/USDT", "ETH/USDT"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AssetTargetConfig:
    canonical_symbol: str
    inst_id: str
    venue: str = "okx"
    inst_type: str = "SPOT"

    def to_scan_target(self) -> BacktestScanTarget:
        return BacktestScanTarget(
            canonical_symbol=self.canonical_symbol,
            inst_id=self.inst_id,
            venue=self.venue,
            inst_type=self.inst_type,
        )


@dataclass(frozen=True)
class AssetConfig:
    universe: str
    primary_venue: str
    validation_venues: tuple[str, ...]
    targets: tuple[AssetTargetConfig, ...]
    contract_mode: str = "spot"
    allow_short: bool = False


@dataclass(frozen=True)
class CostTierConfig:
    name: str
    fee_rate: float
    spread_slippage_rate: float


@dataclass(frozen=True)
class CostConfig:
    name: str
    fee_rate: float
    spread: float
    slippage: float
    funding: float
    description: str = ""
    spread_slippage_rate: float = 0.0
    funding_mode: str = "static_config_only"
    cost_model_tiers: tuple[CostTierConfig, ...] = ()


@dataclass(frozen=True)
class ExecutionConfig:
    initial_equity: float
    max_holding_bars: int
    conservative_same_bar: bool
    point_value: float
    enable_advanced_exits: bool
    partial_take_profit_r: float
    partial_take_profit_pct: float
    move_stop_to_true_breakeven: bool
    chandelier_period: int
    chandelier_atr_multiple: float
    invalidation_mode: str = "atr_buffer"
    invalidation_buffer_atr: float = 1.0
    invalidation_buffer_atr_candidates: tuple[float, ...] = ()
    shadow_max_stop_atr_multiple_candidates: tuple[float, ...] = ()
    reversal_time_cut_bars: int = 0
    reversal_time_cut_min_mfe_r: float = 0.0
    reversal_time_cut_bars_candidates: tuple[int, ...] = ()
    reversal_time_cut_min_mfe_r_candidates: tuple[float, ...] = ()
    breakeven_after_mfe_r: float = 0.0


@dataclass(frozen=True)
class ScanConfig:
    profile_keys: tuple[str, ...]
    start_ms: int | None = None
    end_ms: int | None = None
    max_context_bars_by_timeframe: Mapping[str, int] | None = None


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    version: str
    enabled: bool
    enabled_setups: tuple[str, ...]
    parameters: Mapping[str, object] = field(default_factory=dict)
    parameter_grid: Mapping[str, object] = field(default_factory=dict)
    profile_status: Mapping[str, str] = field(default_factory=dict)
    volume: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RankingConfig:
    fast_profile_fee_reject_threshold: float
    min_trades_for_primary: int


@dataclass(frozen=True)
class BacktestPresetConfig:
    config_version: str
    config_fingerprint: str
    assets: AssetConfig
    risk: RiskParameters
    costs: CostConfig
    execution: ExecutionConfig
    scan: ScanConfig
    strategy: StrategyConfig
    ranking: RankingConfig

    def to_scan_config(self) -> BacktestScanConfig:
        return BacktestScanConfig(
            targets=tuple(target.to_scan_target() for target in self.assets.targets),
            profile_keys=self.scan.profile_keys,
            start_ms=self.scan.start_ms,
            end_ms=self.scan.end_ms,
            max_context_bars_by_timeframe=self.scan.max_context_bars_by_timeframe or {},
        )

    def to_risk_parameters(self) -> RiskParameters:
        return self.risk

    def to_execution_config(self) -> BacktestExecutionConfig:
        return BacktestExecutionConfig(
            initial_equity=self.execution.initial_equity,
            max_holding_bars=self.execution.max_holding_bars,
            fee_rate=self.costs.fee_rate,
            spread=self.costs.spread,
            slippage=self.costs.slippage,
            funding=self.costs.funding,
            conservative_same_bar=self.execution.conservative_same_bar,
            point_value=self.execution.point_value,
            enable_advanced_exits=self.execution.enable_advanced_exits,
            partial_take_profit_r=self.execution.partial_take_profit_r,
            partial_take_profit_pct=self.execution.partial_take_profit_pct,
            move_stop_to_true_breakeven=self.execution.move_stop_to_true_breakeven,
            breakeven_after_mfe_r=self.execution.breakeven_after_mfe_r,
            chandelier_period=self.execution.chandelier_period,
            chandelier_atr_multiple=self.execution.chandelier_atr_multiple,
            spread_slippage_rate=self.costs.spread_slippage_rate,
            reversal_time_cut_bars=self.execution.reversal_time_cut_bars,
            reversal_time_cut_min_mfe_r=self.execution.reversal_time_cut_min_mfe_r,
        )


def load_backtest_preset(path: str | Path, *, project_root: str | Path | None = None) -> BacktestPresetConfig:
    root = Path(project_root).resolve() if project_root is not None else PROJECT_ROOT
    preset_path = _resolve_path(path, root)
    preset_data = _read_toml(preset_path)
    include = _mapping(preset_data, "include")

    assets_data = _read_toml(_include_path(include, "assets", root))
    risk_data = _read_toml(_include_path(include, "risk", root))
    costs_data = _read_toml(_include_path(include, "costs", root))
    strategy_data = _read_toml(_include_path(include, "strategy", root))

    assets = _parse_assets(assets_data)
    risk = _parse_risk(risk_data)
    costs = _parse_costs(costs_data)
    execution = _parse_execution(_mapping(preset_data, "execution"))
    scan = _parse_scan(_mapping(preset_data, "scan"))
    strategy = _parse_strategy(strategy_data)
    ranking = _parse_ranking(_mapping(preset_data, "ranking"))

    normalized = {
        "config_version": _required_str(preset_data, "config_version"),
        "assets": asdict(assets),
        "risk": asdict(risk),
        "costs": asdict(costs),
        "execution": asdict(execution),
        "scan": asdict(scan),
        "strategy": asdict(strategy),
        "ranking": asdict(ranking),
    }
    return BacktestPresetConfig(
        config_version=normalized["config_version"],
        config_fingerprint=_fingerprint(normalized),
        assets=assets,
        risk=risk,
        costs=costs,
        execution=execution,
        scan=scan,
        strategy=strategy,
        ranking=ranking,
    )


def _parse_assets(data: Mapping[str, object]) -> AssetConfig:
    targets_raw = data.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ConfigError("assets.targets must be a non-empty list")
    targets = tuple(
        AssetTargetConfig(
            canonical_symbol=_required_str(row, "canonical_symbol").upper(),
            inst_id=_required_str(row, "inst_id").upper(),
            venue=_required_str(row, "venue").lower(),
            inst_type=_required_str(row, "inst_type").upper(),
        )
        for row in targets_raw
        if isinstance(row, Mapping)
    )
    if len(targets) != len(targets_raw):
        raise ConfigError("assets.targets must contain TOML tables")

    universe = _required_str(data, "universe")
    if universe == "btc_eth":
        symbols = {target.canonical_symbol for target in targets}
        if symbols != BTC_ETH_SYMBOLS:
            raise ConfigError("btc_eth preset must contain only BTC/USDT and ETH/USDT")

    return AssetConfig(
        universe=universe,
        primary_venue=_required_str(data, "primary_venue").lower(),
        validation_venues=_str_tuple(data.get("validation_venues", ()), "validation_venues"),
        targets=targets,
        contract_mode=str(data.get("contract_mode", "spot")),
        allow_short=bool(data.get("allow_short", False)),
    )


def _parse_risk(data: Mapping[str, object]) -> RiskParameters:
    risk = RiskParameters(
        risk_pct=_float(data, "risk_pct"),
        drawdown_level_1_pct=_float(data, "drawdown_level_1_pct"),
        drawdown_level_1_risk_pct=_float(data, "drawdown_level_1_risk_pct"),
        drawdown_level_2_pct=_float(data, "drawdown_level_2_pct"),
        drawdown_level_2_risk_pct=_float(data, "drawdown_level_2_risk_pct"),
        hard_drawdown_stop_pct=_float(data, "hard_drawdown_stop_pct"),
        daily_loss_limit_pct=_float(data, "daily_loss_limit_pct"),
        min_stop_atr_multiple=_float(data, "min_stop_atr_multiple"),
        max_stop_atr_multiple=_float(data, "max_stop_atr_multiple"),
        max_single_notional_pct=_float(data, "max_single_notional_pct"),
        max_total_gross_leverage=_float(data, "max_total_gross_leverage"),
        max_portfolio_heat_pct=_float(data, "max_portfolio_heat_pct"),
        min_liquidity_reversal_target_r=_float(data, "min_liquidity_reversal_target_r"),
    )
    _pct("risk_pct", risk.risk_pct)
    _pct("drawdown_level_1_pct", risk.drawdown_level_1_pct)
    _pct("drawdown_level_1_risk_pct", risk.drawdown_level_1_risk_pct)
    _pct("drawdown_level_2_pct", risk.drawdown_level_2_pct)
    _pct("drawdown_level_2_risk_pct", risk.drawdown_level_2_risk_pct)
    _pct("hard_drawdown_stop_pct", risk.hard_drawdown_stop_pct)
    _pct("daily_loss_limit_pct", risk.daily_loss_limit_pct)
    _pct("max_single_notional_pct", risk.max_single_notional_pct)
    _pct("max_portfolio_heat_pct", risk.max_portfolio_heat_pct)
    if not 0 < risk.min_stop_atr_multiple <= risk.max_stop_atr_multiple:
        raise ConfigError("min_stop_atr_multiple must be > 0 and <= max_stop_atr_multiple")
    if risk.max_total_gross_leverage <= 0:
        raise ConfigError("max_total_gross_leverage must be greater than 0")
    if risk.min_liquidity_reversal_target_r <= 0:
        raise ConfigError("min_liquidity_reversal_target_r must be greater than 0")
    return risk


def _parse_costs(data: Mapping[str, object]) -> CostConfig:
    tiers = _parse_cost_tiers(data.get("cost_model_tiers", {}))
    costs = CostConfig(
        name=_required_str(data, "name"),
        description=str(data.get("description", "")),
        fee_rate=_float(data, "fee_rate"),
        spread=_float(data, "spread"),
        slippage=_float(data, "slippage"),
        funding=_float(data, "funding"),
        spread_slippage_rate=_optional_float(data, "spread_slippage_rate", 0.0),
        funding_mode=str(data.get("funding_mode", "static_config_only")),
        cost_model_tiers=tiers,
    )
    _non_negative("fee_rate", costs.fee_rate)
    _non_negative("spread", costs.spread)
    _non_negative("slippage", costs.slippage)
    _non_negative("funding", costs.funding)
    _non_negative("spread_slippage_rate", costs.spread_slippage_rate)
    for tier in costs.cost_model_tiers:
        _non_negative(f"cost_model_tiers.{tier.name}.fee_rate", tier.fee_rate)
        _non_negative(f"cost_model_tiers.{tier.name}.spread_slippage_rate", tier.spread_slippage_rate)
    if costs.fee_rate > 0.05:
        raise ConfigError("fee_rate must be <= 0.05")
    return costs


def _parse_cost_tiers(value: object) -> tuple[CostTierConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ConfigError("cost_model_tiers must be a TOML table")
    tiers: list[CostTierConfig] = []
    for name in ("base", "stress", "harsh"):
        raw = value.get(name)
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            raise ConfigError(f"cost_model_tiers.{name} must be a TOML table")
        tiers.append(
            CostTierConfig(
                name=name,
                fee_rate=_float(raw, "fee_rate"),
                spread_slippage_rate=_float(raw, "spread_slippage_rate"),
            )
        )
    return tuple(tiers)


def _parse_execution(data: Mapping[str, object]) -> ExecutionConfig:
    execution = ExecutionConfig(
        initial_equity=_float(data, "initial_equity"),
        max_holding_bars=_int(data, "max_holding_bars"),
        conservative_same_bar=_bool(data, "conservative_same_bar"),
        point_value=_float(data, "point_value"),
        enable_advanced_exits=_bool(data, "enable_advanced_exits"),
        partial_take_profit_r=_float(data, "partial_take_profit_r"),
        partial_take_profit_pct=_float(data, "partial_take_profit_pct"),
        move_stop_to_true_breakeven=_bool(data, "move_stop_to_true_breakeven"),
        chandelier_period=_int(data, "chandelier_period"),
        chandelier_atr_multiple=_float(data, "chandelier_atr_multiple"),
        invalidation_mode=str(data.get("invalidation_mode", "atr_buffer")),
        invalidation_buffer_atr=_optional_float(data, "invalidation_buffer_atr", 1.0),
        invalidation_buffer_atr_candidates=_float_tuple(
            data.get("invalidation_buffer_atr_candidates", ()),
            "invalidation_buffer_atr_candidates",
        ),
        shadow_max_stop_atr_multiple_candidates=_float_tuple(
            data.get("shadow_max_stop_atr_multiple_candidates", ()),
            "shadow_max_stop_atr_multiple_candidates",
        ),
        reversal_time_cut_bars=_optional_int(data, "reversal_time_cut_bars", 0),
        reversal_time_cut_min_mfe_r=_optional_float(data, "reversal_time_cut_min_mfe_r", 0.0),
        reversal_time_cut_bars_candidates=_int_tuple(
            data.get("reversal_time_cut_bars_candidates", ()),
            "reversal_time_cut_bars_candidates",
        ),
        reversal_time_cut_min_mfe_r_candidates=_float_tuple(
            data.get("reversal_time_cut_min_mfe_r_candidates", ()),
            "reversal_time_cut_min_mfe_r_candidates",
        ),
        breakeven_after_mfe_r=_optional_float(data, "breakeven_after_mfe_r", 0.0),
    )
    if execution.initial_equity <= 0:
        raise ConfigError("initial_equity must be greater than 0")
    if execution.max_holding_bars <= 0:
        raise ConfigError("max_holding_bars must be greater than 0")
    if execution.point_value <= 0:
        raise ConfigError("point_value must be greater than 0")
    if execution.partial_take_profit_r <= 0:
        raise ConfigError("partial_take_profit_r must be greater than 0")
    if not 0 < execution.partial_take_profit_pct <= 1:
        raise ConfigError("partial_take_profit_pct must be > 0 and <= 1")
    if execution.chandelier_period <= 0:
        raise ConfigError("chandelier_period must be greater than 0")
    if execution.chandelier_atr_multiple <= 0:
        raise ConfigError("chandelier_atr_multiple must be greater than 0")
    return execution


def _parse_scan(data: Mapping[str, object]) -> ScanConfig:
    profiles = tuple(key.upper() for key in _str_tuple(data.get("profile_keys", ()), "profile_keys"))
    invalid = sorted(set(profiles) - ALLOWED_PROFILES)
    if invalid:
        raise ConfigError(f"profile keys must be A/B/C; invalid profile: {', '.join(invalid)}")
    return ScanConfig(profile_keys=profiles)


def _parse_strategy(data: Mapping[str, object]) -> StrategyConfig:
    strategy = StrategyConfig(
        name=_required_str(data, "name"),
        version=_required_str(data, "version"),
        enabled=_bool(data, "enabled"),
        enabled_setups=tuple(_str_tuple(data.get("enabled_setups", ()), "enabled_setups")),
        parameters=dict(data.get("parameters", {})) if isinstance(data.get("parameters", {}), Mapping) else {},
        parameter_grid=dict(data.get("parameter_grid", {})) if isinstance(data.get("parameter_grid", {}), Mapping) else {},
        profile_status={
            str(key).upper(): str(value)
            for key, value in dict(data.get("profile_status", {})).items()
        }
        if isinstance(data.get("profile_status", {}), Mapping)
        else {},
        volume=dict(data.get("volume", {})) if isinstance(data.get("volume", {}), Mapping) else {},
    )
    if strategy.name == "trend_price_volume" and strategy.version == "v1":
        invalid = sorted(set(strategy.enabled_setups) - TREND_PRICE_VOLUME_SETUPS)
        if invalid:
            raise ConfigError(f"strategy setup is not supported: {', '.join(invalid)}")
    if not strategy.enabled_setups:
        raise ConfigError("enabled_setups must not be empty")
    return strategy


def _parse_ranking(data: Mapping[str, object]) -> RankingConfig:
    ranking = RankingConfig(
        fast_profile_fee_reject_threshold=_float(data, "fast_profile_fee_reject_threshold"),
        min_trades_for_primary=_int(data, "min_trades_for_primary"),
    )
    _pct("fast_profile_fee_reject_threshold", ranking.fast_profile_fee_reject_threshold)
    if ranking.min_trades_for_primary <= 0:
        raise ConfigError("min_trades_for_primary must be greater than 0")
    return ranking


def _resolve_path(path: str | Path, project_root: Path) -> Path:
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
    if not resolved.is_relative_to(project_root):
        raise ConfigError(f"config path must stay inside project root: {path}")
    return resolved


def _include_path(include: Mapping[str, object], key: str, project_root: Path) -> Path:
    raw = include.get(key)
    if not isinstance(raw, str) or not raw:
        raise ConfigError(f"include.{key} must be a relative path")
    if Path(raw).is_absolute():
        raise ConfigError(f"include.{key} must be relative to project root")
    return _resolve_path(raw, project_root)


def _read_toml(path: Path) -> Mapping[str, object]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as error:
        raise ConfigError(f"config file not found: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"invalid TOML in {path}: {error}") from error


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ConfigError(f"{key} must be a TOML table")
    return value


def _required_str(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _str_tuple(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return tuple(value)


def _float(source: Mapping[str, object], key: str) -> float:
    value = source.get(key)
    if not isinstance(value, int | float):
        raise ConfigError(f"{key} must be a number")
    return float(value)


def _int(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def _optional_float(source: Mapping[str, object], key: str, default: float) -> float:
    if key not in source:
        return default
    return _float(source, key)


def _optional_int(source: Mapping[str, object], key: str, default: int) -> int:
    if key not in source:
        return default
    return _int(source, key)


def _float_tuple(value: object, key: str) -> tuple[float, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list | tuple) or not all(isinstance(item, int | float) and not isinstance(item, bool) for item in value):
        raise ConfigError(f"{key} must be a list of numbers")
    return tuple(float(item) for item in value)


def _int_tuple(value: object, key: str) -> tuple[int, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list | tuple) or not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise ConfigError(f"{key} must be a list of integers")
    return tuple(value)


def _bool(source: Mapping[str, object], key: str) -> bool:
    value = source.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def _pct(key: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ConfigError(f"{key} must be between 0 and 1")


def _non_negative(key: str, value: float) -> None:
    if value < 0:
        raise ConfigError(f"{key} must be non-negative")


def _fingerprint(value: Mapping[str, object]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
