from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import html


EMPTY_TEXT = "\u6682\u65e0\u6570\u636e"
READ_ONLY_TITLE = "\u53ea\u8bfb\u770b\u677f"
READ_ONLY_MESSAGE = (
    "\u672c\u9875\u4ec5\u8bfb\u53d6\u672c\u5730 DuckDB \u3001\u56de\u6d4b snapshot "
    "\u548c Proposal \u961f\u5217\uff0c\u4e0d\u63d0\u4f9b\u4ea4\u6613\u6216\u81ea\u52a8\u5e94\u7528\u5165\u53e3\u3002"
)


@dataclass(frozen=True)
class StatusCardSpec:
    label: str
    summary_key: str
    default: object = "\u2014"
    help_text: str | None = None
    formatter: Callable[[object], object] | None = None


def apply_dashboard_component_style(st) -> None:
    st.markdown(
        """
        <style>
        .p5-section-header,
        .p5-readonly-notice,
        .p5-metric-notes {
            background: #ffffff;
            border: 1px solid #dde3ea;
            border-radius: 8px;
            padding: 12px 14px;
            margin: 8px 0 12px;
        }
        .p5-section-header h2 {
            color: #111827;
            font-size: 1.1rem;
            line-height: 1.35;
            margin: 0;
            letter-spacing: 0;
        }
        .p5-section-header p,
        .p5-readonly-notice p,
        .p5-metric-notes p,
        .p5-table-note {
            color: #4b5563;
            font-size: 0.88rem;
            line-height: 1.55;
            margin: 6px 0 0;
        }
        .p5-readonly-notice strong,
        .p5-metric-notes strong {
            color: #111827;
        }
        .p5-table-wrap {
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid #dde3ea;
            border-radius: 8px;
            margin-top: 8px;
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
            color: #111827;
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


def render_section_header(st, title: str, description: str | None = None) -> None:
    body = f"<h2>{_escape(title)}</h2>"
    if description:
        body += f"<p>{_escape(description)}</p>"
    st.markdown(
        f'<div class="p5-section-header" style="background: #ffffff;">{body}</div>',
        unsafe_allow_html=True,
    )


def render_read_only_notice(st, message: str = READ_ONLY_MESSAGE) -> None:
    st.markdown(
        (
            '<div class="p5-readonly-notice" style="background: #ffffff;">'
            f"<strong>{READ_ONLY_TITLE}</strong>"
            f"<p>{_escape(message)}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_summary_status_cards(
    st,
    snapshot,
    specs: Sequence[StatusCardSpec],
) -> None:
    summary = _snapshot_summary(snapshot)
    values = []
    for spec in specs:
        value = summary.get(spec.summary_key, spec.default)
        if spec.formatter is not None:
            value = spec.formatter(value)
        values.append(
            {
                "label": spec.label,
                "value": value,
                "help_text": spec.help_text,
            }
        )
    render_status_cards(st, values)


def render_status_cards(st, cards: Sequence[Mapping[str, object]]) -> None:
    if not cards:
        st.caption(EMPTY_TEXT)
        return

    columns = st.columns(len(cards))
    for column, card in zip(columns, cards, strict=False):
        column.metric(
            str(card.get("label", "")),
            card.get("value", "\u2014"),
            help=card.get("help_text") or None,
        )


def render_table_container(
    st,
    rows: Sequence[Mapping[str, object]],
    *,
    trace_note: str | None = None,
    empty_text: str = EMPTY_TEXT,
) -> None:
    if not rows:
        st.caption(empty_text)
        return

    columns = tuple(rows[0].keys())
    header = "".join(f"<th>{_escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_escape(_format_cell(row.get(column)))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")

    note = f'<p class="p5-table-note">{_escape(trace_note)}</p>' if trace_note else ""
    st.markdown(
        (
            '<div class="p5-table-wrap">'
            '<table class="p5-table">'
            f"<thead><tr>{header}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
            "</table>"
            "</div>"
            f"{note}"
        ),
        unsafe_allow_html=True,
    )


def render_metric_notes(st, notes: Sequence[tuple[str, str]]) -> None:
    rows = "".join(f"<p><strong>{_escape(title)}</strong>: {_escape(text)}</p>" for title, text in notes)
    st.markdown(
        f'<div class="p5-metric-notes"><strong>\u6307\u6807\u8bf4\u660e</strong>{rows}</div>',
        unsafe_allow_html=True,
    )


def render_lazy_area(st, label: str, renderer: Callable[[], None], *, expanded: bool = False) -> None:
    with st.expander(label, expanded=expanded):
        renderer()


def snapshot_rows(snapshot, attribute: str) -> tuple[Mapping[str, object], ...]:
    rows = getattr(snapshot, attribute, ())
    if rows is None:
        return ()
    return tuple(rows)


def _snapshot_summary(snapshot) -> Mapping[str, object]:
    summary = getattr(snapshot, "summary", {})
    if isinstance(summary, Mapping):
        return summary
    return {}


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


def _escape(value: object) -> str:
    return html.escape(str(value))
