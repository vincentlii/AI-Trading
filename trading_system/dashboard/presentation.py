from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SummaryCard:
    title: str
    value: object
    help_text: str = ""


DASHBOARD_SECTION_FIELDS: dict[str, dict[str, str]] = {
    "ranking": {
        "rank": "排名",
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "timeframe_group": "周期组",
        "profile": "周期组",
        "status": "状态",
        "reason_codes": "原因代码",
        "score": "综合评分",
        "signal_count": "信号数",
        "trade_count": "交易数",
        "net_profit": "净利润",
        "max_drawdown": "最大回撤",
        "win_rate": "胜率",
        "profit_factor": "Profit Factor",
        "expectancy_per_trade": "单笔期望",
        "config_version": "配置版本",
        "config_fingerprint": "配置指纹",
    },
    "data_coverage": {
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "bar": "K 线周期",
        "row_count": "K 线数",
        "earliest_ts_ms": "最早时间",
        "latest_ts_ms": "最新时间",
        "meets_regime_minimum": "满足趋势识别最低量",
        "meets_minimum_runnable": "满足可运行最低量",
        "meets_initial_diagnostic": "满足初诊断量",
        "formal_target_candles": "正式回测目标 K 线数",
        "meets_formal_backtest": "满足正式回测",
        "quality_pass": "数据质量通过",
        "quality_issue_count": "质量问题数",
        "quality_issue_codes": "质量问题代码",
        "next_action": "下一步",
    },
    "profile_coverage": {
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "profile": "周期组",
        "entry_timeframe": "入场周期",
        "structure_timeframe": "结构周期",
        "trend_timeframe": "趋势周期",
        "timeframe_counts": "各周期 K 线数",
        "minimum_row_count": "最少 K 线数",
        "can_compute_regime": "可计算趋势状态",
        "can_run": "可运行",
        "diagnostic_ready": "诊断就绪",
        "formal_backtest_ready": "正式回测就绪",
        "blocking_timeframes": "阻塞周期",
        "quality_failure_timeframes": "质量失败周期",
        "next_action": "下一步",
    },
    "signal_funnel": {
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "profile": "周期组",
        "entry_timeframe": "入场周期",
        "structure_timeframe": "结构周期",
        "trend_timeframe": "趋势周期",
        "candle_counts_by_timeframe": "各周期 K 线数",
        "windows_checked": "检查窗口数",
        "data_insufficient": "数据不足",
        "regime_not_computable": "趋势不可计算",
        "regime_rejected": "趋势状态拒绝",
        "price_action_rejected": "价格行为拒绝",
        "volume_price_rejected": "量价拒绝",
        "target_space_insufficient": "目标空间不足",
        "risk_rejected": "风控拒绝",
        "approved_signal": "通过信号",
        "reason_codes": "原因代码",
        "next_action": "下一步",
    },
    "volume_rejection": {
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "profile": "周期组",
        "entry_timeframe": "入场周期",
        "strategy_family": "策略族",
        "setup_type": "Setup 类型",
        "direction": "方向",
        "candidate_count": "候选数",
        "confirm": "量价通过",
        "reject": "量价拒绝",
        "cooldown": "冷却过滤",
        "anomaly": "异常量价",
        "no_volume_baseline": "缺少成交量基线",
        "low_relative_volume": "相对量不足",
        "price_not_accepting_direction": "价格未接受方向",
        "cooldown_after_anomaly": "异常后冷却",
        "other_reasons": "其他原因",
        "volume_ratio_count": "RVOL 样本数",
        "volume_ratio_min": "RVOL 最小值",
        "volume_ratio_p25": "RVOL P25",
        "volume_ratio_median": "RVOL 中位数",
        "volume_ratio_p75": "RVOL P75",
        "volume_ratio_max": "RVOL 最大值",
    },
    "risk_rejection": {
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "profile": "周期组",
        "entry_timeframe": "入场周期",
        "strategy_family": "策略族",
        "setup_type": "Setup 类型",
        "direction": "方向",
        "reason_code": "风控原因",
        "candidate_count": "候选数",
        "max_stop_atr_multiple": "最大止损/ATR",
        "stop_distance_count": "止损距离样本数",
        "stop_distance_min": "止损距离最小值",
        "stop_distance_p25": "止损距离 P25",
        "stop_distance_median": "止损距离中位数",
        "stop_distance_p75": "止损距离 P75",
        "stop_distance_max": "止损距离最大值",
        "atr_count": "ATR 样本数",
        "atr_min": "ATR 最小值",
        "atr_p25": "ATR P25",
        "atr_median": "ATR 中位数",
        "atr_p75": "ATR P75",
        "atr_max": "ATR 最大值",
        "stop_atr_count": "止损/ATR 样本数",
        "stop_atr_min": "止损/ATR 最小值",
        "stop_atr_p25": "止损/ATR P25",
        "stop_atr_median": "止损/ATR 中位数",
        "stop_atr_p75": "止损/ATR P75",
        "stop_atr_max": "止损/ATR 最大值",
        "reward_to_risk_median": "盈亏比中位数",
        "estimated_cost_r_median": "成本/R 中位数",
        "net_reward_to_risk_median": "扣成本盈亏比中位数",
    },
    "near_miss": {
        "symbol": "交易对",
        "venue": "交易所",
        "inst_type": "合约类型",
        "inst_id": "交易所标的",
        "profile": "周期组",
        "entry_timeframe": "入场周期",
        "strategy_family": "策略族",
        "setup_type": "Setup 类型",
        "direction": "方向",
        "timestamp_ms": "信号时间",
        "terminal_stage": "终止阶段",
        "volume_status": "量价状态",
        "volume_reason": "量价原因",
        "volume_ratio": "RVOL",
        "risk_reason_codes": "风控原因代码",
        "stop_distance": "止损距离",
        "atr": "ATR",
        "stop_atr_multiple": "止损/ATR",
        "max_stop_atr_multiple": "最大止损/ATR",
        "reward_to_risk": "盈亏比",
        "estimated_cost_r": "成本/R",
        "net_reward_to_risk": "扣成本盈亏比",
        "near_miss_type": "Near Miss 类型",
        "distance_to_pass": "距通过阈值",
    },
    "proposal": {
        "path": "文件路径",
        "status": "状态",
        "error": "错误",
        "proposal_id": "Proposal ID",
        "title": "标题",
        "source": "来源",
        "base_config_version": "基准配置版本",
        "base_config_fingerprint": "基准配置指纹",
        "change_count": "变更数",
        "auto_apply": "自动应用",
    },
}


STATUS_TEXT: dict[str, str] = {
    "candidate": "候选",
    "supporting_only": "辅助观察",
    "rejected": "已拒绝",
    "completed": "已完成",
    "pass": "通过",
    "fail": "失败",
    "loaded": "已载入",
    "invalid": "无效",
    "available": "可用",
    "missing": "缺失",
    "generated": "已生成",
    "not_generated": "未生成",
    "ready": "已就绪",
    "fix_data_quality": "修复数据质量",
    "backfill_regime_minimum": "补齐趋势识别最低 K 线",
    "backfill_minimum_runnable": "补齐可运行最低 K 线",
    "backfill_initial_diagnostic": "补齐初诊断 K 线",
    "backfill_formal_backtest": "补齐正式回测 K 线",
    "fix_profile_data_quality": "修复周期组数据质量",
    "backfill_profile_minimum": "补齐周期组最低 K 线",
    "backfill_profile_diagnostic": "补齐周期组诊断 K 线",
    "backfill_profile_formal": "补齐周期组正式回测 K 线",
    "backfill_data": "补齐数据",
    "backfill_trend_timeframe": "补齐趋势周期",
    "run_p4_4_backtest": "运行 P4.4 回测",
    "inspect_risk_rejections": "检查风控拒绝",
    "inspect_strategy_conditions": "检查策略条件",
    "data_insufficient": "数据不足",
    "regime_not_computable": "趋势不可计算",
    "regime_rejected": "趋势状态拒绝",
    "price_action_rejected": "价格行为拒绝",
    "volume_price_rejected": "量价拒绝",
    "target_space_insufficient": "目标空间不足",
    "risk_rejected": "风控拒绝",
    "approved_signal": "通过信号",
    "confirm": "通过",
    "reject": "拒绝",
    "cooldown": "冷却",
    "anomaly": "异常",
    "stop_distance_too_near": "止损距离过近",
    "stop_distance_too_far": "止损距离过远",
    "invalid_stop_distance": "止损距离无效",
    "position_size_below_minimum": "仓位低于最小值",
    "position_size_above_maximum": "仓位高于最大值",
    "daily_loss_limit": "触及日内亏损限制",
    "hard_drawdown_stop": "触及硬回撤停止",
    "portfolio_heat_limit": "组合热度超限",
    "target_reward_too_low": "目标盈亏比过低",
    "missing_atr": "缺少 ATR",
    "missing_stop_loss": "缺少止损",
    "volume_confirm_threshold": "接近量价确认阈值",
    "risk_stop_atr_limit": "接近止损/ATR 上限",
}


SECTION_DESCRIPTIONS: dict[str, str] = {
    "ranking": "按当前 ranking 规则展示各交易对与周期组的候选、辅助观察和拒绝结果。",
    "data_coverage": "检查每个交易对和 K 线周期的数据量、质量与下一步补数动作。",
    "profile_coverage": "按周期组汇总入场、结构、趋势周期是否足够运行诊断和正式回测。",
    "signal_funnel": "从数据、趋势、价格行为、量价、目标空间到风控逐层统计信号流失原因。",
    "volume_rejection": "聚合量价确认阶段的通过、拒绝、冷却和异常原因。",
    "risk_rejection": "聚合风控拒绝原因，并展示止损距离、ATR、成本和盈亏比的分布。",
    "near_miss": "列出最接近通过量价或风控阈值的候选，供优先复核。",
    "proposal": "只读展示参数 Proposal 的载入状态、来源、变更数量和自动应用标记。",
}


FIELD_TOOLTIPS: dict[str, dict[str, str]] = {
    "ranking": {
        "score": "综合评分用于排序，不改变回测结果本身。",
        "profit_factor": "总盈利除以总亏损，越高表示盈利交易覆盖亏损交易的能力越强。",
        "expectancy_per_trade": "平均每笔交易的净收益。",
    },
    "data_coverage": {
        "row_count": "当前仓库内该交易对和 K 线周期的已确认 K 线数量。",
        "next_action": "根据数据量和质量推导出的下一步处理建议。",
    },
    "signal_funnel": {
        "windows_checked": "本次诊断实际检查的滚动入场窗口数量。",
        "volume_price_rejected": "量价确认未通过的窗口数量。",
        "approved_signal": "完整通过策略和风控检查的信号数量。",
    },
    "volume_rejection": {
        "volume_ratio_median": "候选窗口 RVOL 的中位数。",
        "cooldown": "异常量价后被冷却规则过滤的候选数量。",
    },
    "risk_rejection": {
        "stop_atr_median": "止损距离除以 ATR 的中位数。",
        "estimated_cost_r_median": "预估交易成本占单笔风险 R 的中位数。",
        "net_reward_to_risk_median": "扣除成本后的盈亏比中位数。",
    },
    "near_miss": {
        "distance_to_pass": "当前候选距离对应通过阈值的差距，越小越接近通过。",
        "near_miss_type": "标识接近通过的是量价确认还是风控限制。",
    },
    "proposal": {
        "auto_apply": "是否允许自动应用；看板只展示，不执行应用。",
        "change_count": "Proposal 中声明的参数变更数量。",
    },
}


METRIC_DESCRIPTIONS: dict[str, str] = {
    "RVOL": "Relative Volume，相对成交量；当前成交量相对历史基线的倍数，用于判断放量、缩量和异常量价。",
    "ATR": "Average True Range，平均真实波幅；衡量近期价格波动幅度，用于止损距离、突破缓冲和风险归一化。",
    "ADX/DMI": "ADX 衡量趋势强度，DMI+ 与 DMI- 判断多空方向强弱；本策略用它们过滤趋势背景。",
    "CHOP": "Choppiness Index，震荡程度指标；数值越高越偏震荡，越低越偏趋势。",
    "ER": "Kaufman Efficiency Ratio，效率比；衡量价格移动是否顺畅，越高代表趋势噪声越低。",
    "TTM Squeeze": "波动压缩状态；用于识别布林带进入 Keltner Channel 的低波动压缩阶段。",
    "Profit Factor": "总盈利除以总亏损；大于 1 表示总盈利覆盖总亏损。",
    "最大回撤": "权益曲线从高点到后续低点的最大跌幅，用于衡量策略历史风险暴露。",
    "单笔期望": "每笔交易平均净收益，等于净收益除以交易次数。",
    "止损/ATR": "止损距离与 ATR 的比值，用来判断止损是否相对当前波动过近或过远。",
    "Near Miss": "接近通过但被量价或风控阈值拦截的候选，优先用于诊断阈值边界。",
}

SIGNAL_FUNNEL_STAGE_ORDER = (
    "windows_checked",
    "data_insufficient",
    "regime_not_computable",
    "regime_rejected",
    "price_action_rejected",
    "volume_price_rejected",
    "target_space_insufficient",
    "risk_rejected",
    "approved_signal",
)


_VALUE_TEXT_KEYS = {
    "status",
    "next_action",
    "reason_code",
    "reason_codes",
    "quality_issue_codes",
    "near_miss_type",
    "terminal_stage",
    "volume_status",
    "volume_reason",
    "risk_reason_codes",
    "blocking_timeframes",
    "quality_failure_timeframes",
    "other_reasons",
}

_DIMENSION_KEYS = {
    "symbol",
    "venue",
    "inst_type",
    "inst_id",
    "profile",
    "entry_timeframe",
    "structure_timeframe",
    "trend_timeframe",
    "strategy_family",
    "setup_type",
    "direction",
}


def field_label(section: str, key: str) -> str:
    return DASHBOARD_SECTION_FIELDS.get(section, {}).get(key, key)


def label_for(key: str, *, section: str = "ranking") -> str:
    if section in DASHBOARD_SECTION_FIELDS and key in DASHBOARD_SECTION_FIELDS[section]:
        return DASHBOARD_SECTION_FIELDS[section][key]
    for labels in DASHBOARD_SECTION_FIELDS.values():
        if key in labels:
            return labels[key]
    return key


def field_tooltip(section: str, key: str) -> str:
    return FIELD_TOOLTIPS.get(section, {}).get(key, "")


def section_description(section: str) -> str:
    return SECTION_DESCRIPTIONS.get(section, "")


def status_text(code: str) -> str:
    return STATUS_TEXT.get(code, code)


def metric_description(term: str) -> str:
    return METRIC_DESCRIPTIONS.get(term, "")


def present_row(section: str, row: Mapping[str, object]) -> dict[str, object]:
    return {field_label(section, key): _present_value(key, value) for key, value in row.items()}


def localized_rows(rows: tuple[Mapping[str, object], ...], *, section: str = "ranking") -> tuple[dict[str, object], ...]:
    return tuple({label_for(key, section=section): value for key, value in row.items()} for row in rows)


def signal_funnel_points(rows: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "key": stage,
            "label": label_for(stage, section="signal_funnel"),
            "value": sum(_int(row.get(stage)) for row in rows),
        }
        for stage in SIGNAL_FUNNEL_STAGE_ORDER
    )


def rejection_reason_top(rows: tuple[Mapping[str, object], ...], *, top_n: int = 10) -> tuple[dict[str, object], ...]:
    counts: dict[str, int] = {}
    for row in rows:
        for reason in row.get("reason_codes", ()) or ():
            reason_text = str(reason)
            counts[reason_text] = counts.get(reason_text, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple({"reason": reason, "count": count} for reason, count in ordered[:top_n])


def volume_reason_rows(rows: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {"reason": key, "count": sum(_int(row.get(key)) for row in rows)}
        for key in ("reject", "cooldown", "anomaly", "confirm")
    )


def risk_reason_rows(rows: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = row.get("reason_code")
        if reason:
            counts[str(reason)] = counts.get(str(reason), 0) + _int(row.get("candidate_count"))
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple({"reason": reason, "count": count} for reason, count in ordered)


def near_miss_summary(rows: tuple[Mapping[str, object], ...], *, limit: int = 20) -> tuple[Mapping[str, object], ...]:
    return tuple(sorted(rows, key=_near_miss_sort_key)[:limit])


def full_backtest_summary(snapshot) -> tuple[SummaryCard, ...]:
    ranking_rows = tuple(getattr(snapshot, "ranking_rows", ()))
    summary = getattr(snapshot, "summary", {})
    best = min(ranking_rows, key=lambda row: _int(row.get("rank"), default=10**9), default={})
    max_drawdown = _float(best.get("max_drawdown"))
    best_name = " / ".join(
        str(part)
        for part in (
            best.get("symbol"),
            best.get("timeframe_group", best.get("profile")),
            best.get("setup_type"),
        )
        if part
    )
    return (
        SummaryCard("最佳组合", best_name),
        SummaryCard("净利润", _format_number(summary.get("net_profit", 0.0))),
        SummaryCard("交易数", _format_number(best.get("trade_count", 0))),
        SummaryCard("最大回撤", f"{max_drawdown:.2%}"),
        SummaryCard("Profit Factor", _format_number(best.get("profit_factor", 0.0))),
    )


def build_dashboard_presentation_data(snapshot, *, top_n: int = 5) -> dict[str, object]:
    ranking_rows = tuple(getattr(snapshot, "ranking_rows", ()))
    performance_rows = tuple(getattr(snapshot, "performance_metric_rows", ()))
    signal_funnel_rows = tuple(getattr(snapshot, "signal_funnel_rows", ()))
    volume_rejection_rows = tuple(getattr(snapshot, "volume_rejection_rows", ()))
    risk_rejection_rows = tuple(getattr(snapshot, "risk_rejection_rows", ()))
    near_miss_rows = tuple(getattr(snapshot, "near_miss_rows", ()))

    return {
        "signal_funnel": _signal_funnel_summary(signal_funnel_rows),
        "rejection_reason_top": _rejection_reason_top(volume_rejection_rows, risk_rejection_rows, top_n=top_n),
        "near_miss_summary": tuple(sorted(near_miss_rows, key=_near_miss_sort_key)[:top_n]),
        "full_backtest_summary": _full_backtest_summary(ranking_rows, performance_rows),
    }


def _present_value(key: str, value: object) -> object:
    if key not in _VALUE_TEXT_KEYS:
        return value
    if isinstance(value, tuple | list):
        return ", ".join(status_text(str(item)) for item in value)
    if value is None:
        return ""
    return status_text(str(value))


def _signal_funnel_summary(rows: tuple[Mapping[str, object], ...]) -> dict[str, object]:
    return {
        "stages": SIGNAL_FUNNEL_STAGE_ORDER,
        "values": tuple(sum(_int(row.get(stage)) for row in rows) for stage in SIGNAL_FUNNEL_STAGE_ORDER),
    }


def _rejection_reason_top(
    volume_rejection_rows: tuple[Mapping[str, object], ...],
    risk_rejection_rows: tuple[Mapping[str, object], ...],
    *,
    top_n: int,
) -> tuple[dict[str, object], ...]:
    counts: dict[str, int] = {}
    for row in volume_rejection_rows:
        for key, value in row.items():
            if key in _DIMENSION_KEYS or key == "candidate_count":
                continue
            count = _int(value)
            if count > 0:
                counts[key] = counts.get(key, 0) + count
    for row in risk_rejection_rows:
        reason = row.get("reason_code")
        if reason:
            counts[str(reason)] = counts.get(str(reason), 0) + _int(row.get("candidate_count"))

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple({"reason_code": key, "count": value} for key, value in ordered[:top_n])


def _full_backtest_summary(
    ranking_rows: tuple[Mapping[str, object], ...],
    performance_rows: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    return {
        "ranked_groups": len(ranking_rows),
        "candidates": sum(1 for row in ranking_rows if row.get("status") == "candidate"),
        "supporting_only": sum(1 for row in ranking_rows if row.get("status") == "supporting_only"),
        "rejected": sum(1 for row in ranking_rows if row.get("status") == "rejected"),
        "ranking_net_profit": sum(_float(row.get("net_profit")) for row in ranking_rows),
        "performance_runs": len(performance_rows),
        "performance_trade_count": sum(_int(row.get("trade_count")) for row in performance_rows),
        "performance_net_profit": sum(_float(row.get("net_profit")) for row in performance_rows),
        "best_ranked_symbol": _best_symbol(ranking_rows, "rank", reverse=False),
        "best_performance_symbol": _best_symbol(performance_rows, "net_profit", reverse=True),
    }


def _best_symbol(rows: tuple[Mapping[str, object], ...], key: str, *, reverse: bool) -> str:
    if not rows:
        return ""
    if reverse:
        selected = max(rows, key=lambda row: _float(row.get(key)))
    else:
        selected = min(rows, key=lambda row: _float(row.get(key), default=float("inf")))
    return str(selected.get("symbol", ""))


def _near_miss_sort_key(row: Mapping[str, object]) -> tuple[float, str, str, int]:
    return (
        _float(row.get("distance_to_pass"), default=float("inf")),
        str(row.get("symbol", "")),
        str(row.get("profile", "")),
        _int(row.get("timestamp_ms")),
    )


def _int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _float(value: object, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    return default


def _format_number(value: object) -> str:
    number = _float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


__all__ = (
    "DASHBOARD_SECTION_FIELDS",
    "FIELD_TOOLTIPS",
    "METRIC_DESCRIPTIONS",
    "SECTION_DESCRIPTIONS",
    "STATUS_TEXT",
    "SIGNAL_FUNNEL_STAGE_ORDER",
    "SummaryCard",
    "build_dashboard_presentation_data",
    "field_label",
    "field_tooltip",
    "full_backtest_summary",
    "label_for",
    "localized_rows",
    "metric_description",
    "near_miss_summary",
    "present_row",
    "rejection_reason_top",
    "risk_reason_rows",
    "section_description",
    "signal_funnel_points",
    "status_text",
    "volume_reason_rows",
)
