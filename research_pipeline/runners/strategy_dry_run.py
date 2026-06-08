from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_pipeline.core.artifacts.manifest import RunManifest
from research_pipeline.core.cache.keys import stable_fingerprint
from research_pipeline.registry.strategy_registry import default_strategy_registry


@dataclass(frozen=True)
class StrategyDryRunResult:
    strategy: str
    adapter_version: str
    proposal_only: bool
    formal_conclusion_enabled: bool
    dry_run_only: bool
    manifest: dict[str, Any]
    audit_input: dict[str, Any]
    checks: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def run_strategy_dry_run(
    *,
    strategy: str,
    dataset_window: str,
    output_dir: Path | None,
) -> StrategyDryRunResult:
    adapter = default_strategy_registry().get(strategy)
    audit_input = adapter.audit_input_manifest()
    run_id = stable_fingerprint(
        {
            "strategy": strategy,
            "adapter_version": adapter.adapter_version,
            "dataset_window": dataset_window,
            "dry_run": True,
        }
    )[:24]
    manifest = RunManifest(
        run_id=run_id,
        strategy=strategy,
        adapter_version=adapter.adapter_version,
        dataset_window=dataset_window,
        artifact_contract=adapter.artifact_contract().as_dict(),
        audit_profile=adapter.audit_profile().as_dict(),
        artifact_paths={},
        config_snapshot={"dry_run_only": True},
        proposal_only=True,
        formal_conclusion_enabled=False,
        notes="Dry run validates Research Pipeline contract only; no strategy research or formal candidate.",
    )
    checks = _checks(audit_input)
    result = StrategyDryRunResult(
        strategy=strategy,
        adapter_version=adapter.adapter_version,
        proposal_only=True,
        formal_conclusion_enabled=False,
        dry_run_only=True,
        manifest=manifest.as_dict(),
        audit_input=audit_input,
        checks=checks,
    )
    if output_dir is not None:
        _write_outputs(result, manifest, Path(output_dir))
    return result


def _checks(audit_input: dict[str, Any]) -> list[dict[str, Any]]:
    contract = audit_input["artifact_contract"]
    profile = audit_input["audit_profile"]
    return [
        {
            "check_name": "artifact_contract_declared",
            "passed": bool(contract["required_inputs"]) and bool(contract["required_outputs"]),
            "blocking": True,
        },
        {
            "check_name": "closed_trade_only_metrics_declared",
            "passed": profile["performance_row_type"] == "closed_trade",
            "blocking": True,
        },
        {
            "check_name": "proposal_rows_excluded",
            "passed": "proposal_candidate" in profile["excluded_performance_row_types"],
            "blocking": True,
        },
        {
            "check_name": "lineage_fields_declared",
            "passed": {"execution_id", "candidate_id", "event_id"}.issubset(set(profile["required_lineage_fields"])),
            "blocking": True,
        },
        {
            "check_name": "no_formal_candidate_created",
            "passed": audit_input["proposal_only"] is True and audit_input["formal_conclusion_enabled"] is False,
            "blocking": True,
        },
    ]


def _write_outputs(result: StrategyDryRunResult, manifest: RunManifest, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "strategy_dry_run_result.json").write_text(result.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.json").write_text(manifest.as_json(), encoding="utf-8")
    (output_dir / "run_manifest.md").write_text(manifest.as_markdown() + "\n", encoding="utf-8")
