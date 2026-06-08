---
type: strategy-family
strategy_family: compression_expansion_breakout
status: diagnostic_candidate
updated: 2026-06-08
tags:
  - strategy/pa-vpa
  - strategy/research-only
---

# 07_compression_expansion_breakout

结论：`compression_expansion_breakout` 是中文语义名；Research Pipeline / adapter / manifest / setup_id 统一使用 `compression_expansion`。该 setup 已完成 proposal-only baseline、candidate anatomy、RiskEngine reject diagnostics、semantic repair round、有限 variants、Full Audit Gate 和 cross-run artifact reuse 验证，当前状态仍是 `diagnostic_candidate`，不是 formal candidate。最新结论是暂停 CE 局部优化，下一步转向 `breakout_pullback`。

## 定位

缩量压缩后的真实扩张。关注低波动压缩后的方向选择，避免沿用原宽泛 `trend_continuation` 的成熟趋势硬门控。

## 趋势角色

不是成熟趋势必要条件。该 setup 更适合 Fresh Trend / Volatility Expansion，核心门控应放在 compression box、breakout displacement、volume expansion、failed breakout filter、midpoint / boundary hold 和 RiskEngine precheck。

## 实现前置

- `setup_id`: `compression_expansion`。
- `strategy_family` / 中文语义名：`compression_expansion_breakout`。
- adapter：`research_pipeline/adapters/compression_expansion.py`。
- 诊断阶段：`window_ready`、`compression_detected`、`compression_quality_valid`、`breakout_detected`、`breakout_displacement_valid`、`breakout_volume_valid`、`failed_breakout_absent`、`midpoint_hold`、`retest_hold`、`continuation_ready`、`risk_precheck_pass`。
- 所有 expansion 仅 proposal-only，不修改正式配置。

## 2026-06-03 研究验证

- baseline 2000 entry windows / 8000 context windows：candidate_ready_windows=224，raw_candidates=56。
- baseline research validation：candidate_rows=56，formal_approved=3，closed_trades=1。
- baseline base net_R_avg=-0.5615660957783337，stress=-0.5768621686484112，harsh=-0.6023556234318735。
- 主要拒绝原因：`stop_distance_too_near=48`、`margin_required_too_high=5`、approved=3。
- 诊断漏斗主卡点：`breakout_detected=5394`、`compression_quality_valid=2154`、`breakout_displacement_valid=80`、`midpoint_hold=60`、`failed_breakout_absent=48`、`breakout_volume_valid=40`。
- B profile：candidate_ready_windows=92，raw 候选主要受 compression quality 和 breakout detected 限制。
- C profile：candidate_ready_windows=132，相比 B 更容易进入 candidate_ready，但样本仍不足。
- 有限 variants：`box_atr_max_1_75` raw=58；`breakout_buffer_atr_0_10` raw=63；`breakout_rvol_min_1_30` raw=60；`retest_tolerance_atr_0_20` raw=56；`midpoint_or_boundary_hold_v1` raw=68。
- Full Audit Gate：baseline 通过；`box_atr_max_1_75` 和 `breakout_buffer_atr_0_10` 的 closed_trade variant audit 通过。
- cross-run reuse：复用 baseline artifact 后，`midpoint_or_boundary_hold_v1` variant-only replay 约 7.5 秒完成，raw_candidates=68。
- 当前结论：可升级为 `diagnostic_candidate`，但 closed_trades=1，远低于讨论 formal candidate 的最低样本门槛，不建议 formalize。

## 2026-06-03 Candidate Anatomy / RiskEngine Diagnostics

产物：`storage/research_runs/compression_expansion/ce_anatomy_diagnostics/6e8aa4734698300a9714ed4d/`。

baseline anatomy 结论：

- raw_candidates=56，formal_approved=3，closed_trades=1。
- near-miss shadow：approved=3，reasonable_near_miss=48，definition_conflict=5。
- 主要 RiskEngine 拒绝：`stop_distance_too_near=48`、`margin_required_too_high=5`。
- `stop_distance_too_near` 主要归因：`stop_anchor_too_close=48`。
- `margin_required_too_high` 与 stop 距离 / position size 膨胀存在共因关系；不能优先放宽 margin，应先研究结构性 stop anchor。

proposal-only variants：

| variant | raw | approved | closed | base net_R_avg | stress net_R_avg | harsh net_R_avg | Full Audit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ce_stop_opposite_edge_atr_buffer_v1` | 56 | 31 | 29 | 0.05932697824620631 | 0.04827942872960517 | 0.02986684620193658 | pass |
| `ce_breakout_candle_extreme_stop_v1` | 56 | 12 | 7 | 0.1098484031529654 | 0.09643079645530403 | 0.07406811862586839 | pass |
| `ce_box_height_atr_band_filter_v1` | 58 | 3 | 1 | -0.5615660957783337 | -0.5768621686484112 | -0.6023556234318735 | pass |
| `ce_midpoint_or_boundary_hold_retest_v1` | 68 | 3 | 1 | -0.5615660957783337 | -0.5768621686484112 | -0.6023556234318735 | pass |
| `ce_cost_adjusted_target_space_filter_v1` | 56 | 3 | 1 | -0.5615660957783337 | -0.5768621686484112 | -0.6023556234318735 | pass |

结论：

- `ce_stop_opposite_edge_atr_buffer_v1` 证明 baseline 的 stop anchor 过近确实造成大量技术性拒绝；但剩余 `margin_required_too_high=25`，总收益很薄，walk-forward 后段转负，top trade concentration 偏高。
- `ce_breakout_candle_extreme_stop_v1` 收益和回撤更干净，但 closed_trades=7，样本过少。
- box height、hold confirmation、cost-adjusted target filters 没有解决核心拒绝，不能继续围绕它们局部优化。
- 当前判定：CE 继续保留 `diagnostic_candidate`，允许最多再做一轮受限研究；不得 formalize，不得进入 P6。下一轮只允许研究结构性 stop anchor / sizing cap 约束与样本扩展解释；若不能提升样本稳定性，应停止 CE 并转向 `breakout_pullback`。

## 2026-06-04 Semantic Repair Round

集中报告：`storage/research_runs/compression_expansion/ce_semantic_repair/c8e463f1961589d37eaa3d8e/compression_expansion_semantic_repair_report.md`。

本轮目的：验证 CE 交易少、收益薄是否来自“压缩后的真实扩张”语义实现不完整，而不是普通参数优化。

新增诊断：

- `semantic_v2` breakout policy：在 1-3 bars acceptance window 内识别 breakout，而不是只依赖单根 K 线。
- `breakout_score` 及组成字段：displacement、box ratio、close location、body/range expansion、volume expansion。
- acceptance window：区分 wick 回 box 但 close hold、close back inside box、midpoint/boundary hold、high volume no result。
- breakout failure taxonomy：`primary_failure_reason` 与 `secondary_failure_reasons`。
- CE subtype：`impulse_breakout`、`acceptance_retest`、`ambiguous`。
- structural stop anchor：opposite edge、breakout extreme、acceptance retest structural stop。

proposal-only variants：

| variant | raw | approved | closed | base net_R_avg | stress net_R_avg | harsh net_R_avg | Full Audit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ce_semantic_acceptance_opposite_stop_v2` | 88 | 45 | 42 | -0.0289 | -0.0400 | -0.0585 | pass |
| `ce_semantic_acceptance_breakout_extreme_stop_v2` | 38 | 11 | 7 | -0.1151 | -0.1287 | -0.1513 | pass |
| `ce_acceptance_then_retest_entry_v2` | 18 | 0 | 0 | n/a | n/a | n/a | fail / no closed_trade unverifiable |

结论：

- semantic repair 增加了候选数量，也证明结构止损能让 `stop_distance_too_near` 不再是主拒绝。
- 但收益质量没有改善，base/stress/harsh 全部未稳定转正。
- `acceptance_retest` subtype 没有形成 approved/closed trade，更像 `breakout_pullback` 的入口桥接，而不是 CE 独立可推进方向。
- 当前决策：B. CE remains diagnostic_candidate but should pause and move to breakout_pullback.
- 不得 formalize，不得进入 P6，不得继续围绕 CE 添加局部参数网格。

## 风险

- 低波动阶段容易频繁假突破。
- 需要高质量成本模型和足够样本。
- 当前主要风险不是 RVOL，而是 stop anchor、position sizing / margin coupling、样本不足和收益过薄。
- Semantic repair 后仍不能改善样本稳定性和成本后 edge；下一步应转向 `breakout_pullback`。

## 2026-06-05 lifecycle core trade-count round

集中报告：`storage/research_runs/trend_continuation_family/trade_count_variant_expansion/runs/20260605T064451Z_f05f2b741564/tc_family_trade_count_and_variant_expansion_report.md`。

本轮重新在 shared lifecycle core 下验证 CE，不再使用旧 `true_breakout` / 单根 displacement 逻辑，也不把 CE 原生策略强制绑到 BP 的完整 pullback / relaunch 条件上。

CE 结果：

| variant | raw | proposal approved | closed | base avg R | stress avg R | harsh avg R | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ce_lifecycle_native_light_confirm_v1` | 1740 | 464 | 449 | -0.1981 | -0.2295 | -0.2821 | 交易数恢复，但收益质量弱；`stop_distance_too_near=1013` 仍是主拒绝。 |
| `ce_lifecycle_shallow_momentum_v1` | 601 | 459 | 455 | -0.0115 | -0.0403 | -0.0880 | 作为 compression quality filter 接近可讨论，但 harsh 仍为负。 |

长期判断：

- 旧 CE 的“样本不足”结论不能直接代表新 lifecycle core 下的 CE；本轮证明 CE 原生交易数可以恢复。
- CE native 交易数恢复但收益结构较弱，不能 formalize。
- CE shallow 质量优于 CE native，但仍未证明成本后稳定 edge。
- CE 保持 diagnostic candidate；下一轮若继续，只能围绕收益质量做受限优化，不能放宽 RiskEngine、成本、margin、notional cap、portfolio heat、stop、target 或 exit boundary。

## 2026-06-05 profit and execution optimization round

集中报告：`storage/research_runs/trend_continuation_family/profit_execution_optimization/runs/20260605T083733Z_66ce079af61a/tc_family_profit_and_execution_optimization_report.md`。

本轮 CE 只作为 TC family diagnostic/proposal-only 研究对象，不 formalize，不进入 P6。

CE 结果：

- `ce_lifecycle_native_light_confirm_v1` baseline：closed=449，base/stress/harsh avg R=-0.1981/-0.2295/-0.2821，median_R=-0.2500，PF=0.3913。
- CE native path diagnostics：MFE_avg=0.3834、MAE_avg=0.5125，说明主要是信号质量和入场后不利路径问题，不是单纯出场问题。
- `ce_lifecycle_shallow_momentum_v1` baseline：closed=455，base/stress/harsh avg R=-0.0115/-0.0403/-0.0880，median_R=-0.0241。
- `ce_shallow_exit_efficiency_v1`：closed=456，base/stress/harsh=-0.0088/-0.0372/-0.0837，仅小幅改善，仍未证明成本后 edge。

长期判断：

- CE native 交易数已恢复，但收益路径偏弱，不能作为下一阶段主线。
- CE shallow 有浮盈与回吐现象，但 exit-only 改善不足，仍保持 diagnostic candidate。
- 不建议继续 CE 局部调参；如后续重启，应先重新审查 compression context 的质量过滤和 target_space，而不是放宽风险、成本或 margin。

## 2026-06-06 cost-aware exit / target round CE 对照

集中报告：`storage/research_runs/trend_continuation_family/cost_aware_exit_target/runs/20260605T161630Z_43f268f39cc0/tc_family_cost_aware_exit_target_report.md`。

本轮没有运行新的 CE optimization variant，只读取上一轮 `ce_shallow_exit_efficiency_v1` 作为对照。

CE shallow 对照结果：

- closed=456。
- base/stress/harsh avg R=-0.0088/-0.0372/-0.0837。
- median_R=-0.0148，PF=0.9563。
- MFE_avg=0.5194，但 positive_MFE_but_final_loss share 仍约 53.9%，cost_flipped_to_loss share 约 20.2%。

长期判断：

- compression context 没有证明优于 BP shallow cost-aware admission。
- CE shallow 暂不继续优化；CE native 继续冻结。
- 后续 TC family 若继续，只应围绕 `breakout_pullback` 的 `bp_shallow_cost_aware_admission_v2` 做极小范围验证。
## 2026-06-08 cleanup and preservation note

TC family cleanup 后，`compression_expansion` / CE native / CE shallow 不再继续局部优化。

保留口径：

- CE 相关研究结果只作为 trend continuation family 的历史诊断与语义修复参考。
- 当前 TC family best diagnostic snapshot 是 `bp_shallow_cost_aware_admission_v3`，不是 CE。
- CE artifacts 不进入 formal candidate、不进入 P6、不进入正式 proposal 队列。
- 后续优先方向为 simple support/resistance fixed RR baseline 对照，不是继续 CE 参数微调。
## 2026-06-08 Codex Skills 同步口径

`compression_expansion` 后续若重启，只能通过 Research Pipeline 和 Strategy Expansion Diagnostics 流程进入 proposal-only 研究。当前不再继续 CE native / CE shallow 局部优化；本页结论由 `trading-system-obsidian-sync` 同步维护，不能把 CE diagnostic 结果写成 formal candidate 或 P6 证据。
