from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from scripts.run_tc_bp_strict_causal_smoke import ReadOnlyDuckDbCandleRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    events = [json.loads(line) for line in Path(args.events).read_text(encoding="utf-8").splitlines() if line]
    events = sorted(events, key=lambda row: hashlib.sha256(row["event_id"].encode()).hexdigest())[:20]
    repository = ReadOnlyDuckDbCandleRepository(Path(args.db))
    canvas = Image.new("RGB", (1600, 1200), "white")
    draw = ImageDraw.Draw(canvas)
    for index, event in enumerate(events):
        left = (index % 4) * 400
        top = (index // 4) * 240
        _draw_panel(draw, repository, event, left, top)
    canvas.save(args.output)
    print(args.output)
    return 0


def _draw_panel(draw, repository, event, left: int, top: int) -> None:
    signal = int(event["signal_time"])
    hour = 60 * 60 * 1000
    rows = repository.load_range(event["instrument"], "15m", signal - 24 * hour, signal + 12 * hour, inst_type="SWAP")
    if not rows:
        return
    plot_left, plot_top, width, height = left + 30, top + 28, 350, 180
    low = min(row.low for row in rows)
    high = max(row.high for row in rows)
    span = max(high - low, 1e-9)
    x_step = width / max(len(rows), 1)
    y = lambda price: plot_top + height - (price - low) / span * height
    draw.text((left + 6, top + 4), f"{event['instrument'][:3]} {event['direction']} {event['setup'][7:14]}", fill="black")
    for i, row in enumerate(rows):
        x = plot_left + (i + 0.5) * x_step
        color = "#17855b" if row.close >= row.open else "#c84343"
        draw.line((x, y(row.low), x, y(row.high)), fill=color, width=1)
        draw.rectangle((x - max(1, x_step * 0.3), y(max(row.open, row.close)), x + max(1, x_step * 0.3), y(min(row.open, row.close))), outline=color, fill=color)
    for price, color in ((float(event["level_price"]), "#2d5fb3"), (float(event["invalidation"]), "#c84343"), (float(event["signal_price"]), "#17855b")):
        draw.line((plot_left, y(price), plot_left + width, y(price)), fill=color, width=1)
    signal_index = min(range(len(rows)), key=lambda i: abs(rows[i].timestamp_ms - signal))
    x = plot_left + (signal_index + 0.5) * x_step
    draw.line((x, plot_top, x, plot_top + height), fill="#111111", width=1)
    draw.rectangle((plot_left, plot_top, plot_left + width, plot_top + height), outline="#aaaaaa")


if __name__ == "__main__":
    raise SystemExit(main())
