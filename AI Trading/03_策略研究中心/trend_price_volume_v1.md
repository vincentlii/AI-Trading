---
type: strategy-card
strategy: trend_price_volume_v1
status: implemented_subset
updated: 2026-06-23
tags:
  - strategy/implemented
  - domain/strategy
---

# trend_price_volume_v1

结论：这是当前唯一可执行策略插件，只对应 PA+VPA 01 与 04 的 BTC/ETH OHLCV confirmed K 线 v1 子集，不等于完整 PA+VPA/SMC/VSA 策略。

## 当前能力

- 使用 confirmed OHLCV K 线。
- 生成 `trend_continuation` 与 `liquidity_reversal` 两类标准信号。
- 不管理账户、不下单、不绕过风控。
- 通过 `StrategyContext.features["strategy_parameters"]` 支持参数覆盖，但正式调整必须走 proposal。
- 支持 P5/P5.1/P5.2 对信号漏斗、量价拒绝、风控拒绝和 Near Miss 的诊断。

## v1 可依赖

- OHLCV。
- 多周期 K 线。
- confirmed K 线。
- 基础趋势、波动、量价指标。
- 已有 P5/P5.1/P5.2 诊断结果。

## v1 不应依赖

- OB/FVG 生命周期。
- ToD RVOL。
- AVWAP / Session VWAP。
- CVD/OI。
- 订单簿。
- taker imbalance。
- 宏观事件过滤。

这些能力属于后续增强，不得在当前 v1 中被描述成入场必要条件。

## 映射关系

| 当前 setup | PA+VPA 策略族 | 实现状态 | 趋势门控 |
| --- | --- | --- | --- |
| `trend_continuation` | [[04_breakout_pullback_continuation]] | 已实现 BTC/ETH OHLCV v1 | 04 周期趋势可作为硬门控 |
| `liquidity_reversal` | [[01_liquidity_sweep_reclaim]] | 已实现 BTC/ETH OHLCV v1 | 01 周期趋势更适合确认、软过滤或风险降权 |

## 逻辑清晰度规则

- 入场逻辑、失效条件、止损逻辑、出场逻辑和拒绝原因必须分开描述。
- 诊断项只能解释信号为何被过滤，不应被自动升级成新的交易条件。
- 04 延续类逻辑可以要求趋势背景；01 扫荡反转逻辑不能被统一趋势硬门控误杀。
- 逆势 01 信号可以提高量价阈值、降低风险权重或要求更清晰结构确认，但不应直接等同无效。

## P5.2 模拟盘前诊断

进入正式 P6 模拟盘前，必须保留并检查：

- 量价拒绝细分。
- 风控拒绝细分。
- Near Miss。
- `stop_distance/ATR` 分布。
- 成本后 R 倍数。

## TC/BP strict causal 研究状态（2026-06-23）

- `TC BP Entry Model Quick Compare` 仅为 development diagnostic，不是正式策略、execution 或 closed-trade 证据。
- True breakout 已修正为 fresh cross：前一根 4H close 必须位于 level 内侧；第一次 accepted breakout 会消耗该 level；level 最长有效 180 天；trend_state 只由 causal confirmed swings 计算。
- 右侧确认使用 BOS 后下一根连续 15m bar close；若 retest、确认等待期或 entry bar 已触及 invalidation，则不得入场。
- 独立研究起点的窗口不变性已验证：2024-07 至 2024-11 的 34 个 physical event 与 level_id 全部一致。
- BTC 2024-07 至 2024-11 只有 34 个 event、7 个右侧触发，低于样本 gate，只能判定 `inconclusive_need_more_development_scan`。
- BTC 2022-01 至 2024-11 有 185 个 event、46 个右侧触发；upstream acceptance 4H/12H/24H median return 均为负，decision 为 `stop_bp_upstream_breakout_edge_failed`。右侧 +1R path-order 尚可，但 4H 至 96H 固定时间收益多数为负，表现更像短时冲击后回吐，不支持持续趋势 edge。
- 当前 TC/BP 不进入 execution、exit/sizing/cost 优化或 formalization；以 [[TC BP Entry Model Quick Compare Extended BTC 2022-01 to 2024-11]] 为主报告，短窗口仅作对照。

## TC/BP 35M 综合诊断（2026-06-23）

- 新增 `TC BP 35M Comprehensive Diagnostic Report`，性质为 diagnostic-only；不生成 `execution_rows` 或 `closed_trade_rows`，不读取 2024-12-01 后 holdout，不修改 RiskEngine、cost、exit、sizing 或正式配置。
- BTC 2022-01 至 2024-11 的 no-trend-gate raw accepted breakout candidate 为 974 个；current hard confirmed-swing trend match 仅 274 个，说明单一 confirmed-swing trend hard gate 存在明显过度过滤风险。
- 同一 level later accepted attempt 保留后，attempt 1 / attempt 2 / attempt >=3 分别为 362 / 243 / 369 个；level first-consume 规则需要继续作为诊断维度，而不是立即作为唯一正式语义。
- `right_level_retest_confirm_soft_vpa` 将单根 wick breach 改为风险标签，允许 reclaim 后继续诊断；触发 702/974，但 4H/12H fixed return 仅 -0.0178% / +0.0014%，说明放宽 PA 后样本恢复，edge 仍未稳定。
- VPA 分桶有初步区分：`weak_vpa` 的 48H median 为 -0.4100%，`normal_vpa` 为 +0.2086%，`strong_vpa` 为 -0.0802%；VPA 有诊断价值，但不能直接作为正式 gate 或 fitted score。
- 本轮 primary decision 为 `trend_gate_overfiltered_continue_soft_score`；下一步只允许做 trend score 与 VPA attribution 的机制诊断，不进入 execution、exit/sizing 或 formalization。

## 后续增强

- 接入 CVD、OI、taker imbalance。
- 接入 AVWAP / Session VWAP。
- 接入 OB/FVG 生命周期。
- 按资产和 session 配置阈值。

## 权威来源

- [[策略规格]]
- `trading_system/strategies/trend_price_volume_v1/strategy.md`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
