from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from research_pipeline.legacy.registry import LegacyScriptMapping


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def build_legacy_command_payload(
    mapping: LegacyScriptMapping,
    legacy_args: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    cleaned_args = list(legacy_args or [])
    if cleaned_args and cleaned_args[0] == "--":
        cleaned_args = cleaned_args[1:]
    script_path = WORKSPACE_ROOT / "scripts" / mapping.legacy_script_name
    return {
        "dry_run": dry_run,
        "mapping": mapping.as_dict(),
        "legacy_args": cleaned_args,
        "command": [sys.executable, str(script_path), *cleaned_args],
        "calls_old_logic": mapping.calls_old_logic,
        "migrated_to_core": mapping.migrated_to_core,
    }
