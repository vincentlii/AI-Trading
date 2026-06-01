from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchFlowAuditResult:
    strategy: str
    proposal_only: bool
    formal_conclusion_enabled: bool
    audit_passed: bool
    primary_decision: str
    blocking_issues: list[str]
    non_blocking_warnings: list[str]
    next_pr_recommendation: str
    lineage_rows: list[dict[str, Any]]
    join_audit_rows: list[dict[str, Any]]
    invariant_rows: list[dict[str, Any]]
    metric_recompute_rows: list[dict[str, Any]]
    cross_report_rows: list[dict[str, Any]]
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True)
class FullPipelineAuditResult:
    strategy: str
    proposal_only: bool
    formal_conclusion_enabled: bool
    audit_passed: bool
    primary_decision: str
    blocking_issues: list[str]
    non_blocking_warnings: list[str]
    next_pr_recommendation: str
    schema_contract_rows: list[dict[str, Any]]
    lineage_rows: list[dict[str, Any]]
    join_integrity_rows: list[dict[str, Any]]
    proposal_boundary_rows: list[dict[str, Any]]
    no_lookahead_rows: list[dict[str, Any]]
    metric_recompute_rows: list[dict[str, Any]]
    report_consistency_rows: list[dict[str, Any]]
    artifact_integrity_rows: list[dict[str, Any]]
    code_logic_review_rows: list[dict[str, Any]]
    source_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
