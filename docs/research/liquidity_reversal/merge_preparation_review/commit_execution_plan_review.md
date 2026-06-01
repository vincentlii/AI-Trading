# PR12 Commit Execution Plan Review

## 1. Executive Summary

Primary Decision = B：某些文件归属仍不清楚，继续人工确认。

当前可以确认：

- `docs/research/liquidity_reversal/final_evidence/` 已准备好。
- 11 / 11 个小型 final evidence 文件存在。
- final evidence 目录未发现 row-level `jsonl`、`csv`、backtest cache、Monte Carlo 明细或 old PR artifact。
- 未执行 `git add`。
- 未 commit / merge / tag。

阻断进入 staging 的原因：

- `trading_system/backtest/contract_risk.py` 不是纯 diagnostics。它计算 margin、liquidation、portfolio heat，并返回 reject reason。
- `trading_system/backtest/layered_pipeline.py` 会使用 `contract_risk_filter` 改变 `formal_approved`，因此可能影响 research filter semantics。
- `trading_system/backtest/layered_pipeline.py` 的 `_execution_row()` 当前未显式写出 `trade_id` / `execution_id` / `event_id`，需要确认是否只用于旧 layered proposal 输出，还是会被误认为 full-audit robustness input。
- `trading_system/data/download.py`、`trading_system/data/history.py`、`scripts/check_data_quality.py`、`scripts/download_okx_history.py` 属于 data infra / SWAP reproducibility 支持，默认不应进入 PR12 finalization commit，除非人工确认它们是 clean rebuild reproducibility 必需。

因此，本报告给出可执行顺序，但不建议立即 staging。

## 2. Commit 1 / 2 / 3 人工确认项状态

### Commit 1: Execution lineage / audited replay support

Status: conditionally satisfied, pending human confirmation.

逐项判断：

- RiskEngine 未放宽：satisfied。`execution.py` 使用已有 `RiskDecision` / approved order，未修改 RiskEngine approval。
- fee / funding / margin / notional cap 未放宽：satisfied with note。未看到 fee/funding 降低；`spread_slippage_rate` 是额外 slippage 成本项。margin / notional cap 不在 `execution.py` 中放宽。
- same-bar 仍 conservative / pessimistic：satisfied。same-bar stop+target 仍 stop-first when `conservative_same_bar=True`，并新增 `forced_pessimistic_exit` audit 字段。
- `spread_slippage_rate` 不是降低成本：satisfied。实现为 `expected_slippage += notional * spread_slippage_rate`。
- time-cut 只在 validated proposal / diagnostics replay 中使用：needs human confirmation。代码默认 `reversal_time_cut_bars=0` 关闭，但一旦 config 启用会改变 LR exit replay。
- live path 不受影响：needs human confirmation。文件是 backtest execution，但需确认 live runtime 不复用该 execution config。
- `trade_id` / `execution_id` 是 execution lineage 支持：satisfied。ID 在 execution fill 层基于 candidate/event/execution context 生成，不是在 report 层从 summary 反推。

Commit 1 recommendation:

- 可按单独 commit 准备，但 staging 前必须人工确认 time-cut / live path 边界。

## 3. Commit 2: Research / proposal config schema

Status: conditionally satisfied, pending human confirmation.

逐项判断：

- 只是扩展 research/proposal config surface：mostly satisfied。新增 cost tiers、funding mode、execution proposal params、strategy profile/parameters/volume config。
- proposal 不能绕过 full-audit / regression / human approval：needs human confirmation。代码扩展 proposal allowed paths，但 gate 约束依赖流程，不完全由该文件自身保证。
- proposal approval 不等于 formal approval：satisfied by process intent；仍需 commit note 明确。
- 不自动放宽正式风控：needs human confirmation。配置 schema 本身不放宽，但允许 proposal 修改更多字段。
- cost tier / funding mode 只用于 research/proposal cost stress：needs human confirmation。需要确认 live/formal config loader 不自动启用 proposal-only fields。

Commit 2 recommendation:

- 单独提交。
- commit message 必须明确 proposal 扩展不等于 formal approval，不能绕过 full-audit / regression / human approval。

## 4. Commit 3: Validated LR strategy feature support

Status: conditionally satisfied, pending human confirmation.

逐项判断：

- confirmed candle / no-lookahead 是修复：satisfied。`features.py` 和 `candidates.py` 均过滤 confirmed candles 或传递 confirmed context。
- `structure_extreme_buffer` / asset-specific params / volume baseline 属于 clean rebuild 已验证支持：satisfied with note。已有 tests 覆盖 structure buffer、asset-specific params、TOD/DOW baseline。
- 未默认启用 PDH/PDL、EQH/EQL、rolling_range、runner、partial TP、structure target：satisfied。`candidates.py` 未发现这些 expansion active source / exit profile。
- `live_trading_enabled=false`：satisfied in final config。
- context features 不会启用未验证 expansion：needs human confirmation。`strategy.py` 将 `context.features` 传入 setup detection，需确认 live path 不提供未验证 proposal params。

Commit 3 recommendation:

- `trading_system/strategies/trend_price_volume_v1/candidates.py` 可纳入 Commit 3：文件实现 raw candidate schema、candidate_id/sweep_event_id、confirmed-only candles、lifecycle fields、structure_extreme_buffer evidence；未发现 PDH/PDL、EQH/EQL、rolling_range、runner、partial TP、structure target 默认启用。
- 仍需人工确认 `candidates.py` 中 trend candidate 支持是否属于本次 validated LR research support，或应随 Research Pipeline commit。

## 5. 待归属文件判定

### `trading_system/strategies/trend_price_volume_v1/candidates.py`

Decision: include in Commit 3, after human confirmation.

Reason:

- 属于 validated LR candidate schema / evidence / no-lookahead support。
- 使用 confirmed candles。
- 生成 deterministic `candidate_id` / `sweep_event_id`。
- 保留 lifecycle / timing / stop formula evidence。
- 未发现未验证 expansion 默认启用。

Risk note:

- 同文件也包含 trend continuation raw candidates，需确认这不是启动 trend_continuation 研究。

### `trading_system/backtest/contract_risk.py`

Decision: do not stage until human confirmation.

Reason:

- 不是单纯 diagnostics。它生成 `margin_required_too_high`、`liquidation_distance_too_close`、`portfolio_heat_exceeded`。
- `layered_pipeline.py` 使用这些 reject reasons 参与 `contract_risk_filter`。

Recommended classification:

- 若人工确认它只用于 proposal layered research filter，并已由 PR12 clean rebuild / full-audit 覆盖，可纳入 Commit 4。
- 若它改变 formal approval semantics 或替代 RiskEngine，应拆出或暂不 stage。

### `trading_system/backtest/layered_cache.py`

Decision: include in Commit 4.

Reason:

- 主要提供 artifact paths、config hash、data hash、json/jsonl/csv read/write。
- 属于 Research Pipeline/cache/robustness framework。
- 未发现 RiskEngine、margin、notional cap、liquidation approval 修改。

### `trading_system/backtest/layered_pipeline.py`

Decision: do not stage until human confirmation.

Reason:

- 属于 layered proposal / cache / filter / execution framework。
- 但它调用 `RiskEngine` 后又调用 `estimate_contract_risk()`，并用 `contract_risk_filter` 改变 `formal_approved`。
- `_ensure_execution_results()` 会先收集 `formal_approved or shadow_approved`，随后跳过非 formal rows；这是 proposal boundary 相关逻辑，需要确认。
- `_execution_row()` 当前未显式输出 `trade_id` / `execution_id` / `event_id`，需确认它不会成为 PR11H robustness input。

Recommended classification:

- 如果确认只用于 research proposal artifacts，且 full-audit 不把它当 final robustness input，可纳入 Commit 4。
- 如果 intended as canonical execution artifact writer，必须先修 lineage fields，不能 stage。

### `trading_system/data/download.py`

Decision: default exclude from PR12 sequence.

Reason:

- 仅将 OKX downloader 支持 `inst_type` 参数，属于 SWAP data infra。
- 对 clean rebuild reproducibility 有帮助，但不属于 final formalization / audit core。

Recommended action:

- 放入后续 data infra commit，除非人工确认它是重现 final evidence 必需。

### `trading_system/data/history.py`

Decision: default exclude from PR12 sequence.

Reason:

- 修改 in-memory `CandleRepository` key，使其按 venue / inst_type 区分。
- DuckDB repository 当前已支持 venue / inst_type；tracked diff 主要影响 in-memory repo。
- 属于 data infra / SWAP test support，不应混入 finalization commit。

Recommended action:

- 可与 data/download scripts 单独做后续 data infra commit。

### `scripts/check_data_quality.py`

Decision: default exclude from PR12 sequence.

Reason:

- 新增 `--preset`，可从 preset 派生 symbols/bars/venue/inst_type。
- 属于 data quality convenience / reproducibility。

Recommended action:

- 后续 data infra commit。

### `scripts/download_okx_history.py`

Decision: default exclude from PR12 sequence.

Reason:

- 新增 `--preset` 和 inst_type grouped download。
- 属于 SWAP data infra / reproducibility，不是 PR12 finalization 必需。

Recommended action:

- 后续 data infra commit。

### Optional docs

Decision: include only directly related docs in Commit 5.

Include:

- `docs/research/liquidity_reversal/final_research_memo.md`
- `docs/research/liquidity_reversal/final_evidence/**`
- `docs/research/liquidity_reversal/merge_preparation_review/**`
- `AI Trading/01_长期记忆/测试与验证命令.md`
- `AI Trading/01_长期记忆/项目事实库.md`
- `AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md`
- `AI Trading/03_策略研究中心/策略研究总览.md`
- `AI Trading/05_回测风控与模拟盘/Proposal验证流程.md`

Do not include:

- `.obsidian/**`
- `.claudian/**`
- `AI Trading/99_归档/**`
- 大量入口文档，除非人工确认是 PR12 必需更新。

## 6. Final 5 Commit Execution Order

### Commit 1: Execution lineage / audited replay support

Included files:

- `trading_system/backtest/execution.py`
- `tests/test_backtest_execution.py`

Exact git add commands:

```powershell
git add -- "trading_system/backtest/execution.py"
git add -- "tests/test_backtest_execution.py"
```

Tests/checks after staging:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_backtest_execution -v
git diff --cached --check
```

Suggested commit message:

```text
add execution lineage and audited replay diagnostics

- add deterministic trade_id and execution_id to backtest fills
- preserve candidate_id and event_id lineage through execution replay
- record same-bar pessimistic audit fields and MAE/MFE diagnostics
- add LR time-cut replay diagnostics without changing RiskEngine
```

Risk note:

- Stage only after confirming LR time-cut remains validated proposal / diagnostics replay support and live path is unaffected.

### Commit 2: Research / proposal config schema

Included files:

- `trading_system/config/__init__.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`
- `configs/assets/btc_eth_swap.toml`
- `configs/costs/crypto_swap_research.toml`
- `configs/presets/btc_eth_swap_proposal.toml`
- `configs/strategies/trend_price_volume_swap_proposal.toml`
- `tests/test_config_loader.py`

Exact git add commands:

```powershell
git add -- "trading_system/config/__init__.py"
git add -- "trading_system/config/loader.py"
git add -- "trading_system/config/proposals.py"
git add -- "configs/assets/btc_eth_swap.toml"
git add -- "configs/costs/crypto_swap_research.toml"
git add -- "configs/presets/btc_eth_swap_proposal.toml"
git add -- "configs/strategies/trend_price_volume_swap_proposal.toml"
git add -- "tests/test_config_loader.py"
```

Tests/checks after staging:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_config_loader -v
git diff --cached --check
```

Suggested commit message:

```text
add research proposal config schema for LR rebuild

- add swap contract metadata and cost tier config
- support proposal-only execution and strategy parameter fields
- validate proposal cost tiers and profile status fields
- keep proposal approval separate from formal approval
```

Risk note:

- Stage only after confirming proposal fields cannot bypass full-audit, regression, or human approval.

### Commit 3: Validated LR strategy feature support

Included files:

- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
- `trading_system/strategies/trend_price_volume_v1/candidates.py`
- `tests/test_trend_price_volume_features.py`

Exact git add commands:

```powershell
git add -- "trading_system/strategies/trend_price_volume_v1/features.py"
git add -- "trading_system/strategies/trend_price_volume_v1/strategy.py"
git add -- "trading_system/strategies/trend_price_volume_v1/candidates.py"
git add -- "tests/test_trend_price_volume_features.py"
```

Tests/checks after staging:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_trend_price_volume_features -v
git diff --cached --check
```

Suggested commit message:

```text
add validated LR feature support for clean rebuild

- pass confirmed context features into setup detection
- add structure extreme buffer invalidation support
- add asset-specific LR parameters and TOD/DOW volume baseline evidence
- keep unvalidated expansion sources out of the default strategy path
```

Risk note:

- Stage only after confirming `candidates.py` trend candidate support is acceptable in this commit and does not start trend_continuation work.

### Commit 4: Research Pipeline / audit / artifact / robustness framework

Included files:

- `research_pipeline/**` excluding `__pycache__` / `.pyc`
- `scripts/export_lr_regression_baseline.py`
- `scripts/run_fresh_lr_scanner.py`
- `scripts/run_minimal_lr_v0_filter.py`
- `scripts/run_stage6_quality_recovery.py`
- `scripts/run_stage6c_sizing_proposal.py`
- `scripts/run_stage6d_edge_validation.py`
- `scripts/run_stage6e_aggregator.py`
- `scripts/run_stage7_smoke_plan.py`
- `scripts/run_candidate_anatomy_audit.py`
- `scripts/run_btc_eth_swap_proposal.py`
- `trading_system/backtest/scanner.py`
- `trading_system/backtest/batch.py`
- `trading_system/backtest/layered_cache.py`
- `trading_system/diagnostics/fresh_lr_scanner.py`
- `trading_system/diagnostics/minimal_lr_filter.py`
- `trading_system/diagnostics/stage6_quality.py`
- `trading_system/diagnostics/stage6c_sizing.py`
- `trading_system/diagnostics/stage6d_edge.py`
- `trading_system/diagnostics/stage6e_aggregator.py`
- `trading_system/diagnostics/stage7_smoke.py`
- `trading_system/diagnostics/rejection_detail.py`
- `trading_system/diagnostics/signal_funnel.py`
- `trading_system/reports/**`
- `tests/fixtures/regression_baselines/liquidity_reversal/stage6e_10000w/**`
- `tests/test_backtest_batch.py`
- `tests/test_backtest_run_records.py`
- `tests/test_candidate_anatomy_audit.py`
- `tests/test_contract_risk_diagnostics.py`
- `tests/test_fresh_lr_scanner.py`
- `tests/test_layered_proposal_pipeline.py`
- `tests/test_lr_regression_baseline.py`
- `tests/test_minimal_lr_filter.py`
- `tests/test_proposal_contract_report.py`
- `tests/test_stage6_quality_recovery.py`
- `tests/test_signal_rejection_detail.py`

Conditionally include after human confirmation:

- `trading_system/backtest/contract_risk.py`
- `trading_system/backtest/layered_pipeline.py`

Exact git add commands:

```powershell
git add -- "research_pipeline"
git add -- "scripts/export_lr_regression_baseline.py"
git add -- "scripts/run_fresh_lr_scanner.py"
git add -- "scripts/run_minimal_lr_v0_filter.py"
git add -- "scripts/run_stage6_quality_recovery.py"
git add -- "scripts/run_stage6c_sizing_proposal.py"
git add -- "scripts/run_stage6d_edge_validation.py"
git add -- "scripts/run_stage6e_aggregator.py"
git add -- "scripts/run_stage7_smoke_plan.py"
git add -- "scripts/run_candidate_anatomy_audit.py"
git add -- "scripts/run_btc_eth_swap_proposal.py"
git add -- "trading_system/backtest/scanner.py"
git add -- "trading_system/backtest/batch.py"
git add -- "trading_system/backtest/layered_cache.py"
git add -- "trading_system/diagnostics/fresh_lr_scanner.py"
git add -- "trading_system/diagnostics/minimal_lr_filter.py"
git add -- "trading_system/diagnostics/stage6_quality.py"
git add -- "trading_system/diagnostics/stage6c_sizing.py"
git add -- "trading_system/diagnostics/stage6d_edge.py"
git add -- "trading_system/diagnostics/stage6e_aggregator.py"
git add -- "trading_system/diagnostics/stage7_smoke.py"
git add -- "trading_system/diagnostics/rejection_detail.py"
git add -- "trading_system/diagnostics/signal_funnel.py"
git add -- "trading_system/reports"
git add -- "tests/fixtures/regression_baselines/liquidity_reversal/stage6e_10000w"
git add -- "tests/test_backtest_batch.py"
git add -- "tests/test_backtest_run_records.py"
git add -- "tests/test_candidate_anatomy_audit.py"
git add -- "tests/test_contract_risk_diagnostics.py"
git add -- "tests/test_fresh_lr_scanner.py"
git add -- "tests/test_layered_proposal_pipeline.py"
git add -- "tests/test_lr_regression_baseline.py"
git add -- "tests/test_minimal_lr_filter.py"
git add -- "tests/test_proposal_contract_report.py"
git add -- "tests/test_stage6_quality_recovery.py"
git add -- "tests/test_signal_rejection_detail.py"
```

Only after human confirmation:

```powershell
git add -- "trading_system/backtest/contract_risk.py"
git add -- "trading_system/backtest/layered_pipeline.py"
```

After staging, remove accidental bytecode if any:

```powershell
git diff --cached --name-only | Select-String -Pattern '__pycache__|\\.pyc$'
```

Tests/checks after staging:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline/tests -v
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_regression_baseline tests.test_fresh_lr_scanner tests.test_minimal_lr_filter tests.test_stage6_quality_recovery tests.test_contract_risk_diagnostics tests.test_layered_proposal_pipeline tests.test_proposal_contract_report tests.test_candidate_anatomy_audit tests.test_backtest_run_records -v
git diff --cached --check
```

Suggested commit message:

```text
add reusable research pipeline audit and robustness framework

- add strategy adapter, registry, CLI, artifact, and audit gate modules
- add LR read-only analytics, sizing, robustness, and legacy wrapper runners
- add regression fixtures and tests for research artifact workflows
- keep strategy formalization separate from framework capabilities
```

Risk note:

- Do not include `contract_risk.py` / `layered_pipeline.py` until the `contract_risk_filter` semantics are explicitly approved.

### Commit 5: LR final formalization / evidence / docs

Included files:

- `configs/strategies/liquidity_reversal.yaml`
- `configs/research_backlog/liquidity_reversal_backlog.yaml`
- `docs/research/liquidity_reversal/final_research_memo.md`
- `docs/research/liquidity_reversal/final_evidence/**`
- `docs/research/liquidity_reversal/merge_preparation_review/**`
- `tests/test_liquidity_reversal_final_config.py`
- `AI Trading/01_长期记忆/测试与验证命令.md`
- `AI Trading/01_长期记忆/项目事实库.md`
- `AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md`
- `AI Trading/03_策略研究中心/策略研究总览.md`
- `AI Trading/05_回测风控与模拟盘/Proposal验证流程.md`

Exact git add commands:

```powershell
git add -- "configs/strategies/liquidity_reversal.yaml"
git add -- "configs/research_backlog/liquidity_reversal_backlog.yaml"
git add -- "docs/research/liquidity_reversal/final_research_memo.md"
git add -- "docs/research/liquidity_reversal/final_evidence"
git add -- "docs/research/liquidity_reversal/merge_preparation_review"
git add -- "tests/test_liquidity_reversal_final_config.py"
git add -- "AI Trading/01_长期记忆/测试与验证命令.md"
git add -- "AI Trading/01_长期记忆/项目事实库.md"
git add -- "AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md"
git add -- "AI Trading/03_策略研究中心/策略研究总览.md"
git add -- "AI Trading/05_回测风控与模拟盘/Proposal验证流程.md"
```

Optional only after human confirmation:

```powershell
git add -- "AI Trading/01_长期记忆/架构地图.md"
git add -- "AI Trading/05_回测风控与模拟盘/P5中文交易诊断驾驶舱.md"
git add -- "README.md"
git add -- "AGENTS.md"
git add -- "代理协作流程.md"
git add -- "开发记录.md"
git add -- "策略规格.md"
git add -- "项目总规划.md"
git add -- "AI Trading/01_长期记忆/项目总体架构.md"
```

Tests/checks after staging:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_liquidity_reversal_final_config -v
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline/tests -v
git diff --cached --check
```

Suggested commit message:

```text
formalize restricted LR Variant B research candidate

- add final LR config for Restricted Variant B with portfolio heat cap
- set C profile formal scope and keep B profile diagnostic-only
- add final audit, robustness, regression, rollback, and cleanup evidence
- keep live trading disabled and exclude unexecuted proposal rows
```

Risk note:

- Do not include unrestricted Variant B, Full original family, Tier 3, PDH/PDL, EQH/EQL, rolling_range, runner, partial TP, structure target, or unexecuted proposal rows.

## 7. Final Exclusion List

Must exclude:

- `AI Trading/.obsidian/plugins/**`
- `AI Trading/.obsidian/community-plugins.json`
- `.obsidian/workspace.json`
- `AI Trading/.claudian/**`
- `AI Trading/99_归档/**`
- `storage/backtest_cache/**`
- row-level `jsonl`
- Monte Carlo row-level output
- `full_audit/*.jsonl`
- old PR11 artifacts
- `__pycache__/**`
- `.pyc`
- temporary `csv/jsonl/md`
- large local tool files

Default exclude from this 5-commit sequence:

- `trading_system/data/download.py`
- `trading_system/data/history.py`
- `scripts/check_data_quality.py`
- `scripts/download_okx_history.py`
- `scripts/run_btc_eth_p4_4_backtest.py`

These should be a later data infra commit if needed.

## 8. Go / No-Go Decision

Primary Decision = B：某些文件归属仍不清楚，继续人工确认。

Blocking confirmation items before staging:

- Decide whether `contract_risk.py` and `layered_pipeline.py` are allowed in Commit 4 despite `contract_risk_filter` affecting `formal_approved`.
- Decide whether `layered_pipeline.py` must first add explicit `trade_id` / `execution_id` / `event_id` to `_execution_row()`, or whether it is excluded from final robustness input.
- Decide whether `trend_price_volume_v1/candidates.py` trend candidate support is acceptable inside Commit 3, or should be moved to Commit 4 / later.
- Decide whether data infra files remain excluded, as recommended.

Next Step:

- Continue PR12 cleanup / commit boundary confirmation.
- Do not recommend merge / tag.
