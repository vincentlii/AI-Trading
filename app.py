from __future__ import annotations

import html
from pathlib import Path

from trading_system.dashboard.panel import (
    DEFAULT_DB_PATH,
    DEFAULT_PRESET_PATH,
    DEFAULT_PROPOSALS_DIR,
    build_default_dashboard_snapshot,
)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="P5 Local Dashboard", layout="wide")
    _apply_style(st)

    st.title("P5 本地 Streamlit 看板")

    with st.sidebar:
        st.header("输入")
        preset_path = st.text_input("Preset", value=str(DEFAULT_PRESET_PATH))
        db_path = st.text_input("DuckDB", value=str(DEFAULT_DB_PATH))
        proposals_dir = st.text_input("Proposals", value=str(DEFAULT_PROPOSALS_DIR))
        refresh = st.button("刷新", type="primary")

    snapshot = _load_snapshot(
        preset_path=preset_path,
        db_path=db_path,
        proposals_dir=proposals_dir,
        refresh=refresh,
    )

    _render_overview(st, snapshot)
    tabs = st.tabs(("周期排名", "数据质量", "跳过扫描", "Proposal"))

    with tabs[0]:
        _render_table(st, snapshot.ranking_rows)

    with tabs[1]:
        _render_table(st, snapshot.quality_rows)

    with tabs[2]:
        _render_table(st, snapshot.skipped_run_rows)

    with tabs[3]:
        _render_table(st, snapshot.proposal_rows)


def _load_snapshot(*, preset_path: str, db_path: str, proposals_dir: str, refresh: bool):
    import streamlit as st

    @st.cache_data(show_spinner="加载本地回测与数据质量状态...")
    def cached_snapshot(preset_value: str, db_value: str, proposals_value: str):
        return build_default_dashboard_snapshot(
            preset_path=Path(preset_value),
            db_path=Path(db_value),
            proposals_dir=Path(proposals_value) if proposals_value else None,
        )

    if refresh:
        cached_snapshot.clear()
    return cached_snapshot(preset_path, db_path, proposals_dir)


def _render_overview(st, snapshot) -> None:
    st.caption(f"{snapshot.config_version} | {snapshot.config_fingerprint}")

    columns = st.columns(8)
    columns[0].metric("排名组", snapshot.summary["ranked_groups"])
    columns[1].metric("候选", snapshot.summary["candidates"])
    columns[2].metric("辅助", snapshot.summary["supporting_only"])
    columns[3].metric("淘汰", snapshot.summary["rejected"])
    columns[4].metric("净利润", f"{float(snapshot.summary['net_profit']):.2f}")
    columns[5].metric("数据失败", snapshot.summary["quality_failures"])
    columns[6].metric("跳过扫描", snapshot.summary["skipped_runs"])
    columns[7].metric("Proposal", snapshot.summary["proposals"])


def _render_table(st, rows: tuple[dict[str, object], ...]) -> None:
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


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, tuple | list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in value.items())
    return str(value)


def _apply_style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f7f8fa;
            color: #111827;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #dde3ea;
            border-radius: 8px;
            padding: 10px 12px;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem;
        }
        .p5-table-wrap {
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid #dde3ea;
            border-radius: 8px;
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
