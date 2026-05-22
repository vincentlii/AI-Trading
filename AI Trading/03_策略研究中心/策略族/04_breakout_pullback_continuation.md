---
type: strategy-family
strategy_family: breakout_pullback_continuation
status: partially_implemented
updated: 2026-05-19
tags:
  - strategy/pa-vpa
  - strategy/implemented
---

# 04_breakout_pullback_continuation

结论：当前已通过 `trend_price_volume_v1` 的 `trend_continuation` 实现 BTC/ETH OHLCV v1 子集。

## 定位

放量突破、缩量回踩、顺势续攻。适合趋势延续交易。

## 趋势角色

必要条件 / 硬门控。必须顺高一级趋势或完成趋势启动确认。

## 当前实现

- 趋势周期输出 `TREND`。
- 结构周期出现同向 BOS + displacement。
- 回踩到 active zone。
- 入场周期得到量价确认。
- 达到 `1R` 后部分止盈，剩余仓位使用 Chandelier Exit。

## 未实现

- OB/FVG/AVWAP/Session VWAP。
- 高量低结果过滤。
- CVD/OI/盘口吸收。
- 按 session 的 RVOL 阈值。
