# LR Causal Rebuild Phase 0-1

## 结论

Restricted Variant B 已暂停作为正式候选。历史 `183` 笔结果保留用于追溯，但因 4h 时间戳、事后 MFE exit、结果排序 exposure cap 和物理事件重复问题，不再作为可信绩效基线。

Phase 0-1 已完成：审计语义加固、逐 variant closed-trade 产物补齐、因果 level/event anatomy scanner、仅 development CLI 和两周 smoke。近 18 个月 holdout 未访问。

## 因果研究边界

- development：`2020-12-31` 至 `2024-11-30`。
- holdout：从 `2024-12-01` 开始，继续封存。
- level family：完成的 8h Session H/L、完成的 UTC PDH/PDL、两左两右确认后的 4h swing。
- sweep/reclaim：使用已确认 15m bar；信号时间为 reclaim bar 收盘时间。
- anatomy entry：严格晚于 signal 的下一根 15m bar 开盘。
- 最大诊断窗口：`1200` 分钟；development 候选截止时间预留完整 20h 路径。
- anatomy diagnostics 不属于 closed-trade performance，不允许形成正式收益结论。

## 工程约束

- ATR 只使用 level 确认时点前已收盘的 bar。
- ATR 全历史只预计算一次，level 查询使用二分索引，避免 `O(levels × bars)`。
- 同族同方向 level 只在下一 level 确认前有效。
- `market_event_key` 表示物理 sweep/reclaim；不同 level 命中同一事件时保留共同 key，供后续去重与归因。
- `bar_confirmed=false`、`no_lookahead_safe=false` 或 ambiguous same-bar 未强制悲观处理时，No-Lookahead Audit 必须失败。

## 两周 smoke

窗口：`2021-01-01` 至 `2021-01-15`。

- raw levels：`315`。
- causal events / candidates：`106`。
- diagnostics：`742`。
- level family：Session H/L `66`、PDH/PDL `24`、confirmed swing `16`。
- 时间链违规：`0`。
- performance eligible rows：`0`。
- closed trades：`0`。
- 重复物理事件组：`24`，表示多个 level 描述同一市场事件，不是可重复下单许可。
- audit status：`not_run_no_closed_trade_unverifiable`。

## 下一步

人工运行完整 development anatomy：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research lr-causal-rebuild --stage anatomy --mode development --start 2020-12-31 --end 2024-11-30 --output-root storage/research_runs/liquidity_reversal/causal_rebuild_v1 --format json
```

运行完成后先审查 level/event 漏斗、重复物理事件、方向与年份稳定性、forward path 分布，再进入 entry tournament。不得提前运行 holdout，不得直接恢复 Restricted Variant B，也不得依据 anatomy diagnostics 宣称策略可盈利。

## 2026-06-19 全量 v1 复核与修正

首次完整 development anatomy v1 产生 `27,820` 个 levels、`10,869` 个 events/candidates 和 `76,083` 条 diagnostics。逐笔复核发现 `797` 个候选的 stop 位于入场价错误一侧，但旧实现使用 `abs(entry-stop)` 将其错误保留；另有 `229` 个候选的 stop 小于 `0.1 ATR`，导致 R 路径出现极端分母效应。因此该次 v1 全量产物不得进入 entry tournament。

修正后的 `causal_anatomy.v2`：

- long stop 必须严格低于 entry，short stop 必须严格高于 entry。
- geometry 无效的事件进入 `filter_results.jsonl` 并记录明确 reject reason。
- diagnostics 新增 `forward_ATR`、`MFE_ATR`、`MAE_ATR`；聚合摘要同步输出 ATR 标准化统计。
- R 路径仍保留作风险几何研究，但 anatomy 的事件方向判断优先使用 ATR 标准化路径。

两周 v2 smoke：`106` 个 events，`93` 个有效 candidates，`13` 个 geometry rejects，候选中的无效 stop 数为 `0`，closed trades 仍为 `0`。

首次全量 v1 目录应视为 invalidated evidence。重新运行完整 development 时使用独立 v2 目录：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research lr-causal-rebuild --stage anatomy --mode development --start 2020-12-31 --end 2024-11-30 --output-root storage/research_runs/liquidity_reversal/causal_rebuild_v2 --format json
```

## 2026-06-19 v2 Anatomy 结论

完整 v2 development 产生 `27,820` 个 levels、`10,869` 个 events、`10,072` 个 geometry-valid candidates 和 `70,504` 条 diagnostics；`797` 个无效 stop geometry 事件被拒绝。

- 唯一物理事件：`7,903`。
- 跨 level 重复增加的 candidates：`2,169`；单事件最多命中 3 个 level family。
- `0.5-2.5 ATR` stop 区间内 candidates：`6,503`。
- 240 分钟路径中，PDH/PDL 的 median forward ATR 最强：long 约 `0.47 ATR`，short 约 `0.41 ATR`。
- Session H/L 与 confirmed swing 的 240 分钟 median forward ATR 为正，但 mean 接近零且年度方向会翻转，不能据此挑选单一 family。
- anatomy 仍是 diagnostic evidence，不是 closed-trade performance。

v2 candidate 缺少 `level_confirmed_time` 与 `level_source_time`，无法在 closed-trade Full Audit 中验证 `structure_confirmed_time <= sweep_time`。因此 v2 可用于 anatomy 诊断，但不得作为 entry tournament 的审计来源。

## Causal Anatomy v3

v3 只补齐 lineage，不改变 level/event/entry anatomy 逻辑：

- event/candidate 增加 `level_confirmed_time`、`level_source_time`。
- 新增 `level_rows.jsonl`。
- tournament 只接受 `causal_anatomy.v3`、相同 config fingerprint、development-only 且未访问 holdout 的来源。

## Entry Tournament v1

五个预注册入场模型：

1. `market_next_open`：signal 后第一根严格更晚的 15m bar 开盘。
2. `level_retest_limit`：signal 后 4 根 bar 内回踩原 level 成交。
3. `reclaim_midpoint_limit`：signal 后 4 根 bar 内回踩 level 与 reclaim close 中点成交。
4. `mss_market`：4 根 bar 内收盘突破 reclaim bar 极值，随后第一根严格更晚的 bar 开盘成交。
5. `mss_midpoint_limit`：MSS 确认后 4 根 bar 内回踩确认 candle body 中点成交。

统一边界：

- 所有模型使用相同 sweep extreme stop、固定 `2R` target、最长 `80` 根 15m bar（20h）。
- 统一使用当前 preset 的 `RiskEngine`、notional cap、最小实际风险与 base/stress/harsh 成本。
- limit 成交首 bar 屏蔽成交前可能发生的有利 wick，但保留不利 excursion 与 close，采用悲观 OHLC 语义。
- 按 level family 分开比较，不把跨 family 的同一物理事件合并成美化后的总收益。
- 全部交易写入 `variant_closed_trade_rows.jsonl`；在 winner 预注册选择前，正式 `closed_trade_rows.jsonl` 保持为空，Full Audit 状态为 `not_run_no_selected_variant`。

两周端到端 smoke：93 个 v3 candidates、465 个 entry decisions、315 个 filled decisions、181 个 base closed trades（543 条三成本 variant rows）；时间链违规 `0`，同 variant/family 物理事件重复 `0`。

## 2026-06-19 运行前最终逻辑复核

原 v3/v1 在运行前复核中发现两个阻断问题：

1. anatomy 将 ATR 固定在 level 确认时点；confirmed swing 等长期 level 到 sweep 的时间差可能超过 20 小时，导致 sweep depth、stop buffer 与 RiskEngine 使用过时波动率。
2. tournament 最慢模型可能在 signal 后第 9 根 15m bar 才成交，再持有 80 根 bar；原实现只预留 20h，并可能查询 development end 之后的数据，存在进入 holdout 的风险。

修正后的版本：

- `causal_anatomy.v4`：ATR 在 sweep bar close 时以当时已确认数据计算。
- `lr_entry_tournament.v2`：所有模型共用 `9 + 80 = 89` 根 15m bar 的尾部预留；不足者记录 `insufficient_development_tail`，数据库查询严格截断在 development end 之前。
- limit 首 bar 的悲观归一化单独记录为 `limit_fill_bar_pessimistic=true`，不再伪造 `same_bar_ambiguous` 或 `forced_pessimistic_exit`。

两周 v4/v2 smoke：94 个 anatomy candidates、470 个 entry decisions、320 个 filled decisions、196 个 base closed trades（588 条三成本 variant rows）；development 越界 `0`，时间链违规 `0`，limit 悲观标记遗漏 `0`，正式 `closed_trade_rows` 仍为空。

数据连续性复核：2020-12-31 至 2024-11-30 的 BTC/ETH swap 15m 与 4H confirmed candles 均无内部时间缺口。

已知但不阻断当前 entry comparison 的限制：development 期间缺少历史 funding 覆盖，当前 funding 为 `0`。因此 v4/v2 全量结果只能用于入场模型筛选；选 winner 前必须增加保守 funding sensitivity，且组合层仍需 portfolio heat、exposure 与 Full Audit。
