# LR Entry Signal Mechanism Review Missing Data Manifest

## 结论

现有 artifacts 足以回答主要机制问题，但不支持 first-touch、active-session 和 100% 逐笔 anatomy-to-execution 结论。本次没有为补齐数据而重跑。

| 缺失项 | 替代证据 | 影响 |
|---|---|---|
| 独立 `order_rows` | `candidate_rows` 已含 order type、entry price/time、fill/missed | 不影响 fill 与 chase proxy；文档中不宣称存在独立 order artifact |
| first-touch / prior-touch row-level 字段 | 无 | 不能回溯判定 Session H/L 是否首次触及；只能建议下一次显式定义 |
| active-session 标识 | 现有 Session H/L 是已完成 8h block 高低点 | 无法将它等同为人类交易者语义下的 active-session liquidity |
| Tournament source 的 `physical_event_key` | 按 instrument + level_id + direction + sweep/reclaim time 与 MT 15m control 匹配 | 10,085 个 source 中 8,368 个唯一匹配，覆盖 82.97%；1,717 个不可逐笔桥接 |
| 被 admission 拒绝者的完整连续风险分布 | `filter_results` 有 reason codes，无所有中间数值 | 可定量拒绝原因，不可重建每个拒绝样本的 risk-margin 距离 |
| 显式 entry-chase label | 从 entry/reclaim close/15m ATR 派生 | 仅是 proxy，不是原始特征；正值表示沿信号方向追价 |

## 桥接限制

Tournament v2 来源是 `causal_anatomy.v4`，Multi-Timeframe 是后来的 scanner schema。因此只桥接到 MT `15m_micro` control，不把同时间的 1H/4H event 误认为同一 source event。未匹配 rows 只做 summary-level bridge。
