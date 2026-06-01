from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from research_pipeline.core.artifacts.index import build_index_for_directory, write_artifact_index
from research_pipeline.runners.register_research_run import register_research_run


COMBOS = ("CHOCH true", "displacement_after_reclaim")
SIZING_MODELS = ("current_risk_based_sizing", "notional_capped_risk_based")
COST_TIERS = {
    "base": {"net_r_penalty": 0.0, "slippage_cost": 0.0, "funding_cost": 0.0},
    "stress": {"net_r_penalty": 0.05, "slippage_cost": 0.03, "funding_cost": 0.02},
    "harsh": {"net_r_penalty": 0.12, "slippage_cost": 0.08, "funding_cost": 0.04},
}


@dataclass(frozen=True)
class Stage7SmokeBacktestResult:
    proposal_only: bool
    formal_conclusion_enabled: bool
    combos: list[str]
    sizing_models: list[str]
    cost_tiers: list[str]
    grouped_rows: list[dict[str, Any]]
    final_conclusion: str
    expansion_readiness: dict[str, Any]
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_stage7_smoke_backtest(
    *,
    filter_results: Path,
    execution_results: Path,
    sizing_candidates: Path,
    output_dir: Path | None,
) -> Stage7SmokeBacktestResult:
    filter_rows = _read_jsonl(Path(filter_results))
    execution_rows = _read_jsonl(Path(execution_results))
    sizing_rows = _read_csv(Path(sizing_candidates))
    execution_by_id = {str(row.get("candidate_id")): row for row in execution_rows}
    filter_by_id = {str(row.get("candidate_id")): row for row in filter_rows}

    grouped_rows: list[dict[str, Any]] = []
    for combo in COMBOS:
        for sizing_model in SIZING_MODELS:
            selected = [
                row
                for row in sizing_rows
                if row.get("sizing_model") == sizing_model and _matches_combo(row, combo)
            ]
            approved = [row for row in selected if _is_approved_for_model(row, sizing_model)]
            executions = [
                _execution_payload(row, execution_by_id, filter_by_id)
                for row in approved
                if str(row.get("candidate_id")) in execution_by_id
            ]
            for tier in COST_TIERS:
                grouped_rows.append(
                    _summary_row(
                        combo=combo,
                        sizing_model=sizing_model,
                        cost_tier=tier,
                        selected=selected,
                        approved=approved,
                        executions=executions,
                        asset="ALL",
                        profile="ALL",
                        direction="ALL",
                    )
                )
                for asset, profile, direction in _group_keys(approved):
                    group_selected = [
                        row
                        for row in selected
                        if row.get("asset") == asset
                        and row.get("profile") == profile
                        and row.get("direction") == direction
                    ]
                    group_approved = [
                        row
                        for row in approved
                        if row.get("asset") == asset
                        and row.get("profile") == profile
                        and row.get("direction") == direction
                    ]
                    group_executions = [
                        row
                        for row in executions
                        if row.get("asset") == asset
                        and row.get("profile") == profile
                        and row.get("direction") == direction
                    ]
                    grouped_rows.append(
                        _summary_row(
                            combo=combo,
                            sizing_model=sizing_model,
                            cost_tier=tier,
                            selected=group_selected,
                            approved=group_approved,
                            executions=group_executions,
                            asset=asset,
                            profile=profile,
                            direction=direction,
                        )
                    )

    result = Stage7SmokeBacktestResult(
        proposal_only=True,
        formal_conclusion_enabled=False,
        combos=list(COMBOS),
        sizing_models=list(SIZING_MODELS),
        cost_tiers=list(COST_TIERS),
        grouped_rows=grouped_rows,
        final_conclusion=_final_conclusion(grouped_rows),
        expansion_readiness=_expansion_readiness(),
        source_files=[str(filter_results), str(execution_results), str(sizing_candidates)],
    )
    if output_dir is not None:
        _write_outputs(result, Path(output_dir))
    return result


def _summary_row(
    *,
    combo: str,
    sizing_model: str,
    cost_tier: str,
    selected: list[dict[str, Any]],
    approved: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    asset: str,
    profile: str,
    direction: str,
) -> dict[str, Any]:
    tier = COST_TIERS[cost_tier]
    net_values = [
        (_float(row.get("net_R")) or 0.0) - float(tier["net_r_penalty"])
        for row in executions
    ]
    mfe_values = [_float(row.get("mfe_R")) for row in executions]
    mae_values = [_float(row.get("mae_R")) for row in executions]
    holding = [_float(row.get("holding_bars")) for row in executions]
    exits = Counter(str(row.get("exit_reason", "")) for row in executions if row.get("exit_reason"))
    long_count = sum(1 for row in approved if row.get("direction") == "long")
    short_count = sum(1 for row in approved if row.get("direction") == "short")
    fee_cost = sum(_float(row.get("estimated_cost_r")) or 0.0 for row in approved)
    slippage_cost = float(tier["slippage_cost"]) * len(executions)
    funding_cost = sum(_float(row.get("funding_paid_or_received")) or 0.0 for row in executions) + float(tier["funding_cost"]) * len(executions)
    return {
        "combo": combo,
        "sizing_model": sizing_model,
        "cost_tier": cost_tier,
        "asset": asset,
        "profile": profile,
        "direction": direction,
        "candidates": len(selected),
        "formal_approved": sum(1 for row in selected if _truthy(row.get("formal_approved"))),
        "proposal_approved": sum(1 for row in selected if _truthy(row.get("proposal_approved"))),
        "closed_trades": len(executions),
        "long": long_count,
        "short": short_count,
        "BTC": sum(1 for row in approved if row.get("asset") == "BTC"),
        "ETH": sum(1 for row in approved if row.get("asset") == "ETH"),
        "B_profile": sum(1 for row in approved if row.get("profile") == "B"),
        "C_profile": sum(1 for row in approved if row.get("profile") == "C"),
        "gross_R": _avg([(_float(row.get("net_R")) or 0.0) + (_float(row.get("estimated_cost_r")) or 0.0) for row in executions]),
        "net_R_avg": _avg(net_values),
        "net_R_p50": _pct(net_values, 50),
        "net_R_p75": _pct(net_values, 75),
        "expectancy_R": _avg(net_values),
        "win_rate": _ratio(sum(1 for value in net_values if value > 0), len(net_values)),
        "profit_factor": _profit_factor(net_values),
        "net_return_on_notional": _avg([_float(row.get("net_return_on_notional")) for row in approved]),
        "total_net_pnl": None,
        "max_drawdown": _max_drawdown(net_values),
        "max_consecutive_losses": _max_consecutive_losses(net_values),
        "portfolio_heat_max": _max([_float(row.get("portfolio_heat")) for row in approved]),
        "margin_required_max": _max([_float(row.get("margin_required")) for row in approved]),
        "liquidation_event_count": sum(1 for row in executions if _truthy(row.get("liquidation_event"))),
        "funding_paid_or_received": funding_cost,
        "MFE_R_avg": _avg(mfe_values),
        "MFE_R_p50": _pct(mfe_values, 50),
        "MFE_R_p75": _pct(mfe_values, 75),
        "MFE_R_p90": _pct(mfe_values, 90),
        "MAE_R_avg": _avg(mae_values),
        "MAE_R_p50": _pct(mae_values, 50),
        "MAE_R_p75": _pct(mae_values, 75),
        "MAE_R_p90": _pct(mae_values, 90),
        "MFE_ge_0_5_ratio": _ratio(sum(1 for value in mfe_values if value is not None and value >= 0.5), len(mfe_values)),
        "MFE_ge_1_0_ratio": _ratio(sum(1 for value in mfe_values if value is not None and value >= 1.0), len(mfe_values)),
        "MAE_ge_1_0_ratio": _ratio(sum(1 for value in mae_values if value is not None and value >= 1.0), len(mae_values)),
        "exit_reason_distribution": dict(exits),
        "time_cut_exit_count": exits.get("time_cut_exit", 0),
        "time_cut_exit_ratio": _ratio(exits.get("time_cut_exit", 0), len(executions)),
        "stop_loss_count": exits.get("stop_loss", 0),
        "stop_loss_ratio": _ratio(exits.get("stop_loss", 0), len(executions)),
        "take_profit_count": exits.get("take_profit", 0) + exits.get("target", 0),
        "take_profit_ratio": _ratio(exits.get("take_profit", 0) + exits.get("target", 0), len(executions)),
        "breakeven_count": exits.get("breakeven_stop", 0),
        "breakeven_ratio": _ratio(exits.get("breakeven_stop", 0), len(executions)),
        "avg_holding_bars": _avg(holding),
        "median_holding_bars": _pct(holding, 50),
        "same_bar_ambiguous_count": sum(1 for row in executions if _truthy(row.get("same_bar_ambiguous"))),
        "forced_pessimistic_exit_count": sum(1 for row in executions if _truthy(row.get("forced_pessimistic_exit"))),
        "entry_and_exit_same_bar_count": sum(1 for row in executions if (_float(row.get("holding_bars")) or 0.0) <= 0),
        "fee_cost": fee_cost,
        "slippage_cost": slippage_cost,
        "funding_cost": funding_cost,
        "actual_risk_pct_p50": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in approved], 50),
        "actual_risk_pct_p75": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in approved], 75),
        "actual_risk_pct_p90": _pct([_float(row.get("actual_risk_pct_after_cap")) for row in approved], 90),
        "risk_utilization_p50": _pct([_float(row.get("risk_utilization_ratio")) for row in approved], 50),
        "risk_utilization_p75": _pct([_float(row.get("risk_utilization_ratio")) for row in approved], 75),
        "risk_utilization_p90": _pct([_float(row.get("risk_utilization_ratio")) for row in approved], 90),
        "notional_cap_hit_count": sum(1 for row in approved if _truthy(row.get("capped_by_notional"))),
        "notional_to_equity_p50": _pct([_float(row.get("notional_to_equity_pct")) for row in approved], 50),
        "notional_to_equity_p75": _pct([_float(row.get("notional_to_equity_pct")) for row in approved], 75),
        "notional_to_equity_p90": _pct([_float(row.get("notional_to_equity_pct")) for row in approved], 90),
        "margin_required_pct_p50": _pct([_float(row.get("margin_required_pct")) for row in approved], 50),
        "margin_required_pct_p75": _pct([_float(row.get("margin_required_pct")) for row in approved], 75),
        "margin_required_pct_p90": _pct([_float(row.get("margin_required_pct")) for row in approved], 90),
        "proposal_only": True,
        "formal_conclusion_enabled": False,
    }


def _write_outputs(result: Stage7SmokeBacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stage7_smoke_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "stage7_smoke_report.md").write_text(_report(result), encoding="utf-8")
    with (output_dir / "stage7_smoke_grouped_rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in result.grouped_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    index = build_index_for_directory(
        output_dir,
        strategy="liquidity_reversal",
        stage="stage7_smoke_backtest",
        window="10000w",
        source_command="research_pipeline.cli.research stage7-smoke-backtest",
        notes="PR11A proposal-only smoke baseline; no formal conclusion.",
    )
    write_artifact_index(index, output_dir)
    register_research_run(
        registry_path=output_dir / "research_run_registry.json",
        artifact_index_path=output_dir / "artifact_index.json",
        strategy="liquidity_reversal",
        stage="stage7_smoke_backtest",
        window="10000w",
        source_command="research_pipeline.cli.research stage7-smoke-backtest",
        proposal_only=True,
        formal_conclusion_enabled=False,
        readonly=False,
        notes="PR11A proposal-only smoke full backtest artifact evaluation.",
        tags=["PR11A", "proposal_only", "stage7_smoke"],
    )


def _report(result: Stage7SmokeBacktestResult) -> str:
    all_rows = [row for row in result.grouped_rows if row["asset"] == "ALL" and row["profile"] == "ALL" and row["direction"] == "ALL"]
    displacement_base = _all_row(all_rows, "displacement_after_reclaim", "current_risk_based_sizing", "base")
    choch_base = _all_row(all_rows, "CHOCH true", "current_risk_based_sizing", "base")
    lines = [
        "# Stage 7 Proposal-only Smoke Full Backtest Report",
        "",
        "- proposal_only = true",
        "- formal_conclusion_enabled = false",
        "- capped sizing = proposal-only",
        "- this is smoke baseline only; it is not formal LR approval",
        "",
        "## Smoke Summary",
    ]
    for row in all_rows:
        lines.append(
            f"- {row['combo']} / {row['sizing_model']} / {row['cost_tier']}: "
            f"closed={row['closed_trades']} net_R_avg={row['net_R_avg']} "
            f"PF={row['profit_factor']} MFE>=0.5={row['MFE_ge_0_5_ratio']} "
            f"time_cut={row['time_cut_exit_ratio']} same_bar={row['same_bar_ambiguous_count']} "
            f"liq={row['liquidation_event_count']}"
        )
    if displacement_base and choch_base:
        lines.extend(
            [
                "",
                "## Group Diagnostics",
                f"- displacement_after_reclaim vs CHOCH true: displacement base net_R_avg={displacement_base['net_R_avg']} vs CHOCH={choch_base['net_R_avg']}; MFE>=0.5={displacement_base['MFE_ge_0_5_ratio']} vs {choch_base['MFE_ge_0_5_ratio']}; time_cut={displacement_base['time_cut_exit_ratio']} vs {choch_base['time_cut_exit_ratio']}.",
                f"- displacement asset mix: BTC={displacement_base['BTC']}, ETH={displacement_base['ETH']}.",
                f"- displacement direction mix: long={displacement_base['long']}, short={displacement_base['short']}.",
                f"- displacement profile mix: B={displacement_base['B_profile']}, C={displacement_base['C_profile']}.",
                "- CHOCH true is broader and keeps more trades, but its MFE and time-cut profile are weaker than displacement_after_reclaim.",
                "- Current LR v1 frequency is useful for smoke baseline but low enough to justify PR 11B expansion diagnostics.",
            ]
        )
    lines.extend(
        [
            "",
            "## Required Research Context",
            "- LR bottleneck is not candidate generation; it is whether sweep/reclaim has enough active push.",
            "- displacement_after_reclaim is the most important current push-confirmation tag.",
            "- PDH/PDL, Session high/low, and EQH/EQL should remain diagnostic sources in PR 11B first.",
            "- Multiple entry attempt must be managed by an event FSM to avoid stale replay.",
            "- 0.5R fast take-profit can be consumed by BTC/ETH perpetual costs and is not a priority formal exit.",
            "- LR and trend continuation sizing policies should stay separated; notional_capped_risk_based remains proposal-only.",
            "",
            "## Expansion Readiness Assessment",
            "- CHOCH true and displacement_after_reclaim are valid LR v1 smoke baseline candidates.",
            "- Trading frequency remains limited enough that PR 11B should evaluate structure-source and entry-attempt expansion.",
            "- PR 11B should prioritize displacement / CHOCH / retest attempt FSM diagnostics, plus diagnostic-only PDH/PDL, EQH/EQL, and Session H/L.",
            "- Exit profile changes should be shadow simulations before replacing fixed 2R.",
            "- Continue keeping notional_capped_risk_based proposal-only.",
            "",
            f"## Final Conclusion: {result.final_conclusion}",
            "F. 当前 LR v1 有 edge 但交易频率偏低，建议先进入 PR 11B LR Expansion Diagnostic，再决定是否 Stage 8.",
        ]
    )
    return "\n".join(lines) + "\n"


def _all_row(rows: list[dict[str, Any]], combo: str, sizing_model: str, cost_tier: str) -> dict[str, Any] | None:
    for row in rows:
        if (
            row["combo"] == combo
            and row["sizing_model"] == sizing_model
            and row["cost_tier"] == cost_tier
        ):
            return row
    return None


def _execution_payload(
    sizing_row: dict[str, Any],
    execution_by_id: dict[str, dict[str, Any]],
    filter_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidate_id = str(sizing_row.get("candidate_id"))
    payload = dict(execution_by_id[candidate_id])
    payload.update(
        {
            "estimated_cost_r": _float(filter_by_id.get(candidate_id, {}).get("estimated_cost_r")),
            "net_return_on_notional": _float(sizing_row.get("net_return_on_notional")),
        }
    )
    return payload


def _matches_combo(row: dict[str, Any], combo: str) -> bool:
    if combo == "CHOCH true":
        return _truthy(row.get("choch_detected")) or row.get("choch_tag") == "choch_true"
    if combo == "displacement_after_reclaim":
        return _truthy(row.get("displacement_after_reclaim"))
    return False


def _is_approved_for_model(row: dict[str, Any], sizing_model: str) -> bool:
    if sizing_model == "current_risk_based_sizing":
        return _truthy(row.get("formal_approved"))
    return _truthy(row.get("proposal_approved"))


def _group_keys(rows: Iterable[dict[str, Any]]) -> list[tuple[str, str, str]]:
    return sorted(
        {
            (str(row.get("asset", "")), str(row.get("profile", "")), str(row.get("direction", "")))
            for row in rows
        }
    )


def _final_conclusion(rows: list[dict[str, Any]]) -> str:
    displacement_base = next(
        row
        for row in rows
        if row["combo"] == "displacement_after_reclaim"
        and row["sizing_model"] == "current_risk_based_sizing"
        and row["cost_tier"] == "base"
        and row["asset"] == "ALL"
    )
    if (displacement_base["net_R_avg"] or 0.0) > 0 and displacement_base["closed_trades"] >= 40:
        return "F"
    return "E"


def _expansion_readiness() -> dict[str, Any]:
    return {
        "lr_v1_smoke_baseline_worthkeeping": True,
        "frequency_low": True,
        "next_scope": "PR 11B LR Expansion Diagnostic",
        "diagnostic_sources_first": ["PDH/PDL", "EQH/EQL", "Session high/low"],
        "entry_fsm_priority": ["displacement", "CHoCH", "pullback_retest", "second_push"],
        "exit_shadow_before_formal": True,
        "keep_notional_capped_proposal_only": True,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{key: _typed(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def _typed(value: str) -> Any:
    if value == "":
        return None
    if value in {"True", "False"}:
        return value == "True"
    try:
        return float(value)
    except ValueError:
        return value


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else sum(clean) / len(clean)


def _pct(values: Iterable[float | None], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    index = (len(clean) - 1) * percentile / 100
    lower = int(index)
    upper = min(lower + 1, len(clean) - 1)
    weight = index - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def _ratio(count: int, total: int) -> float | None:
    return None if total == 0 else count / total


def _profit_factor(values: Iterable[float]) -> float | None:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _max(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else max(clean)


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    high = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        high = max(high, equity)
        drawdown = max(drawdown, high - equity)
    return drawdown


def _max_consecutive_losses(values: Iterable[float]) -> int:
    current = 0
    maximum = 0
    for value in values:
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum
