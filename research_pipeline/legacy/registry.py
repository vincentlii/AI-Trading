from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LegacyScriptMapping:
    legacy_script_name: str
    pipeline_command_alias: str
    strategy: str
    stage: str
    status: str
    calls_old_logic: bool
    migrated_to_core: bool
    readonly_wrapper_to_core: bool
    notes: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def list_legacy_mappings(strategy: str | None = None) -> list[LegacyScriptMapping]:
    from research_pipeline.legacy.liquidity_reversal import LIQUIDITY_REVERSAL_LEGACY_MAPPINGS

    mappings = list(LIQUIDITY_REVERSAL_LEGACY_MAPPINGS)
    if strategy is None:
        return mappings
    return [mapping for mapping in mappings if mapping.strategy == strategy]


def get_legacy_mapping(alias: str) -> LegacyScriptMapping:
    for mapping in list_legacy_mappings():
        if mapping.pipeline_command_alias == alias:
            return mapping
    raise KeyError(f"Unknown legacy wrapper alias: {alias}")
