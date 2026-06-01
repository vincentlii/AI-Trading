from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class PushClassification:
    no_push_count: int | None
    weak_push_count: int | None
    medium_push_count: int
    strong_push_count: int
    no_push_ratio: float | None
    weak_push_ratio: float | None
    medium_push_ratio: float
    strong_push_ratio: float
    classification_source: str = "mfe_values"

    def as_dict(self) -> dict[str, int | float | str | None]:
        return asdict(self)


def classify_mfe_push(values: Iterable[float]) -> PushClassification:
    materialized = [float(value) for value in values]
    total = len(materialized)
    no_push = sum(1 for value in materialized if value < 0.3)
    weak = sum(1 for value in materialized if 0.3 <= value < 0.5)
    medium = sum(1 for value in materialized if 0.5 <= value < 1.0)
    strong = sum(1 for value in materialized if value >= 1.0)
    return PushClassification(
        no_push_count=no_push,
        weak_push_count=weak,
        medium_push_count=medium,
        strong_push_count=strong,
        no_push_ratio=_ratio(no_push, total),
        weak_push_ratio=_ratio(weak, total),
        medium_push_ratio=_ratio(medium, total),
        strong_push_ratio=_ratio(strong, total),
    )


def classify_from_mfe_threshold_ratios(
    closed_trades: int,
    mfe_ge_0_5_ratio: float,
    mfe_ge_1_0_ratio: float,
) -> PushClassification:
    total = max(int(closed_trades), 0)
    strong = round(total * float(mfe_ge_1_0_ratio or 0.0))
    medium = round(total * max(float(mfe_ge_0_5_ratio or 0.0) - float(mfe_ge_1_0_ratio or 0.0), 0.0))
    return PushClassification(
        no_push_count=None,
        weak_push_count=None,
        medium_push_count=medium,
        strong_push_count=strong,
        no_push_ratio=None,
        weak_push_ratio=None,
        medium_push_ratio=_ratio(medium, total),
        strong_push_ratio=_ratio(strong, total),
        classification_source="threshold_ratios_only",
    )


def _ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return count / total
