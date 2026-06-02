---
type: strategy-family
strategy_family: liquidity_sweep_reclaim
status: formal_research_candidate
updated: 2026-06-02
tags:
  - strategy/pa-vpa
  - strategy/implemented
---

# 01_liquidity_sweep_reclaim

结论：`liquidity_reversal` 已完成 LR 研究收口，当前正式状态是 formal research candidate；它不是 live trading strategy，`live_trading_enabled=false`。

## 定位

扫损、假突破、快速收回。适合识别流动性池被穿越后迅速回收的反转或局部均值回归机会。

## 趋势角色

软过滤 / 反转豁免。逆势允许，但需要更高量价阈值、更清晰结构确认和风险降权。

## 当前实现

- sweep 后收盘回到池内侧。
- N 根内出现反向 CHoCH 或入场周期确认。
- 量价确认吸收、停止量或对手盘衰竭。
- 目标扣除成本后至少 `1.5R`。

## 当前正式研究候选

| 项目 | 结论 |
| --- | --- |
| 正式候选 | Restricted Variant B |
| 组合 | Tier 1 + Positive Tier 2 |
| 风险限制 | `portfolio_heat_cap=0.05` |
| 正式适用范围 | C profile |
| B profile | diagnostic-only |
| live trading | `live_trading_enabled=false` |
| 最终指标 | closed=183，total_R=85.070，PF=7.80，max_concurrent=10，same_direction_overlap=303，portfolio_heat=0.05 |

正式化不包含 unrestricted Variant B、Full original family、Tier 3、rolling_range、PDH/PDL、EQH/EQL、runner、partial TP、structure target 或 unexecuted proposal rows。

## 研究收口结论

- raw candidates=0 的根因不是 LR 方向无效，而是旧 structure source 使用全历史 range high/low，结构位过旧且离当前价格太远。
- active structure source 已从全历史 range high/low 调整为 `recent_swing` / `rolling_range`；其中 `recent_swing` 是稳定 baseline，`rolling_range` 保留观察。
- Session_HL 在 clean rebuild 中表现强，但当前仍作为通过 proposal 验证的 LR family 组成部分，不代表所有 session source 均已正式泛化。
- PDH/PDL、EQH/EQL 当前保留 diagnostic / backlog，需要后续 scanner/source 支持。
- attempt_4 displacement 是高质量主 setup；attempt_3 CHOCH/MSS 是覆盖更宽的 secondary setup。
- B profile 不是没有候选，但 formal approval 极低；未发现 writer / join / execution mapping 丢失，因此当前只保留 diagnostic-only。
- 旧 PR11C-PR11G 结果只作为历史参考，最终决策以 clean rebuild、full-audit、robustness、exposure restriction 和 final evidence 为准。

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
