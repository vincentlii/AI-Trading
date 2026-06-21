---
type: research-validation-report
status: invalidated
updated: 2026-06-21
invalidation_reason: TC event ATR/regime and 4H confirmation time were not causally frozen
tags:
  - strategy/trend-continuation
  - validation/development
  - audit/full-audit
---

> [!WARNING]
> 本报告的 112 笔盈利结果已失效，不得作为正式化证据。后续审计发现历史 lifecycle event 会被未来 context 的 ATR/zone/regime 覆盖，且候选曾以 4H relaunch bar 开盘时间作为 signal_time，导致 4H 未确认即进入 execution。2026-06-22 最终 causal rescue 仍为负，旧结论不再成立。

## 2026-06-22 Causal Entry Rescue

| Variant | Closed | Base avg R | Harsh avg R | PF | Walk-forward |
|---|---:|---:|---:|---:|---:|
| C 4H event + next 1H | 84 | -0.0810 | -0.1300 | 0.5944 | 1/5 positive |
| C 4H event + next 15m | 84 | -0.0420 | -0.0917 | 0.7723 | 1/5 positive |
| B 1H event + next 15m | 358 | -0.3047 | -0.4391 | 0.4503 | 0/5 positive |

15m 相对 1H control 仅改善 0.039R，未达到预注册的 0.05R，且 base、harsh、median、PF、资产与方向分组全部未通过。B 的更早 causal event 同样显著为负。三组 Full Audit、no-lookahead 与 metric recompute 均通过，因此决策为 `pause_tc_causal_rebuild`，不进入 exit、sizing、quality gate 或参数网格优化。

最终 artifact：`storage/research_runs/trend_continuation_family/tc_causal_entry_rescue_v1/runs/20260621T165901Z_c4106336ca89`

# TC Profile C 当前语义复验 2026-06-21

## 结论

`bp_shallow_cost_aware_admission_v3` 是 2026-06-08 保存的最佳 diagnostic snapshot，但不是 Git 历史中的最新 TC 优化。2026-06-16 提交 `1b02c61` 后，最新且开发集证据更强的方案是 `bp_tc_v1_exit_opt`。

本次在当前 master 公共执行、RiskEngine、成本与审计语义下，只复验预先限定的 Profile C。结果为正且通过 Full Audit，但样本仅覆盖 2026-02-28 至 2026-05-26，共 112 笔，因此只能确认 development reproduction，不能直接 formalize，也不能据此证明长期可盈利。

## 历史判断

| 版本 | 时间 | 样本 | base avg R | harsh avg R | 定位 |
|---|---:|---:|---:|---:|---|
| `bp_shallow_cost_aware_admission_v3` | 2026-06-08 | 416 | 0.0612 | -0.0010 | 当时最佳、已封存 diagnostic snapshot |
| `bp_tc_v1_exit_opt` mixed B/C | 2026-06-15 | 200 | 0.1332 | 0.0280 | 后续 exit proposal，B/C 混合仍为正 |
| `bp_tc_v1_exit_opt` Profile C only | 2026-06-21 | 112 | 0.2696 | 0.2067 | 当前公共语义严格复验 |

`tc_v1_exit_opt` 仅在内存中应用 proposal：`partial_take_profit_r=0.75`、`breakeven_after_mfe_r=0.75`、`reversal_time_cut_bars=48`。正式配置未修改，`auto_apply=false`。

## C-only 结果

| 指标 | 结果 |
|---|---:|
| raw candidates | 114 |
| proposal approved | 113 |
| closed trades | 112 |
| base / stress / harsh avg R | 0.2696 / 0.2476 / 0.2067 |
| base total R | 30.1911 |
| base PF | 3.1813 |
| base win rate | 68.75% |
| base median R | 0.3157 |
| max drawdown | 2.0849R |
| excluding top 1 / top 2 avg R | 0.2548 / 0.2431 |
| walk-forward positive / negative windows | 5 / 0 |
| max concurrent positions | 5 |
| max portfolio heat | 1.8582% |

BTC 为 51 笔、平均 0.2602R、PF 3.7217；ETH 为 61 笔、平均 0.2774R、PF 2.8873。long 为 65 笔、平均 0.2423R；short 为 47 笔、平均 0.3073R。两资产、双方向均未单边失效。

## 审计

- Full Audit、no-lookahead、metric recompute、regression baseline 全部通过。
- artifact index 共校验 12 项，0 error。
- 复验只复用已保存的 candidate/filter artifacts，并用当前执行引擎重新执行 Profile C；未读取独立 holdout。
- 新结果与 2026-06-15 mixed run 中手工提取的 Profile C 子集完全一致，说明当前公共语义修正没有改变该批 C 交易结果。

## 边界与下一步

现有 generic decision 仍因 C-only 单维集中及样本不足 250 返回不可自动 formalize。更重要的是，112 笔全部来自约三个月窗口，尚无跨年、不同市场状态和 untouched holdout 证据。

该段是 2026-06-21 当时判断，已被后续 causal audit 推翻：`bp_tc_v1_exit_opt` 不再是有效 development proposal，112 笔盈利结果仅作 historical invalidated evidence。正式策略配置始终未修改。

## Artifact

`storage/research_runs/trend_continuation_family/tc_v1_exit_opt_c_only_validation/runs/20260620T183940Z_296ab7be45f3/variants/bp_tc_v1_exit_opt`

## 研究终止与归档

2026-06-22 完成 TC Causal Entry Rescue 后，Profile C 4H→1H、Profile C 4H→15m 与 Profile B 1H→15m 均为负期望，TC 研究状态正式标记为 `stopped`。最终因果实验、逐笔证据、参数快照与 Full Audit 保存在 `storage/research_runs/trend_continuation_family/tc_causal_entry_rescue_v1/runs/20260621T165901Z_c4106336ca89`；临时 source cache、parity 与 smoke 产物已按该目录下 `cleanup_manifest.json` 清理。
