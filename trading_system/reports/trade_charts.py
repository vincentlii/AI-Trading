from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import tomllib

from trading_system.data.history import DuckDbCandleRepository


TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1H": 60 * 60_000,
    "4H": 4 * 60 * 60_000,
    "1D": 24 * 60 * 60_000,
}

DEFAULT_ROW_TYPES = ("closed_trade", "shadow_pre_risk_closed_trade")


def discover_rows_path(run_dir: str | Path) -> Path:
    directory = Path(run_dir)
    for filename in (
        "closed_trade_rows.jsonl",
        "execution_results.jsonl",
        "minimal_lr_v0_execution_results.jsonl",
        "shadow_pre_risk_rows.jsonl",
    ):
        candidate = directory / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no supported trade rows file found under {directory}")


def render_trade_charts(
    *,
    db_path: Path,
    rows_path: Path,
    output_dir: Path,
    strategy: str = "auto",
    inst_id: str | None = None,
    inst_type: str = "SWAP",
    bar: str = "1H",
    max_trades: int | None = None,
    lookback_bars: int = 24,
    forward_bars: int = 8,
    window_anchor: str = "exit",
    row_types: tuple[str, ...] | None = None,
    include_unclosed_orders: bool = False,
    config_window: dict[str, object] | None = None,
) -> dict[str, object]:
    rows = _load_replay_rows(
        rows_path,
        row_types=row_types or DEFAULT_ROW_TYPES,
        include_unclosed_orders=include_unclosed_orders,
    )
    if max_trades is not None:
        rows = rows[:max_trades]
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_previous_render(output_dir)
    repo = DuckDbCandleRepository(db_path)
    rendered: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    missing_zone_rows = 0
    missing_price_level_rows = 0

    for index, raw_row in enumerate(rows, start=1):
        row = normalize_trade_row(raw_row, strategy=strategy, inst_id=inst_id, inst_type=inst_type)
        if row.get("entry_zone_low") is None or row.get("entry_zone_high") is None:
            missing_zone_rows += 1
        if row.get("entry_price") is None or row.get("stop") is None or row.get("target") is None:
            missing_price_level_rows += 1
        row_inst_id = str(row.get("inst_id") or inst_id or "")
        if not row_inst_id:
            skipped.append({"candidate_id": row.get("candidate_id"), "reason": "missing_inst_id"})
            continue
        candles = _load_chart_candles(
            repo,
            row,
            inst_id=row_inst_id,
            inst_type=str(row.get("inst_type") or inst_type),
            bar=bar,
            lookback_bars=lookback_bars,
            forward_bars=forward_bars,
            window_anchor=window_anchor,
        )
        if not candles:
            skipped.append({"candidate_id": row.get("candidate_id"), "inst_id": row_inst_id, "reason": "no_candles"})
            continue
        filename = f"{index:03d}_{_safe_name(str(row.get('candidate_id') or row.get('trade_id') or row.get('event_id') or 'trade'))}.svg"
        svg = build_trade_chart_svg(candles, row, title=f"{index:03d} {row.get('candidate_id', '')}")
        path = output_dir / filename
        path.write_text(svg, encoding="utf-8")
        rendered.append(
            {
                "candidate_id": row.get("candidate_id"),
                "trade_id": row.get("trade_id"),
                "direction": row.get("direction"),
                "exit_reason": row.get("exit_reason") or row.get("reason_code"),
                "net_R": row.get("net_R"),
                "mfe_R": row.get("mfe_R") or row.get("mfe_r") or row.get("MFE_R"),
                "mae_R": row.get("mae_R") or row.get("mae_r") or row.get("MAE_R"),
                "path": str(path),
                "inst_id": row_inst_id,
            }
        )

    index_path = output_dir / "index.html"
    index_path.write_text(_build_index_html(rendered, skipped), encoding="utf-8")
    summary = {
        "rows_path": str(rows_path),
        "output_dir": str(output_dir),
        "index_html": str(index_path),
        "selected_rows": len(rows),
        "rendered_charts": len(rendered),
        "skipped": skipped,
        "include_unclosed_orders": include_unclosed_orders,
        "strategy": strategy,
        "bar": bar,
        "lookback_bars": lookback_bars,
        "forward_bars": forward_bars,
        "window_anchor": window_anchor,
        "config_window": config_window,
        "missing_zone_rows": missing_zone_rows,
        "missing_price_level_rows": missing_price_level_rows,
    }
    (output_dir / "chart_render_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def normalize_trade_row(
    row: dict[str, object],
    *,
    strategy: str = "auto",
    inst_id: str | None = None,
    inst_type: str = "SWAP",
) -> dict[str, object]:
    normalized = dict(row)
    normalized["strategy_chart_style"] = _infer_strategy(row, strategy)
    normalized["inst_id"] = row.get("inst_id") or inst_id or _infer_inst_id(row)
    normalized["inst_type"] = row.get("inst_type") or inst_type
    normalized["entry_time"] = row.get("fill_time") or row.get("entry_time") or row.get("signal_time")
    normalized["entry_price"] = _first_value(row, ("entry_price", "fill_price", "limit_price", "actual_entry_price_if_simulated"))
    normalized["exit_price"] = _first_value(row, ("exit_price",))
    normalized["stop"] = _first_value(row, ("stop", "stop_price", "initial_stop_price", "stop_loss"))
    normalized["target"] = _first_value(row, ("target", "target_price"))
    normalized["entry_zone_low"] = _first_value(row, ("entry_zone_low", "zone_low", "pullback_zone_low", "retest_zone_low"))
    normalized["entry_zone_high"] = _first_value(row, ("entry_zone_high", "zone_high", "pullback_zone_high", "retest_zone_high"))
    return normalized


def build_trade_chart_svg(candles, row: dict[str, object], *, title: str) -> str:
    width = 2240
    height = 680
    margin_left = 80
    margin_right = 250
    margin_top = 64
    margin_bottom = 86
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    prices = []
    for candle in candles:
        prices.extend([float(candle.high), float(candle.low)])
    for key in ("entry_zone_low", "entry_zone_high", "entry_price", "stop", "target", "exit_price"):
        value = row.get(key)
        if value is not None:
            prices.append(float(value))
    low_price = min(prices)
    high_price = max(prices)
    padding = max((high_price - low_price) * 0.08, 1e-9)
    low_price -= padding
    high_price += padding

    def x_for(i: int) -> float:
        if len(candles) == 1:
            return margin_left + plot_width / 2
        return margin_left + i * (plot_width / (len(candles) - 1))

    def y_for(price: float) -> float:
        return margin_top + (high_price - price) / (high_price - low_price) * plot_height

    ts_to_index = {int(candle.timestamp_ms): i for i, candle in enumerate(candles)}
    body_width = max(4.0, min(18.0, plot_width / max(len(candles), 1) * 0.55))
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="{margin_left}" y="30" font-family="Arial" font-size="18" font-weight="700" fill="#111827">{_xml(title)}</text>',
        f'<text x="{margin_left}" y="52" font-family="Arial" font-size="12" fill="#475569">{_xml(_subtitle(row))}</text>',
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#ffffff" stroke="#cbd5e1"/>',
    ]
    zone_low = _optional_float(row.get("entry_zone_low"))
    zone_high = _optional_float(row.get("entry_zone_high"))
    if zone_low is not None and zone_high is not None:
        y_top = y_for(max(zone_low, zone_high))
        y_bottom = y_for(min(zone_low, zone_high))
        zone_height = y_bottom - y_top
        if zone_height < 8.0:
            zone_mid_y = (y_top + y_bottom) / 2.0
            y_top = zone_mid_y - 4.0
            zone_height = 8.0
        elements.append(
            f'<rect x="{margin_left}" y="{y_top:.2f}" width="{plot_width}" height="{zone_height:.2f}" '
            'fill="#dbeafe" opacity="0.65" data-zone-band="true"/>'
        )

    for price in _price_ticks(low_price, high_price, 6):
        y = y_for(price)
        elements.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" stroke="#e2e8f0"/>')
        elements.append(f'<text x="{margin_left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#64748b">{price:.2f}</text>')

    for i, candle in enumerate(candles):
        x = x_for(i)
        open_y = y_for(float(candle.open))
        close_y = y_for(float(candle.close))
        high_y = y_for(float(candle.high))
        low_y = y_for(float(candle.low))
        color = "#16a34a" if float(candle.close) >= float(candle.open) else "#dc2626"
        body_y = min(open_y, close_y)
        body_h = max(1.0, abs(close_y - open_y))
        elements.append(f'<line x1="{x:.2f}" y1="{high_y:.2f}" x2="{x:.2f}" y2="{low_y:.2f}" stroke="{color}" stroke-width="1.4"/>')
        elements.append(f'<rect x="{x - body_width / 2:.2f}" y="{body_y:.2f}" width="{body_width:.2f}" height="{body_h:.2f}" fill="{color}" opacity="0.85"/>')

    for label, key, color in (
        ("entry", "entry_price", "#0f766e"),
        ("stop", "stop", "#dc2626"),
        ("target", "target", "#16a34a"),
    ):
        value = _optional_float(row.get(key))
        if value is not None:
            elements.extend(_horizontal_line(label, value, color, margin_left, plot_width, y_for))

    elements.extend(_event_markers(row, candles, ts_to_index, x_for, margin_top, plot_height))
    elements.extend(_trade_arrow_markers(row, candles, ts_to_index, x_for, y_for, low_price, high_price))

    for i in _time_label_indices(len(candles)):
        x = x_for(i)
        text = _format_ts(candles[i].timestamp_ms)
        elements.append(f'<text x="{x:.2f}" y="{height - 44}" text-anchor="middle" font-family="Arial" font-size="10" fill="#64748b">{_xml(text)}</text>')

    legend_x = margin_left + plot_width + 24
    elements.append(f'<text x="{legend_x}" y="{margin_top}" font-family="Arial" font-size="14" font-weight="700" fill="#111827">Trade</text>')
    for offset, (name, value) in enumerate(_legend_rows(row), start=1):
        y = margin_top + offset * 24
        elements.append(f'<text x="{legend_x}" y="{y}" font-family="Arial" font-size="12" fill="#334155">{_xml(name)}: {_xml(value)}</text>')

    elements.append("</svg>")
    return "\n".join(elements)


def chart_window_from_config(config_path: Path, *, variant_id: str | None, bar: str) -> dict[str, object]:
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    chart = data.get("chart_replay", {})
    variants = data.get("variants", {})
    selected_variant_id = variant_id or str(data.get("recommended_primary_variant"))
    if selected_variant_id not in variants:
        known = ", ".join(str(key) for key in variants)
        raise ValueError(f"unknown variant_id for chart replay: {selected_variant_id}; known: {known}")
    variant = variants[selected_variant_id]
    entry_timeframe = str(variant["entry_timeframe"])
    entry_minutes = max(_timeframe_minutes(entry_timeframe), 1)
    pre_entry_units = int(chart.get("pre_entry_units", 8))
    post_entry_units = int(chart.get("post_entry_units", 28))
    bar_minutes = max(_timeframe_minutes(bar), 1)
    pre_minutes = pre_entry_units * entry_minutes
    post_minutes = post_entry_units * entry_minutes
    return {
        "variant_id": selected_variant_id,
        "entry_timeframe": entry_timeframe,
        "bar": bar,
        "pre_entry_units": pre_entry_units,
        "post_entry_units": post_entry_units,
        "pre_entry_hours": pre_minutes / 60,
        "post_entry_hours": post_minutes / 60,
        "lookback_bars": max(1, int(round(pre_minutes / bar_minutes))),
        "forward_bars": max(1, int(round(post_minutes / bar_minutes))),
        "window_anchor": str(chart.get("window_anchor", "entry")),
    }


def _load_replay_rows(
    path: Path,
    *,
    row_types: tuple[str, ...],
    include_unclosed_orders: bool,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    orders: list[dict[str, object]] = []
    wanted = set(row_types)
    if include_unclosed_orders:
        wanted.add("shadow_pre_risk_order")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row_type = str(row.get("row_type") or "")
        if row_type not in wanted:
            continue
        if row_type == "shadow_pre_risk_order":
            orders.append(row)
            continue
        if row.get("exit_time") is None:
            continue
        selected.append(row)
    closed_ids = {str(row.get("candidate_id")) for row in selected}
    return selected + [row for row in orders if str(row.get("candidate_id")) not in closed_ids]


def _load_chart_candles(repo, row: dict[str, object], *, inst_id: str, inst_type: str, bar: str, lookback_bars: int, forward_bars: int, window_anchor: str):
    signal_time = int(row.get("signal_time") or row.get("decision_time") or row.get("entry_time") or 0)
    entry_time = int(row.get("entry_time") or signal_time)
    exit_time = int(row.get("exit_time") or signal_time)
    bar_ms = TIMEFRAME_MS.get(bar, 60 * 60_000)
    start_ms = entry_time - lookback_bars * bar_ms
    if window_anchor == "entry":
        end_ms = entry_time + forward_bars * bar_ms
    else:
        end_ms = max(exit_time, signal_time) + forward_bars * bar_ms
    return repo.load_range(inst_id, bar, start_ms, end_ms, inst_type=inst_type, confirmed_only=True)


def _clear_previous_render(output_dir: Path) -> None:
    for path in output_dir.glob("*.svg"):
        if path.is_file():
            path.unlink()
    for filename in ("index.html", "chart_render_summary.json"):
        path = output_dir / filename
        if path.is_file():
            path.unlink()


def _infer_strategy(row: dict[str, object], strategy: str) -> str:
    if strategy != "auto":
        return strategy
    keys = set(row)
    if "touch_event_time" in keys or "zone_id" in keys:
        return "vincent"
    if "breakout_time" in keys or "pullback_confirmed_time" in keys:
        return "trend_continuation_family"
    if "sweep_time" in keys or "reclaim_time" in keys:
        return "liquidity_reversal"
    return "generic"


def _infer_inst_id(row: dict[str, object]) -> str:
    symbol = str(row.get("symbol") or "")
    if symbol:
        base = symbol.split("/")[0].split("-")[0].upper()
        quote = "USDT" if "USDT" in symbol.upper() else "USDT"
        return f"{base}-{quote}-SWAP"
    asset = str(row.get("asset") or "").upper()
    if asset:
        return f"{asset}-USDT-SWAP"
    return ""


def _first_value(row: dict[str, object], keys: tuple[str, ...]):
    for key in keys:
        if row.get(key) is not None:
            return row.get(key)
    return None


def _horizontal_line(label: str, value: float, color: str, margin_left: int, plot_width: int, y_for) -> list[str]:
    y = y_for(value)
    x2 = margin_left + plot_width
    return [
        f'<line x1="{margin_left}" y1="{y:.2f}" x2="{x2}" y2="{y:.2f}" stroke="{color}" stroke-width="1.5" stroke-dasharray="6 4"/>',
        f'<text x="{x2 + 8}" y="{y + 4:.2f}" font-family="Arial" font-size="11" fill="{color}">{_xml(label)} {value:.2f}</text>',
    ]


def _event_markers(row: dict[str, object], candles, ts_to_index: dict[int, int], x_for, margin_top: int, plot_height: int) -> list[str]:
    elements: list[str] = []
    for label, key, color in _event_specs(str(row.get("strategy_chart_style") or "")):
        index = _nearest_index(ts_to_index, candles, row.get(key))
        if index is None:
            continue
        x = x_for(index)
        elements.append(
            f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{margin_top + plot_height}" stroke="{color}" stroke-width="1" stroke-dasharray="2 4" opacity="0.55" data-event-marker="{_xml(label)}"/>'
        )
        elements.append(f'<text x="{x + 4:.2f}" y="{margin_top + 14}" font-family="Arial" font-size="10" fill="{color}" data-event-marker="{_xml(label)}">{_xml(label)}</text>')
    return elements


def _event_specs(strategy: str) -> tuple[tuple[str, str, str], ...]:
    if strategy == "vincent":
        return ()
    if strategy == "liquidity_reversal":
        return (
            ("structure", "structure_confirmed_time", "#64748b"),
            ("sweep", "sweep_time", "#7c3aed"),
            ("reclaim", "reclaim_time", "#2563eb"),
            ("signal", "signal_time", "#0f766e"),
        )
    if strategy in {"trend_continuation", "trend_continuation_family", "breakout_pullback", "compression_expansion"}:
        return (
            ("trend", "trend_confirmed_time", "#64748b"),
            ("breakout", "breakout_time", "#7c3aed"),
            ("pullback", "pullback_confirmed_time", "#2563eb"),
            ("confirm", "confirmation_time", "#0f766e"),
            ("signal", "signal_time", "#0f766e"),
        )
    if strategy == "generic":
        return (("signal", "signal_time", "#0f766e"),)
    return ()


def _trade_arrow_markers(row: dict[str, object], candles, ts_to_index: dict[int, int], x_for, y_for, low_price: float, high_price: float) -> list[str]:
    direction = str(row.get("direction") or "").lower()
    entry_index = _nearest_index(ts_to_index, candles, row.get("entry_time") or row.get("signal_time"))
    exit_index = _nearest_index(ts_to_index, candles, row.get("exit_time"))
    elements: list[str] = []
    if entry_index is not None:
        entry_above = direction == "short"
        elements.append(_arrow_marker(x=x_for(entry_index), y=_marker_y(candles[entry_index], y_for, low_price, high_price, above=entry_above), above=entry_above, color="#16a34a", label="entry"))
    if exit_index is not None:
        exit_above = direction != "short"
        elements.append(_arrow_marker(x=x_for(exit_index), y=_marker_y(candles[exit_index], y_for, low_price, high_price, above=exit_above), above=exit_above, color="#dc2626", label="exit"))
    return elements


def _nearest_index(ts_to_index: dict[int, int], candles, ts_ms) -> int | None:
    if ts_ms is None:
        return None
    ts = int(ts_ms)
    if ts in ts_to_index:
        return ts_to_index[ts]
    if not candles:
        return None
    distances = [(abs(int(candle.timestamp_ms) - ts), index) for index, candle in enumerate(candles)]
    return min(distances, key=lambda item: item[0])[1]


def _marker_y(candle, y_for, low_price: float, high_price: float, *, above: bool) -> float:
    offset = max((high_price - low_price) * 0.025, 1e-9)
    price = float(candle.high) + offset if above else float(candle.low) - offset
    return y_for(price)


def _arrow_marker(*, x: float, y: float, above: bool, color: str, label: str) -> str:
    size = 9.0
    if above:
        points = ((x, y + size), (x - size * 0.7, y - size * 0.2), (x + size * 0.7, y - size * 0.2))
    else:
        points = ((x, y - size), (x - size * 0.7, y + size * 0.2), (x + size * 0.7, y + size * 0.2))
    points_text = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
    return f'<polygon points="{points_text}" fill="{color}" stroke="#ffffff" stroke-width="1.2" data-trade-marker="{_xml(label)}"/>'


def _price_ticks(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [low]
    step = (high - low) / (count - 1)
    return [low + i * step for i in range(count)]


def _time_label_indices(count: int) -> list[int]:
    if count <= 1:
        return [0] if count else []
    return sorted({0, count - 1, count // 4, count // 2, (count * 3) // 4})


def _legend_rows(row: dict[str, object]) -> list[tuple[str, str]]:
    return [
        ("candidate", str(row.get("candidate_id") or "")),
        ("trade", str(row.get("trade_id") or "")),
        ("side", str(row.get("direction") or "").upper()),
        ("exit", str(row.get("exit_reason") or row.get("reason_code") or "")),
        ("net_R", _fmt(row.get("net_R"))),
        ("MFE_R", _fmt(row.get("MFE_R") or row.get("mfe_R"))),
        ("MAE_R", _fmt(row.get("MAE_R") or row.get("mae_R"))),
    ]


def _subtitle(row: dict[str, object]) -> str:
    return (
        f"{str(row.get('direction') or '').upper()} | "
        f"signal={_format_ts(row.get('signal_time'))} | "
        f"entry={_format_ts(row.get('entry_time'))} | "
        f"exit={_format_ts(row.get('exit_time'))} | "
        f"{row.get('exit_reason') or row.get('reason_code') or ''}"
    )


def _build_index_html(rendered: list[dict[str, object]], skipped: list[dict[str, object]]) -> str:
    rows = []
    for item in rendered:
        path = Path(str(item["path"]))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('candidate_id') or ''))}</td>"
            f"<td>{html.escape(str(item.get('inst_id') or ''))}</td>"
            f"<td>{html.escape(str(item.get('direction') or ''))}</td>"
            f"<td>{html.escape(str(item.get('exit_reason') or ''))}</td>"
            f"<td>{html.escape(_fmt(item.get('net_R')))}</td>"
            f"<td>{html.escape(_fmt(item.get('mfe_R')))}</td>"
            f"<td>{html.escape(_fmt(item.get('mae_R')))}</td>"
            f'<td><a href="{html.escape(path.name)}">svg</a></td>'
            "</tr>"
        )
    skipped_rows = "".join(f"<li>{html.escape(str(item))}</li>" for item in skipped)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Trade Charts</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;color:#111827}table{border-collapse:collapse}"
        "td,th{border:1px solid #cbd5e1;padding:6px 10px}th{background:#f1f5f9}</style></head><body>"
        "<h1>Trade Charts</h1>"
        "<table><thead><tr><th>candidate</th><th>inst</th><th>side</th><th>exit</th><th>net_R</th><th>MFE_R</th><th>MAE_R</th><th>chart</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<h2>Skipped</h2><ul>{skipped_rows}</ul>"
        "</body></html>"
    )


def _timeframe_minutes(value: str) -> int:
    if value.endswith("m"):
        return int(value[:-1])
    if value.endswith("H"):
        return int(value[:-1]) * 60
    if value.endswith("D"):
        return int(value[:-1]) * 1440
    if value.endswith("W"):
        return int(value[:-1]) * 10080
    return 1


def _format_ts(ts_ms) -> str:
    if ts_ms in (None, ""):
        return "n/a"
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _optional_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:80]


def _xml(value: object) -> str:
    return html.escape(str(value), quote=True)
