from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_system.reports.lr_regression_baseline import (
    DEFAULT_BASELINE_DIR,
    export_lr_regression_baseline,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the current liquidity_reversal Stage 6E regression baseline."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_BASELINE_DIR),
        help="Directory for key_metrics.json, baseline_manifest.json, and report snapshots.",
    )
    args = parser.parse_args()

    result = export_lr_regression_baseline(Path(args.output_dir))
    manifest = result["manifest"]
    print(f"baseline_dir={manifest['baseline_dir']}")
    print("artifacts:")
    print("- key_metrics.json")
    print("- baseline_manifest.json")
    for snapshot in manifest["snapshots"].values():
        print(f"- {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
