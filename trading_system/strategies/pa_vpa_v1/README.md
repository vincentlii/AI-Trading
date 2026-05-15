# PA+VPA 策略体系 v1

本目录记录“价格行为 + 量价分析”策略体系的自然语言规格。它来自三份研究文档的整合、去重和趋势门控优化，不是可执行代码插件。

当前可执行代码插件仍是：

- `trading_system/strategies/trend_price_volume_v1/strategy.py`

当前代码插件只覆盖本体系中的两个早期子集：

- `01_liquidity_sweep_reclaim` 的第一版：`liquidity_reversal`
- `04_breakout_pullback_continuation` 的第一版：`trend_continuation`

## 研究来源

- `交易策略研究1-PA+VPA的top10策略（Gemini版）.md`
- `交易策略研究2-PA+VPA的top10策略（GPT版）.md`
- `交易策略研究3-PA+VPA的趋势前置门控研究（进阶）.md`

Gemini 版更偏 Wyckoff / VSA 结构命名，GPT 版更偏量化触发器表达，进阶版负责判断趋势门控在不同策略族中的角色。

核心结论：

- 不把两个 Top 10 机械合并为 20 个策略。
- 去重后保留 8 个独立策略族。
- 趋势判断不统一硬前置；它按策略类型分别承担必要条件、软过滤、环境选择器或风险调节器。

## 最终 Top 8 策略族

| ID | 策略族 | 定位 | 趋势判断角色 |
| --- | --- | --- | --- |
| 01 | `liquidity_sweep_reclaim` | 扫损、假突破、快速收回 | 软过滤 / 反转豁免 |
| 02 | `stopping_volume_retest` | 停止量后缩量二次测试 | 软过滤 / 局部结构确认 |
| 03 | `absorption_box_break` | 高量窄幅吸收后选择方向 | 辅助过滤 |
| 04 | `breakout_pullback_continuation` | 放量突破、缩量回踩、顺势续攻 | 必要条件 / 硬门控 |
| 05 | `failed_breakout_effort_result` | 努力结果背离后的失败突破 | 软过滤 |
| 06 | `climax_exhaustion_reversal` | 高潮量、二次推进衰竭、极值反转 | 风险调节 |
| 07 | `compression_expansion_breakout` | 缩量压缩后的真实扩张 | 必要条件 / 硬门控 |
| 08 | `hvn_fvg_rejection_trap` | HVN/FVG/价值区接受失败 | 环境选择器 |

## 文件说明

- `strategy_map.md`：Gemini/GPT Top 10 与最终 Top 8 的去重映射。
- `specs/01_liquidity_sweep_reclaim.md`：流动性扫荡回收。
- `specs/02_stopping_volume_retest.md`：停止量后二次缩量测试。
- `specs/03_absorption_box_break.md`：高量窄幅吸收突破。
- `specs/04_breakout_pullback_continuation.md`：放量突破缩量回踩续攻。
- `specs/05_failed_breakout_effort_result.md`：努力结果背离失败突破。
- `specs/06_climax_exhaustion_reversal.md`：高潮量衰竭反转。
- `specs/07_compression_expansion_breakout.md`：缩量压缩真实扩张。
- `specs/08_hvn_fvg_rejection_trap.md`：HVN/FVG 放量拒绝陷阱。

## 实现边界

本目录只描述策略逻辑和后续实现方向。策略代码实现必须继续通过 `Strategy` 接口输出 `StrategySignal`，不得直接下单、不得管理账户、不得绕过 `RiskEngine`。
