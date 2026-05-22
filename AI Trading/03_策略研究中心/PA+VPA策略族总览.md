---
type: strategy-system
status: active
updated: 2026-05-19
tags:
  - strategy/pa-vpa
  - domain/strategy
---

# PA+VPA策略族总览

结论：PA+VPA v1 去重后保留 8 个策略族；趋势判断不是统一硬前置，而是按策略类型承担硬门控、软过滤、环境选择器或风险调节。

| ID | 策略族 | 状态 | 趋势角色 |
| --- | --- | --- | --- |
| 01 | [[01_liquidity_sweep_reclaim]] | BTC/ETH OHLCV v1 子集已实现 | 软过滤 / 反转豁免 |
| 02 | [[02_stopping_volume_retest]] | 未实现 | 软过滤 |
| 03 | [[03_absorption_box_break]] | 未实现 | 辅助过滤 |
| 04 | [[04_breakout_pullback_continuation]] | BTC/ETH OHLCV v1 子集已实现 | 必要条件 / 硬门控 |
| 05 | [[05_failed_breakout_effort_result]] | 未实现 | 软过滤 |
| 06 | [[06_climax_exhaustion_reversal]] | 未实现 | 风险调节 |
| 07 | [[07_compression_expansion_breakout]] | 未实现 | 必要条件 / 硬门控 |
| 08 | [[08_hvn_fvg_rejection_trap]] | 未实现 | 环境选择器 |

## 实现优先级建议

1. 先继续验证 01/04 的 BTC/ETH OHLCV v1。
2. 再实现 07，因为它与趋势延续和压缩突破路径最接近。
3. 后续实现 02/03/05/06/08，并按样本量、成本和假突破风险排序。

## 关键原则

- 不把 Gemini/GPT Top 10 机械合并成 20 个策略。
- 同一交易结构只保留一个策略族。
- 策略只输出标准信号，不管理账户、不下单。
- 回测和模拟盘必须通过 RiskEngine。
