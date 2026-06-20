# LR Level Mechanism Review

## 结论

PDH/PDL 最接近稳定、可共识的真实流动性；confirmed swing 具有结构语义，但更依赖确认滞后与位置。当前 Session H/L 主要是高频、宽泛的基线，不应继续无条件视为独立流动性位。

## 样本与路径

| Level family | Events | Unique physical | 240m median R | 1200m median R | Follow-through 240m | Invalidation-first 1200m |
|---|---:|---:|---:|---:|---:|---:|
| PDH/PDL | 5,388 | 5,388 | 0.134 | 0.230 | 68.24% | 48.27% |
| Confirmed swing | 4,776 | 4,776 | 0.083 | 0.214 | 66.09% | 49.20% |
| Session H/L | 16,330 | 16,330 | 0.085 | 0.047 | 66.29% | 50.14% |

Follow-through 以 240m 内 0.5R 与 invalidation 的已决定样本为分母；invalidation-first 以 1200m 内 1R 与 invalidation 的已决定样本为分母。这些是 diagnostic labels，不是绩效。

## Timeframe 交叉

| Timeframe | Level | Events | 240m median R | 1200m median R | Invalidation-first |
|---|---|---:|---:|---:|---:|
| 15m | PDH/PDL | 2,255 | 0.232 | 0.213 | 48.96% |
| 15m | Confirmed swing | 2,044 | 0.121 | 0.258 | 50.68% |
| 15m | Session H/L | 6,574 | 0.204 | 0.122 | 49.58% |
| 1H | PDH/PDL | 1,755 | 0.170 | 0.244 | 47.03% |
| 1H | Confirmed swing | 1,553 | 0.107 | 0.239 | 47.01% |
| 1H | Session H/L | 5,526 | 0.097 | 0.046 | 50.07% |
| 4H | PDH/PDL | 1,378 | 0.041 | 0.218 | 48.70% |
| 4H | Confirmed swing | 1,179 | 0.030 | 0.122 | 49.40% |
| 4H | Session H/L | 4,230 | -0.014 | -0.001 | 51.23% |

## 跨年数量

2020 仅有 10 个边界 rows，不用于结论。

| Level | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|
| PDH/PDL | 1,372 | 1,412 | 1,348 | 1,256 |
| Confirmed swing | 1,057 | 1,252 | 1,278 | 1,187 |
| Session H/L | 4,170 | 4,051 | 4,120 | 3,981 |

PDH/PDL 和 confirmed swing 数量跨年稳定。Session H/L 每年约 4,000 个，说明它构成大多数信号池，也说明它的定义过宽。

## 资产与方向数量

| Level | BTC long | BTC short | ETH long | ETH short |
|---|---:|---:|---:|---:|
| PDH/PDL | 1,309 | 1,399 | 1,287 | 1,393 |
| Confirmed swing | 1,182 | 1,236 | 1,133 | 1,225 |
| Session H/L | 4,069 | 4,141 | 3,902 | 4,218 |

数量无明显单资产或单方向偏置。但 Session H/L 的 BTC long follow-through 仅 63.60%、invalidation-first 53.32%，提示宽基线在局部市场状态下不稳定。

## 机制解释

- **PDH/PDL**：日历周期固定、全市场可见、易聚集止损与突破挂单，具有最清晰的流动性原因。
- **Confirmed swing**：代表已确认的局部结构极值，有 PA 语义；中位 level age 约 8.75h，需保持 causal confirmation，不能回溯把未确认 swing 当成已知位。
- **Session H/L**：现实现是已完成 8h block 高低点，中位 age 4h；它不等同于特定交易时段正在形成的 active-session liquidity。其 12,789 个 physical events 仅有 Session H/L 自身、无其他 level confluence。

## Session H/L 决策

Session H/L 若继续研究，必须改为受限定义：

1. 显式记录 first touch，排除已多次消耗的 level。
2. 明确 session 名称、时区、生效区间和过期规则，而不是泛化 8h block。
3. 优先只作 PDH/PDL 或 confirmed swing 的 confluence，不再作无条件独立 level family。

本次数据缺少 first-touch 与 active-session 字段，上述是下一版定义要求，不是从当前小分组挑出的 winner。
