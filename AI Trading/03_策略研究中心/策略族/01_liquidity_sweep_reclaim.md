---
type: strategy-family
strategy_family: liquidity_sweep_reclaim
status: partially_implemented
updated: 2026-05-19
tags:
  - strategy/pa-vpa
  - strategy/implemented
---

# 01_liquidity_sweep_reclaim

结论：当前已通过 `trend_price_volume_v1` 的 `liquidity_reversal` 实现 BTC/ETH OHLCV v1 子集。

## 定位

扫损、假突破、快速收回。适合识别流动性池被穿越后迅速回收的反转或局部均值回归机会。

## 趋势角色

软过滤 / 反转豁免。逆势允许，但需要更高量价阈值、更清晰结构确认和风险降权。

## 当前实现

- sweep 后收盘回到池内侧。
- N 根内出现反向 CHoCH 或入场周期确认。
- 量价确认吸收、停止量或对手盘衰竭。
- 目标扣除成本后至少 `1.5R`。

## 未实现

- CVD、taker imbalance、OI。
- 盘口吸收。
- 二次缩量测试。
- FVG/VWAP retest。
- 更细的流动性池识别。
