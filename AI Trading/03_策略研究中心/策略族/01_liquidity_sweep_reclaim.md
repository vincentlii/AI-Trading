---
type: strategy-family
strategy_family: liquidity_sweep_reclaim
status: research_stopped
updated: 2026-06-21
tags:
  - strategy/pa-vpa
  - strategy/implemented
---

# 01_liquidity_sweep_reclaim

结论：`liquidity_reversal` causal rebuild 已停止。当前无 formal research candidate，Restricted Variant B 仅作 historical invalidated evidence，`live_trading_enabled=false`，holdout 未访问。

## 定位

扫损、假突破、快速收回。适合识别流动性池被穿越后迅速回收的反转或局部均值回归机会。

## 趋势角色

软过滤 / 反转豁免。逆势允许，但需要更高量价阈值、更清晰结构确认和风险降权。

## 当前实现

- sweep 后收盘回到池内侧。
- N 根内出现反向 CHoCH 或入场周期确认。
- 量价确认吸收、停止量或对手盘衰竭。
- 目标扣除成本后至少 `1.5R`。

## 当前状态

| 项目 | 结论 |
| --- | --- |
| 状态 | `research_stopped` |
| 正式候选 | 无 |
| 历史候选 | Restricted Variant B，已被 causal timestamp audit 否定 |
| 正确语义复验 | historical repair：5,078 笔，total_net_R=-356.64，PF=0.722；rebuilt 1H+15m：223 笔，total_net_R=-23.26，PF=0.724 |
| holdout | 未访问，继续封存 |
| live trading | `live_trading_enabled=false` |

历史配置和 183 笔指标只用于追溯，不得恢复、推广或作为下一策略的正式基线。

## 停止结论

- 旧 183 笔高收益主要来自错误 4H 确认时间、事后路径 exit、结果排序 exposure cap 和重复 physical event，不能迁移到正确语义。
- 15m 事件池并非完全无方向性，但 MFE/MAE 近似对称，属于宽事件池中的路径噪声。
- 1H same-bar failure auction 语义更干净；15m structural confirmation 的表面改善主要来自 confirmation chase 和 R geometry。
- 从 confirmation close 重新计算后，path-order 回到接近基线；固定持有仅有弱短期漂移，去重后 36h 转负、48h 接近零。
- Anatomy 到 execution 的 gross edge 只有约 +0.081R，约 0.228R 成本将其稳定翻为 -0.147R；成本是直接损耗，但上游 edge 太薄才是根因。
- PDH/PDL 比 Session H/L 更接近共识流动性，VPA 只有弱到中等 attribution 价值，均不足以恢复 LR。

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
- B profile 正式主配置。
- PDH/PDL、EQH/EQL active source。
- runner、partial TP、structure target 正式出场。
