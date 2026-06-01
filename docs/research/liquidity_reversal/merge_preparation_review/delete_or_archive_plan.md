# Delete Or Archive Plan

## 结论

本阶段没有删除任何文件。当前建议先按白名单提交，再单独执行 cleanup PR；不要在 merge 前用 `git add -A`。

## 已删除

- 无。

## 已移动到 archive / legacy

- 无新增移动。

## 未跟踪且应忽略或谨慎处理

- `AI Trading/.obsidian/plugins/**`：Obsidian 插件文件，最大文件约 3.8 MB，不应进入本次策略 merge。
- `AI Trading/.claudian/**`：本地工具配置，不应进入本次策略 merge。
- `AI Trading/99_归档/**`：归档资料，默认不进入本次 merge。
- `storage/**`：被 `.gitignore` 忽略。仅可在人工确认后 force-add 精选 final evidence。

## 仍存在但只作为 historical reference

- `storage/backtest_cache/pr11g_clean_rebuild/**`
- `storage/backtest_cache/pr11h_robustness/**`
- `storage/backtest_cache/pr11h_fix/**`
- old PR11C-PR11G artifacts。
- rejected proposal artifacts。
- diagnostic-only research outputs。

## 不应进入 master 主路径

- PR11A-PR11H 中间 artifacts。
- broken lineage artifacts。
- old proposal/debug rows。
- obsolete reports。
- 临时 jsonl/csv/md。
- 一次性 runner 输出。
- old backtest cache outputs。

## 建议后续 cleanup 顺序

1. 先确认 final config、final memo、final baseline、final audit summary 已进入可追踪位置。
2. 再清理 `.obsidian`、`.claudian`、`AI Trading/99_归档` 中不相关未跟踪内容。
3. 最后清理 storage 中历史 cache；不要删除 final evidence。
