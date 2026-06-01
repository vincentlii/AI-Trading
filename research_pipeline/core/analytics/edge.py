from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EdgeMetrics:
    closed_trades: int
    MFE_R_avg: float | None = None
    MFE_R_p50: float | None = None
    MFE_R_p75: float | None = None
    MFE_R_p90: float | None = None
    MAE_R_avg: float | None = None
    MAE_R_p50: float | None = None
    MAE_R_p75: float | None = None
    net_R_avg: float | None = None
    net_R_p50: float | None = None
    net_return_on_notional_avg: float | None = None
    time_cut_exit_rate: float | None = None
    MFE_ge_0_5_ratio: float | None = None
    MFE_ge_1_0_ratio: float | None = None
    sample_size_warning: str | None = None

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "EdgeMetrics":
        return cls(
            closed_trades=int(_num(row, "closed_trades")),
            MFE_R_avg=_optional_num(row, "MFE_R_avg"),
            MFE_R_p50=_optional_num(row, "MFE_R_p50"),
            MFE_R_p75=_optional_num(row, "MFE_R_p75"),
            MFE_R_p90=_optional_num(row, "MFE_R_p90"),
            MAE_R_avg=_optional_num(row, "MAE_R_avg"),
            MAE_R_p50=_optional_num(row, "MAE_R_p50"),
            MAE_R_p75=_optional_num(row, "MAE_R_p75"),
            net_R_avg=_optional_num(row, "net_R_avg"),
            net_R_p50=_optional_num(row, "net_R_p50"),
            net_return_on_notional_avg=_optional_num(row, "net_return_on_notional_avg"),
            time_cut_exit_rate=_optional_num(row, "time_cut_exit_rate"),
            MFE_ge_0_5_ratio=_optional_num(row, "MFE_R_ge_0_5_ratio"),
            MFE_ge_1_0_ratio=_optional_num(row, "MFE_R_ge_1_0_ratio"),
            sample_size_warning=row.get("sample_size_warning"),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_num(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    return float(value)


def _num(row: dict[str, Any], key: str) -> float:
    return _optional_num(row, key) or 0.0
