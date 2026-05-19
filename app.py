from __future__ import annotations

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
        st.dataframe(snapshot.ranking_rows, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.dataframe(snapshot.quality_rows, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.dataframe(snapshot.skipped_run_rows, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.dataframe(snapshot.proposal_rows, use_container_width=True, hide_index=True)


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
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
