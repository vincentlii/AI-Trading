# Git Hygiene Report

## 结论

当前不能直接 `git add -A`。工作区含大量未跟踪文件与本地工具/归档内容，存在误提交风险。

## Branch

- branch = `codex/proposal-diagnostics`

## git status 摘要

- tracked modified files: 34+
- untracked files: 236
- `storage/` ignored by `.gitignore`

## git diff --stat 摘要

当前 tracked diff 约：

- 34 files changed
- 1678 insertions
- 175 deletions

主要集中在：

- `trading_system/backtest/execution.py`
- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/config/loader.py`
- `tests/*`
- `AI Trading/*`

## git diff --check

结果：通过，无 whitespace error。

仅有 CRLF warning，涉及多个既有文件。

## 大体积未跟踪风险

最大未跟踪文件：

- `AI Trading/.obsidian/plugins/realclaudian/main.js`，约 3.8 MB。
- `AI Trading/.obsidian/plugins/realclaudian/styles.css`，约 126 KB。

这些不应进入本次 merge。

## storage / backtest cache

- `storage/` 被 `.gitignore` 忽略。
- `storage/backtest_cache/**` 不会自动进入 commit。
- `storage/research_runs/liquidity_reversal/final/**` 也不会自动进入 commit。

若 final artifacts 必须进入 master，只能精确 `git add -f` 小型 final 文件，不能 force-add 整个 `storage/`。

## final artifacts 缺失检查

存在：

- `storage/research_runs/liquidity_reversal/final/final_regression_baseline.json`
- `storage/research_runs/liquidity_reversal/final/final_full_audit_report.md`
- `storage/research_runs/liquidity_reversal/final/final_robustness_summary.md`
- `storage/research_runs/liquidity_reversal/final/final_test_results.md`
- `storage/research_runs/liquidity_reversal/final/merge_readiness_report.md`
- `storage/research_runs/liquidity_reversal/final/rollback_instructions.md`

注意：这些文件当前被 `.gitignore` 排除。

## 建议 staging 策略

只按 `commit_candidate_files.md` 白名单 staging。

禁止：

```powershell
git add -A
```
