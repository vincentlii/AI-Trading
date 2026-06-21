---
type: strategy-family
strategy_family: breakout_pullback_continuation
status: research_stopped
updated: 2026-06-22
tags:
  - strategy/pa-vpa
  - strategy/implemented
---

# 04_breakout_pullback_continuation

结论：`breakout_pullback` / TC 研究已停止。旧盈利 snapshot 存在 causal event/entry 语义问题；修正后 Profile C 4H 与 Profile B 1H causal rescue 均为负期望，因此无 formal candidate，不进入 validation-prep 或 P6。

## 定位

放量突破、缩量回踩、顺势续攻。适合趋势延续交易。

## 趋势角色

必要条件 / 硬门控。必须顺高一级趋势或完成趋势启动确认。

## 当前实现

- Research Pipeline / adapter / manifest / setup_id 统一使用 `breakout_pullback`。
- 状态机：Structure Context -> True Breakout -> Acceptance Window -> Healthy Pullback -> Relaunch Confirmation -> Structural Stop and Target Feasibility。
- 已复用 CE semantic repair 经验：`breakout_score`、acceptance window、normal retest vs failed breakout、structural stop、stop_distance x margin diagnostics、subtype split、base/stress/harsh 成本层。
- 首轮只跑 3 个 proposal-only variants：`bp_level_retest_continuation_v1`、`bp_boundary_or_midpoint_retest_v1`、`bp_shallow_pullback_momentum_v1`。

## 2026-06-04 initial research round

产物：`storage/research_runs/breakout_pullback/initial_research/66591695010676daa1e2434a/`。

集中报告：`storage/research_runs/breakout_pullback/initial_research/66591695010676daa1e2434a/breakout_pullback_initial_research_report.md`。

核心结果：

- baseline：8000 context windows，candidate_ready_windows=194，raw_candidates=49。
- 最大漏斗断点：`true_breakout=7169`，其次为 `relaunch_confirmation=253`、`acceptance_window=220`、`breakout_quality_valid=152`。
- `bp_level_retest_continuation_v1`：raw=47，approved=0，closed=0；主要拒绝为 `stop_distance_too_near=45`、`margin_required_too_high=2`。
- `bp_boundary_or_midpoint_retest_v1`：raw=49，approved=17，closed=10；base/stress/harsh net_R_avg=-0.2125/-0.2251/-0.2461，Full Audit 对 closed_trade variants 可验证通过。
- `bp_shallow_pullback_momentum_v1`：raw=27，approved=9，closed=3；base/stress/harsh net_R_avg=-0.3176/-0.3308/-0.3528，样本过少。
- 所有 performance metrics 只来自 `row_type=closed_trade`；diagnostic/proposal/summary rows 未进入收益统计。
- LR final evidence 未被覆盖或重解释；CE artifacts 只作为语义经验复用。

当前决策：D. BP backlog due to insufficient sample / weak edge / unstable robustness。

## 下一步

- 不继续混合研究整个 BP 家族，不扩大参数网格。
- 下一轮只隔离 `bp_lifecycle_shallow_momentum_v2`，验证样本、资产/profile/方向覆盖和成本后 robustness。
- 不得放宽成本、slippage、margin、notional cap、portfolio heat、formal stop、formal target 或 exit boundary。

## 2026-06-04 trend continuation core rebuild round

集中报告：`storage/research_runs/breakout_pullback/core_rebuild_round/3b660ac6d760fa52aed21418/trend_continuation_core_rebuild_report.md`。

长期结论：

- 共享内核已重建为 structure zone -> breakout lifecycle -> pullback health -> relaunch -> structural stop -> cost-adjusted tradeability。
- breakout 不再是一票否决；只有 `failed_breakout` 直接淘汰，`strong_breakout`、`accepted_breakout`、`weak_but_watch` 均可进入 pullback observation。
- 400 context windows 产生 144000 个生命周期事件种子、38 个 baseline raw candidates；说明旧 `true_breakout=7169` 的早杀样本问题已被修复。
- `stop_distance_too_near` 已不再是主拒绝；当前主要 RiskEngine 拒绝为 `margin_required_too_high`，不得通过放宽 margin 解决。
- `bp_lifecycle_shallow_momentum_v2`：raw=50、approved=16、closed=12；base/stress/harsh net_R_avg=0.2586/0.2477/0.2296，Full Audit、no-lookahead、metric recompute 通过。
- shallow 结果高度集中：全部为 profile C / short，ETH=10、BTC=2；样本过少，不能升级 research candidate。
- level/zone retest 仅 closed=2 且三档成本为负；boundary/midpoint 与 weak-break-watch 未产生 closed trades。
- 当前决策：C. Core rebuild identifies one promising subtype; perform subtype-focused refactor。

## 未实现

- OB/FVG/AVWAP/Session VWAP。
- 高量低结果过滤。
- CVD/OI/盘口吸收。
- 按 session 的 RVOL 阈值。

## 2026-06-05 TC family trade-count round

集中报告：`storage/research_runs/trend_continuation_family/trade_count_variant_expansion/runs/20260605T064451Z_f05f2b741564/tc_family_trade_count_and_variant_expansion_report.md`。

本轮只验证交易数、候选转化和策略形态覆盖，不做 formalization。

BP 相关结果：

- `bp_shallow_momentum_capped_risk_v3` 使用 shared lifecycle core、proposal-only capped risk sizing 和 structural stop。
- raw=1058，proposal approved=680，closed=671。
- base/stress/harsh avg R=0.0075/-0.0235/-0.0756，PF=1.0384，median_R=-0.0072。
- capped sizing 将 `margin_required_too_high_after_cap` 降为 0，但 `portfolio_heat_exceeded_after_cap=372`，说明 portfolio heat 仍是有效约束，不能放宽。
- `stop_distance_too_near=0`，说明当前 BP shallow 的结构止损不再是主拒绝。
- BTC/ETH、B/C、long/short 覆盖较上一轮明显改善，但 harsh 成本仍为负，不能升级 research candidate。

当前状态：

- `breakout_pullback` 仍为 diagnostic candidate，不得 formalize，不得进入 P6。
- 当前最值得继续的是 `shallow_pullback_momentum` 子型，但下一轮只能做一次受限收益质量优化，不能扩大参数网格或放宽风控。
- 若下一轮 harsh 成本、median_R、walk-forward、top winner concentration 仍不稳定，应停止 BP shallow 并回到策略定义层审查。

## 2026-06-05 profit and execution optimization round

集中报告：`storage/research_runs/trend_continuation_family/profit_execution_optimization/runs/20260605T083733Z_66ce079af61a/tc_family_profit_and_execution_optimization_report.md`。

本轮只做 proposal-only / diagnostic-only 的 MAE/MFE、entry、exit、cost resilience 诊断，不 formalize，不进入 P6，不修改正式配置。

BP shallow 相关结果：

- baseline `bp_shallow_momentum_capped_risk_v3`：closed=671，base/stress/harsh avg R=0.0075/-0.0235/-0.0756，PF=1.0384，median_R=-0.0072。
- baseline path diagnostics 显示 MFE_avg=0.5445、MAE_avg=0.3091、positive_MFE_but_final_loss=1105 个成本层 closed rows、cost_flipped_to_loss=502，说明存在浮盈回吐和成本吞噬，但不是简单 exit tweak 就能修复。
- `bp_shallow_exit_efficiency_v1`：closed=672，base/stress/harsh=0.0088/-0.0222/-0.0743，仅小幅改善，harsh 仍显著为负。
- `bp_shallow_entry_timing_v1`：closed=652，base/stress/harsh=-0.0260/-0.0551/-0.1040，保守 entry timing 使 MFE 与收益变差。
- `bp_shallow_cost_quality_v1`：closed=628，base/stress/harsh=0.0210/-0.0080/-0.0569，PF=1.1161，是本轮最好结果，但仍未满足 stress/harsh 正收益和 median_R >= 0。

当前决策：D. Cost structure dominates; keep diagnostic only。

长期判断：

- `shallow_pullback_momentum` 仍有研究信息价值，但不能进入 validation-prep，更不能 formalize。
- 当前主要问题不是交易数，而是成本后边际不足、exit efficiency 不足和 median_R 偏弱。
- 下一步若继续 BP shallow，只能围绕 cost_per_R、target_space、exit efficiency 做更小范围研究；不得增加策略种类、放宽风险或选择性挑 asset/profile/direction。

## 2026-06-06 cost-aware exit / target round

集中报告：`storage/research_runs/trend_continuation_family/cost_aware_exit_target/runs/20260605T161630Z_43f268f39cc0/tc_family_cost_aware_exit_target_report.md`。

本轮只基于上一轮最佳 `bp_shallow_cost_quality_v1` 做 proposal-only / diagnostic-only 研究，不扩大交易数，不新增策略族，不优化 entry timing，不重启 CE native。

核心结果：

| variant | closed | base avg R | stress avg R | harsh avg R | median R | PF | WF | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `bp_shallow_micro_profit_capture_v1` | 629 | 0.0154 | -0.0149 | -0.0596 | 0.0774 | 1.1080 | 2/3 | median 改善，但 stress/harsh 变差，不能作为主线。 |
| `bp_shallow_momentum_decay_time_stop_v1` | 629 | 0.0198 | -0.0093 | -0.0584 | -0.0435 | 1.1454 | 2/3 | time stop 减少 MAE，但增加 cost flip 和 final loser，不适合继续。 |
| `bp_shallow_cost_aware_admission_v2` | 472 | 0.0644 | 0.0390 | -0.0042 | 0.0221 | 1.4313 | 5/0 | 明显最佳，但 harsh 仍略负，未达到 validation-prep。 |

诊断结论：

- `bp_shallow_cost_aware_admission_v2` 使用入场前可知的 target_space / gross_RR / relaunch / pullback / cost_per_R / risk / stop 信息，过滤底部约 25% 候选，不按 asset/profile/direction 手工筛选。
- retained vs removed：retained avg R=0.0331，removed avg R=-0.1589；retained harsh=-0.0042，removed harsh=-0.2164；说明 cost-aware admission 确实识别了薄边际坏交易。
- micro profit capture 降低 positive MFE final loss 和 cost flip，但牺牲大赢家后 stress/harsh 没改善。
- momentum decay time stop 触发 936 个成本层 rows，avg R=-0.1579，说明 no-follow-through 存在，但当前 6 bars / 0.25R 规则过粗。
- CE shallow 对照仍弱：closed=456，base/stress/harsh=-0.0088/-0.0372/-0.0837，不建议继续 CE 优化。

当前决策：B. Exit/target optimization improved edge but not enough; one more bounded refinement allowed。

下一步边界：

- 允许最多再做一轮仅围绕 `bp_shallow_cost_aware_admission_v2` 的 bounded refinement。
- 不能进入 validation-prep，除非 harsh 转正、median_R 维持正、closed >= 400、Full Audit/no-lookahead/metric recompute/regression baseline 继续通过。
- 不得新增策略族、扩大交易数、优化 entry timing、筛 asset/profile/direction 或放宽任何风险/成本边界。

## 2026-06-06 cost-aware refinement with trend_state round

集中报告：`storage/research_runs/trend_continuation_family/cost_aware_refinement_with_trend_state/runs/20260605T173718Z_61df2053b9f1/tc_family_cost_aware_refinement_with_trend_state_report.md`。

本轮只基于 `bp_shallow_cost_aware_admission_v2` 做 proposal-only / diagnostic-only refinement，并修复 trend_state lineage；不 formalize，不进入 P6，不修改正式配置。

核心结果：

| variant | closed | base avg R | stress avg R | harsh avg R | median R | PF | WF | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `bp_shallow_cost_aware_admission_v3` | 416 | 0.0612 | 0.0381 | -0.0010 | 0.0184 | 1.4068 | 5/0 | harsh 接近打平但未转正；低质量二次过滤有效但仍不足。 |
| `bp_shallow_cost_aware_partial_capture_v1` | 472 | 0.0510 | 0.0243 | -0.0153 | 0.0864 | 1.3874 | 5/0 | median 改善、MFE>=0.5R 后亏损显著下降，但削弱右尾后 harsh 变差。 |
| `bp_shallow_cost_aware_momentum_failure_exit_v1` | 472 | 0.0644 | 0.0390 | -0.0042 | 0.0221 | 1.4313 | 5/0 | 证据型 failure exit 未触发，等同 v2，不能替代当前主线。 |

trend_state 修复：

- 原因：profile 使用 `4h/1d`，DuckDB 历史数据 bar 为 `4H/1D`，大小写精确匹配导致 regime 回算取不到 K 线。
- 修复：Research Pipeline trend_state lineage 读取时复用既有 `build_market_regime()`，先按 profile timeframe 读取，取不到再用 uppercase fallback；该修复只补诊断字段，不改变历史绩效。
- repaired coverage：candidate/filter/closed_trade trend_state coverage=100%，closed_trade unknown share=0%。
- v2 repaired split：`COMPRESSION_PENDING_BREAKOUT=142`、`MEAN_REVERTING_TRANSITION=299`、`RANGE=24`、`TREND=7`。

诊断结论：

- BP shallow 当前更像 transition / compression / range breakout momentum，而不是成熟趋势延续；`TREND` 样本少，不得据此做交易结论。
- `COMPRESSION_PENDING_BREAKOUT` 与 `RANGE` 分层表现更强，但本轮没有用 trend_state 手工筛样本。
- 当前决策：B. Refinement improved edge but still needs one final regime-aware diagnostic round。
- 下一步只允许做 regime-aware diagnostic，不得直接用 trend_state formal filter，也不得进入 validation-prep。

## 2026-06-08 final regime-aware refinement round

集中报告：`storage/research_runs/trend_continuation_family/final_regime_aware_refinement/runs/20260607T172428Z_bb3914fa269c/tc_family_final_regime_aware_refinement_report.md`。

本轮只基于 `bp_shallow_cost_aware_admission_v3` 做 proposal-only / diagnostic-only final regime-aware refinement；不 formalize，不进入 P6，不修改正式配置，不放宽成本、滑点、margin、notional cap、portfolio heat、stop、target 或正式 exit boundary。

核心结果：

| variant | closed | base avg R | stress avg R | harsh avg R | median R | PF | WF | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `bp_shallow_regime_diagnostic_no_filter_v1` | 416 | 0.0612 | 0.0381 | -0.0010 | 0.0195 | 1.4068 | 4/1 | 等同 v3 baseline；作为 regime split 诊断，不是新策略。 |
| `bp_shallow_regime_adaptive_exit_v1` | 416 | 0.0561 | 0.0307 | -0.0061 | 0.0671 | 1.4087 | 3/2 | median 改善，但 harsh 与 WF 变差；partial capture 仍削弱右尾。 |
| `bp_shallow_regime_cost_gate_v1` | 380 | 0.0558 | 0.0339 | -0.0034 | 0.0099 | 1.3798 | 4/1 | 轻度收紧 MRT 后反而删除了较好的交易，属于 overfilter。 |

regime 诊断：

- `COMPRESSION_PENDING_BREAKOUT`：closed=132，base/stress/harsh=0.1445/0.1254/0.0916，PF=2.2080，median_R=0.1065，是最明确的正贡献 regime。
- `RANGE`：closed=22，base/stress/harsh=0.1453/0.1237/0.0878，PF=2.4520，但样本偏少，只能作为提示性证据。
- `MEAN_REVERTING_TRANSITION`：closed=259，base/stress/harsh=0.0140/-0.0111/-0.0529，是主要拖累来源，但本轮不能直接删除该 regime。
- `TREND`：closed=3，样本不足，不能形成交易结论。

最终决策：C. Regime-aware rules overfit or overfiltered; revert to v3 baseline。

长期结论：

- `trend_state` split 有诊断价值，但本轮 regime-aware policy routing 没有稳定改善 harsh。
- `bp_shallow_cost_aware_admission_v3` 是当时最稳的 diagnostic baseline，但已被 2026-06-22 causal audit 标记为 historical invalidated evidence。
- 暂停 TC family refinement；后续若继续，应先做 read-only LR 互补性分析或 simple support/resistance fixed-RR baseline 对照，而不是继续局部调 BP shallow。

## 2026-06-08 cleanup and preservation

TC family best diagnostic snapshot 已固化：

- snapshot: `storage/research_runs/trend_continuation_family/best_diagnostic_snapshot/tc_family_best_diagnostic_snapshot.md`
- machine-readable summary: `storage/research_runs/trend_continuation_family/best_diagnostic_snapshot/tc_family_best_diagnostic_snapshot.json`
- cleanup report: `storage/research_runs/trend_continuation_family/best_diagnostic_snapshot/tc_family_cleanup_and_preservation_report.md`
- best variant artifact: `storage/research_runs/trend_continuation_family/cost_aware_refinement_with_trend_state/runs/20260605T173718Z_61df2053b9f1/variants/bp_shallow_cost_aware_admission_v3`

最终状态：

- status: `diagnostic_best_snapshot_preserved`
- best_variant: `bp_shallow_cost_aware_admission_v3`
- formal_candidate: false
- proposal_candidate: false
- p6_allowed: false
- live_trading_enabled: false
- refinement_status: stopped
- next_research: `simple_support_resistance_fixed_rr_baseline_pending_user_spec`

清理口径：保留 v3 最佳复现链路、final reports、audit、metric recompute、regression baseline；删除 partial capture、momentum failure、regime adaptive exit、regime cost gate 等失败/重复 replay variant 目录。LR final evidence 未触碰。
## 2026-06-08 Codex Skills 同步口径

`breakout_pullback` 当前仅保留 `bp_shallow_cost_aware_admission_v3` 作为 historical invalidated snapshot。后续若提出不同的上游机制，必须走 `trading-system-research-pipeline-runner`、`trading-system-full-audit-gate-checker` 和 `trading-system-backtest-report-analyst`；不得继续局部调参、手工筛 regime 或把旧 snapshot 写成 formal candidate。

## 2026-06-13 TC Exit Counterfactual Diagnostic

本轮专门针对 `bp_shallow_cost_aware_admission_v3` 中 396 笔 `time_exit` 且 `cost_tier == "harsh"` 的交易执行了**反事实延时持有诊断**。

核心论点：“我们一直在优化信号，而没有真正优化持仓管理。”

诊断结果：
如果强制在 20h 的基础上继续持有 12h 到 72h：
- **Original 20h Exit**: Avg R = 0.0175, Win Rate = 46.21%
- **+12h (Total ~32h)**: Avg R = -0.1427 | Win Rate = 37.22% | Stop Rate = 9.62%
- **+24h (Total ~44h)**: Avg R = -0.1603 | Win Rate = 37.47% | Stop Rate = 15.70%
- **+48h (Total ~68h)**: Avg R = -0.1373 | Win Rate = 41.52% | Stop Rate = 23.04%
- **+72h (Total ~92h)**: Avg R = -0.2018 | Win Rate = 40.76% | Stop Rate = 30.13%

**结论：**
1. 随着持有时间增加，原本 46% 的胜率稳步下跌至 37% 左右。
2. 触发原始结构止损的概率从 0 稳步攀升至 30%。
3. 平均 R 从微弱的正值迅速崩塌至深度负值 (-0.14R ~ -0.20R)。
4. “死扛不走”策略严格降低了所有指标表现，说明行情在 20 根 bar 附近确实已经失去了原有动能，并不是“退出过早”。
5. 因此，核心问题确实在于**“20根bar内跑出浮盈后，没能保全利润”**。

**下一步：**
研究重点正式从 “信号过滤 (Admission/Filtering)” 转向 “动态持仓管理 (Dynamic Exit Management)”，尤其是实现：
- **True Breakeven**：在 MFE 达到 0.5R~0.75R 时，自动将止损上移至保本+覆盖滑点手续费的位置。
- **Dynamic Time Cut**：在持有 8~10 bars 后，如果 MFE 仍低于 0.3R，则判定为动能失败，提前退出，不干等 20 bars。
