from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.reports.trade_charts import discover_rows_path, render_trade_charts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Render generic strategy trade candlestick charts.")
    parser.add_argument("--db", default="storage/history.duckdb")
    parser.add_argument("--rows", default=None, help="Path to JSONL trade rows.")
    parser.add_argument("--run-dir", default=None, help="Research run directory; auto-discovers trade rows.")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--strategy", default="auto")
    parser.add_argument("--inst-id", default=None)
    parser.add_argument("--inst-type", default="SWAP")
    parser.add_argument("--bar", default="1H")
    parser.add_argument("--max-trades", type=int, default=None)
    parser.add_argument("--lookback-bars", type=int, default=24)
    parser.add_argument("--forward-bars", type=int, default=8)
    parser.add_argument("--window-anchor", choices=("exit", "entry"), default="entry")
    parser.add_argument("--include-unclosed-orders", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    rows_path = _resolve_rows_path(args.rows, args.run_dir)
    output_dir = _resolve_output_dir(args.output_dir, args.run_dir, rows_path)
    summary = render_trade_charts(
        db_path=_resolve_project_path(args.db),
        rows_path=rows_path,
        output_dir=output_dir,
        strategy=args.strategy,
        inst_id=args.inst_id,
        inst_type=args.inst_type,
        bar=args.bar,
        max_trades=args.max_trades,
        lookback_bars=args.lookback_bars,
        forward_bars=args.forward_bars,
        window_anchor=args.window_anchor,
        include_unclosed_orders=args.include_unclosed_orders,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["rendered_charts"] else 2


def _resolve_rows_path(rows: str | None, run_dir: str | None) -> Path:
    if rows:
        return _resolve_project_path(rows)
    if run_dir:
        return discover_rows_path(_resolve_project_path(run_dir))
    raise ValueError("either --rows or --run-dir is required")


def _resolve_output_dir(output_dir: str | None, run_dir: str | None, rows_path: Path) -> Path:
    if output_dir:
        return _resolve_project_path(output_dir)
    if run_dir:
        return _resolve_project_path(run_dir) / "trade_charts"
    return rows_path.parent / "trade_charts"


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
