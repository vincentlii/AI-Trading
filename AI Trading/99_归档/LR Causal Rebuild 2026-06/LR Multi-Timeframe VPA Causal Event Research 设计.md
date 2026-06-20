---
type: architecture-decision
status: approved-design
updated: 2026-06-19
tags:
  - strategy/liquidity-reversal
  - research/causal
  - research/vpa
---

# LR Multi-Timeframe VPA Causal Event Research 设计

## 结论

停止从 Causal Entry Tournament v2 的五个下游入场中选择相对 winner。当前研究回到 LR event definition、signal timeframe 与 VPA attribution，只生成 causal event、anatomy、diagnostic label 和审计产物。

本阶段不得访问 2024-12-01 起的 holdout，不生成正式策略，不进入 entry、exit、sizing 或 portfolio 优化，不修改 RiskEngine、成本、stop、notional cap，不恢复 Restricted Variant B。

## 架构

新增共享 causal event scanner，以 timeframe policy 驱动 15m、1H、4H 三类事件。Scanner 只负责已确认 level 与 event；VPA 模块只计算因果特征；anatomy 模块只生成未来诊断标签；runner 负责数据装载、产物、审计和集中报告。

旧 15m scanner 保留为 control。1H 与 4H 不复用旧 entry tournament，也不产生 entry decision。

## Event 定义

三类事件共享当前已确认 liquidity levels：完成的 8h Session H/L、完成的 UTC PDH/PDL、两左两右确认后的 4H swing。

### 15m control

- 15m confirmed candle 刺破 level。
- sweep 当根或后续最多 3 根 15m candle 收盘回到 level 内侧。
- signal_time 为 reclaim candle close。
- 与 causal_anatomy.v4 的 15m event 语义保持一致。
- 保留旧 control 的 `sweep_depth <= confirmed 4H ATR`；4H ATR 只能取 sweep close 时已经确认的数据。

### 1H sweep/reclaim

- 第一根 confirmed 1H candle 刺破 level。
- 同根或后续最多 2 根 confirmed 1H candle 收盘回到 level 内侧。
- 输出 `reclaim_span_bars=1/2/3`，不把三个跨度作为可调 variant。
- sweep extreme 为该事件窗口内最极端价格。
- signal_time 为 reclaim candle close。
- 首次 sweep 后三根内未 reclaim，则该 level 对本轮事件失效；不得逐根重启 TTL 把窗口无限延长。
- 不预设 sweep depth 的 ATR 硬门槛，避免在 timeframe comparison 前先验删去深度事件。

### 4H wick-reclaim

- 单根 confirmed 4H candle high/low 刺破已知 level。
- 同一根 4H candle 收盘回到 level 内侧。
- signal_time 为该 4H candle close。
- 不接受跨多根 4H 的 reclaim。
- 单根 sweep 未 reclaim 后不得在下一根继续沿用同一次 level 事件。
- 不预设 sweep depth 的 ATR 硬门槛；深度仅作为 event anatomy 可派生属性参与诊断。

每个 event-level 命中保留 `level_id` 与 `level_family`。`physical_event_key` 不含 level identity，用 instrument、direction、event timeframe、sweep start time、reclaim time 标识物理事件；报告同时输出 event-level count 与跨 family unique physical event count。

## Diagnostic R

- reference price：signal_time 对应 reclaim bar close。
- long invalidation：`sweep_low - 0.10 * event_timeframe_ATR`。
- short invalidation：`sweep_high + 0.10 * event_timeframe_ATR`。
- `1R = abs(signal_close - invalidation)`。
- ATR period 为 14，只使用 signal_time 已确认的 event timeframe candles。

Forward diagnostic R：long 为 `(future_price - signal_close) / 1R`，short 为 `(signal_close - future_price) / 1R`。

ATR-normalized forward return 使用相同方向符号并除以 event timeframe ATR。窗口为 15、30、60、120、240、480、1200 分钟。

Diagnostic R 不代表真实交易收益。未来 Entry Tournament 必须重新使用真实 entry、stop、fill、成本和 RiskEngine。

## VPA 字段边界

### Tradable features

以下字段只能使用 signal_time 及以前已确认 candles：

- sweep relative volume。
- reclaim relative volume。
- sweep volume percentile。
- reclaim volume percentile。
- sweep range expansion。
- reclaim range expansion。
- directional wick ratio。
- direction-aware close location value。
- sweep + reclaim combined volume ratio。

Relative volume 与 range expansion 使用不含当前 candle 的前 20 根 confirmed event-timeframe candles作为 causal baseline。Volume percentile 使用当前值在此前最多 100 根 confirmed candles 中的经验分位。样本不足时输出 null 与明确 baseline sample count，不做 fallback 到未来或全样本。

### Diagnostic labels

Follow-through volume 与 reclaim 后 volume contraction/expansion 发生在 signal_time 之后，只能写入 `diagnostic_label_rows`，不得进入 feature、entry 或 quality gate。

## Anatomy 标签

未来路径只使用 signal_time 后的 confirmed 15m candles。

- 输出七个 horizon 的 signed return、diagnostic R 与 ATR-normalized return。
- 输出 1200 分钟路径内 MFE、MAE。
- 输出首次到达 0.5R、1R、1.5R、2R 的分钟数。
- 同一 15m candle 同时触及 invalidation 与目标时，悲观判定 invalidation 先发生。
- follow-through：240 分钟内先到 +0.5R、未先触及 invalidation。
- invalidation-first：1200 分钟内 invalidation 先于 +1R。

Future price、future volume、MFE、MAE、time-to-R、follow-through 与 invalidation-first 全部标记为 `diagnostic_label`，不得成为 tradable feature。

## 汇总与报告

机器产物至少包含：

- `event_rows.jsonl`
- `vpa_feature_rows.jsonl`
- `diagnostic_label_rows.jsonl`
- `anatomy_rows.jsonl`
- `summary_rows.jsonl`
- `causality_audit.json`
- `artifact_index.json`

集中报告包含：

1. `lr_multitimeframe_event_scanner_report`
2. `lr_vpa_attribution_report`
3. `lr_event_timeframe_anatomy_report`
4. `lr_event_causality_audit_report`
5. `lr_research_direction_recommendation`

汇总维度包括 timeframe、asset、direction、year、UTC session、level family、VPA causal percentile bucket。Bucket 使用预定义 percentile quartile，不使用全 development 调 score threshold。

最终报告不给硬 winner，只回答各方向的证据强弱、稳定性、限制和下一步优先级。

## 审计与停止规则

- 所有 event candle 必须 confirmed。
- `signal_time >= event timeframe reclaim bar close`，实际要求相等。
- `feature_cutoff_time <= signal_time`。
- VPA feature source time 不得晚于 signal_time。
- Diagnostic labels 与 tradable features 物理隔离。
- 报告 event-level 与 unique physical event 两套计数。
- 核心 JSONL 排序与序列化必须确定；重复 smoke 的核心 artifact SHA-256 必须一致。
- Manifest 必须记录 `holdout_accessed=false`、proposal-only、无正式结论。
- 若 scanner 需要读取 holdout、因果审计失败或核心 hash 不稳定，立即停止。
- 若三个 timeframe 均无跨年度稳定 follow-through，或 VPA attribution 无可重复区分能力，建议暂停 LR Causal Rebuild。
