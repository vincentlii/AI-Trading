# trend_price_volume v1

本文件是初始策略插件的自然语言规格。策略代码入口为同目录下的 `strategy.py`。

## Summary

本策略是项目第一套默认策略，核心链路为：

```text
MarketRegime -> PriceActionSetup -> VolumePriceConfirmation -> RiskDecision -> SimulatedOrder -> PositionState
```

业务表达：

```text
趋势判断 -> 价格行为 -> 量价确认/否决 -> 风控执行 -> 结构化复盘
```

策略只生成标准信号和解释载荷，不管理账户、不下单、不绕过风控。

## Implementation Status

当前代码 v1 已实现确定性信号候选生成：

- `features.py` 输出 `MarketRegimeContext`、`PriceActionSetup`、`VolumePriceConfirmation`。
- `strategy.py` 基于三周期上下文生成标准 `StrategySignal`。
- 已支持 `trend_continuation` 与 `liquidity_reversal` 两个第一版剧本。
- 风控、仓位、拒单和模拟订单仍由 P4 的 `RiskEngine` 和回测撮合层处理。

v1 只使用 confirmed OHLCV K 线。ToD RVOL 正式基线未接入前，量价确认使用滚动成交量基线 fallback；如果 `StrategyContext.features` 提供 `tod_volume_baseline`，则优先使用该基线。

## Timeframe Profiles

| 组别 | 入场周期 | 结构周期 | 趋势周期 | 用途 | Session 策略 |
| --- | --- | --- | --- | --- | --- |
| A | 5m | 15m | 1h | 日内快节奏，BTC/ETH 高流动性时段 | 默认 hard gate |
| B | 15m | 1h | 4h | 标准波段，默认主候选 | 先记录标签，是否过滤交给回测 |
| C | 1h | 4h | 1d | 慢趋势，低频趋势捕捉 | 先记录标签，是否过滤交给回测 |

Session Gate 使用 UTC 时间戳转换到 `America/New_York`：

- London: `02:00-05:00`
- New York: `07:00-10:00`

## MarketRegime

趋势周期只负责判断市场体制、方向和策略权限，不直接生成入场。

输出状态：

- `TREND`
- `RANGE`
- `COMPRESSION_PENDING_BREAKOUT`
- `OVERHEATED_TREND_END`
- `MEAN_REVERTING_TRANSITION`

默认指标：

- ADX/DMI：周期 `14`；`ADX >= 25` 为趋势强度成立，`ADX < 20` 为震荡，`20 <= ADX < 25` 为过渡，`ADX >= 45` 标记过热风险。
- EMA：使用 `EMA50/EMA200`。`EMA50 > EMA200` 且 `Close > EMA50` 为多头宏观偏向；`EMA50 < EMA200` 且 `Close < EMA50` 为空头宏观偏向。
- Kaufman ER：周期 `14`；`ER >= 0.6` 为高效率趋势，`ER <= 0.3` 为低效率噪音。
- CHOP：周期 `14`；`CHOP <= 38.2` 为趋势，`CHOP >= 61.8` 为重度震荡。
- TTM Squeeze：SMA `20`，BB 倍数 `2.0`，KC ATR 周期 `20`，KC 倍数 `1.5`。
- GMMA：短组 `[3,5,8,10,12,15]`，长组 `[30,35,40,45,50,60]`，v1 只作二级确认。

状态裁决：

- `TREND`：EMA 方向、DMI 方向一致，`ADX >= 25`，且 `ER >= 0.6`、`CHOP <= 38.2`。
- `RANGE`：`ADX < 20`，且 `ER <= 0.3`、`CHOP >= 61.8`。
- `COMPRESSION_PENDING_BREAKOUT`：TTM Squeeze ON；阻断提前追突破。
- `OVERHEATED_TREND_END`：`ADX >= 45` 且 ADX 回落，或 ADX 极高但 ER/CHOP 不再支持趋势。
- `MEAN_REVERTING_TRANSITION`：指标冲突、中间阈值或方向未统一。

## PriceActionSetup

结构周期负责标记结构与位置。价格行为层可以不依赖 volume。

默认定义：

- `Swing High/Low`：左右各 `n` 根确认；默认 `internal_n=2`，`swing_n=5`。
- `BOS`：收盘价突破最近有效结构极值，并超过 `break_buffer = max(0.1 * ATR14, 2 * tick_size)`。
- `CHoCH`：已有趋势下首次收盘突破受保护结构点，只表示进入 transition。
- `Liquidity Sweep`：影线穿越 swing 或 equal high/low 池，但收盘回到池内侧。
- `Equal High/Low`：至少两个已确认 swing 极值，价差在 `max(0.05 * ATR14, 3 * tick_size)` 内。
- `OB`：导致 displacement/BOS 前最后一根反向 K 线，v1 使用整根 K 线区间 `[low, high]`。
- `FVG`：三根 K 线失衡区，最小缺口 `max(0.1 * ATR14, 2 * tick_size)`。
- `Displacement`：方向净移动 `>= 1.2 * ATR14`，主方向实体占总 range `>= 60%`，收盘位于方向端 `25%` 区域内。

结构生命周期：

- `active`
- `mitigated`
- `expired`
- `invalidated`

OB/FVG 首次触碰后只允许当前触发链使用一次，之后标记为 `mitigated`。

## VolumePriceConfirmation

入场周期负责最终确认、否决、冷却或异常标记。量价层不能单独生成买卖方向。

输出：

- `confirm`
- `reject`
- `cooldown`
- `anomaly`

默认特征：

- `tod_rvol`
- `volume_zscore`
- `spread_ratio`
- `close_location`
- `upper_wick_ratio`
- `lower_wick_ratio`
- `synthetic_flow`

关键规则：

- ToD RVOL 使用同一 `venue + inst_type + inst_id + bar + slot_of_day` 的 `20-30` 天历史基线。
- OKX v1 优先使用 `volume_currency_quote` 做统计，同时保留原始 `volume`。
- `Volume Z-Score`: `normal < 1.5`，`loading 1.5-2.0`，`climax >= 2.0`，`anomaly_candidate >= 3.0`。
- `Spread Ratio`: `< 0.75` 为结果偏弱，`>= 1.2` 为温和扩张，`>= 1.5` 为强位移。
- 真实 BOS 需要收盘突破、放量、大位移、收盘靠近突破方向端点。
- 弱突破、缩量突破、高量低结果或长反向影线应输出 `reject` 或 `anomaly`。

## Setups

### trend_continuation

触发链：

1. 趋势周期输出 `TREND`，方向为 `LONG` 或 `SHORT`。
2. 结构周期出现同向 BOS + displacement。
3. 价格行为层生成 active OB/FVG，等待回踩。
4. 入场周期在 active zone 内得到量价 `confirm`，且没有 `cooldown/anomaly`。
5. 风控层通过后生成模拟订单。

出场以动态追踪为主，不设置固定最终止盈。达到 `1R` 后执行部分止盈，剩余仓位使用 Chandelier Exit。

### liquidity_reversal

触发链：

1. 价格行为层定位 equal high/low 或最近 swing 组成的 active liquidity pool。
2. 价格发生 sweep，收盘回到池内侧。
3. `N=3` 根内出现反向 CHoCH 或入场周期确认。
4. 量价层确认吸收、停止量或对手盘衰竭，且没有异常冷却。
5. 风控层确认对侧流动性目标扣除成本后至少 `1.5R`，否则拒单。

止损使用结构止损，目标优先参考对侧流动性池。

## Risk Defaults

- 单笔风险：`0.5% equity`。
- 初始止损优先使用结构止损：多头为最近确认 swing low 下方 `0.2 * ATR14`，空头对称。
- 趋势延续可用 `2.5 * ATR20` 作为兜底止损。
- 止损距离 `< 0.8 * ATR20` 或 `> 3.0 * ATR20` 时拒绝交易。
- 单笔名义价值不超过权益 `15%`；总名义敞口默认不超过 `1.0x equity`。
- 组合热度不超过权益 `2%`；同方向/高相关资产簇不超过 `1%`。
- 达到 `1R` 后默认平掉 `50%`，剩余仓位止损移动到真实盈亏平衡点。
- 趋势延续使用 Chandelier Exit：周期 `22`，BTC/ETH 乘数 `4.0`，XAUT 乘数 `3.0`。
- 流动性反转若扣除成本后目标不足 `1.5R`，拒绝交易。
