---
type: strategy-family
strategy_family: liquidity_sweep_reclaim
status: partially_implemented
updated: 2026-05-25
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

## 长期研究结论

- 单纯极值穿刺不是扫荡；需要异常成交量、结构收回和 effort/result 失衡共同验证。
- 逆势扫荡不应被统一趋势硬门控直接误杀，但必须要求更高量价阈值、更清晰 CHoCH 或风险降权。
- 最佳入场不应追扫荡极值，而应等待收回确认、结构确认或合理回踩。
- 风控上不能通过简单放宽 stop/ATR 上限掩盖问题，应优先研究扫荡距离、结构止损、reclaim 速度和目标 R 是否匹配。
- ETH 噪音通常高于 BTC，参数应允许资产级覆盖，不强行共用一套阈值。
- reclaim RVOL 应分层诊断：`ideal_reclaim` 为 `<= 1.2`，`acceptable_reclaim` 为 `1.2-1.6` 且不直接硬拒绝，`high_reclaim_rvol` 为 `> 1.6`。

## 未实现

- CVD、taker imbalance、OI。
- 盘口吸收。
- 二次缩量测试。
- FVG/VWAP retest。
- 更细的流动性池识别。
