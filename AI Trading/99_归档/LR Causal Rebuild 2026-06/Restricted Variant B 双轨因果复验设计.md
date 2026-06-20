---
type: architecture-decision
status: implemented
updated: 2026-06-20
tags:
  - strategy/liquidity-reversal
  - research/causal
---

# Restricted Variant B 双轨因果复验设计

## 结论

新增 development-only、proposal-only 的双轨复验。Track A 隔离旧 Variant B 的实现错误；Track B 验证三个 setup 概念在 1H event + 15m confirmation 架构下是否仍有价值。两轨不合并、不事后选优、不读取 holdout。

## Track A：historical_causal_repair

- 使用当前修正 4H bar close 语义的 fresh LR scanner。
- 固定三 setup：Session H/L attempt 4 fixed、recent swing attempt 4 dynamic、Session H/L attempt 3 dynamic。
- 固定历史 approval：先对 fresh scanner 候选重放 Stage 5 minimal LR filter，再重放 Stage 6C sizing；fixed setup 使用 current risk sizing 的 `formal_approved`，dynamic setup 使用 notional-capped sizing 的 `proposal_approved`。不运行 score 50/60/70。
- fixed setup 使用 2R / 20h；dynamic setup 使用逐 bar causal protection、8h momentum deadline、20h max holding。
- dynamic setup 使用 notional cap；attempt 3 使用 75% risk。

## Track B：rebuilt_1h_15m

- 父事件只读取已审计 multitimeframe artifact 中的 `1H_sweep_reclaim`。
- Session H/L attempt 4：Session H/L event 后四根 15m 内确认同方向 `body >= 0.8 * causal 15m ATR` 且 close 突破 1H reclaim range，下一根 15m open 入场。
- Recent swing attempt 4：confirmed swing event，使用相同 displacement trigger。
- Session H/L attempt 3：Session H/L event 后八根 15m 内，confirmed 15m close 突破 signal_time 前已确认的最近 2-left/2-right micro swing，下一根 15m open 入场。
- stop 使用 parent sweep extreme 外加 `0.10 * parent event ATR`，目标为 2R；RiskEngine 继续执行 stop/notional/risk 边界。
- VPA 只保留 attribution，不参与本轮 gate。

## 共享执行与组合

- BTC/ETH SWAP、C profile、development `2020-12-31` 至 `2024-11-30`。
- base/stress/harsh 三档现有成本。
- 按 physical event + direction 去重；setup priority 为 fixed session attempt 4、recent swing attempt 4、session attempt 3。
- `portfolio_heat_cap=0.05` 按 `(entry_time, setup priority, candidate_id)` 因果排序，禁止读取 `net_R` 排序。
- 输出 candidate/filter/execution/closed_trade/diagnostic/summary/robustness、manifest、artifact index、Full Audit 和双轨对比报告。
- Restricted Variant B 保持 suspended；本复验不修改正式配置。

## 验收

- Track A 精确包含三 setup 且没有 score variant。
- Track B 的 feature cutoff、trigger close、entry open 严格递增。
- dynamic exit 不读取事后 MFE；heat 选择不按结果排序。
- 两轨分别从 `closed_trade_rows` 复算指标并通过 Full Audit，或明确报告 blocking issue。
- holdout access 为 false。

## 实现与验证

- CLI：`lr-restricted-variant-b-causal-retest --track historical|rebuilt|both`。
- 全量事件来源必须同时具备通过状态的 `run_manifest.json`、`causality_audit.json` 和匹配的 `artifact_index.json` hash。
- 每个标的一次性构建 15m timestamp、ATR 和 micro swing 索引；每个候选只向 executor 传入最多 80 根 15m K 线，避免候选数乘全量 K 线的复杂度。
- 2023-08-01 至 2023-09-30 真实数据 smoke：historical 为 149 candidates / 143 base closed trades，rebuilt 为 67 / 2；两轨 Full Audit 均通过。
- smoke 结果只验证数据流与审计闭环，不构成策略结论或 winner 选择。
