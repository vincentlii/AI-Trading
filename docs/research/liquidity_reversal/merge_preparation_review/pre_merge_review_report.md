# PR12 Merge Preparation Review

## Primary Decision

B. 有临时文件或过程 artifacts 可能误入 commit，需要先按白名单 staging。

## 结论

PR12 formalization 与 validation 已完成，但当前工作区不适合直接 commit / merge / tag。

原因：

- `git status` 显示大量未跟踪文件。
- `storage/` 被 `.gitignore` 忽略，final artifacts 不会自动进入 master。
- `.obsidian` plugin、本地工具配置、归档资料存在误提交风险。
- backtest/execution 相关 diff 需要人工确认属于已验证 lineage / audit 支持，而不是策略边界放宽。

## 本次应进入 master 的内容

- Restricted Variant B 正式候选配置。
- `portfolio_heat_cap=0.05`。
- C profile formal scope。
- B profile diagnostic-only。
- Research Pipeline / Full Audit Gate / robustness runners。
- final research memo。
- final regression baseline 和 final audit/robustness summary，若人工确认需要进入 master，应精确 force-add。
- cleanup / rollback / legacy migration manifest。

## 不应进入 master 的内容

- PR11A-PR11H 中间 row-level artifacts。
- broken lineage artifacts。
- old proposal/debug rows。
- storage/backtest_cache。
- `.obsidian` plugin。
- `.claudian` local config。
- unrestricted Variant B。
- Full original family。

## Git Hygiene

- branch = `codex/proposal-diagnostics`
- untracked files = 236
- largest untracked = `AI Trading/.obsidian/plugins/realclaudian/main.js`，约 3.8 MB
- `git diff --check` passed with CRLF warnings only
- `storage/` ignored by `.gitignore`

## Safety Boundary

Final LR config 与 Restricted Variant B 一致：

- closed=183
- total_R=85.070
- PF=7.80
- max_concurrent=10
- same_direction_overlap=303
- portfolio_heat=0.05

未在 final config 中正式化：

- B profile。
- unrestricted Variant B。
- Full original family。
- Tier 3。
- PDH/PDL。
- EQH/EQL。
- runner / partial TP / structure target。

## Next Step

继续 PR12 cleanup / staging review。

人工确认后再执行：

1. 按 `commit_candidate_files.md` 白名单 staging。
2. 明确是否 force-add 精选 final artifacts。
3. 排除 `.obsidian`、`.claudian`、`AI Trading/99_归档`、`storage/backtest_cache`。
4. 人工 review execution/backtest diff。
5. 再 commit / merge / tag。
