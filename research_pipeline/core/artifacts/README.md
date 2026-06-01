# Artifact Reader

## Conclusion

The PR 4 artifact reader is read-only. It parses existing LR research artifacts into a normalized `ResearchRunSummary` without running scanner, filter, sizing, execution, or any legacy script.

## Supported Files

- JSON: `key_metrics.json`, `baseline_manifest.json`, and metrics-style JSON files.
- CSV: comparison and summary tables.
- JSONL: grouped rows, candidate rows, and event rows.
- Markdown: raw text and heading extraction only.

## Rules

- Structured files are authoritative for metrics.
- Markdown is auxiliary and should not override structured metrics.
- Existing legacy report generation remains unchanged.
- `legacy` wrapper mappings remain `migrated_to_core=false`.
- Real aggregation and reporting migration starts in a later PR.

## Current LR Baseline Use

For the frozen PR 1 baseline, the normalizer reads:

- `key_metrics.json`
- `baseline_manifest.json`
- `stage7_smoke_plan_snapshot.md`

It preserves the frozen counts, selected smoke combos, sizing metrics, and tracked combo metrics such as `displacement_after_reclaim`.

## Artifact Index

PR 6 adds a read-only artifact index manifest.

The indexer scans a selected artifact directory, records supported files, computes SHA-256 hashes, and writes:

- `artifact_index.json`
- `artifact_index.md`

Each record includes:

- strategy
- stage
- window
- artifact type
- path
- file hash
- source command
- source files
- config hash
- pipeline version
- legacy source flag

The indexer does not parse strategy logic and does not run scanner, filter, sizing, edge validation, execution replay, or full backtests.

## Research Run Registry

PR 7 adds a `ResearchRunRegistry` for registering artifact indexes as research runs.

Each run record stores:

- `run_id`
- strategy, stage, and window
- artifact index path and hash
- artifact count
- source command
- pipeline and adapter version
- baseline reference
- proposal/formal/read-only/legacy flags
- config and data hashes when available
- notes and tags

The registry lets later PRs query baseline, aggregation, smoke-plan, proposal-only, and legacy-wrapper runs without rerunning research code.

## Hash Validation

`validate-artifacts` reloads an `artifact_index.json`, checks that each file still exists, recomputes SHA-256, and reports:

- `passed=true` when every file matches.
- `missing: <path>` when an artifact path no longer exists.
- `hash_changed: <path>` when content changed after indexing.

Validation only checks files. It does not parse strategy semantics and does not run backtests.

## CLI

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research build-artifact-index --strategy liquidity_reversal --stage stage6e_aggregation --window 10000w --artifact-dir <dir> --output-dir <dir>
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research register-run --registry <registry.json> --artifact-index <artifact_index.json> --strategy liquidity_reversal --stage stage6e_aggregation --window 10000w
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research list-artifacts --artifact-index <artifact_index.json>
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research validate-artifacts --artifact-index <artifact_index.json>
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research list-runs --registry <registry.json>
```

## Proposal Boundary

This module manages research artifacts only. It does not mean LR proposal tuning is complete, and it does not promote proposal-only results into formal config.

- LR formal proposal validation belongs to PR 11.
- Legacy cleanup, merge to master, and stable tag belong to PR 12.
