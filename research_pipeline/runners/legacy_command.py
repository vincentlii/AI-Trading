from __future__ import annotations

import json

from research_pipeline.legacy.registry import get_legacy_mapping, list_legacy_mappings
from research_pipeline.legacy.wrappers import build_legacy_command_payload


def legacy_mapping_report(strategy: str | None = None) -> str:
    payload = {
        "mappings": [mapping.as_dict() for mapping in list_legacy_mappings(strategy=strategy)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def legacy_run_preview(alias: str, legacy_args: list[str] | None = None) -> str:
    mapping = get_legacy_mapping(alias)
    payload = build_legacy_command_payload(mapping, legacy_args=legacy_args, dry_run=True)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
