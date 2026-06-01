# Research Pipeline Full Audit Gate

## 结论

Full audit gate 是每次策略调参结束、进入 robustness 或正式 proposal 前必须运行的审计层。它不优化策略、不生成交易、不修改参数，只验证研究产物是否能被追溯、重算和解释。

## Row Type Contract

所有新 research artifact row 应显式包含 `row_type`。允许值包括：

- `market_bar`
- `context_row`
- `feature_row`
- `structure_level`
- `raw_candidate`
- `proposal_candidate`
- `formal_approved`
- `rejected_candidate`
- `sizing_diagnostic`
- `executed_trade`
- `closed_trade`
- `diagnostic_only`
- `summary_row`
- `report_metric`

Performance metrics 只能来自 `closed_trade`。`proposal_candidate`、`sizing_diagnostic`、`diagnostic_only`、`summary_row` 不得进入 `net_R`、`profit_factor`、`MFE_R`、`MAE_R`、`drawdown`。

## Lineage Schema

核心 rows 应保留：

- identity：`strategy`、`adapter_version`、`pipeline_version`、`run_id`、`stage`、`row_type`
- trading identity：`event_id`、`candidate_id`、`trade_id`、`execution_id`
- temporal：`feature_cutoff_time`、`structure_confirmed_time`、`sweep_time`、`reclaim_time`、`signal_time`、`entry_time`、`exit_time`
- policy：`structure_source`、`attempt_type`、`filter_policy`、`risk_policy`、`sizing_policy`、`exit_profile`、`cost_tier`
- state：`proposal_only`、`diagnostic_only`、`selected`、`executed`、`closed`、`eligible_for_performance`、`eligible_for_robustness`

缺失 lineage 时不得静默跳过。无法 backfill 的 rows 必须标记为不可进入 robustness。

## Audit Coverage

Full audit gate 覆盖：

- schema contract
- lineage
- join integrity
- proposal boundary
- no-lookahead
- metric recompute
- report consistency
- artifact integrity
- pipeline-wide code logic review

## Proposal Boundary

Proposal-only 结果可以用于覆盖率、sizing diagnostics 和组合候选解释，但不能作为 formal performance。未执行 proposal rows 必须保持 diagnostic，不得伪造成 closed trades。

## No-lookahead

Audit 会检查 `feature_cutoff_time <= signal_time`、`structure_confirmed_time <= sweep_time`、`sweep_time <= reclaim_time`、`signal_time < entry_time`、`bar_confirmed=true` 等字段。若 artifact 缺字段，则标记 `unverifiable`，不得作为 robustness 主输入。

## Metric Recompute

所有核心 performance 指标必须从 row-level closed trade artifacts 重算。Markdown summary 只能作为展示，不得作为收益指标原始来源。

## Lineage Repair

`lineage-repair` 是 PR 11G-QA-fix-2 的 robustness preflight 修复入口。它只允许从真实 upstream artifacts 回填 `candidate_id`、`event_id`、时间链和已有 execution identity。

硬边界：

- 不生成、伪造或猜测 `trade_id` / `execution_id`。
- 不从 summary rows 反推 closed trades。
- 不把 proposal / diagnostic rows 转成 closed rows。
- 不能精确 join 的 rows 标记 `invalid_for_robustness=true`。
- `invalid_for_robustness` 和 `no_lookahead_unverifiable` rows 不得进入 PR 11H 输入。

当前 LR artifacts 的 upstream execution rows 缺少真实 `trade_id` / `execution_id`，因此 repair 会输出空的 `robustness_input_candidate_rows.jsonl`，并保持 Primary Decision = C。

## Failure Handling

Audit failed 时：

- 不进入 robustness。
- 不正式化 proposal。
- 回到对应 PR 修 lineage、join、schema、no-lookahead 或 report writer。

## New Strategy Integration

新 adapter，如 `trend_continuation`、`breakout_pullback`、`stopping_volume_retest`，需要输出同一套 `row_type`、lineage、policy、state 字段，才能复用 full-audit CLI。

## CLI

```powershell
python -m research_pipeline.cli.research full-audit `
  --strategy liquidity_reversal `
  --artifact-dir <artifact_dir> `
  --output-dir <output_dir>
```

```powershell
python -m research_pipeline.cli.research lineage-repair `
  --strategy liquidity_reversal `
  --combined-artifact-dir <combined_artifact_dir> `
  --filter-results <filter_results.jsonl> `
  --execution-results <execution_results.jsonl> `
  --output-dir <output_dir>
```

未来其他策略使用同一 CLI，只替换 `--strategy` 和 artifact 目录。
