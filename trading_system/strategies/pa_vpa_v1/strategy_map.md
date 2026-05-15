# PA+VPA 策略去重映射 v1

本文档把 Gemini 版 Top 10、GPT 版 Top 10 和趋势门控进阶研究整合为最终 Top 8 策略族。

## 去重原则

- 同一交易结构只保留一个策略族，命名差异不单独保留。
- Wyckoff、VSA、ICT、价格行为术语如果描述的是同一条交易链路，合并为同一族。
- 能作为独立 alpha 来源的结构保留为独立策略族。
- 仅是入场细节、确认方式或资产适配差异的内容，归为策略族变体。
- 趋势门控只在提供独立信息时保留；如果只是重复 PA/VPA 条件，不作为额外门槛。

## Gemini Top 10 映射

| Gemini 策略 | 最终归属 | 处理 |
| --- | --- | --- |
| 高潮放量假跌破 / Spring | 01 `liquidity_sweep_reclaim` | 核心保留 |
| 派发后上冲回落 / UTAD | 01 `liquidity_sweep_reclaim` | 镜像方向保留 |
| 努力与结果背离 / 高潮吸收盒 | 03 `absorption_box_break` 或 05 `failed_breakout_effort_result` | 按是否已经突破失败分流 |
| 恐慌抛售高潮 / Selling Climax | 06 `climax_exhaustion_reversal` | 核心保留 |
| 缩量二次测试 | 02 `stopping_volume_retest` | 核心保留 |
| 放量强势结构破坏 / SOS | 04 `breakout_pullback_continuation` | 核心保留 |
| 最后支撑点回踩 / LPS | 04 `breakout_pullback_continuation` | 作为突破后回踩变体 |
| 隐性派发 / 上涨努力失败 | 05 `failed_breakout_effort_result` | 核心保留 |
| 买入高潮耗尽 / Buying Climax | 06 `climax_exhaustion_reversal` | 核心保留，更偏止盈/反转 |
| HVN/FVG 放量拒绝 | 08 `hvn_fvg_rejection_trap` | 核心保留 |

## GPT Top 10 映射

| GPT 策略 | 最终归属 | 处理 |
| --- | --- | --- |
| 爆量扫损回收 | 01 `liquidity_sweep_reclaim` | 核心保留 |
| 停止量后的缩量测试 | 02 `stopping_volume_retest` | 核心保留 |
| 高量窄实体吸收 | 03 `absorption_box_break` | 核心保留 |
| 放量突破与缩量回踩续攻 | 04 `breakout_pullback_continuation` | 核心保留 |
| 努力与结果背离失败突破 | 05 `failed_breakout_effort_result` | 核心保留 |
| 无供给与无需求测试 | 02 或 04 | 底部/顶部测试归 02；趋势中继归 04 |
| 开盘或会话极值放量拒绝 | 01 或 08 | 扫损回收归 01；价值区拒绝归 08 |
| 缩量压缩后的真实扩张 | 07 `compression_expansion_breakout` | 核心保留 |
| 停止量关键反转棒 | 06 `climax_exhaustion_reversal` | 作为单根停止量变体 |
| 二次推进衰竭与反向高潮量 | 06 `climax_exhaustion_reversal` | 作为成熟衰竭变体 |

## 趋势门控整合

| 策略族 | 趋势判断角色 | 设计原则 |
| --- | --- | --- |
| 01 流动性扫荡回收 | 软过滤 / 反转豁免 | 逆势允许，但提高量价阈值、缩小仓位、要求更清晰结构收回。 |
| 02 停止量后二次测试 | 软过滤 | 不看慢趋势硬否决，重点看停止量后的供需枯竭。 |
| 03 高量窄幅吸收 | 辅助过滤 | 用关键位、AVWAP、局部结构判断，不用慢 EMA 硬卡。 |
| 04 放量突破回踩续攻 | 必要条件 | 必须顺高一级趋势或完成趋势启动确认。 |
| 05 努力结果背离失败突破 | 软过滤 | 趋势背景用于解释，不否决反向失败突破。 |
| 06 高潮量衰竭反转 | 风险调节 | 不硬门控；极端逆势只降低仓位或作为止盈信号。 |
| 07 缩量压缩真实扩张 | 必要条件 | 趋势方向、压缩状态、突破确认共同过滤。 |
| 08 HVN/FVG 放量拒绝 | 环境选择器 | 关注价值区接受失败，趋势只判断是否适合做均值回归或拒绝交易。 |

## 对当前实现的影响

`trend_price_volume_v1` 当前不是完整 PA+VPA 策略体系，只是第一版可执行子集：

- `trend_continuation` 映射到 04。
- `liquidity_reversal` 映射到 01。

后续代码优化时，不能继续把 `MarketRegime` 作为所有 setup 的统一硬前置。趋势延续需要硬门控，流动性反转需要软门控和风险降权。
