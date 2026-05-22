---
type: strategy-card
strategy: trend_price_volume_v1
status: implemented_subset
updated: 2026-05-22
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

## 后续增强

- 接入 CVD、OI、taker imbalance。
- 接入 AVWAP / Session VWAP。
- 接入 OB/FVG 生命周期。
- 按资产和 session 配置阈值。

## 权威来源

- [[策略规格]]
- `trading_system/strategies/trend_price_volume_v1/strategy.md`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
