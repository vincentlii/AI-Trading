from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegressionSummary:
    strategy: str
    window: str
    counts: dict[str, int]
    selected_smoke_combos: list[str]
    displacement_after_reclaim: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "window": self.window,
            "counts": self.counts,
            "selected_smoke_combos": self.selected_smoke_combos,
            "displacement_after_reclaim": self.displacement_after_reclaim,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def as_markdown(self) -> str:
        displacement = self.displacement_after_reclaim
        lines = [
            f"# Regression Summary: {self.strategy}",
            "",
            f"- window: {self.window}",
            f"- fresh_candidates: {self.counts['fresh_candidates']}",
            f"- formal_approved: {self.counts['formal_approved']}",
            f"- proposal_approved: {self.counts['proposal_approved']}",
            f"- closed_trades: {self.counts['closed_trades']}",
            f"- selected_smoke_combos: {', '.join(self.selected_smoke_combos)}",
            "",
            "## displacement_after_reclaim",
            "",
            f"- closed_trades: {displacement['closed_trades']}",
            f"- MFE_R_avg: {displacement['MFE_R_avg']}",
            f"- MFE_R_ge_0_5_ratio: {displacement['MFE_R_ge_0_5_ratio']}",
            f"- MFE_R_ge_1_0_ratio: {displacement['MFE_R_ge_1_0_ratio']}",
            f"- time_cut_exit_rate: {displacement['time_cut_exit_rate']}",
        ]
        return "\n".join(lines)
