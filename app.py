from __future__ import annotations

import html
from pathlib import Path
from typing import Mapping, Sequence

from trading_system.dashboard.components import (
    apply_dashboard_component_style,
    render_read_only_notice,
)
from trading_system.dashboard.panel import (
    DEFAULT_DB_PATH,
    DEFAULT_PRESET_PATH,
    DEFAULT_PROPOSALS_DIR,
    DEFAULT_REVIEW_LOG_PATH,
    build_default_dashboard_snapshot,
)
from trading_system.dashboard.presentation import (
    METRIC_DESCRIPTIONS,
    full_backtest_summary,
    near_miss_summary,
    present_row,
    rejection_reason_top,
    risk_reason_rows,
    signal_funnel_points,
    status_text,
    volume_reason_rows,
)


DASHBOARD_TABS = (
    "首页",
    "信号诊断",
    "策略排名",
    "风控分析",
    "完整回测",
    "绩效报告",
    "数据质量",
    "Proposal 队列",
    "P6 Paper",
    "系统说明",
)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="中文交易诊断驾驶舱", layout="wide")
    _apply_style(st)
    apply_dashboard_component_style(st)

    st.title("中文交易诊断驾驶舱")
    st.caption("只读 P5 看板：近期诊断解释当前信号卡点，完整回测摘要展示 P4 主口径结论。")

    with st.sidebar:
        st.header("输入")
        preset_path = st.text_input("Preset", value=str(DEFAULT_PRESET_PATH))
        db_path = st.text_input("DuckDB", value=str(DEFAULT_DB_PATH))
        proposals_dir = st.text_input("Proposals", value=str(DEFAULT_PROPOSALS_DIR))
        review_log_path = st.text_input("ReviewLog", value=str(DEFAULT_REVIEW_LOG_PATH))
        refresh = st.button("刷新", type="primary")

    snapshot = _load_snapshot(
        preset_path=preset_path,
        db_path=db_path,
        proposals_dir=proposals_dir,
        review_log_path=review_log_path,
        refresh=refresh,
    )

    render_read_only_notice(st)
    tabs = st.tabs(DASHBOARD_TABS)

    with tabs[0]:
        _render_overview(st, snapshot)

    with tabs[1]:
        _render_diagnostics(st, snapshot)

    with tabs[2]:
        _render_strategy_ranking(st, snapshot)

    with tabs[3]:
        _render_risk_analysis(st, snapshot)

    with tabs[4]:
        _render_full_backtest(st, snapshot)

    with tabs[5]:
        _render_performance_report(st, snapshot)

    with tabs[6]:
        _render_data_quality(st, snapshot)

    with tabs[7]:
        _render_proposal_queue(st, snapshot)

    with tabs[8]:
        _render_p6_paper(st, snapshot)

    with tabs[9]:
        _render_system_info(st, snapshot)


def _load_snapshot(*, preset_path: str, db_path: str, proposals_dir: str, review_log_path: str, refresh: bool):
    import streamlit as st

    @st.cache_data(show_spinner="加载本地回测、数据质量与信号诊断状态...")
    def cached_snapshot(preset_value: str, db_value: str, proposals_value: str, review_log_value: str, schema_version: str):
        return build_default_dashboard_snapshot(
            preset_path=Path(preset_value),
            db_path=Path(db_value),
            proposals_dir=Path(proposals_value) if proposals_value else None,
            review_log_path=Path(review_log_value) if review_log_value else None,
        )

    if refresh:
        cached_snapshot.clear()
    return cached_snapshot(preset_path, db_path, proposals_dir, review_log_path, "p5_cockpit_v2")


def _render_overview(st, snapshot) -> None:
    st.markdown(
        (
            "### 首页总览\n"
            "**近期 200 window 诊断** 用于解释当前为什么没有信号；"
            "**完整回测主口径** 来自 P4 ranking / performance rows，用于观察策略长期表现。"
        )
    )
    st.caption(f"{snapshot.config_version} | {snapshot.config_fingerprint}")

    columns = st.columns(8)
    for column, (label, value) in zip(columns, _overview_cards(snapshot), strict=False):
        column.metric(label, value)

    _safe_plotly_chart(st, _make_signal_funnel_figure(snapshot), key="overview_signal_funnel")
    _safe_plotly_chart(
        st,
        _make_bar_figure("主要拒绝原因 Top 5", _top_rejection_rows(snapshot, limit=5)),
        key="overview_rejection_top",
    )

    st.markdown("### 完整回测结论摘要")
    _render_summary_cards(st, full_backtest_summary(snapshot))

    st.markdown("### Near Miss 候选摘要")
    _render_table(st, near_miss_summary(_snapshot_rows(snapshot, "near_miss_rows"), limit=5))

    _render_metric_notes(st)


def _render_strategy_ranking(st, snapshot) -> None:
    st.subheader("策略排名")
    _render_chinese_table(st, "ranking", _snapshot_rows(snapshot, "ranking_rows"))


def _render_risk_analysis(st, snapshot) -> None:
    st.subheader("风控拒绝原因")
    risk_rows = _snapshot_rows(snapshot, "risk_rejection_rows")
    _safe_plotly_chart(
        st,
        _make_bar_figure("risk_rejected 原因排行", risk_reason_rows(risk_rows)),
        key="risk_reason_top",
    )
    _render_chinese_table(st, "risk_rejection", risk_rows)

    st.subheader("止损 / ATR 分布")
    _safe_plotly_chart(st, _make_risk_distribution_figure(risk_rows), key="risk_stop_atr_distribution")

    st.subheader("因 stop_distance_too_far 被拒绝的候选")
    _render_chinese_table(
        st,
        "risk_rejection",
        tuple(row for row in risk_rows if row.get("reason_code") == "stop_distance_too_far"),
    )


def _render_full_backtest(st, snapshot) -> None:
    st.markdown(
        (
            "### 完整回测结论摘要\n"
            "这里展示 P4 完整回测主口径摘要；首页不默认展开完整明细，避免进入页面时加载过重。"
        )
    )
    _render_summary_cards(st, full_backtest_summary(snapshot))

    with st.expander("加载完整回测明细", expanded=False):
        st.caption("明细保持原始字段，便于追溯 P4 ranking / performance 输出。")
        _render_table(st, _snapshot_rows(snapshot, "performance_metric_rows"))
        _render_table(st, _snapshot_rows(snapshot, "ranking_rows"))


def _render_performance_report(st, snapshot) -> None:
    st.subheader("绩效指标")
    _render_table(st, _snapshot_rows(snapshot, "performance_metric_rows"))
    st.subheader("第三方库状态")
    _render_table(st, _snapshot_rows(snapshot, "performance_library_rows"))
    st.subheader("报告 Artifact")
    _render_table(st, _snapshot_rows(snapshot, "performance_artifact_rows"))


def _render_data_quality(st, snapshot) -> None:
    st.subheader("数据覆盖")
    _render_chinese_table(st, "data_coverage", _snapshot_rows(snapshot, "data_coverage_rows"))
    st.subheader("Profile 覆盖")
    _render_chinese_table(st, "profile_coverage", _snapshot_rows(snapshot, "profile_coverage_rows"))
    st.subheader("原始质量检查")
    _render_table(st, _snapshot_rows(snapshot, "quality_rows"))


def _render_proposal_queue(st, snapshot) -> None:
    st.markdown(
        (
            "### Proposal 队列\n"
            "这里只读展示待验证、待回测、待人工确认的 Proposal；看板不提供自动应用入口。"
        )
    )
    _render_chinese_table(st, "proposal", _snapshot_rows(snapshot, "proposal_rows"))


def _render_p6_paper(st, snapshot) -> None:
    st.subheader("P6 Paper ReviewLog")
    _render_table(st, _snapshot_rows(snapshot, "paper_review_log_rows"))
    st.subheader("Paper Equity")
    _render_table(st, _snapshot_rows(snapshot, "paper_equity_rows"))
    st.subheader("Paper Trades")
    _render_table(st, _snapshot_rows(snapshot, "paper_trade_rows"))
    st.subheader("Failure Attribution")
    _render_table(st, _snapshot_rows(snapshot, "paper_failure_rows"))
    invalid_rows = _snapshot_rows(snapshot, "paper_review_log_invalid_rows")
    if invalid_rows:
        st.subheader("Invalid ReviewLog Rows")
        _render_table(st, invalid_rows)


def _render_system_info(st, snapshot) -> None:
    st.markdown(
        (
            "### 系统说明\n"
            "- P5 是**只读看板**，不下单、不修改正式配置、不自动应用 Proposal。\n"
            "- **近期 200 window** 只用于页面诊断，解释当前信号在哪一层被过滤。\n"
            "- **P4 完整回测** 是完整回测主口径，首页只展示摘要，明细在完整回测页延迟展开。\n"
            "- Proposal 队列必须经过人工审批和回测验证，不能绕过审批机制。\n"
            "- Plotly 仅作为展示层依赖，不进入策略、风控、撮合或回测模型。"
        )
    )
    _render_metric_notes(st)


def _render_diagnostics(st, snapshot) -> None:
    signal_rows = _snapshot_rows(snapshot, "signal_funnel_rows")
    volume_rows = _snapshot_rows(snapshot, "volume_rejection_rows")

    _safe_plotly_chart(st, _make_signal_funnel_figure(snapshot), key="diagnostics_signal_funnel")
    _safe_plotly_chart(
        st,
        _make_bar_figure("量价拒绝细分", volume_reason_rows(volume_rows)),
        key="diagnostics_volume_reasons",
    )

    st.subheader("数据覆盖")
    _render_table(st, _snapshot_rows(snapshot, "data_coverage_rows"))
    st.subheader("Profile 覆盖")
    _render_table(st, _snapshot_rows(snapshot, "profile_coverage_rows"))
    st.subheader("信号漏斗")
    _render_table(st, signal_rows)
    st.subheader("量价拒绝细分")
    _render_table(st, volume_rows)
    st.subheader("量价 RVOL 分布")
    _render_table(st, _snapshot_rows(snapshot, "volume_distribution_rows"))
    st.subheader("风控拒绝细分")
    _render_table(st, _snapshot_rows(snapshot, "risk_rejection_rows"))
    st.subheader("最接近通过候选")
    _render_table(st, _snapshot_rows(snapshot, "near_miss_rows"))


def _render_summary_cards(st, cards: Sequence[object]) -> None:
    columns = st.columns(len(cards) or 1)
    for column, card in zip(columns, cards, strict=False):
        column.metric(str(card.title), card.value)


def _render_metric_notes(st) -> None:
    keys = (
        "RVOL",
        "ATR",
        "ADX/DMI",
        "CHOP",
        "ER",
        "TTM Squeeze",
        "Profit Factor",
        "最大回撤",
        "单笔期望",
        "止损/ATR",
        "Near Miss",
    )
    st.markdown("### 指标说明")
    _render_table(
        st,
        tuple(
            {"指标名称": key, "说明": METRIC_DESCRIPTIONS[key]}
            for key in keys
            if key in METRIC_DESCRIPTIONS
        ),
    )


def _render_chinese_table(st, section: str, rows: tuple[Mapping[str, object], ...]) -> None:
    _render_table(st, tuple(present_row(section, row) for row in rows))


def _render_table(st, rows: tuple[Mapping[str, object], ...]) -> None:
    if not rows:
        st.caption("暂无数据")
        return

    columns = tuple(rows[0].keys())
    header = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_format_cell(row.get(column)))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")

    st.markdown(
        (
            '<div class="p5-table-wrap">'
            '<table class="p5-table">'
            f"<thead><tr>{header}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
            "</table>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _overview_cards(snapshot) -> tuple[tuple[str, object], ...]:
    summary = _summary(snapshot)
    funnel_totals = _funnel_totals(_snapshot_rows(snapshot, "signal_funnel_rows"))
    windows_checked = max(int(funnel_totals.get("windows_checked", 0)), 1)
    volume_rejected = int(funnel_totals.get("volume_price_rejected", 0))
    risk_rejected = int(funnel_totals.get("risk_rejected", 0))
    quality_failures = int(summary.get("quality_failures", 0) or 0)
    can_run = int(summary.get("profile_can_run", 0) or 0)
    system_status = "正常" if quality_failures == 0 and can_run > 0 else "待检查"
    return (
        ("系统状态", system_status),
        ("数据质量", "通过" if quality_failures == 0 else f"{quality_failures} 个失败"),
        ("可运行 Profile", can_run),
        ("量价拒绝率", _format_percent(volume_rejected / windows_checked)),
        ("风控拒绝率", _format_percent(risk_rejected / windows_checked)),
        ("最终信号", int(summary.get("approved_signals", 0) or 0)),
        ("Near Miss", int(summary.get("near_miss_candidates", 0) or 0)),
        ("完整回测净利润", _format_number(summary.get("net_profit", 0.0))),
    )


def _make_signal_funnel_figure(snapshot):
    points = signal_funnel_points(_snapshot_rows(snapshot, "signal_funnel_rows"))
    labels = [str(point["label"]) for point in points]
    values = [int(point["value"]) for point in points]
    go = _plotly_go()
    if go is None:
        return {"title": "近期信号漏斗", "y": labels, "x": values}
    return go.Figure(
        data=[
            go.Funnel(
                y=labels,
                x=values,
                marker={"color": ["#64748b", "#ef4444", "#f97316", "#f97316", "#f59e0b", "#dc2626", "#f59e0b", "#b91c1c", "#16a34a"]},
            )
        ],
        layout={"title": "近期信号漏斗：最近 200 entry window", "margin": {"l": 10, "r": 10, "t": 42, "b": 10}},
    )


def _make_bar_figure(title: str, rows: Sequence[Mapping[str, object]]):
    labels = [status_text(str(row.get("reason", row.get("reason_code", "")))) for row in rows]
    values = [int(row.get("count", 0) or 0) for row in rows]
    go = _plotly_go()
    if go is None:
        return {"title": title, "x": values, "y": labels}
    return go.Figure(
        data=[go.Bar(x=values, y=labels, orientation="h", marker={"color": "#dc2626"})],
        layout={"title": title, "margin": {"l": 10, "r": 10, "t": 42, "b": 10}, "height": 320},
    )


def _make_risk_distribution_figure(rows: Sequence[Mapping[str, object]]):
    labels = [f"{row.get('symbol', '')} {row.get('profile', '')}".strip() for row in rows]
    values = [_as_float(row.get("stop_atr_median")) for row in rows]
    go = _plotly_go()
    if go is None:
        return {"title": "stop_distance / ATR 中位数", "x": labels, "y": values}
    return go.Figure(
        data=[go.Bar(x=labels, y=values, marker={"color": "#2563eb"})],
        layout={"title": "stop_distance / ATR 中位数", "margin": {"l": 10, "r": 10, "t": 42, "b": 80}, "height": 320},
    )


def _safe_plotly_chart(st, figure, *, key: str) -> None:
    if figure is None:
        st.caption("暂无图表数据")
        return
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False}, key=key)


def _plotly_go():
    try:
        import plotly.graph_objects as go
    except ModuleNotFoundError:
        return None
    return go


def _snapshot_rows(snapshot, attribute: str) -> tuple[Mapping[str, object], ...]:
    rows = getattr(snapshot, attribute, ())
    if rows is None:
        return ()
    return tuple(rows)


def _summary(snapshot) -> Mapping[str, object]:
    summary = getattr(snapshot, "summary", {})
    if isinstance(summary, Mapping):
        return summary
    return {}


def _funnel_totals(rows: tuple[Mapping[str, object], ...]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        for key in (
            "windows_checked",
            "data_insufficient",
            "regime_not_computable",
            "regime_rejected",
            "price_action_rejected",
            "volume_price_rejected",
            "target_space_insufficient",
            "risk_rejected",
            "approved_signal",
        ):
            totals[key] = totals.get(key, 0) + _as_int(row.get(key))
    return totals


def _top_rejection_rows(snapshot, *, limit: int) -> tuple[dict[str, object], ...]:
    counts: dict[str, int] = {}
    for row in rejection_reason_top(_snapshot_rows(snapshot, "signal_funnel_rows"), top_n=50):
        reason = str(row.get("reason", ""))
        counts[reason] = counts.get(reason, 0) + _as_int(row.get("count"))
    for row in volume_reason_rows(_snapshot_rows(snapshot, "volume_rejection_rows")):
        reason = str(row.get("reason", ""))
        counts[reason] = counts.get(reason, 0) + _as_int(row.get("count"))
    for row in risk_reason_rows(_snapshot_rows(snapshot, "risk_rejection_rows")):
        reason = str(row.get("reason", ""))
        counts[reason] = counts.get(reason, 0) + _as_int(row.get("count"))

    return tuple(
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if reason and count > 0
    )[:limit]


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, tuple | list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return ", ".join(f"{key}={item}" for key, item in value.items())
    return str(value)


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


def _format_number(value: object) -> str:
    number = _as_float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def _as_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f5f7fa;
            color: #111827;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #dde3ea;
            border-radius: 8px;
            padding: 10px 12px;
        }
        div[data-testid="stMetricValue"] {
            color: #0f172a;
            font-size: 1.35rem;
        }
        div[data-testid="stMetricLabel"] {
            color: #475569;
            font-size: 0.84rem;
        }
        .p5-table-wrap {
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid #dde3ea;
            border-radius: 8px;
            margin: 8px 0 14px;
        }
        .p5-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }
        .p5-table th,
        .p5-table td {
            padding: 8px 10px;
            border-bottom: 1px solid #e7ecf2;
            text-align: left;
            vertical-align: top;
            white-space: nowrap;
        }
        .p5-table th {
            background: #eef3f8;
            color: #1f2937;
            font-weight: 650;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
