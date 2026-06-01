# Post-Commit Merge Readiness Report

## 1. Primary Decision

B. 有 tracked unstaged diff，需处理。

核心结论：

- Commit 1-6 已完成，最近 6 个 commit 顺序正确。
- staged diff 为空。
- final config test 通过。
- research_pipeline tests 通过。
- compileall 通过。
- post-commit full-audit 通过，blocking=0。
- strategy regression check 通过。
- artifact validation 通过。
- safety boundary 未发现失败。
- 但当前工作区仍有 tracked unstaged diff，因此在真正 merge master / tag stable 前，需要先人工处理这些剩余 diff：保留、另开 commit、stash、或回退。

本报告不执行 merge，不执行 tag，不开始 trend_continuation。

## 2. Git Checks

### Branch

```text
codex/proposal-diagnostics
```

### Recent Commits

```text
6086f84 add data infra support for swap research reproducibility
fc22004 formalize restricted LR Variant B research candidate
a93e60f add reusable research pipeline audit and robustness framework
cbf8e0d add validated LR feature support for clean rebuild
d39d087 add research proposal config schema for LR rebuild
47ea6d8 add execution lineage and audited replay diagnostics
```

### Staged Diff

```text
git diff --cached --name-only
<empty>
```

结论：staged diff 为空。

### Unstaged Diff

当前仍有 tracked unstaged diff：

- `.obsidian/workspace.json`
- `AI Trading/01_长期记忆/架构地图.md`
- `AI Trading/05_回测风控与模拟盘/P5中文交易诊断驾驶舱.md`
- `README.md`
- `代理协作流程.md`
- `开发记录.md`
- `策略规格.md`
- `项目总规划.md`

当前仍有 untracked / excluded / future items：

- `AGENTS.md`
- `AI Trading/.claudian/`
- `AI Trading/.obsidian/community-plugins.json`
- `AI Trading/.obsidian/plugins/`
- `AI Trading/01_长期记忆/项目总体架构.md`
- `AI Trading/99_归档/`
- `tests/fixtures/regression_baselines/liquidity_reversal/stage6e_10000w/stage7_smoke_grouped_rows_snapshot.jsonl`

判断：

- 这些未提交内容不属于已经完成的 Commit 1-6。
- `.obsidian` / `.claudian` / `99_归档` 明确不应进入 master。
- `stage7_smoke_grouped_rows_snapshot.jsonl` 是前序 forbidden scan 排除项，不应在本轮直接提交。
- optional docs / root docs 需要人工决定是否另开 docs commit，或在 merge/tag 前 stash / revert。

### Diff Check

```text
git diff --check
```

结果：

- exit code 0。
- 仅 CRLF warning。
- 未发现 whitespace error。

## 3. Final Validation Results

### Final Config Test

Command:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_liquidity_reversal_final_config -v
```

Result:

```text
Ran 2 tests
OK
```

### Research Pipeline Tests

Command:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s research_pipeline\tests -v
```

Result:

```text
Ran 93 tests
OK
```

### Compile

Command:

```powershell
.\.venv\Scripts\python.exe -B -m compileall research_pipeline trading_system scripts
```

Result:

```text
compileall completed successfully
```

### Final Full Audit

Command:

```powershell
python -m research_pipeline.cli.research full-audit --strategy liquidity_reversal --artifact-dir storage\backtest_cache\pr11g_clean_rebuild\lr_combined_fix --output-dir storage\research_runs\liquidity_reversal\final\post_commit_full_audit
```

Result:

```json
{
  "audit_passed": true,
  "blocking_count": 0,
  "warning_count": 147,
  "strategy": "liquidity_reversal"
}
```

结论：

- full-audit passed。
- blocking issue = 0。
- warnings 为 accepted warnings，不阻断 readiness。

### Strategy Regression Check

Command:

```powershell
python -m research_pipeline.cli.research strategy-regression-check --strategy liquidity_reversal --baseline-dir tests\fixtures\regression_baselines\liquidity_reversal\stage6e_10000w --summary-dir tests\fixtures\regression_baselines\liquidity_reversal\stage6e_10000w --output-dir storage\research_runs\liquidity_reversal\final\post_commit_strategy_regression
```

Result:

```json
{
  "passed": true,
  "proposal_only": true,
  "formal_conclusion_enabled": false,
  "failed": 0
}
```

结论：strategy regression check passed。

### Artifact Validation

Command:

```powershell
python -m research_pipeline.cli.research validate-artifacts --artifact-index docs\research\liquidity_reversal\final_evidence\artifact_index.json
```

Result:

```json
{
  "checked_count": 10,
  "errors": [],
  "passed": true
}
```

结论：artifact validation passed。

## 4. Final Config Safety Check

已确认 `configs/strategies/liquidity_reversal.yaml` 当前关键字段：

- `config_version: pr12_final_restricted_variant_b`
- `status: formalized_research_candidate`
- `live_trading_enabled: false`
- `formalized_candidate: restricted_variant_b`
- `profile_scope: C_only`
- `diagnostic_profiles: [B]`
- `portfolio_heat_cap: 0.05`
- `b_profile: diagnostic_only`
- `unrestricted_variant_b: false`
- `b_profile_main_config: false`
- `unexecuted_proposal_rows: excluded_from_performance`

结论：

- final config 仍是 Restricted Variant B。
- `portfolio_heat_cap=0.05` 保持。
- C profile 是 formal scope。
- B profile 保持 diagnostic-only。
- `live_trading_enabled=false` 保持。

## 5. Safety Boundary Check

### Risk / Cost / Exit Boundaries

检查结果：

- 未发现 `trading_system/backtest/risk.py` 进入 Commit 1-6。
- 未发现 RiskEngine 放宽。
- 未发现 fee / funding / margin / notional cap 正式风控放宽。
- 未发现 stop / target / exit 正式公式被放宽。
- Session_HL / dynamic_time_cut / quality_aware_capped_sizing 仅按 Restricted Variant B final config 收口，未启用 unrestricted family。

### Forbidden Committed Content

检查最近 6 个 commit：

- 未提交 `storage/backtest_cache/**`。
- 未提交 `.obsidian/**`。
- 未提交 `.claudian/**`。
- 未提交 `AI Trading/99_归档/**`。
- 未提交 parquet。
- 未提交 storage row-level artifacts。

注意：

- 最近 6 个 commit 中包含一个小型 regression fixture：`tests/fixtures/regression_baselines/liquidity_reversal/stage6e_10000w/stage6e_aggregated_comparison_snapshot.csv`。
- 该文件位于 tests fixture 目录，是 regression snapshot，不是 `storage/backtest_cache` 下的 row-level research output。
- 前序 forbidden scan 已排除 `.jsonl` row-level fixture。

## 6. Remaining Work Before Merge / Tag

在人工确认 merge/tag 前，必须先处理当前 dirty worktree：

1. 对 optional tracked docs 做决定：
   - commit 到单独 docs commit；
   - stash；
   - 或回退。

2. 明确排除本地/归档内容：
   - `.obsidian/workspace.json`
   - `AI Trading/.claudian/`
   - `AI Trading/.obsidian/plugins/`
   - `AI Trading/.obsidian/community-plugins.json`
   - `AI Trading/99_归档/`

3. 处理未提交 `.jsonl` fixture：
   - 保持不提交；
   - 或如果确认为必要 fixture，需单独人工确认后再处理。

4. 处理本报告本身：
   - 本报告是 post-commit readiness 输出文件。
   - 如需保留在 master，需要单独人工确认是否作为 docs commit 纳入。

## 7. Readiness Summary

已通过：

- staged diff empty。
- final config test passed。
- research_pipeline tests passed。
- compileall passed。
- final full-audit passed。
- strategy regression check passed。
- artifact validation passed。
- final config safety boundary passed。
- Commit 1-6 未包含 storage/backtest_cache / .obsidian / .claudian / 99_归档。

阻断 merge/tag 的剩余事项：

- tracked unstaged diff 仍存在。
- untracked local / excluded items 仍存在。

## 8. Final Decision

B. 有 tracked unstaged diff，需处理。

Next Step：

- 不要直接 merge/tag。
- 先人工决定剩余 tracked docs / local files 的处理方式。
- 工作区清干净或明确隔离后，再执行 merge master / tag stable 的人工确认步骤。
