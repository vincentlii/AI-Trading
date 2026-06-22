---
type: research-report
strategy_family: breakout_pullback_continuation
status: stopped
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
