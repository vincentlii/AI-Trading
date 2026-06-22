---
type: research-report
strategy_family: breakout_pullback_continuation
status: stopped_after_first_pullback_v2
updated: 2026-06-22
---

# TC BP Strict Causal Smoke

## 结论

Profile C 严格因果 BP 的统计门改善，但视觉结构门失败，不进入 execution feasibility，不启动四年 development 扫描。

## 范围

- BTC/ETH USDT SWAP，2024-07-01 至 2024-11-30。
- Holdout 从 2024-12-01 开始，本轮未读取。
- 只从 raw OHLCV 重新生成；未复用旧 event、candidate、filter、execution 缓存。
- 4H 严格结构事件，15m BOS，`signal_time < entry_time`。
- 未修改 RiskEngine、成本、stop、notional cap 或正式配置。

## 结果

- setup rows / unique physical events：142 / 96。
- 4H / 12H median signed return：0.1324% / 0.3344%。
- +1R-first / invalidation-first：47.89% / 30.28%。
- BTC 4H/12H：0.2219% / 0.1220%。
- ETH 4H/12H：-0.0086% / 0.4398%。
- long 4H/12H：0.1735% / 0.3536%。
- short 4H/12H：-0.0032% / 0.3259%。

统计门通过，但 20 图显示多笔 confirmation 已远离 level，且部分 shallow 事件更像趋势中后段追随。Decision：`engineering_or_visual_audit_failed`；execution 未运行。

## 审计

因果审计通过。第一次扫描的 868 rows 因同一 breakout 对多个历史 swing level 重复计数而作废；修复为每个 breakout/direction/setup 只保留最近有效结构位后，已从 raw OHLCV 重跑。

20 个确定性抽样图已生成 PNG/HTML/SVG 并完成审查。视觉状态为 `fail_confirmation_chase_or_level_geometry`，不能把正向 diagnostic 直接解释为可交易 edge。

## 边界

- 不调 exit、sizing、quality gate 或 cost-aware admission。
- 不运行四年扫描，除非未来提出新的上游 BP 机制。
- `bp_shallow_cost_aware_admission_v3` 继续作为 invalidated historical evidence。

## First Pullback Geometry v2

在独立分支 `codex/tc-bp-strict-causal-smoke` 上完成 first-pullback lifecycle v2：

- breakout 时冻结 level、ATR 与 trend state；acceptance 后动态更新 impulse extreme。
- attempt 1/2 分层，attempt 3 拒绝；close 回到结构区、过深 wick、过远 extension 为硬拒绝。
- balanced 保留研究样本，clean 仅作视觉 sanity check；visual score 不参与信号过滤。
- 15m BOS 使用索引定位；entry geometry 单独标记为 diagnostic label，不反馈上游信号。
- repeated-boundary 改用第二次反应确认时已经可知的 ATR，不再使用全样本 ATR 中位数。
- diagnostic 数据查询严格截止 `2024-12-01` holdout 前；临界事件的未来标签允许缺失。

五个月 raw OHLCV 重扫结果：

| setup | rows / unique | 4H median | 12H median | +1R first | invalidation first |
|---|---:|---:|---:|---:|---:|
| level retest v1 control | 47 / 47 | +0.1493% | +0.3982% | 57.45% | 38.30% |
| shallow v1 causal control | 75 / 75 | -0.0032% | +0.1904% | 33.33% | 29.33% |
| v2 balanced | 34 / 34 | +0.0732% | -0.0317% | 55.88% | 35.29% |
| v2 clean | 9 / 9 | -0.5293% | -0.0133% | 44.44% | 44.44% |

v2 balanced 的 median/p90 signal-to-level 为 `1.034/1.453 ATR`，confirmation chase rate 为 `26.47%`，second-pullback rate 为 `17.65%`。它没有达到 `unique events >= 50`，且 12H 方向诊断转负；Decision 为 `semantic_filter_overfit_sample_collapse`。

Physical candidate funnel 在 level alternatives 去重前有 16,864 行，按真实 breakout 去重后为 323 个；主要损耗是 extension 过远 103、pullback 过深 68、deep reentry 45、15m 无 BOS 39、confirmation chase hard cap 5。最终 34 个 balanced signals 与 funnel 可以逐项对账。

结论：首次回踩语义已经工程化，但本组 balanced/clean 规则没有保留足够且稳定的方向优势。execution、四年扫描、exit/sizing/quality gate 优化继续封锁；不得为了样本数放宽规则或恢复旧缓存。

GitHub 可读取的完整证据包：[[TC BP First Pullback v2 Evidence/README]]。
