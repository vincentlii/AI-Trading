from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from trading_system.backtest.contract_risk import estimate_contract_risk
from trading_system.backtest.execution import BacktestExecutionEngine, BacktestSignalInput
from trading_system.backtest.risk import AccountState, CostEstimate, OrderIntent, RiskEngine
from trading_system.backtest.scanner import BacktestScanTarget
from trading_system.config.loader import BacktestPresetConfig
from trading_system.data.universe import timeframe_to_okx_bar
from trading_system.strategies.base import StrategySignal
from trading_system.timeframe_profiles import get_profile


@dataclass(frozen=True)
class MinimalLRFilterResult:
    filter_rows: tuple[dict[str, object], ...]
    funnel_rows: tuple[dict[str, object], ...]
    tag_rows: tuple[dict[str, object], ...]
    report: str


def replay_minimal_lr_v0(*, candidates: Sequence[Mapping[str, object]], preset: BacktestPresetConfig) -> MinimalLRFilterResult:
    filter_rows = tuple(_filter_candidate(candidate, preset) for candidate in candidates)
    funnel_rows = _funnel_rows(filter_rows)
    tag_rows = _tag_rows(filter_rows)
    report = build_minimal_lr_v0_report(filter_rows=filter_rows, funnel_rows=funnel_rows, tag_rows=tag_rows)
    return MinimalLRFilterResult(filter_rows=filter_rows, funnel_rows=funnel_rows, tag_rows=tag_rows, report=report)


def write_minimal_lr_v0_artifacts(output_dir: str | Path, result: MinimalLRFilterResult) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "filter_jsonl": output / "minimal_lr_v0_filter_results.jsonl",
        "funnel_csv": output / "minimal_lr_v0_funnel.csv",
        "tags_csv": output / "minimal_lr_v0_tags.csv",
        "report_md": output / "minimal_lr_v0_report.md",
    }
    _write_jsonl(paths["filter_jsonl"], result.filter_rows)
    _write_csv(paths["funnel_csv"], result.funnel_rows)
    _write_csv(paths["tags_csv"], result.tag_rows)
    paths["report_md"].write_text(result.report, encoding="utf-8")
    return paths


def run_minimal_execution_replay(*, repository, filter_rows: Sequence[Mapping[str, object]], preset: BacktestPresetConfig) -> tuple[dict[str, object], ...]:
    approved = tuple(row for row in filter_rows if row.get("formal_approved"))
    engine = BacktestExecutionEngine(risk_engine=RiskEngine(preset.to_risk_parameters()), config=preset.to_execution_config())
    rows: list[dict[str, object]] = []
    for row in approved:
        signal_input = _execution_input(repository=repository, row=row, preset=preset)
        if signal_input is None:
            continue
        result = engine.run((signal_input,))
        for fill in result.fills:
            rows.append(
                {
                    "row_type": "closed_trade",
                    "candidate_id": row.get("candidate_id"),
                    "event_id": row.get("event_id"),
                    "trade_id": fill.trade_id,
                    "execution_id": fill.execution_id,
                    "asset": row.get("asset"),
                    "profile": row.get("profile"),
                    "direction": row.get("direction"),
                    "structure_level_source": row.get("structure_level_source"),
                    "structure_confirmed_time": row.get("structure_confirmed_time") or row.get("structure_time"),
                    "feature_cutoff_time": row.get("signal_time"),
                    "sweep_time": row.get("sweep_time"),
                    "reclaim_time": row.get("reclaim_time"),
                    "signal_time": row.get("signal_time"),
                    "entry_time": fill.entry_timestamp_ms,
                    "exit_time": fill.exit_timestamp_ms,
                    "bar_confirmed": True,
                    "no_lookahead_safe": signal_input.no_lookahead_safe,
                    "closed_trade": True,
                    "eligible_for_performance": True,
                    "eligible_for_robustness": True,
                    "mae_R": fill.mae_r,
                    "MAE_R": fill.mae_r,
                    "mfe_R": fill.mfe_r,
                    "MFE_R": fill.mfe_r,
                    "bars_to_MAE": fill.bars_to_mae,
                    "bars_to_MFE": fill.bars_to_mfe,
                    "exit_reason": fill.exit_reason,
                    "holding_bars": fill.holding_bars,
                    "same_bar_ambiguous": fill.same_bar_ambiguous,
                    "forced_pessimistic_exit": fill.forced_pessimistic_exit,
                    "liquidation_event": False,
                    "funding_paid_or_received": fill.cost_estimate.funding,
                    "fee_cost": fill.cost_estimate.fees,
                    "slippage_cost": fill.cost_estimate.spread + fill.cost_estimate.expected_slippage,
                    "funding_cost": fill.cost_estimate.funding,
                    "net_R": fill.r_multiple,
                    "cost_adjusted_R": fill.r_multiple,
                }
            )
    return tuple(rows)


def write_execution_rows(path: str | Path, rows: Sequence[Mapping[str, object]]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output, rows)
    return output


def read_candidates(path: str | Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return tuple(rows)


def build_minimal_lr_v0_report(
    *,
    filter_rows: Sequence[Mapping[str, object]],
    funnel_rows: Sequence[Mapping[str, object]],
    tag_rows: Sequence[Mapping[str, object]],
) -> str:
    reasons = Counter(str(row.get("reject_reason", "")) for row in filter_rows if row.get("reject_reason"))
    stop_values = [float(row["stop_atr"]) for row in filter_rows if row.get("stop_atr") is not None]
    target_values = [float(row["target_r"]) for row in filter_rows if row.get("target_r") is not None]
    approved = sum(1 for row in filter_rows if row.get("formal_approved"))
    shadow_5 = sum(1 for row in filter_rows if row.get("shadow_approved_5"))
    shadow_8 = sum(1 for row in filter_rows if row.get("shadow_approved_8"))
    top_groups = sorted(tag_rows, key=lambda row: (float(row.get("approval_rate") or 0.0), int(row.get("formal_approved") or 0)), reverse=True)[:8]
    return "\n".join(
        (
            "# Stage 5 Minimal LR v0 Filter Replay Report",
            "",
            f"- fresh_candidates={len(filter_rows)}",
            f"- formal_approved={approved}",
            f"- shadow_approved_5={shadow_5}",
            f"- shadow_approved_8={shadow_8}",
            f"- reject_reason_top={dict(reasons.most_common(10))}",
            f"- stop_atr_p50={_percentile(stop_values, 0.50)} stop_atr_p90={_percentile(stop_values, 0.90)}",
            f"- target_r_p50={_percentile(target_values, 0.50)} target_r_p90={_percentile(target_values, 0.90)}",
            "",
            "## Best Diagnostic Tags",
            *(
                f"- {row['tag_type']}={row['tag_value']}: fresh={row['fresh_candidates']} approved={row['formal_approved']} rate={row['approval_rate']}"
                for row in top_groups
            ),
            "",
            "## Funnel",
            *(
                f"- {row['asset']} {row['profile']} {row['direction']} {row['structure_level_source']}: "
                f"fresh={row['fresh_candidates']} approved={row['formal_approved']} top_reject={row['top_reject_reason']}"
                for row in funnel_rows
            ),
        )
    ) + "\n"


def _filter_candidate(candidate: Mapping[str, object], preset: BacktestPresetConfig) -> dict[str, object]:
    entry = _required_float(candidate, "entry_price")
    stop = _required_float(candidate, "stop_price")
    target = _required_float(candidate, "target_price")
    atr = _candidate_atr(candidate)
    direction = str(candidate.get("direction", "")).lower()
    stop_distance = abs(entry - stop)
    target_r = 0.0 if stop_distance <= 0 else abs(target - entry) / stop_distance
    estimated_cost_r = _estimated_cost_r(entry=entry, stop=stop, target=target, preset=preset)
    reject_stage = ""
    reject_reason = ""

    if direction not in {"long", "short"}:
        reject_stage, reject_reason = "direction_filter", "invalid_direction"
    elif stop_distance <= 0 or atr <= 0:
        reject_stage, reject_reason = "risk_filter", "missing_stop"
    elif target <= 0:
        reject_stage, reject_reason = "risk_filter", "missing_target"
    elif target_r < preset.risk.min_liquidity_reversal_target_r:
        reject_stage, reject_reason = "target_r_filter", "target_r_too_low"

    intent = OrderIntent(
        strategy_name=preset.strategy.name,
        strategy_version=preset.strategy.version,
        setup_type="liquidity_reversal",
        symbol=str(candidate.get("symbol", "")),
        venue=str(candidate.get("venue", "")),
        direction="LONG" if direction == "long" else "SHORT",
        entry_price=entry,
        stop_loss=stop,
        target_price=target,
        point_value=preset.execution.point_value,
    )
    risk_decision = RiskEngine(preset.to_risk_parameters()).evaluate(
        intent,
        AccountState(
            equity=preset.execution.initial_equity,
            high_water_mark=preset.execution.initial_equity,
            current_drawdown_pct=0.0,
            daily_pnl=0.0,
            open_positions=(),
        ),
        atr=atr,
        cost_estimate=CostEstimate(),
    )
    if not reject_reason and risk_decision.approved_order is None:
        reject_stage = "risk_filter"
        reject_reason = _risk_reason(risk_decision.reason_codes)

    contract = None
    diagnostic_quantity = 0.0 if stop_distance <= 0 else risk_decision.risk_amount / (stop_distance * preset.execution.point_value)
    if diagnostic_quantity > 0:
        contract = estimate_contract_risk(
            intent=intent,
            quantity=diagnostic_quantity,
            risk_amount=risk_decision.risk_amount,
            preset=preset,
        )
        if not reject_reason and risk_decision.approved_order is not None and contract.reject_reason:
            reject_stage = "contract_risk_filter"
            reject_reason = contract.reject_reason

    if not reject_reason and target_r - estimated_cost_r <= 0:
        reject_stage = "cost_after_r_filter"
        reject_reason = "cost_after_r_too_low"

    formal_approved = not reject_reason and risk_decision.approved_order is not None
    stop_atr = stop_distance / atr if atr > 0 else None
    risk_pct = risk_decision.risk_pct
    risk_amount = risk_decision.risk_amount
    raw_position_qty = 0.0 if stop_distance <= 0 else risk_amount / (stop_distance * preset.execution.point_value)
    raw_position_notional = abs(raw_position_qty * entry * preset.execution.point_value)
    max_single_notional = preset.execution.initial_equity * preset.risk.max_single_notional_pct
    capped_notional = min(raw_position_notional, max_single_notional)
    capped_qty = 0.0 if entry <= 0 or preset.execution.point_value <= 0 else capped_notional / (entry * preset.execution.point_value)
    capped_risk_amount = capped_qty * stop_distance * preset.execution.point_value
    capped_risk_pct = 0.0 if preset.execution.initial_equity <= 0 else capped_risk_amount / preset.execution.initial_equity
    row = dict(candidate)
    signal_time = _optional_int(candidate.get("signal_time"))
    entry_time_value = _optional_int(candidate.get("entry_time"))
    row.update(
        {
            "row_type": "formal_approved" if formal_approved else "rejected_candidate",
            "candidate_id": str(candidate.get("event_id") or candidate.get("candidate_id") or ""),
            "event_id": str(candidate.get("event_id") or candidate.get("candidate_id") or ""),
            "setup": "liquidity_reversal",
            "feature_cutoff_time": signal_time,
            "structure_confirmed_time": candidate.get("structure_confirmed_time") or candidate.get("structure_time"),
            "bar_confirmed": True,
            "no_lookahead_safe": _no_lookahead_safe(candidate, signal_time=signal_time, entry_time=entry_time_value or 0),
            "direction_pass": direction in {"long", "short"},
            "target_r_pass": target_r >= preset.risk.min_liquidity_reversal_target_r,
            "risk_pass": risk_decision.approved_order is not None,
            "contract_risk_pass": contract is None or not contract.reject_reason,
            "cost_after_r_pass": target_r - estimated_cost_r > 0,
            "formal_approved": formal_approved,
            "approved": formal_approved,
            "shadow_approved_5": _shadow_allowed(stop_atr, preset.risk.min_stop_atr_multiple, 5.0),
            "shadow_approved_8": _shadow_allowed(stop_atr, preset.risk.min_stop_atr_multiple, 8.0),
            "reject_stage": "" if formal_approved else reject_stage or "filter_replay",
            "reject_reason": "" if formal_approved else reject_reason or "filtered_without_reason",
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "stop_distance_abs": stop_distance,
            "stop_distance_pct": 0.0 if entry <= 0 else stop_distance / entry,
            "stop_atr": stop_atr,
            "target_r": target_r,
            "target_source": str(candidate.get("target_source", "fixed_2r")),
            "target_distance_abs": abs(target - entry),
            "target_distance_atr_entry_tf": abs(target - entry) / atr if atr > 0 else None,
            "estimated_cost_r": estimated_cost_r,
            "cost_after_r": target_r - estimated_cost_r,
            "risk_pct": risk_pct,
            "risk_amount": risk_amount,
            "raw_position_qty_by_risk": raw_position_qty,
            "raw_position_notional_by_risk": raw_position_notional,
            "max_single_notional": max_single_notional,
            "max_single_notional_pct": preset.risk.max_single_notional_pct,
            "capped_position_qty": capped_qty,
            "capped_position_notional": capped_notional,
            "capped_actual_risk_amount": capped_risk_amount,
            "capped_actual_risk_pct": capped_risk_pct,
            "margin_required_pct": None if contract is None or preset.execution.initial_equity <= 0 else contract.margin_required / preset.execution.initial_equity,
            "notional_to_equity_pct": None if contract is None or preset.execution.initial_equity <= 0 else contract.notional / preset.execution.initial_equity,
            "margin_reject_reason": reject_reason if reject_reason in {"margin_required_too_high", "stop_distance_too_near"} else "",
            "wick_ratio_tier": _wick_tier(_optional_float(candidate.get("wick_ratio"))),
            "sweep_rvol_tier": _sweep_rvol_tier(_optional_float(candidate.get("sweep_rvol"))),
            "reclaim_rvol_tier": _reclaim_rvol_tier(_optional_float(candidate.get("reclaim_rvol"))),
            "choch_tag": "choch_true" if bool(candidate.get("choch_detected")) else "choch_false",
            "trend_alignment_tag": _trend_tag(candidate),
            "liquidity_score_tier": _score_tier(_optional_float(candidate.get("liquidity_score"))),
            "notional": None if contract is None else contract.notional,
            "leverage": None if contract is None else contract.leverage,
            "margin_required": None if contract is None else contract.margin_required,
            "liquidation_price": None if contract is None else contract.liquidation_price,
            "liquidation_distance_pct": None if contract is None else contract.liquidation_distance_pct,
            "funding_rate": preset.costs.funding if contract is None else contract.funding_rate,
            "estimated_funding_cost": None if contract is None else contract.funding_paid_or_received,
            "gross_exposure": None if contract is None else contract.gross_exposure,
            "portfolio_heat": risk_decision.risk_amount / preset.execution.initial_equity if preset.execution.initial_equity > 0 else None,
        }
    )
    return row


def _funnel_rows(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row.get("asset", "")),
                str(row.get("profile", "")),
                str(row.get("direction", "")),
                str(row.get("structure_level_source", "")),
            )
        ].append(row)
    output: list[dict[str, object]] = []
    for key, group in sorted(grouped.items()):
        reasons = Counter(str(row.get("reject_reason", "")) for row in group if row.get("reject_reason"))
        output.append(
            {
                "asset": key[0],
                "profile": key[1],
                "direction": key[2],
                "structure_level_source": key[3],
                "fresh_candidates": len(group),
                "direction_pass": sum(1 for row in group if row.get("direction_pass")),
                "target_r_pass": sum(1 for row in group if row.get("target_r_pass")),
                "risk_pass": sum(1 for row in group if row.get("risk_pass")),
                "contract_risk_pass": sum(1 for row in group if row.get("contract_risk_pass")),
                "cost_after_r_pass": sum(1 for row in group if row.get("cost_after_r_pass")),
                "formal_approved": sum(1 for row in group if row.get("formal_approved")),
                "shadow_approved_5": sum(1 for row in group if row.get("shadow_approved_5")),
                "shadow_approved_8": sum(1 for row in group if row.get("shadow_approved_8")),
                "top_reject_reason": reasons.most_common(1)[0][0] if reasons else "",
                "target_r_too_low": reasons["target_r_too_low"],
                "stop_distance_too_far": reasons["stop_distance_too_far"],
                "cost_after_r_too_low": reasons["cost_after_r_too_low"],
                "margin_required_too_high": reasons["margin_required_too_high"],
                "liquidation_distance_too_close": reasons["liquidation_distance_too_close"],
                "portfolio_heat_exceeded": reasons["portfolio_heat_exceeded"],
                "funding_cost_too_high": reasons["funding_cost_too_high"],
                "invalid_direction": reasons["invalid_direction"],
                "missing_stop": reasons["missing_stop"],
                "missing_target": reasons["missing_target"],
            }
        )
    return tuple(output)


def _tag_rows(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    specs = (
        ("wick_ratio", "wick_ratio_tier"),
        ("sweep_rvol", "sweep_rvol_tier"),
        ("reclaim_rvol", "reclaim_rvol_tier"),
        ("choch", "choch_tag"),
        ("trend_alignment", "trend_alignment_tag"),
        ("structure_source", "structure_level_source"),
        ("liquidity_score", "liquidity_score_tier"),
        ("direction", "direction"),
        ("asset_profile", "asset_profile_tag"),
    )
    augmented = []
    for row in rows:
        copy = dict(row)
        copy["asset_profile_tag"] = f"{row.get('asset', '')} {row.get('profile', '')}".strip()
        augmented.append(copy)

    output: list[dict[str, object]] = []
    for tag_type, field in specs:
        grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in augmented:
            grouped[str(row.get(field, "unknown"))].append(row)
        for value, group in sorted(grouped.items()):
            reasons = Counter(str(row.get("reject_reason", "")) for row in group if row.get("reject_reason"))
            output.append(
                {
                    "tag_type": tag_type,
                    "tag_value": value,
                    "fresh_candidates": len(group),
                    "formal_approved": sum(1 for row in group if row.get("formal_approved")),
                    "approval_rate": _rate(sum(1 for row in group if row.get("formal_approved")), len(group)),
                    "stop_atr_p50": _percentile([float(row["stop_atr"]) for row in group if row.get("stop_atr") is not None], 0.50),
                    "stop_atr_p90": _percentile([float(row["stop_atr"]) for row in group if row.get("stop_atr") is not None], 0.90),
                    "target_r_p50": _percentile([float(row["target_r"]) for row in group if row.get("target_r") is not None], 0.50),
                    "target_r_p90": _percentile([float(row["target_r"]) for row in group if row.get("target_r") is not None], 0.90),
                    "cost_after_r_p50": _percentile([float(row["cost_after_r"]) for row in group if row.get("cost_after_r") is not None], 0.50),
                    "cost_after_r_p90": _percentile([float(row["cost_after_r"]) for row in group if row.get("cost_after_r") is not None], 0.90),
                    "main_reject_reason": reasons.most_common(1)[0][0] if reasons else "",
                }
            )
    return tuple(output)


def _execution_input(*, repository, row: Mapping[str, object], preset: BacktestPresetConfig) -> BacktestSignalInput | None:
    profile = get_profile(str(row["profile"]))
    target = BacktestScanTarget(
        canonical_symbol=str(row["symbol"]),
        inst_id=str(row["inst_id"]),
        venue=str(row["venue"]),
        inst_type=str(row["inst_type"]),
    )
    candles = _load_timeframe(repository, target, profile.entry_timeframe)
    entry_time = int(row["entry_time"])
    execution_candles = tuple(candle for candle in candles if int(getattr(candle, "timestamp_ms")) >= entry_time)[: preset.execution.max_holding_bars]
    if not execution_candles:
        return None
    stop_atr = _optional_float(row.get("stop_atr"))
    stop_distance = abs(float(row["entry_price"]) - float(row["stop_price"]))
    atr = stop_distance / stop_atr if stop_atr and stop_atr > 0 else stop_distance
    signal = StrategySignal(
        strategy_name=preset.strategy.name,
        strategy_version=preset.strategy.version,
        setup_type="liquidity_reversal",
        symbol=str(row["symbol"]),
        venue=str(row["venue"]),
        timeframe_group=str(row["profile"]),
        direction=str(row["direction"]),
        entry_zone={"low": float(row["entry_price"]), "high": float(row["entry_price"]), "reference_price": float(row["entry_price"])},
        invalidation_level=float(row["stop_price"]),
        target_hint={"target_price": float(row["target_price"]), "reward_to_risk": float(row["target_r"])},
        trend_evidence={"atr": atr},
        price_action_evidence=dict(row),
        volume_price_evidence=dict(row),
        risk_profile={},
        explanation_payload={
            "strategy_family": "liquidity_sweep_reclaim",
            "candidate_id": row.get("candidate_id"),
            "event_id": row.get("event_id"),
        },
    )
    signal_time = _optional_int(row.get("signal_time"))
    return BacktestSignalInput(
        signal=signal,
        execution_candles=execution_candles,
        candidate_id=str(row.get("candidate_id") or ""),
        event_id=str(row.get("event_id") or ""),
        feature_cutoff_time=signal_time,
        structure_confirmed_time=_optional_int(row.get("structure_confirmed_time") or row.get("structure_time")),
        sweep_time=_optional_int(row.get("sweep_time")),
        reclaim_time=_optional_int(row.get("reclaim_time")),
        signal_time=signal_time,
        bar_confirmed=True,
        no_lookahead_safe=_no_lookahead_safe(row, signal_time=signal_time, entry_time=entry_time),
    )


def _load_timeframe(repository, target: BacktestScanTarget, timeframe: str) -> tuple[object, ...]:
    bar = timeframe_to_okx_bar(timeframe)
    if hasattr(repository, "load_range"):
        candles = repository.load_range(target.inst_id, bar, 0, 9_223_372_036_854_775_807, venue=target.venue, inst_type=target.inst_type, confirmed_only=True)
    else:
        candles = repository.list_candles(target.inst_id, bar, venue=target.venue, inst_type=target.inst_type)
    return tuple(candle for candle in candles if bool(getattr(candle, "is_confirmed", False)))


def _candidate_atr(candidate: Mapping[str, object]) -> float:
    stop_atr = _optional_float(candidate.get("stop_atr_entry_tf")) or _optional_float(candidate.get("stop_atr_structure_tf"))
    entry = _required_float(candidate, "entry_price")
    stop = _required_float(candidate, "stop_price")
    if stop_atr and stop_atr > 0:
        return abs(entry - stop) / stop_atr
    return abs(entry - stop)


def _estimated_cost_r(*, entry: float, stop: float, target: float, preset: BacktestPresetConfig) -> float:
    risk_amount = preset.execution.initial_equity * preset.risk.risk_pct
    stop_distance = abs(entry - stop)
    if risk_amount <= 0 or stop_distance <= 0:
        return 0.0
    quantity = risk_amount / (stop_distance * preset.execution.point_value)
    point_quantity = quantity * preset.execution.point_value
    cost = (
        (abs(entry * point_quantity) + abs(target * point_quantity)) * preset.costs.fee_rate
        + abs(preset.costs.spread * point_quantity)
        + abs(preset.costs.slippage * point_quantity * 2.0)
        + abs(preset.costs.funding * point_quantity)
        + (abs(entry * point_quantity) + abs(target * point_quantity)) * preset.costs.spread_slippage_rate
    )
    return cost / risk_amount


def _risk_reason(reason_codes: Sequence[str]) -> str:
    mapping = {
        "target_reward_below_minimum": "target_r_too_low",
        "notional_cap_exceeded": "margin_required_too_high",
        "total_gross_leverage_exceeded": "margin_required_too_high",
        "stop_distance_too_far": "stop_distance_too_far",
        "stop_distance_too_near": "stop_distance_too_near",
        "portfolio_heat_exceeded": "portfolio_heat_exceeded",
    }
    if not reason_codes:
        return "risk_rejected"
    return mapping.get(str(reason_codes[0]), str(reason_codes[0]))


def _wick_tier(value: float | None) -> str:
    if value is None:
        return "unknown_wick"
    if value < 0.25:
        return "low_wick"
    if value < 0.50:
        return "medium_wick"
    return "high_wick"


def _sweep_rvol_tier(value: float | None) -> str:
    if value is None:
        return "unknown_sweep_rvol"
    if value < 1.5:
        return "low_sweep_rvol"
    if value < 2.5:
        return "normal_sweep_rvol"
    return "high_sweep_rvol"


def _reclaim_rvol_tier(value: float | None) -> str:
    if value is None:
        return "unknown_reclaim"
    if value <= 1.2:
        return "ideal_reclaim"
    if value <= 1.6:
        return "acceptable_reclaim"
    return "high_reclaim_rvol"


def _trend_tag(candidate: Mapping[str, object]) -> str:
    if bool(candidate.get("trend_aligned")):
        return "trend_aligned"
    if bool(candidate.get("countertrend")):
        return "countertrend"
    if bool(candidate.get("neutral_trend")):
        return "neutral"
    raw = str(candidate.get("trend_aligned", "")).lower()
    if raw in {"true", "1", "aligned", "trend_aligned"}:
        return "trend_aligned"
    if raw in {"false", "0", "countertrend"}:
        return "countertrend"
    return "neutral"


def _score_tier(value: float | None) -> str:
    if value is None:
        return "unknown_score"
    if value < 1.0:
        return "low_score"
    if value < 3.0:
        return "medium_score"
    return "high_score"


def _shadow_allowed(stop_atr: float | None, min_stop: float, max_stop: float) -> bool:
    return stop_atr is not None and min_stop <= stop_atr <= max_stop


def _required_float(row: Mapping[str, object], key: str) -> float:
    value = _optional_float(row.get(key))
    if value is None:
        raise ValueError(f"missing numeric field: {key}")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _no_lookahead_safe(row: Mapping[str, object], *, signal_time: int | None, entry_time: int) -> bool:
    structure_time = _optional_int(row.get("structure_confirmed_time") or row.get("structure_time"))
    sweep_time = _optional_int(row.get("sweep_time"))
    reclaim_time = _optional_int(row.get("reclaim_time"))
    checks = (
        (signal_time, entry_time, "<"),
        (structure_time, sweep_time, "<="),
        (sweep_time, reclaim_time, "<="),
        (reclaim_time, signal_time, "<="),
    )
    for left, right, operator in checks:
        if left is None or right is None:
            return False
        if operator == "<" and not left < right:
            return False
        if operator == "<=" and not left <= right:
            return False
    return True


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def _percentile(values: Sequence[float], q: float) -> float | None:
    numbers = sorted(float(value) for value in values)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * q
    low = int(position)
    high = min(low + 1, len(numbers) - 1)
    fraction = position - low
    return numbers[low] * (1.0 - fraction) + numbers[high] * fraction


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text("".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


__all__ = (
    "MinimalLRFilterResult",
    "build_minimal_lr_v0_report",
    "read_candidates",
    "replay_minimal_lr_v0",
    "run_minimal_execution_replay",
    "write_execution_rows",
    "write_minimal_lr_v0_artifacts",
)
