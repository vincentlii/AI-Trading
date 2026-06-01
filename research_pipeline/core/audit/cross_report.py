from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_cross_report_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    root = Path(artifact_dir).parent
    rows = []
    original = _load_json(root / "lr_combined_pr11g" / "lr_combined_candidate_result.json")
    fixed = _load_json(Path(artifact_dir) / "lr_combined_candidate_fix_result.json")
    if original and fixed:
        original_base = _portfolio_row(original.get("portfolio_rows", []), "ALL", "base")
        fixed_b = _variant_row(fixed.get("variant_rows", []), "Variant B - Tier 1 + Positive Tier 2", "ALL", "base")
        if original_base and fixed_b:
            rows.append(
                {
                    "scope": "Variant B",
                    "metric_name": "closed_trades",
                    "old_value": original_base.get("closed_trades"),
                    "new_value": fixed_b.get("closed_trades"),
                    "metric_changed_reason": "PR11G-fix pruned unmapped dynamic combo and negative Tier 2; Variant B is no longer full original family.",
                    "old_definition": "Full original PR11G combined family",
                    "new_definition": "Tier 1 + positive Tier 2 only",
                    "acceptable": True,
                }
            )
            rows.append(
                {
                    "scope": "Variant B",
                    "metric_name": "total_net_R",
                    "old_value": original_base.get("total_net_R"),
                    "new_value": fixed_b.get("total_net_R"),
                    "metric_changed_reason": "Low-quality Tier 2 was removed; positive Tier 2 kept as increment.",
                    "old_definition": "Full original PR11G combined family",
                    "new_definition": "Tier 1 + positive Tier 2 only",
                    "acceptable": True,
                }
            )
    for stage_name, path in (
        ("PR11C attempt", root / "lr_attempt_pr11c" / "lr_attempt_proposal_result.json"),
        ("PR11D structure", root / "lr_structure_pr11d" / "lr_structure_source_proposal_result.json"),
        ("PR11E exit", root / "lr_exit_pr11e" / "lr_exit_profile_proposal_result.json"),
        ("PR11F sizing", root / "lr_sizing_pr11f" / "lr_sizing_proposal_result.json"),
    ):
        rows.append(
            {
                "scope": stage_name,
                "metric_name": "artifact_presence",
                "old_value": None,
                "new_value": path.exists(),
                "metric_changed_reason": "" if path.exists() else "source artifact missing for cross-report consistency check",
                "old_definition": "upstream proposal stage",
                "new_definition": "audit source availability",
                "acceptable": path.exists(),
            }
        )
    return rows


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _portfolio_row(rows: list[dict[str, Any]], tier: str, cost_tier: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("tier") == tier and row.get("cost_tier") == cost_tier:
            return row
    return None


def _variant_row(rows: list[dict[str, Any]], variant_name: str, tier: str, cost_tier: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("variant_name") == variant_name and row.get("tier") == tier and row.get("cost_tier") == cost_tier:
            return row
    return None
