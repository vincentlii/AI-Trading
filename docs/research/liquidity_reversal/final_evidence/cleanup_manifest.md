# Cleanup Manifest

## 保留主路径

- `configs/strategies/liquidity_reversal.yaml`
- `docs/research/liquidity_reversal/final_research_memo.md`
- `storage/research_runs/liquidity_reversal/final/`
- `storage/backtest_cache/pr11g_clean_rebuild/`
- `storage/backtest_cache/pr11h_fix/`

## 历史参考，不作为 PR12 决策依据

- PR11A-PR11G old proposal artifacts。
- broken lineage artifacts。
- old proposal/debug rows。
- obsolete reports。
- unexecuted proposal rows。

## 本 PR 未直接删除的原因

当前工作区已有大量既有未提交变更。为避免误删用户或历史研究产物，PR12 只建立 final 主路径和废弃边界，不执行大规模删除。

## 后续清理规则

删除或移动旧 artifacts 前，必须确认：

- final config、final baseline、final audit、final robustness summary 已存在。
- old artifacts 不再被 registry 引用为 current source。
- cleanup diff 中不包含 raw data、final baselines 或 audit evidence。
