# PR12 Split Commit Plan

## 1. 当前 Git Status / Diff 概览

当前分支：

- `codex/proposal-diagnostics`

当前工作区状态：

- tracked modified files：34 个。
- untracked files / paths：大量，包含 `research_pipeline/`、configs、scripts、tests、docs、Obsidian 本地插件、归档资料。
- tracked diff stat：34 files changed, 1678 insertions, 175 deletions。
- `storage/` 被 `.gitignore` 忽略，final artifacts 不会自动进入 commit。
- `research_pipeline/` 目录内检测到源码/文档/测试文件，也检测到大量 `__pycache__` / `.pyc`，后者不得提交。
- final evidence 当前存在于 `storage/research_runs/liquidity_reversal/final/`，但 `docs/research/liquidity_reversal/final_evidence/` 当前未准备好。

高风险误提交来源：

- `.obsidian/workspace.json`
- `AI Trading/.obsidian/plugins/**`
- `AI Trading/.claudian/**`
- `AI Trading/99_归档/**`
- `storage/backtest_cache/**`
- `research_pipeline/**/__pycache__/**`
- `*.pyc`

当前计划结论：

- 不建议把所有 PR12 改动合成一个 commit。
- 应拆成 5 个语义 commit，再额外保留一个 “暂不纳入 / 人工确认” 清单。
- 不执行 staging、commit、merge、tag。

## 2. Commit 1: Execution lineage / audited replay support

建议标题：

- `Add execution lineage and audited replay diagnostics`

### 应包含的文件清单

生产代码：

- `trading_system/backtest/execution.py`

测试：

- `tests/test_backtest_execution.py`

### 归类理由

这些改动主要服务于：

- `trade_id` / `execution_id`
- `candidate_id` / `event_id` lineage
- closed trade identity
- same-bar pessimistic audit
- MFE / MAE / R path diagnostics
- forced pessimistic exit audit
- LR time-cut replay diagnostics
- spread slippage cost diagnostics

这些能力是 full-audit、clean rebuild、execution lineage repair、robustness validation 所需。

### 不应包含的文件

- `trading_system/backtest/contract_risk.py`
- `trading_system/backtest/layered_cache.py`
- `trading_system/backtest/layered_pipeline.py`
- `trading_system/backtest/batch.py`
- `trading_system/backtest/scanner.py`
- config schema / proposal schema 文件
- strategy feature 文件
- final docs / evidence

### 建议 git add 命令

```powershell
git add -- "trading_system/backtest/execution.py"
git add -- "tests/test_backtest_execution.py"
```

### 建议 commit message

```text
add execution lineage and audited replay diagnostics

- add deterministic trade_id and execution_id to backtest fills
- preserve candidate_id and event_id lineage through execution replay
- record same-bar pessimistic audit fields and MAE/MFE diagnostics
- add liquidity reversal time-cut replay diagnostics without changing RiskEngine
```

### Commit 后应运行的 tests / checks

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_backtest_execution -v
git diff --cached --check
```

### 边界说明

- 不应包含 RiskEngine 放宽。
- 不应降低 fee / funding / slippage。
- 不应放宽 same-bar；same-bar 必须保持 conservative / pessimistic。
- time-cut 相关变更必须说明为已验证 proposal / diagnostics replay 支持。

## 3. Commit 2: Research / proposal config schema

建议标题：

- `Add research proposal config schema for LR rebuild`

### 应包含的文件清单

生产代码：

- `trading_system/config/__init__.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`

配置：

- `configs/assets/btc_eth_swap.toml`
- `configs/costs/crypto_swap_research.toml`
- `configs/presets/btc_eth_swap_proposal.toml`
- `configs/strategies/trend_price_volume_swap_proposal.toml`

测试：

- `tests/test_config_loader.py`

### 归类理由

这些改动主要服务于：

- SWAP contract metadata
- cost tier / funding mode
- spread slippage cost tier
- execution proposal parameters
- strategy profile status
- strategy parameter grid
- volume baseline config
- proposal validation

这些能力扩大 research/proposal 配置面，但不应自动进入 formal config。

### 不应包含的文件

- `configs/strategies/liquidity_reversal.yaml`
- `configs/research_backlog/liquidity_reversal_backlog.yaml`
- `trading_system/backtest/execution.py`
- `trading_system/strategies/trend_price_volume_v1/features.py`
- `research_pipeline/`
- final evidence / memo

### 建议 git add 命令

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

### 建议 commit message

```text
add research proposal config schema for LR rebuild

- add swap contract metadata and cost tier config
- support proposal-only execution and strategy parameter fields
- validate proposal cost tiers and profile status fields
- keep proposal approval separate from formal approval
```

### Commit 后应运行的 tests / checks

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_config_loader -v
git diff --cached --check
```

### 边界说明

- proposal config 只能进入 proposal 队列。
- proposal 不能绕过 full-audit、regression、human approval。
- proposal approval 不等于 formal approval。
- 该 commit 不应正式化 Restricted Variant B；正式化放到 Commit 5。

## 4. Commit 3: Strategy feature support for validated LR research

建议标题：

- `Add validated LR feature support for clean rebuild`

### 应包含的文件清单

生产代码：

- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
- `trading_system/strategies/trend_price_volume_v1/candidates.py`

测试：

- `tests/test_trend_price_volume_features.py`

### 归类理由

这些改动主要服务于：

- confirmed candle / no-lookahead feature context
- context features 传入 setup detection
- `structure_extreme_buffer`
- asset-specific LR parameters
- TOD/DOW volume baseline
- invalidation / target evidence
- liquidity reversal clean rebuild 支持

### 不应包含的文件

- execution replay code
- config loader / proposal schema
- research pipeline framework
- final formalization config
- PDH/PDL active source
- EQH/EQL active source
- rolling_range formalization
- runner / partial TP / structure target formalization

### 建议 git add 命令

```powershell
git add -- "trading_system/strategies/trend_price_volume_v1/features.py"
git add -- "trading_system/strategies/trend_price_volume_v1/strategy.py"
git add -- "trading_system/strategies/trend_price_volume_v1/candidates.py"
git add -- "tests/test_trend_price_volume_features.py"
```

### 建议 commit message

```text
add validated LR feature support for clean rebuild

- pass confirmed context features into setup detection
- add structure extreme buffer invalidation support
- add asset-specific LR parameters and TOD/DOW volume baseline evidence
- keep unvalidated expansion sources out of the default strategy path
```

### Commit 后应运行的 tests / checks

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_trend_price_volume_features -v
git diff --cached --check
```

### 边界说明

- 不得默认启用未验证 expansion。
- 不得正式化 PDH/PDL、EQH/EQL、rolling_range、runner、partial TP、structure target。
- `live_trading_enabled=false` 必须由 final config 保持。
- 若 `candidates.py` 经人工确认不属于本次 LR clean rebuild 支持，应从该 commit 移出并暂不 stage。

## 5. Commit 4: Research Pipeline / audit / artifact / robustness framework

建议标题：

- `Add reusable research pipeline audit and robustness framework`

### 应包含的文件清单

Research Pipeline：

- `research_pipeline/__init__.py`
- `research_pipeline/adapters/**`
- `research_pipeline/cli/**`
- `research_pipeline/core/**`
- `research_pipeline/legacy/**`
- `research_pipeline/registry/**`
- `research_pipeline/runners/**`
- `research_pipeline/tests/**`

Legacy / research runner scripts：

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

Diagnostics / reports / pipeline support：

- `trading_system/backtest/scanner.py`
- `trading_system/backtest/batch.py`
- `trading_system/backtest/contract_risk.py`
- `trading_system/backtest/layered_cache.py`
- `trading_system/backtest/layered_pipeline.py`
- `trading_system/diagnostics/fresh_lr_scanner.py`
- `trading_system/diagnostics/minimal_lr_filter.py`
- `trading_system/diagnostics/stage6_quality.py`
- `trading_system/diagnostics/stage6c_sizing.py`
- `trading_system/diagnostics/stage6d_edge.py`
- `trading_system/diagnostics/stage6e_aggregator.py`
- `trading_system/diagnostics/stage7_smoke.py`
- `trading_system/diagnostics/rejection_detail.py`
- `trading_system/diagnostics/signal_funnel.py`
- `trading_system/reports/__init__.py`
- `trading_system/reports/backtest_runs.py`
- `trading_system/reports/candidate_anatomy.py`
- `trading_system/reports/lr_regression_baseline.py`
- `trading_system/reports/proposal.py`
- `trading_system/reports/proposal_diagnostics.py`

Tests / fixtures：

- `research_pipeline/tests/**`
- `tests/fixtures/regression_baselines/liquidity_reversal/stage6e_10000w/**`
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
- `tests/test_backtest_batch.py`

### 归类理由

这些改动属于框架能力：

- research pipeline skeleton / adapter / registry / CLI
- artifact reader / index / registry
- full-audit gate
- schema contract / lineage / join / proposal boundary / metric recompute / no-lookahead audit
- aggregation / edge / sizing / robustness runners
- legacy wrappers / compatibility scripts
- scanner/reporting diagnostics

### 不应包含的文件

- `trading_system/backtest/execution.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`
- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
- final formal strategy config
- final evidence docs
- `.obsidian/**`
- `.claudian/**`
- `AI Trading/99_归档/**`
- `research_pipeline/**/__pycache__/**`
- `*.pyc`

### 建议 git add 命令

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
git add -- "trading_system/backtest/contract_risk.py"
git add -- "trading_system/backtest/layered_cache.py"
git add -- "trading_system/backtest/layered_pipeline.py"
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
git add -- "tests/test_backtest_batch.py"
```

提交前必须检查 staged 内容中没有 `__pycache__` 或 `.pyc`：

```powershell
git diff --cached --name-only | Select-String -Pattern '__pycache__|\\.pyc$'
```

### 建议 commit message

```text
add reusable research pipeline audit and robustness framework

- add strategy adapter, registry, CLI, and read-only analytics runners
- add artifact index, research run registry, and full pipeline audit gate
- migrate LR aggregation, edge, sizing, robustness, and legacy wrappers into pipeline
- add regression fixtures and tests for artifact, audit, and robustness workflows
```

### Commit 后应运行的 tests / checks

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline/tests -v
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_regression_baseline tests.test_fresh_lr_scanner tests.test_minimal_lr_filter tests.test_stage6_quality_recovery tests.test_contract_risk_diagnostics tests.test_layered_proposal_pipeline tests.test_proposal_contract_report tests.test_candidate_anatomy_audit tests.test_backtest_run_records -v
git diff --cached --check
```

### 边界说明

- 该 commit 不应改变 strategy signal、RiskEngine、成本模型、正式配置。
- 如果某个 `trading_system/backtest/*` 或 `trading_system/data/*` 改动被发现改变实际回测语义，应从 Commit 4 拆出。
- `research_pipeline` 目录内当前存在大量 `__pycache__` / `.pyc`，必须排除。

## 6. Commit 5: LR final formalization / evidence / docs

建议标题：

- `Formalize restricted LR Variant B research candidate`

### 应包含的文件清单

Final config：

- `configs/strategies/liquidity_reversal.yaml`
- `configs/research_backlog/liquidity_reversal_backlog.yaml`

Final memo / merge prep docs：

- `docs/research/liquidity_reversal/final_research_memo.md`
- `docs/research/liquidity_reversal/merge_preparation_review/commit_candidate_files.md`
- `docs/research/liquidity_reversal/merge_preparation_review/delete_or_archive_plan.md`
- `docs/research/liquidity_reversal/merge_preparation_review/final_safety_boundary_check.md`
- `docs/research/liquidity_reversal/merge_preparation_review/git_hygiene_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/high_risk_diff_triage_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/merge_content_summary.md`
- `docs/research/liquidity_reversal/merge_preparation_review/pre_commit_review_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/pre_merge_review_report.md`
- `docs/research/liquidity_reversal/merge_preparation_review/split_commit_plan.md`

Final evidence, after copying to docs：

- `docs/research/liquidity_reversal/final_evidence/final_regression_baseline.json`
- `docs/research/liquidity_reversal/final_evidence/proposal_to_formal_decision_log.md`
- `docs/research/liquidity_reversal/final_evidence/final_full_audit_report.md`
- `docs/research/liquidity_reversal/final_evidence/final_robustness_summary.md`
- `docs/research/liquidity_reversal/final_evidence/final_test_results.md`
- `docs/research/liquidity_reversal/final_evidence/merge_readiness_report.md`
- `docs/research/liquidity_reversal/final_evidence/cleanup_manifest.md`
- `docs/research/liquidity_reversal/final_evidence/legacy_migration_manifest.md`
- `docs/research/liquidity_reversal/final_evidence/rollback_instructions.md`
- `docs/research/liquidity_reversal/final_evidence/artifact_index.json`
- `docs/research/liquidity_reversal/final_evidence/research_run_registry.json`

Final config regression test：

- `tests/test_liquidity_reversal_final_config.py`

Obsidian / project docs, PR12-relevant only：

- `AI Trading/01_长期记忆/测试与验证命令.md`
- `AI Trading/01_长期记忆/项目事实库.md`
- `AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md`
- `AI Trading/03_策略研究中心/策略研究总览.md`
- `AI Trading/05_回测风控与模拟盘/Proposal验证流程.md`

Optional docs, only after human confirmation：

- `AI Trading/01_长期记忆/架构地图.md`
- `AI Trading/05_回测风控与模拟盘/P5中文交易诊断驾驶舱.md`
- `README.md`
- `AGENTS.md`
- `代理协作流程.md`
- `开发记录.md`
- `策略规格.md`
- `项目总规划.md`
- `AI Trading/01_长期记忆/项目总体架构.md`

### 归类理由

这些文件记录最终正式化结论：

- Restricted Variant B
- `portfolio_heat_cap=0.05`
- C profile formal scope
- B profile diagnostic-only
- `live_trading_enabled=false`
- final audit / robustness / regression evidence
- rollback / cleanup / backlog / merge readiness

### 不应包含的文件

- unrestricted Variant B artifacts
- Full original family artifacts
- Tier 3 proposal artifacts
- rolling_range formalization artifacts
- PDH/PDL active source artifacts
- EQH/EQL active source artifacts
- runner / partial TP / structure target proposal rows
- unexecuted proposal rows
- row-level jsonl large files
- Monte Carlo row-level output
- `storage/backtest_cache/**`
- `full_audit/*.jsonl`
- old PR11A-PR11H process artifacts

### 建议 git add 命令

```powershell
git add -- "configs/strategies/liquidity_reversal.yaml"
git add -- "configs/research_backlog/liquidity_reversal_backlog.yaml"
git add -- "docs/research/liquidity_reversal/final_research_memo.md"
git add -- "docs/research/liquidity_reversal/merge_preparation_review"
git add -- "docs/research/liquidity_reversal/final_evidence"
git add -- "tests/test_liquidity_reversal_final_config.py"
git add -- "AI Trading/01_长期记忆/测试与验证命令.md"
git add -- "AI Trading/01_长期记忆/项目事实库.md"
git add -- "AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md"
git add -- "AI Trading/03_策略研究中心/策略研究总览.md"
git add -- "AI Trading/05_回测风控与模拟盘/Proposal验证流程.md"
```

Optional docs, only after human confirmation：

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

### 建议 commit message

```text
formalize restricted LR Variant B research candidate

- add final LR strategy config for Restricted Variant B
- set C profile formal scope with B profile diagnostic-only
- require portfolio_heat_cap 0.05 and keep live trading disabled
- add final research memo, evidence, rollback, cleanup, and merge readiness docs
```

### Commit 后应运行的 tests / checks

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_liquidity_reversal_final_config -v
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline/tests -v
git diff --cached --check
```

### 边界说明

- 正式化对象只能是 Restricted Variant B。
- 不得正式化 unrestricted Variant B。
- 不得正式化 Full original family。
- 不得正式化 Tier 3、rolling_range、PDH/PDL、EQH/EQL、runner、partial TP、structure target。
- B profile 只能 diagnostic-only。
- `live_trading_enabled=false` 必须保持。

## 7. Final Evidence 纳入方案

Go / No-Go for evidence: 当前未准备好。

推荐方案：

1. 创建 `docs/research/liquidity_reversal/final_evidence/`。
2. 只复制小型 final evidence 文件。
3. 提交 docs 下 final evidence。

应复制的小型 final evidence：

- `storage/research_runs/liquidity_reversal/final/final_regression_baseline.json`
- `storage/research_runs/liquidity_reversal/final/proposal_to_formal_decision_log.md`
- `storage/research_runs/liquidity_reversal/final/final_full_audit_report.md`
- `storage/research_runs/liquidity_reversal/final/final_robustness_summary.md`
- `storage/research_runs/liquidity_reversal/final/final_test_results.md`
- `storage/research_runs/liquidity_reversal/final/merge_readiness_report.md`
- `storage/research_runs/liquidity_reversal/final/cleanup_manifest.md`
- `storage/research_runs/liquidity_reversal/final/legacy_migration_manifest.md`
- `storage/research_runs/liquidity_reversal/final/rollback_instructions.md`
- `storage/research_runs/liquidity_reversal/final/artifact_index.json`
- `storage/research_runs/liquidity_reversal/final/research_run_registry.json`

不推荐方案：

- 直接 force-add `storage/`。

禁止纳入：

- `storage/backtest_cache/**`
- row-level jsonl
- Monte Carlo 明细
- `full_audit/*.jsonl`
- 临时过程 artifacts
- old PR11A-PR11H artifacts

## 8. 全局排除清单

不得纳入任何 commit：

- `.obsidian/workspace.json`
- `AI Trading/.obsidian/community-plugins.json`
- `AI Trading/.obsidian/plugins/**`
- `AI Trading/.claudian/**`
- `AI Trading/99_归档/**`
- `storage/backtest_cache/**`
- old PR11A-PR11H row-level artifacts
- broken lineage artifacts
- old proposal/debug rows
- obsolete reports
- temporary jsonl/csv/md
- `__pycache__/**`
- `*.pyc`
- 大体积本地工具文件
- row-level Monte Carlo output
- `full_audit/*.jsonl`

暂不建议纳入，除非人工确认与 PR12 直接相关：

- `scripts/check_data_quality.py`
- `scripts/download_okx_history.py`
- `scripts/run_btc_eth_p4_4_backtest.py`
- `trading_system/data/download.py`
- `trading_system/data/history.py`
- `README.md`
- root-level Chinese thin-entry docs
- optional Obsidian architecture docs

## 9. 仍需人工确认的文件或 Diff

### 需要确认后才能 stage

- `trading_system/backtest/execution.py`
  - 确认 time-cut replay 和 spread slippage 是已验证 proposal / diagnostics 支持。
  - 确认未改变 RiskEngine。
  - 确认 same-bar 仍 pessimistic。

- `trading_system/config/loader.py`
  - 确认新增 config 字段只用于 research/proposal。
  - 确认不会自动放宽正式风控。

- `trading_system/config/proposals.py`
  - 确认 proposal allowed paths 扩展不会绕过 full-audit / regression / human approval。

- `trading_system/strategies/trend_price_volume_v1/features.py`
  - 确认 invalidation / target / volume baseline 改动属于 clean rebuild 已验证范围。
  - 确认未默认启用未验证 expansion。

- `trading_system/strategies/trend_price_volume_v1/strategy.py`
  - 确认传入 context features 不影响 live path。

- `trading_system/strategies/trend_price_volume_v1/candidates.py`
  - 需人工确认是否属于 validated LR research support。

- `trading_system/backtest/batch.py`
- `trading_system/backtest/contract_risk.py`
- `trading_system/backtest/layered_cache.py`
- `trading_system/backtest/layered_pipeline.py`
  - 需确认是否属于 pipeline / robustness framework，而不是改变正式 backtest semantics。

- `trading_system/data/download.py`
- `trading_system/data/history.py`
- `scripts/check_data_quality.py`
- `scripts/download_okx_history.py`
  - 需确认是否与 PR12 finalization 有直接关系；否则不进本轮 commit。

### 需要先准备后才能 stage

- `docs/research/liquidity_reversal/final_evidence/`
  - 当前目录未准备好。
  - 必须先从 `storage/research_runs/liquidity_reversal/final/` 复制小型 evidence。

## 10. Go / No-Go Decision

Primary Decision = D：final evidence 仍未准备好。

补充判断：

- split commit 边界总体清楚。
- 但 Commit 1 / 2 / 3 中存在语义扩展，仍需人工确认后才能 staged。
- Commit 5 的 final evidence 推荐路径尚未准备好，因此不能进入最终 commit sequence。

Next Step：

- 先准备 `docs/research/liquidity_reversal/final_evidence/` 小型 evidence。
- 人工确认 Commit 1 / 2 / 3 的高风险语义边界。
- 确认后按 Commit 1 到 Commit 5 顺序 staging / commit。
- 每个 commit 后运行对应 tests / checks。

禁止：

- 不要执行全量 staging。
- 不要 commit。
- 不要 merge。
- 不要 tag。
- 不要删除文件。
- 不要继续调参。
- 不要开始 trend_continuation。
