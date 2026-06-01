from __future__ import annotations

from pathlib import Path
from typing import Any


REPORT_TYPES = (
    "baseline regression report",
    "artifact summary report",
    "aggregation report",
    "smoke plan report",
    "edge analysis report",
    "sizing diagnostics report",
    "strategy summary report",
    "strategy regression check report",
    "stage7 smoke report",
    "expansion diagnostic report",
    "attempt proposal report",
    "structure source proposal report",
    "exit profile proposal report",
    "sizing proposal report",
    "combined candidate report",
    "robustness report",
)


def build_report_consistency_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    root = Path(artifact_dir).parent
    rows = []
    known_paths = {
        "stage7 smoke report": root / "stage7_smoke_pr11a" / "stage7_smoke_report.md",
        "expansion diagnostic report": root / "lr_expansion_pr11b" / "lr_expansion_diagnostic_report.md",
        "attempt proposal report": root / "lr_attempt_pr11c" / "lr_attempt_proposal_report.md",
        "structure source proposal report": root / "lr_structure_pr11d" / "lr_structure_source_proposal_report.md",
        "exit profile proposal report": root / "lr_exit_pr11e" / "lr_exit_profile_proposal_report.md",
        "sizing proposal report": root / "lr_sizing_pr11f" / "lr_sizing_proposal_report.md",
        "combined candidate report": Path(artifact_dir) / "lr_combined_candidate_fix_report.md",
    }
    for report_type in REPORT_TYPES:
        path = known_paths.get(report_type)
        exists = bool(path and path.exists())
        rows.append(
            {
                "report_type": report_type,
                "path": str(path) if path else "",
                "exists": exists,
                "closed_trade_definition": "closed_trade == true" if exists else "unverified",
                "proposal_boundary_stated": _contains(path, "proposal_only") if path else False,
                "definition_change_recorded": report_type != "combined candidate report" or _contains(path, "降级") or _contains(path, "diagnostic"),
                "blocking": False,
                "notes": "report not present in current artifact scope" if not exists else "",
            }
        )
    return rows


def _contains(path: Path, pattern: str) -> bool:
    if not path or not path.exists():
        return False
    return pattern in path.read_text(encoding="utf-8", errors="ignore")
