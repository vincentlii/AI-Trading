# PR12 Final Split Commit Execution Plan

## 1. Go / No-Go Decision

Primary Decision = A：文件归属已清楚，可以等待人工确认后按 5 个 commit 顺序 staging / commit。

依据：

- final evidence 已准备好：`docs/research/liquidity_reversal/final_evidence/`。
- 11 / 11 个小型 final evidence 文件存在，missing = 0。
- 未发现 row-level `jsonl`、Monte Carlo 明细、`full_audit/*.jsonl`、`storage/backtest_cache` 或 old PR artifacts 被复制到 final evidence。
- 人工已确认：
  - `contract_risk.py` 纳入 Commit 4。
  - `layered_pipeline.py` 纳入 Commit 4，但不是 PR12 final robustness input。
  - `candidates.py` 纳入 Commit 3。
  - data infra files 不纳入本轮 5 个 commit。

执行前仍需遵守：

- 不使用全量 staging。
- 每个 commit 单独 staging、单独测试、单独 commit。
- staging 后必须检查 staged 文件中没有 `__pycache__` / `.pyc` / forbidden artifacts。
- 5 个 commit 完成前禁止 merge / tag。

## 2. Final 5 Commit 顺序

1. Commit 1: Execution lineage / audited replay support
2. Commit 2: Research / proposal config schema
3. Commit 3: Validated LR strategy feature support
4. Commit 4: Research Pipeline / audit / artifact / robustness framework
5. Commit 5: LR final formalization / evidence / docs

## 3. Commit 1: Execution lineage / audited replay support

### Included files / file groups

- `trading_system/backtest/execution.py`
- `tests/test_backtest_execution.py`

### Boundary

This commit is for audited replay and execution lineage.

Allowed:

- `trade_id` / `execution_id`
- `candidate_id` / `event_id` lineage
- same-bar pessimistic audit fields
- MFE / MAE / R path diagnostics
- slippage and time-cut replay diagnostics

Not allowed:

- RiskEngine changes
- fee / funding / margin / notional cap relaxation
- same-bar optimism
- live trading path changes

Notes:

- `spread_slippage_rate` is additional cost modeling, not cost reduction.
- LR time-cut remains validated proposal / diagnostics replay support.

### Git add commands

```powershell
git add -- "trading_system/backtest/execution.py"
git add -- "tests/test_backtest_execution.py"
```

### Tests / checks after staging

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_backtest_execution -v
git diff --cached --check
git diff --cached --name-only | Select-String -Pattern '__pycache__|\.pyc$|storage/backtest_cache|\.jsonl$'
```

Expected:

- unittest exits 0.
- `git diff --cached --check` exits 0, except line-ending warnings if already known.
- forbidden file scan returns no matches.

### Suggested commit message

```text
add execution lineage and audited replay diagnostics

- add deterministic trade_id and execution_id to backtest fills
- preserve candidate_id and event_id lineage through execution replay
- record same-bar pessimistic audit fields and MAE/MFE diagnostics
- add LR time-cut replay diagnostics without changing RiskEngine
```

## 4. Commit 2: Research / proposal config schema

### Included files / file groups

- `trading_system/config/__init__.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`
- `configs/assets/btc_eth_swap.toml`
- `configs/costs/crypto_swap_research.toml`
- `configs/presets/btc_eth_swap_proposal.toml`
- `configs/strategies/trend_price_volume_swap_proposal.toml`
- `tests/test_config_loader.py`

### Boundary

This commit expands research/proposal configuration only.

Allowed:

- SWAP contract metadata
- cost tier / funding mode fields
- execution proposal parameters
- strategy profile / parameter grid / volume config
- proposal validation

Not allowed:

- automatic formalization
- RiskEngine bypass
- full-audit / regression / human approval bypass
- treating proposal approval as formal approval
- live path activation

### Git add commands

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

### Tests / checks after staging

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_config_loader -v
git diff --cached --check
git diff --cached --name-only | Select-String -Pattern '__pycache__|\.pyc$|storage/backtest_cache|\.jsonl$'
```

Expected:

- unittest exits 0.
- forbidden file scan returns no matches.

### Suggested commit message

```text
add research proposal config schema for LR rebuild

- add swap contract metadata and cost tier config
- support proposal-only execution and strategy parameter fields
- validate proposal cost tiers and profile status fields
- keep proposal approval separate from formal approval
```

## 5. Commit 3: Validated LR strategy feature support

### Included files / file groups

- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
- `trading_system/strategies/trend_price_volume_v1/candidates.py`
- `tests/test_trend_price_volume_features.py`

### Boundary

This commit supports validated LR clean rebuild features.

Allowed:

- confirmed candle / no-lookahead feature context
- `structure_extreme_buffer`
- asset-specific LR parameters
- TOD/DOW volume baseline
- invalidation / target evidence
- candidate schema / evidence / lifecycle fields
- `candidate_id` / `sweep_event_id`

Not allowed:

- enabling PDH/PDL as formal active source
- enabling EQH/EQL as formal active source
- formalizing rolling_range
- formalizing runner exit
- formalizing partial TP
- formalizing structure target
- starting trend_continuation research

Notes:

- `candidates.py` may include shared trend candidate schema support, but this commit does not start or formalize trend_continuation.
- `live_trading_enabled=false` remains enforced by final LR config in Commit 5.

### Git add commands

```powershell
git add -- "trading_system/strategies/trend_price_volume_v1/features.py"
git add -- "trading_system/strategies/trend_price_volume_v1/strategy.py"
git add -- "trading_system/strategies/trend_price_volume_v1/candidates.py"
git add -- "tests/test_trend_price_volume_features.py"
```

### Tests / checks after staging

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_trend_price_volume_features -v
git diff --cached --check
git diff --cached --name-only | Select-String -Pattern '__pycache__|\.pyc$|storage/backtest_cache|\.jsonl$'
```

Expected:

- unittest exits 0.
- forbidden file scan returns no matches.

### Suggested commit message

```text
add validated LR feature support for clean rebuild

- pass confirmed context features into setup detection
- add structure extreme buffer invalidation support
- add asset-specific LR parameters and TOD/DOW volume baseline evidence
- add LR candidate schema and lifecycle evidence without enabling unvalidated expansions
```

## 6. Commit 4: Research Pipeline / audit / artifact / robustness framework

### Included files / file groups

Research Pipeline:

- `research_pipeline/**`, excluding `__pycache__` / `.pyc`

Legacy / research runner scripts:

- `scripts/export_lr_regression_baseline.py`
- `scripts/run_btc_eth_swap_proposal.py`
- `scripts/run_candidate_anatomy_audit.py`
- `scripts/run_fresh_lr_scanner.py`
- `scripts/run_minimal_lr_v0_filter.py`
- `scripts/run_stage6_quality_recovery.py`
- `scripts/run_stage6c_sizing_proposal.py`
- `scripts/run_stage6d_edge_validation.py`
- `scripts/run_stage6e_aggregator.py`
- `scripts/run_stage7_smoke_plan.py`

Backtest / diagnostics / reports framework:

- `trading_system/backtest/batch.py`
- `trading_system/backtest/contract_risk.py`
- `trading_system/backtest/layered_cache.py`
- `trading_system/backtest/layered_pipeline.py`
- `trading_system/backtest/scanner.py`
- `trading_system/diagnostics/fresh_lr_scanner.py`
- `trading_system/diagnostics/minimal_lr_filter.py`
- `trading_system/diagnostics/rejection_detail.py`
- `trading_system/diagnostics/signal_funnel.py`
- `trading_system/diagnostics/stage6_quality.py`
- `trading_system/diagnostics/stage6c_sizing.py`
- `trading_system/diagnostics/stage6d_edge.py`
- `trading_system/diagnostics/stage6e_aggregator.py`
- `trading_system/diagnostics/stage7_smoke.py`
- `trading_system/reports/**`

Tests / fixtures:

- `research_pipeline/tests/**`
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
- `tests/test_signal_rejection_detail.py`
- `tests/test_stage6_quality_recovery.py`

### Boundary

This commit adds reusable research pipeline and audit framework.

Allowed:

- adapter / registry / CLI
- artifact reader / index / registry
- full-audit gate
- schema contract / lineage / join / proposal boundary / metric recompute / no-lookahead audit
- aggregation / edge / sizing / robustness runners
- legacy wrappers
- scanner/reporting diagnostics
- research/proposal contract-risk diagnostics

Specific boundary for `contract_risk.py`:

- It is research/proposal contract-risk diagnostic support.
- It may produce `margin_required_too_high`, `liquidation_distance_too_close`, `portfolio_heat_exceeded`.
- These reject reasons are used by LR exposure restriction and proposal diagnostics.
- It is not a RiskEngine replacement.
- It must not be described as formal risk relaxation.
- It must not bypass RiskEngine.
- It must not modify official margin / notional cap / liquidation risk policy.

Specific boundary for `layered_pipeline.py`:

- It is layered proposal / research pipeline framework.
- Its `contract_risk_filter` affects research `formal_approved` inside proposal research artifacts only.
- It is not production risk replacement.
- Current PR12 final robustness input must not depend on `layered_pipeline.py` `_execution_row()`.
- If it becomes canonical execution artifact writer in the future, it must add `trade_id` / `execution_id` / `event_id` lineage and rerun full-audit.

Not allowed:

- changing formal strategy signal semantics
- bypassing RiskEngine
- reducing cost assumptions
- making proposal rows performance rows
- using summary rows as performance source

### Git add commands

Use explicit commands. Do not use a broad all-files stage.

```powershell
git add -- "research_pipeline"
git add -- "scripts/export_lr_regression_baseline.py"
git add -- "scripts/run_btc_eth_swap_proposal.py"
git add -- "scripts/run_candidate_anatomy_audit.py"
git add -- "scripts/run_fresh_lr_scanner.py"
git add -- "scripts/run_minimal_lr_v0_filter.py"
git add -- "scripts/run_stage6_quality_recovery.py"
git add -- "scripts/run_stage6c_sizing_proposal.py"
git add -- "scripts/run_stage6d_edge_validation.py"
git add -- "scripts/run_stage6e_aggregator.py"
git add -- "scripts/run_stage7_smoke_plan.py"
git add -- "trading_system/backtest/batch.py"
git add -- "trading_system/backtest/contract_risk.py"
git add -- "trading_system/backtest/layered_cache.py"
git add -- "trading_system/backtest/layered_pipeline.py"
git add -- "trading_system/backtest/scanner.py"
git add -- "trading_system/diagnostics/fresh_lr_scanner.py"
git add -- "trading_system/diagnostics/minimal_lr_filter.py"
git add -- "trading_system/diagnostics/rejection_detail.py"
git add -- "trading_system/diagnostics/signal_funnel.py"
git add -- "trading_system/diagnostics/stage6_quality.py"
git add -- "trading_system/diagnostics/stage6c_sizing.py"
git add -- "trading_system/diagnostics/stage6d_edge.py"
git add -- "trading_system/diagnostics/stage6e_aggregator.py"
git add -- "trading_system/diagnostics/stage7_smoke.py"
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
git add -- "tests/test_signal_rejection_detail.py"
git add -- "tests/test_stage6_quality_recovery.py"
```

After staging, verify no bytecode or forbidden rows slipped in:

```powershell
git diff --cached --name-only | Select-String -Pattern '__pycache__|\.pyc$|storage/backtest_cache|\.jsonl$|full_audit'
```

If this command returns matches, unstage those files before commit.

### Tests / checks after staging

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline/tests -v
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_regression_baseline tests.test_fresh_lr_scanner tests.test_minimal_lr_filter tests.test_stage6_quality_recovery tests.test_contract_risk_diagnostics tests.test_layered_proposal_pipeline tests.test_proposal_contract_report tests.test_candidate_anatomy_audit tests.test_backtest_run_records tests.test_backtest_batch tests.test_signal_rejection_detail -v
git diff --cached --check
```

Expected:

- research_pipeline tests exit 0.
- targeted legacy/pipeline tests exit 0.
- forbidden file scan returns no matches.

### Suggested commit message

```text
add reusable research pipeline audit and robustness framework

- add strategy adapter, registry, CLI, artifact, and audit gate modules
- add LR read-only analytics, sizing, robustness, and legacy wrapper runners
- add proposal contract-risk diagnostics for research exposure validation
- add regression fixtures and tests for research artifact workflows
```

## 7. Commit 5: LR final formalization / evidence / docs

### Included files / file groups

Final LR config:

- `configs/strategies/liquidity_reversal.yaml`
- `configs/research_backlog/liquidity_reversal_backlog.yaml`

Final docs / evidence:

- `docs/research/liquidity_reversal/final_research_memo.md`
- `docs/research/liquidity_reversal/final_evidence/**`
- `docs/research/liquidity_reversal/merge_preparation_review/**`

Final config test:

- `tests/test_liquidity_reversal_final_config.py`

Project docs directly related to LR finalization / Research Pipeline / validation:

- `AI Trading/01_长期记忆/测试与验证命令.md`
- `AI Trading/01_长期记忆/项目事实库.md`
- `AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md`
- `AI Trading/03_策略研究中心/策略研究总览.md`
- `AI Trading/05_回测风控与模拟盘/Proposal验证流程.md`

Optional, only if human confirms they are PR12-required:

- `AI Trading/01_长期记忆/架构地图.md`
- `AI Trading/05_回测风控与模拟盘/P5中文交易诊断驾驶舱.md`
- `README.md`
- `AGENTS.md`
- `代理协作流程.md`
- `开发记录.md`
- `策略规格.md`
- `项目总规划.md`
- `AI Trading/01_长期记忆/项目总体架构.md`

### Boundary

This commit formalizes only:

- Restricted Variant B
- `portfolio_heat_cap=0.05`
- C profile formal scope
- B profile diagnostic-only
- `live_trading_enabled=false`

Not formalized:

- unrestricted Variant B
- Full original family
- Tier 3
- rolling_range
- PDH/PDL
- EQH/EQL
- runner
- partial TP
- structure target
- unexecuted proposal rows

### Git add commands

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

Optional docs, only after explicit human confirmation:

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

### Tests / checks after staging

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_liquidity_reversal_final_config -v
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline/tests -v
git diff --cached --check
git diff --cached --name-only | Select-String -Pattern '__pycache__|\.pyc$|storage/backtest_cache|\.jsonl$|full_audit'
```

Expected:

- final config test exits 0.
- research_pipeline tests exit 0.
- forbidden file scan returns no matches.

### Suggested commit message

```text
formalize restricted LR Variant B research candidate

- add final LR config for Restricted Variant B with portfolio heat cap
- set C profile formal scope and keep B profile diagnostic-only
- add final audit, robustness, regression, rollback, and cleanup evidence
- keep live trading disabled and exclude unexecuted proposal rows
```

## 8. Global Exclusion List

Do not stage or commit:

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

Do not include in this PR12 5-commit sequence:

- `trading_system/data/download.py`
- `trading_system/data/history.py`
- `scripts/check_data_quality.py`
- `scripts/download_okx_history.py`
- `scripts/run_btc_eth_p4_4_backtest.py`

These are data infra / SWAP reproducibility convenience files. If needed, commit them later in a separate data infra change.

## 9. Final Execution Notes

Recommended sequence:

1. Stage Commit 1 files only.
2. Run Commit 1 tests/checks.
3. Commit 1.
4. Repeat for Commit 2 through Commit 5.
5. After all 5 commits, run final full validation before any merge/tag discussion.

Do not merge or tag after these commits without a separate explicit confirmation.

Next Step:

- Wait for human confirmation.
- Then execute Commit 1 staging/test/commit first.
