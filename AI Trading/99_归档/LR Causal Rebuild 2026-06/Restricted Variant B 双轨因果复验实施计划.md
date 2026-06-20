# Restricted Variant B 双轨因果复验实施计划

**目标：** 用同一套因果 execution、RiskEngine、成本和 portfolio heat engine，独立复验历史修复版与 1H+15m 重建版。

## Task 1：冻结 policy 与组合选择

- [x] RED：三 setup、历史 approval、sizing/exit mapping、C profile 和 5% heat 固定。
- [x] GREEN：实现 immutable policy 与 outcome-independent dedupe/heat selection。

## Task 2：Track B 15m confirmation

- [x] RED：displacement 只能使用 event 后 confirmed 15m bar 和 causal ATR。
- [x] RED：MSS swing 必须在 trigger 前完成 2-right confirmation。
- [x] RED：entry 必须严格晚于 trigger close，stop 必须位于方向正确一侧。
- [x] GREEN：实现 event artifact adapter 与 confirmation scanner。

## Task 3：双轨 runner 与执行

- [x] RED：development-only、holdout 拒绝、A/B artifact 隔离、三成本档。
- [x] GREEN：接入 fresh scanner、multitimeframe artifact、现有 causal executor 与 75% attempt-3 risk。

## Task 4：审计、CLI 与报告

- [x] RED：manifest lineage/time contract、closed-trade-only metrics、CLI `--track historical|rebuilt|both`。
- [x] GREEN：写入 artifacts、运行 Full Audit、生成无 winner 集中报告。

## Task 5：验证

- [x] 聚焦 unittest、LR 回归、compileall、`git diff --check`。
- [x] 真实短窗口 smoke 运行 A/B；完整 development 交给用户手动执行。

## 当前状态

- 实现完成，Restricted Variant B 继续 suspended。
- 2023-08-01 至 2023-09-30 双轨 smoke 的 Full Audit 均为 pass。
- 完整 development 已完成：historical 为 5,209 candidates / 5,078 base closed trades / `-356.64R`；rebuilt 为 1,363 / 223 / `-23.26R`。
- 两轨 Full Audit 均通过，但所有总体成本档均为负；不读取 holdout、不选择 winner。
- Track A 研究问题已关闭；Track B 仅保留 `1H Session H/L + 15m MSS` 上游 diagnostic hypothesis。
- 复盘报告：[[Restricted Variant B 双轨因果复验 2026-06-20]]。
