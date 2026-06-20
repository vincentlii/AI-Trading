# LR Next Entry Signal Definition

## 结论

下一版不应继续扩展入场网格，而应将 LR 重定义为：**已知、可共识的流动性位被 1H 同根刺破并收回，其后由 15m 证明价格没有立即重回 sweep 区，而是先产生可执行的有利推动。**

这是研究方向，不是正式策略或 winner。

## 建议定义

| 组件 | 建议 |
|---|---|
| Event timeframe | 主研究 `1H`；`15m_micro` 仅作 control；`4H` 暂停 execution |
| Level family | `PDH/PDL` 与 causal `confirmed_swing`；Session H/L 不得无条件独立使用 |
| Sweep semantics | level 在 sweep 前已确认且未过期；明确 first touch；1H high/low 真实越过 level |
| Reclaim semantics | 核心候选为 `1H same-bar close back inside`；span=2/3 只作独立 delayed-reclaim diagnostic |
| VPA role | 仅预注册 fixed-bin attribution；验证 normal/elevated effort-result 是否跨年一致；不打分、不拟合阈值 |
| Path-order requirement | 研究验收必须同时看 +0.5R/+1R first、invalidation-first、no-decision 和 time-to-event，不只看 forward median R |
| 15m execution role | signal_time 之后只负责 micro confirmation 与可执行价格；不再重新定义 liquidity event |

## 15m Micro Confirmation 方向

下一个 smoke 只验证一种最小 confirmation，不重开五种 entry tournament：

1. 1H reclaim bar close 后才开始观察，严格 `feature_cutoff_time <= signal_time/confirmation_time`。
2. 最多观察接下来 1-4 根 15m bars，不使用未确认 bar。
3. 要求价格未在确认前重新穿过 invalidation/sweep extreme。
4. 只验证一个结构事实：是否先出现沿 reversal 方向的 15m displacement/MSS，再考虑 entry feasibility。
5. 本轮仍不优化真实 entry price、stop、exit、sizing；只判断上述机制是否降低 invalidation-first。

## 暂时排除

- 4H wick-reclaim + 15m execution：确认后 240m edge 接近零。
- 无 first-touch/active-session 定义的 Session H/L。
- 15m 同时定义 sweep、reclaim、signal 和 entry。
- 把 1H span=1/2/3 合并为一种事件。
- 极端 volume/range 作为单阈值 gate。
- 恢复 Restricted Variant B，或从 Tournament v2 五种 entry 选相对 winner。
- 任何 exit、sizing、stop boundary、RiskEngine、cost 调整。

## Entry Signal v3 Smoke

可以进入一个很小的 development-only smoke，但必须先预注册并限制为：

- **Event**：1H same-bar sweep/reclaim。
- **Levels**：PDH/PDL + causal confirmed swing，各自报告，不组合网格。
- **Session H/L**：仅当与上述 level confluence 且可确认 first touch/active window 时记录为 attribution，不作独立信号。
- **VPA**：固定 low/normal/elevated/high bins，仅 attribution，不筛选。
- **Confirmation**：一个预注册 15m structural confirmation，最多 4 bars，不叠加多种变体。
- **Primary diagnostic**：+0.5R-first、+1R-first、invalidation-first、no-decision 的跨年/BTC-ETH/long-short 一致性。
- **Stop rule**：若无法在不拟合阈值的前提下显著降低 invalidation-first，停止 LR causal rebuild，不访问 holdout。

只有 v3 smoke 在机制层通过后，才能新建一个真实 entry/stop/fill/cost/RiskEngine 验证；不得复用当前 diagnostic R 作为交易绩效。
