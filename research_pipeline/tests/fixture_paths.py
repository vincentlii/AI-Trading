from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any


_ROOT = Path(tempfile.mkdtemp(prefix="research_pipeline_fixtures_"))
FIXTURE_ROOT = _ROOT
FILTER_RESULTS = _ROOT / "minimal_lr_v0_filter_results.jsonl"
EXECUTION_RESULTS = _ROOT / "minimal_lr_v0_execution_results.jsonl"
SIZING_CANDIDATES = _ROOT / "stage6c_sizing_candidates.csv"
COMBINED_FIX_DIR = _ROOT / "lr_combined_fix_pr11g"
ARTIFACT_SOURCE_DIR = _ROOT / "artifact_source"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _base_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    filter_rows: list[dict[str, Any]] = []
    execution_rows: list[dict[str, Any]] = []
    sizing_rows: list[dict[str, Any]] = []
    for index in range(42):
        candidate_id = f"lr-fixture-{index:03d}"
        direction = "long" if index % 2 == 0 else "short"
        asset = "BTC" if index % 3 else "ETH"
        profile = "C" if index % 4 else "B"
        start = 1_700_000_000_000 + index * 900_000
        net_r = 0.8 if index % 5 else -0.35
        structure_source = "rolling_range" if index % 11 == 0 else ("Session_HL" if index % 2 == 0 else "recent_swing")
        common = {
            "candidate_id": candidate_id,
            "event_id": f"event-{index:03d}",
            "event_key": f"event-{index:03d}",
            "asset": asset,
            "profile": profile,
            "direction": direction,
            "structure_level_source": structure_source,
            "structure_level_type": "high" if direction == "short" else "low",
            "structure_level": 100 + index,
            "structure_time": start,
            "structure_confirmed_time": start,
            "sweep_time": start + 60_000,
            "reclaim_time": start + 120_000,
            "signal_time": start + 180_000,
            "entry_time": start + 240_000,
            "feature_cutoff_time": start + 180_000,
            "bar_confirmed": True,
            "no_lookahead_safe": True,
            "entry_price": 100.0 + index,
            "stop_price": 99.0 + index,
            "target_price": 102.0 + index,
            "estimated_cost_r": 0.02,
            "choch_detected": True,
            "choch_tag": "choch_true",
            "displacement_after_reclaim": True,
            "displacement_direction_valid": True,
            "pullback_retest_after_reclaim": index % 3 == 0,
            "fvg_exists": index % 7 == 0,
            "fvg_retest_hit": False,
            "displacement_close_beyond_structure": True,
            "displacement_body_atr": 1.4,
            "sweep_rvol": 2.1,
            "choch_strength": 0.7,
            "london_ny_overlap": index % 2 == 0,
            "session_high_low_tag": structure_source == "Session_HL",
            "london_open_window": False,
            "ny_open_window": index % 2 == 1,
            "funding_settlement_plus_2h_window": False,
            "formal_approved": True,
            "proposal_approved": True,
        }
        filter_rows.append(dict(common))
        execution_rows.append(
            {
                **common,
                "closed_trade": True,
                "exit_time": start + 540_000,
                "exit_reason": "take_profit" if net_r > 0 else "time_cut_exit",
                "net_R": net_r,
                "mfe_R": 1.25 if net_r > 0 else 0.3,
                "mae_R": 0.25 if net_r > 0 else 0.8,
                "holding_bars": 2,
                "same_bar_ambiguous": False,
                "forced_pessimistic_exit": False,
                "liquidation_event": False,
                "funding_paid_or_received": 0.0,
            }
        )
        for sizing_model in ("current_risk_based_sizing", "notional_capped_risk_based"):
            sizing_rows.append(
                {
                    **common,
                    "sizing_model": sizing_model,
                    "net_return_on_notional": 0.001,
                    "actual_risk_pct_after_cap": 0.004,
                    "risk_utilization_ratio": 0.8,
                    "capped_by_notional": sizing_model == "notional_capped_risk_based",
                    "notional_to_equity_pct": 0.25,
                    "margin_required": 50.0,
                    "margin_required_pct": 0.02,
                    "portfolio_heat": 0.02,
                }
            )
    for index in range(42, 45):
        candidate_id = f"lr-fixture-{index:03d}"
        start = 1_700_000_000_000 + index * 900_000
        common = {
            "candidate_id": candidate_id,
            "event_id": f"event-{index:03d}",
            "event_key": f"event-{index:03d}",
            "asset": "BTC",
            "profile": "C",
            "direction": "long",
            "structure_level_source": "Session_HL",
            "structure_level_type": "low",
            "structure_level": 100 + index,
            "structure_time": start,
            "structure_confirmed_time": start,
            "sweep_time": start + 60_000,
            "reclaim_time": start + 120_000,
            "signal_time": start + 180_000,
            "entry_time": start + 240_000,
            "feature_cutoff_time": start + 180_000,
            "bar_confirmed": True,
            "no_lookahead_safe": True,
            "entry_price": 100.0 + index,
            "stop_price": 99.0 + index,
            "target_price": 102.0 + index,
            "estimated_cost_r": 0.02,
            "choch_detected": True,
            "choch_tag": "choch_true",
            "displacement_after_reclaim": True,
            "displacement_direction_valid": True,
            "pullback_retest_after_reclaim": False,
            "fvg_exists": False,
            "fvg_retest_hit": False,
            "displacement_close_beyond_structure": True,
            "displacement_body_atr": 1.4,
            "sweep_rvol": 2.1,
            "choch_strength": 0.7,
            "london_ny_overlap": True,
            "session_high_low_tag": True,
            "london_open_window": False,
            "ny_open_window": False,
            "funding_settlement_plus_2h_window": False,
            "formal_approved": False,
            "proposal_approved": True,
        }
        filter_rows.append(dict(common))
        sizing_rows.append(
            {
                **common,
                "sizing_model": "notional_capped_risk_based",
                "net_return_on_notional": 0.001,
                "actual_risk_pct_after_cap": 0.004,
                "risk_utilization_ratio": 0.8,
                "capped_by_notional": True,
                "notional_to_equity_pct": 0.25,
                "margin_required": 50.0,
                "margin_required_pct": 0.02,
                "portfolio_heat": 0.02,
            }
        )
    return filter_rows, execution_rows, sizing_rows


def _combo_rows(execution_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    combos = (
        ("T1_session_hl_attempt4_fixed_current", 1),
        ("T1_recent_swing_attempt4_dynamic_quality", 2),
        ("T2_session_hl_attempt3_dynamic_quality", 3),
        ("T3_rolling_range_attempt4_dynamic_quality", 9),
    )
    for execution in execution_rows:
        for cost_tier, penalty in (("base", 0.0), ("stress", 0.05), ("harsh", 0.12)):
            for combo_name, priority in combos:
                closed = combo_name != "T3_rolling_range_attempt4_dynamic_quality"
                rows.append(
                    {
                        **execution,
                        "row_type": "closed_trade" if closed else "proposal_candidate",
                        "combo_name": combo_name,
                        "cost_tier": cost_tier,
                        "priority": priority,
                        "tier": "T1" if combo_name.startswith("T1") else ("T2" if combo_name.startswith("T2") else "T3"),
                        "closed_trade": closed,
                        "net_R": (execution["net_R"] - penalty) if closed else None,
                        "proposal_only": not closed,
                        "sizing_policy": "current_risk_based_sizing",
                        "time_cut_exit": execution["exit_reason"] == "time_cut_exit" if closed else False,
                        "loss_time_cut": execution["exit_reason"] == "time_cut_exit" if closed else False,
                        "profitable_time_cut": False,
                    }
                )
    return rows


def _variant_rows(combo_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        row
        for row in combo_rows
        if row["combo_name"] == "T1_session_hl_attempt4_fixed_current" and row["closed_trade"]
    ]
    output: list[dict[str, Any]] = []
    for variant_name in ("Variant A - Tier 1 only", "Variant B - Tier 1 + Positive Tier 2"):
        for cost_tier in ("base", "stress", "harsh"):
            rows = [row for row in selected if row["cost_tier"] == cost_tier]
            net = [float(row["net_R"]) for row in rows]
            wins = sum(value for value in net if value > 0)
            losses = abs(sum(value for value in net if value < 0))
            output.append(
                {
                    "row_type": "summary_row",
                    "variant_name": variant_name,
                    "tier": "ALL",
                    "cost_tier": cost_tier,
                    "closed_trades": len(rows),
                    "selected_trades": len(rows),
                    "selected_without_closed_count": 0,
                    "proposal_only_unexecuted_count": 0,
                    "net_R_avg": sum(net) / len(net),
                    "total_net_R": sum(net),
                    "profit_factor": wins / losses,
                    "MFE_R_avg": sum(float(row["mfe_R"]) for row in rows) / len(rows),
                    "MAE_R_avg": sum(float(row["mae_R"]) for row in rows) / len(rows),
                    "time_cut_exit_rate": sum(1 for row in rows if row["exit_reason"] == "time_cut_exit") / len(rows),
                    "bad_time_cut_ratio": 1.0,
                    "duplicate_event_count": 0,
                    "proposal_only": True,
                    "formal_conclusion_enabled": False,
                }
            )
    return output


def _build() -> None:
    filter_rows, execution_rows, sizing_rows = _base_rows()
    combo_rows = _combo_rows(execution_rows)
    variant_rows = _variant_rows(combo_rows)
    _write_jsonl(FILTER_RESULTS, filter_rows)
    _write_jsonl(EXECUTION_RESULTS, execution_rows)
    _write_csv(SIZING_CANDIDATES, sizing_rows)
    _write_json(
        COMBINED_FIX_DIR / "lr_combined_candidate_fix_result.json",
        {
            "proposal_only": True,
            "formal_conclusion_enabled": False,
            "mapping_diagnostics": {
                "combo_name": "T1_session_hl_attempt4_dynamic_quality",
                "selected_without_closed_count": 3,
                "missing_trade_id_count": 42,
                "missing_execution_row_count": 42,
                "join_key_mismatch_count": 0,
                "proposal_only_unexecuted_count": 3,
                "fix_applied": "fixture_keeps_missing_execution_identity_for_gate_test",
            },
            "diagnostic_combos": [
                {
                    "combo_name": "T3_rolling_range_attempt4_dynamic_quality",
                    "diagnostic_reason": "fixture_diagnostic_only",
                }
            ],
            "variant_rows": variant_rows,
        },
    )
    _write_jsonl(COMBINED_FIX_DIR / "lr_combined_combo_rows.jsonl", combo_rows)
    _write_jsonl(COMBINED_FIX_DIR / "lr_combined_variant_rows.jsonl", variant_rows)
    _write_jsonl(COMBINED_FIX_DIR / "lr_combined_grouped_rows.jsonl", variant_rows)
    _write_jsonl(COMBINED_FIX_DIR / "lr_combined_event_selection_rows.jsonl", [])
    _write_jsonl(COMBINED_FIX_DIR / "lr_combined_unmapped_rows.jsonl", [])
    original_dir = _ROOT / "lr_combined_pr11g"
    _write_json(
        original_dir / "lr_combined_candidate_result.json",
        {
            "portfolio_rows": [
                {
                    "tier": "ALL",
                    "cost_tier": "base",
                    "closed_trades": 45,
                    "total_net_R": 25.0,
                }
            ]
        },
    )
    _write_json(
        _ROOT / "lr_attempt_pr11c" / "lr_attempt_proposal_result.json",
        {"proposal_only": True},
    )
    _write_json(
        _ROOT / "lr_structure_pr11d" / "lr_structure_source_proposal_result.json",
        {"proposal_only": True},
    )
    _write_json(
        _ROOT / "lr_exit_pr11e" / "lr_exit_profile_proposal_result.json",
        {"proposal_only": True},
    )
    _write_json(
        _ROOT / "lr_sizing_pr11f" / "lr_sizing_proposal_result.json",
        {"proposal_only": True},
    )
    ARTIFACT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in {
        "summary.json": {"strategy": "liquidity_reversal", "closed_trades": 42},
        "metrics.json": {"total_net_R": 24.15},
        "manifest.json": {"strategy": "liquidity_reversal"},
    }.items():
        _write_json(ARTIFACT_SOURCE_DIR / name, payload)
    _write_jsonl(ARTIFACT_SOURCE_DIR / "rows.jsonl", combo_rows[:3])
    _write_csv(ARTIFACT_SOURCE_DIR / "rows.csv", sizing_rows[:3])
    (ARTIFACT_SOURCE_DIR / "report.md").write_text("# Fixture Report\n", encoding="utf-8")


_build()
