from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path


def build_diagnostics_markdown(
    *,
    mode: str,
    scanned_windows: int,
    raw_candidates_count: int,
    filter_rows: Sequence[Mapping[str, object]],
    execution_rows: Sequence[Mapping[str, object]],
    cache_manifest: Mapping[str, object],
) -> str:
    rejects = Counter(str(row.get("reject_reason", "")) for row in filter_rows if row.get("reject_reason"))
    groups: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for row in filter_rows:
        key = (
            str(row.get("asset", "")),
            str(row.get("profile", "")),
            str(row.get("setup", "")),
            str(row.get("direction", "")),
        )
        groups[key] += 1

    lines = [
        "# Proposal Diagnostics",
        "",
        f"- mode: `{mode}`",
        f"- scanned_windows: `{scanned_windows}`",
        f"- raw_candidates_count: `{raw_candidates_count}`",
        f"- filter_rows: `{len(filter_rows)}`",
        f"- execution_rows: `{len(execution_rows)}`",
        f"- context_cache_status: `{cache_manifest.get('context_cache_status', '')}`",
        f"- raw_candidate_cache_status: `{cache_manifest.get('raw_candidate_cache_status', '')}`",
        f"- filter_cache_status: `{cache_manifest.get('filter_cache_status', '')}`",
        f"- execution_cache_status: `{cache_manifest.get('execution_cache_status', '')}`",
        "",
        "## Reject Reasons",
        "",
    ]
    if rejects:
        lines.extend(f"- {reason}: {count}" for reason, count in rejects.most_common(20))
    else:
        lines.append("- none")
    lines.extend(["", "## Candidate Groups", ""])
    if groups:
        for (asset, profile, setup, direction), count in sorted(groups.items()):
            lines.append(f"- {asset}/{profile}/{setup}/{direction}: {count}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_diagnostics_report(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


__all__ = ("build_diagnostics_markdown", "write_diagnostics_report")
