from __future__ import annotations

from pathlib import Path


PATTERNS = (
    ("summary_rows_as_closed_rows", "closed_trades", "medium"),
    ("proposal_only_default", "proposal_only=True", "medium"),
    ("missing_field_default_zero", " or 0", "medium"),
    ("markdown_metric_source", ".md", "low"),
    ("selected_without_execution", "selected_without_closed", "medium"),
)


def build_code_logic_review_rows(root: Path) -> list[dict[str, object]]:
    rows = []
    for path in sorted(Path(root).glob("research_pipeline/**/*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for risk_type, pattern, severity in PATTERNS:
            if pattern not in text:
                continue
            rows.append(
                {
                    "risky_file": str(path),
                    "risky_function": "",
                    "risk_type": risk_type,
                    "severity": severity,
                    "fix_required": severity == "high",
                    "fix_applied": False,
                    "notes": f"pattern '{pattern}' present; review required before robustness if used in performance path",
                }
            )
    if not rows:
        rows.append(
            {
                "risky_file": "",
                "risky_function": "",
                "risk_type": "none",
                "severity": "none",
                "fix_required": False,
                "fix_applied": False,
                "notes": "no configured risky pattern found",
            }
        )
    return rows
