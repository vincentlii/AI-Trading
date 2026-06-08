# Research Pipeline 指南

## 结论

Research Pipeline 是通用研究工厂，不是 LR 专用脚本集合。新策略必须先通过 adapter、registry、run manifest、artifact contract、audit profile、expansion diagnostics 和 Full Audit Gate；不得新增平行 v1 脚本绕过主链路。

## 通用接口

| 接口 | 职责 |
| --- | --- |
| `StrategyAdapter` | 声明 strategy id、adapter version、candidate schema、lineage fields、artifact contract、audit profile、diagnostic stages 和 proposal-only expansion variants |
| `RunManifest` | 声明 run id、strategy、dataset window、artifact paths、config snapshot、baseline ref 和 audit profile |
| `ArtifactContract` | 声明 required inputs、required outputs、performance row type 和禁止进入收益统计的 row types |
| `AuditProfile` | 声明 closed_trade 口径、lineage、no-lookahead、metric recompute、robustness、exposure 和 regression 要求 |
| `strategy-expansion-diagnostics` | 通用 staged diagnostics runner；pipeline 负责窗口回放、artifact、manifest、registry、cross-run reuse；adapter 负责策略专属诊断层 |

## Expansion Diagnostics

`expansion diagnostics` 是 Research Pipeline 的通用阶段，不是某个策略的临时脚本。

通用能力：

- staged progress。
- rejection funnel。
- diagnostic rows。
- near-miss rows。
- proposal-only expansion variants。
- artifact index。
- run registry。
- audit row 隔离。
- cross-run baseline artifact reuse。
- variant validation 的 base / stress / harsh cost tiers。

策略 adapter 必须声明：

- `diagnostic_stages()`：本策略从 context 到 raw candidate 的阶段顺序。
- `proposal_expansion_variants()`：允许的 proposal-only 小范围放宽方案。

命令示例：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research strategy-expansion-diagnostics --strategy compression_expansion --preset configs\presets\btc_eth_swap_proposal.toml --db storage\history.duckdb --dataset-window btc_eth_swap_2000w --output-root storage\research_runs\compression_expansion\ce_anatomy_diagnostics --max-entry-windows 2000 --cost-tier base --cost-tier stress --cost-tier harsh --run-top-variants --force --format json
```

跨 run 复用规则：

- baseline artifact 必须有 `baseline_reuse_manifest.json`。
- 复用前必须校验 strategy、adapter version、dataset window、setup_filter、config fingerprint、stage catalog hash 和 artifact sha256。
- 可复用对象包括 context rows、raw candidate cache、diagnostic funnel rows、near-miss rows、regime rows、run manifest、artifact index 和 run registry。
- fingerprint 不匹配时必须拒绝复用，不得静默回退到旧 artifact。
- variant-only run 只允许用于 proposal-only diagnostics；收益统计仍只能读取 `row_type=closed_trade`。

## Full Audit Gate

- performance metrics 只能来自 `row_type=closed_trade`。
- proposal / diagnostic / summary rows 不得进入收益统计。
- closed trades 必须追溯 execution、candidate、event 和 timeseries。
- no-lookahead 必须验证时间顺序，不只检查字段存在。
- metric recompute 对非 LR 策略必须支持 `event_key -> event_id -> candidate_id -> trade_id` fallback，避免因字段命名差异误报 duplicate event。
- robustness、exposure restriction 和 regression baseline 必须保留。

## 当前策略状态

- `liquidity_reversal` 是 Restricted Variant B formal research candidate，但仍不是 live strategy。
- `trend_continuation` 已停止局部调参，状态为 `strategy_definition_refactor_needed`。
- `compression_expansion` 是 `diagnostic_candidate`；setup_id / adapter / manifest 统一命名为 `compression_expansion`，Obsidian 语义名 `compression_expansion_breakout` 指向同一 setup。
- `breakout_pullback` 已完成 proposal-only initial research，当前为 backlog，不是 formal candidate。
- Research Pipeline tests 使用 deterministic fixtures，不依赖旧 `storage/backtest_cache`。
- LR runner 名称和 PR stage 名称只作为历史兼容层存在，不得作为新策略主路径。

## compression_expansion 记录

2026-06-03，`compression_expansion` 完成 proposal-only candidate anatomy + RiskEngine reject diagnostics。

- baseline：raw_candidates=56，formal_approved=3，closed_trades=1。
- baseline near-miss shadow：reasonable_near_miss=48，definition_conflict=5。
- baseline 主要拒绝：`stop_distance_too_near=48`、`margin_required_too_high=5`。
- `stop_distance_too_near` 主要归因于 `stop_anchor_too_close`。
- `margin_required_too_high` 与 stop 过近导致的 position size / notional 膨胀相关，不应先放宽 margin。
- `ce_stop_opposite_edge_atr_buffer_v1`：raw=56，approved=31，closed=29，base/stress/harsh net_R_avg=0.0593/0.0483/0.0299，Full Audit Gate 通过，但收益薄、分段不稳、剩余 margin 拒绝高。
- `ce_breakout_candle_extreme_stop_v1`：raw=56，approved=12，closed=7，base/stress/harsh net_R_avg=0.1098/0.0964/0.0741，Full Audit Gate 通过，但样本过少。
- 其余 box height、hold confirmation、cost-adjusted target filters 未解决核心拒绝。

当前判断：CE 保留 `diagnostic_candidate`，最多再做一轮受限研究；若不能提升样本稳定性，应停止 CE 并转向 `breakout_pullback`。

## breakout_pullback 记录

2026-06-04，`breakout_pullback` 完成 proposal-only initial research。

命令：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research strategy-expansion-diagnostics --strategy breakout_pullback --preset configs\presets\btc_eth_swap_proposal.toml --db storage\history.duckdb --dataset-window btc_eth_swap_2000w --output-root storage\research_runs\breakout_pullback\initial_research --max-entry-windows 2000 --cost-tier base --cost-tier stress --cost-tier harsh --variant bp_level_retest_continuation_v1 --variant bp_boundary_or_midpoint_retest_v1 --variant bp_shallow_pullback_momentum_v1 --run-top-variants --format json
```

结果：

- run_id：`66591695010676daa1e2434a`。
- baseline：candidate_ready_windows=194，raw_candidates=49。
- `bp_level_retest_continuation_v1`：raw=47，approved=0，closed=0；主要被 `stop_distance_too_near` 拒绝。
- `bp_boundary_or_midpoint_retest_v1`：raw=49，approved=17，closed=10；base/stress/harsh net_R_avg 全部为负。
- `bp_shallow_pullback_momentum_v1`：raw=27，approved=9，closed=3；base/stress/harsh net_R_avg 全部为负。
- 有 closed_trade 的 variants Full Audit 可验证通过；无 closed_trade 的 variant 不得绕过 gate。
- 集中报告：`storage/research_runs/breakout_pullback/initial_research/66591695010676daa1e2434a/breakout_pullback_initial_research_report.md`。

当前判断：BP 进入 backlog。后续若重启，应先修策略定义，不应继续扩大参数网格或放宽 RiskEngine / 成本 / margin / notional / portfolio heat / exit boundary。

## 新策略准入

1. 先注册 adapter。
2. 声明 candidate schema、artifact contract、audit profile。
3. 声明 diagnostic stages 和 proposal-only expansion variants。
4. 生成 dry-run manifest。
5. 进入 proposal-only research validation。
6. raw candidate 不足时先跑 `strategy-expansion-diagnostics`。
7. performance metrics 只能来自 `row_type=closed_trade`。
8. proposal / diagnostic / summary rows 不得进入收益统计。
9. Full Audit Gate 必须覆盖 lineage、no-lookahead、metric recompute、proposal boundary、artifact integrity、robustness、exposure restriction 和 regression baseline。
10. 只有 research validation 有足够 closed trades 且 Full Audit Gate 可验证时，才允许讨论 formal candidate。

## 禁止事项

- 不直接复制 LR PR11 stage 脚本。
- 不依赖旧 cache 作为测试输入。
- 不自动修改 formal config。
- 不把 proposal、diagnostic、summary rows 纳入收益统计。
- 不通过放宽 RiskEngine、fee、funding、margin、notional cap、stop、target 或正式出场边界制造收益。

## 2026-06-05 TC family trade-count round

`tc-family-trade-count-expansion` 已作为 Research Pipeline 的趋势延续家族研究入口，当前只用于 proposal-only / diagnostic-only。

长期规则：

- 高成本 deterministic 中间结果必须写入 `shared_cache/<fingerprint>/family_events.duckdb`，通过 manifest / fingerprint 校验复用。
- fingerprint 必须覆盖 dataset window、setup_filter、adapter/core version、config fingerprint、window limit 等关键输入；不匹配时拒绝复用。
- 共享缓存只保存 compact lifecycle event，不保存全量 diagnostic payload，避免重复 artifacts 占满磁盘。
- variant replay 必须做全 run signal-level arbitration，同一 `asset/profile/direction/signal_time` 只能执行一个最高 rank candidate；不得只在 batch 内去重。
- `duckdb_tmp` 必须放在 cache 目录下，不能落到系统盘临时目录。
- 中断或调试 run 完成后必须清理空 run、小窗口 smoke run 和无用 shared cache；保留 final run、manifest、audit、metric recompute、robustness、regression baseline 所需 artifacts。

本轮发现的性能根因：

- 2000w shared cache 已完整复用，但首次 replay 在第一个 variant 卡住。
- 根因是 batch 内仲裁后仍留下跨 batch 重复信号：CE native 从 28,451 个待执行候选实际可降到 1,740 个全局唯一信号，导致 execution replay 被放大约 16 倍。
- 修复后 2000w 三 variant replay 成功完成，最终报告位于 `storage/research_runs/trend_continuation_family/trade_count_variant_expansion/runs/20260605T064451Z_f05f2b741564/tc_family_trade_count_and_variant_expansion_report.md`。

当前 2000w 结论：

- 决策：A. Trade count and subtype diversity improved; run one bounded profit-optimization round.
- `ce_lifecycle_native_light_confirm_v1`：raw=1740，proposal approved=464，closed=449，base/stress/harsh avg R=-0.1981/-0.2295/-0.2821。
- `ce_lifecycle_shallow_momentum_v1`：raw=601，proposal approved=459，closed=455，base/stress/harsh avg R=-0.0115/-0.0403/-0.0880。
- `bp_shallow_momentum_capped_risk_v3`：raw=1058，proposal approved=680，closed=671，base/stress/harsh avg R=0.0075/-0.0235/-0.0756。
- 三个 variants Full Audit、no-lookahead、metric recompute 均通过；performance metrics 仍只来自 `row_type=closed_trade`。
- 不得据此 formalize；下一轮只能做有边界收益优化，不得扩张数据源、进入 P6 或放宽风险/成本/正式配置边界。

## 2026-06-05 TC family profit and execution optimization

`tc-family-profit-execution-optimization` 是 TC family 的 proposal-only 执行路径与收益归因研究入口，不是 formalization 工具。

用途：

- 读取上一轮 `tc-family-trade-count-expansion` final run。
- 对 CE native、CE shallow、BP shallow 做 baseline MAE/MFE、exit efficiency、cost flip、early MAE 和 attribution diagnostics。
- 最多运行 4 个受限 optimization variants：`bp_shallow_exit_efficiency_v1`、`ce_shallow_exit_efficiency_v1`、`bp_shallow_entry_timing_v1`、`bp_shallow_cost_quality_v1`。
- 输出集中报告 `tc_family_profit_and_execution_optimization_report.md`，内部 artifacts 只服务 audit、metric recompute、robustness、regression baseline 和复现。

命令示例：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research tc-family-profit-execution-optimization --preset configs\presets\btc_eth_swap_proposal.toml --db storage\history.duckdb --dataset-window btc_eth_swap_2000w --baseline-run-root storage\research_runs\trend_continuation_family\trade_count_variant_expansion\runs\<run_id> --output-root storage\research_runs\trend_continuation_family\profit_execution_optimization --format json
```

长期规则：

- 继续使用 capped risk sizing proposal policy，且 cap 后最低实际风险门槛保持 0.10% equity。
- MAE/MFE 只能在 closed trade 生命周期内计算，不得影响入场前信号。
- exit / entry 改动只能作为 proposal-only shadow replay，不得修改正式 exit boundary。
- performance metrics 仍只能来自 `row_type=closed_trade`。
- path diagnostics 会展开 base/stress/harsh closed rows；表内 path `Closed` 是成本层行数，不是唯一交易数。
- 若 best variant 仅 base 为正、stress/harsh 仍为负，不能进入 validation-prep。

当前 2000w 结论：

- 决策：D. Cost structure dominates; keep diagnostic only。
- `bp_shallow_cost_quality_v1` 是本轮最好结果：closed=628，base/stress/harsh avg R=0.0210/-0.0080/-0.0569，PF=1.1161，median_R=-0.0047。
- `bp_shallow_exit_efficiency_v1` 只小幅改善，未修复 harsh 成本。
- `bp_shallow_entry_timing_v1` 明显变差。
- `ce_shallow_exit_efficiency_v1` 未证明 CE shallow 可通过 exit-only 改善。
- TC family 继续 diagnostic-only，不得 formalize，不得进入 P6。

## 2026-06-06 TC family cost-aware exit / target round

`tc-family-cost-aware-exit-target` 是 TC family 的 proposal-only cost-aware exit / target 研究入口。它只能读取上一轮 `tc-family-profit-execution-optimization` final run，不得重新扩张策略族或修改正式配置。

命令示例：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research tc-family-cost-aware-exit-target --preset configs\presets\btc_eth_swap_proposal.toml --db storage\history.duckdb --dataset-window btc_eth_swap_2000w --baseline-run-root storage\research_runs\trend_continuation_family\profit_execution_optimization\runs\<run_id> --output-root storage\research_runs\trend_continuation_family\cost_aware_exit_target --format json
```

长期规则：

- 主线只能基于 `bp_shallow_cost_quality_v1`。
- 本轮最多 3 个 variants：`bp_shallow_micro_profit_capture_v1`、`bp_shallow_momentum_decay_time_stop_v1`、`bp_shallow_cost_aware_admission_v2`。
- `bp_shallow_micro_profit_capture_v1` 使用固定 0.40R proposal partial/breakeven policy，不跑阈值网格。
- `bp_shallow_momentum_decay_time_stop_v1` 只用入场后前 6 根确认 K 线判断 early MFE，不得使用完整未来路径决定入场。
- `bp_shallow_cost_aware_admission_v2` 只使用入场前可知字段计算 score，过滤弱 25% 候选；retained vs removed 是事后诊断，不得用于再次筛选。
- performance metrics 继续只读取 `row_type=closed_trade`。

当前 2000w 结论：

- run_id：`20260605T161630Z_43f268f39cc0`。
- 决策：B. Exit/target optimization improved edge but not enough; one more bounded refinement allowed。
- `bp_shallow_cost_aware_admission_v2`：closed=472，base/stress/harsh avg R=0.0644/0.0390/-0.0042，median_R=0.0221，PF=1.4313，walk-forward=5/0，Full Audit/no-lookahead/metric recompute 通过。
- 该结果未达到 validation-prep：harsh 仍小幅为负，不能 formalize。
- 下一轮若继续，只能围绕 winning mechanism 做一轮更小范围 refinement，不得新增策略、扩大交易数或筛 asset/profile/direction。
## 2026-06-06 TC family cost-aware refinement with trend_state

`tc-family-cost-aware-refinement-with-trend-state` 是 TC family 的 proposal-only refinement runner，只能读取上一轮 `bp_shallow_cost_aware_admission_v2` artifacts 作为 baseline。

命令示例：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research tc-family-cost-aware-refinement-with-trend-state --preset configs\presets\btc_eth_swap_proposal.toml --db storage\history.duckdb --dataset-window tc_family_cost_aware_refinement_with_trend_state_2026_06_06 --baseline-run-root storage\research_runs\trend_continuation_family\cost_aware_exit_target\runs\<run_id> --output-root storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state --format json
```

长期规则：

- 本 runner 最多运行 3 个 performance variants：`bp_shallow_cost_aware_admission_v3`、`bp_shallow_cost_aware_partial_capture_v1`、`bp_shallow_cost_aware_momentum_failure_exit_v1`。
- trend_state lineage 必须贯穿 candidate / filter / closed_trade，并输出 unknown share；若 closed_trade unknown share >= 5%，禁止任何 trend_state 交易结论。
- trend_state 口径必须复用项目既有 `build_market_regime()`，不得另造 regime 定义。
- profile timeframe 与 DuckDB bar 命名存在大小写差异时，lineage 读取允许 uppercase fallback；这只修诊断字段，不改变交易绩效。
- trend_state 只能作为 diagnostic split；不得为了让 harsh 转正而手工筛 asset/profile/direction/trend_state。
- performance metrics 仍只能来自 `row_type=closed_trade`。

当前 2000w 结论：

- run_id：`20260605T173718Z_61df2053b9f1`。
- 集中报告：`storage/research_runs/trend_continuation_family/cost_aware_refinement_with_trend_state/runs/20260605T173718Z_61df2053b9f1/tc_family_cost_aware_refinement_with_trend_state_report.md`。
- trend_state repaired coverage：candidate/filter/closed_trade 均为 100%，closed_trade unknown share=0%。
- `bp_shallow_cost_aware_admission_v3`：closed=416，base/stress/harsh avg R=0.0612/0.0381/-0.0010，median_R=0.0184，PF=1.4068，WF=5/0。
- `bp_shallow_cost_aware_partial_capture_v1`：closed=472，base/stress/harsh avg R=0.0510/0.0243/-0.0153，median_R=0.0864，PF=1.3874，WF=5/0。
- `bp_shallow_cost_aware_momentum_failure_exit_v1` 未触发 failure exit，结果等同 v2。
- 决策：B. Refinement improved edge but still needs one final regime-aware diagnostic round。
- 不得 validation-prep、formalize 或进入 P6；下一轮若继续，只能做 regime-aware diagnostic，且不得直接使用 trend_state 作为正式过滤。
## 2026-06-08 tc-family-final-regime-aware-refinement

`tc-family-final-regime-aware-refinement` 是 TC family 在 validation-prep 前的最后一轮 proposal-only regime-aware diagnostic runner。它只读取上一轮 `bp_shallow_cost_aware_admission_v3` artifacts，不重新扫描全量窗口。

命令示例：

```powershell
.\.venv\Scripts\python.exe -B -m research_pipeline.cli.research tc-family-final-regime-aware-refinement --preset configs\presets\btc_eth_swap_proposal.toml --db storage\history.duckdb --dataset-window tc_family_final_regime_aware_refinement_2026_06_08 --baseline-run-root storage\research_runs\trend_continuation_family\cost_aware_refinement_with_trend_state\runs\<run_id> --output-root storage\research_runs\trend_continuation_family\final_regime_aware_refinement --format json
```

长期规则：

- 本 runner 最多运行 3 个 variants：`bp_shallow_regime_diagnostic_no_filter_v1`、`bp_shallow_regime_adaptive_exit_v1`、`bp_shallow_regime_cost_gate_v1`。
- `trend_state` 只能用于 diagnostic split 或 proposal-only policy routing，不得作为 formal filter，也不得手工删除某个 regime 来美化收益。
- `bp_shallow_regime_diagnostic_no_filter_v1` 必须等同 v3 baseline，只用于分层报告。
- `bp_shallow_regime_adaptive_exit_v1` 只能路由 exit policy，不得改变 entry / stop / target / RiskEngine。
- `bp_shallow_regime_cost_gate_v1` 只能轻度收紧 entry-known cost/space score，不得按 asset/profile/direction 筛选。
- performance metrics 仍只能来自 `row_type=closed_trade`；diagnostic/proposal/summary rows 不得纳入收益统计。

当前结论：

- run_id=`20260607T172428Z_bb3914fa269c`。
- 集中报告：`storage/research_runs/trend_continuation_family/final_regime_aware_refinement/runs/20260607T172428Z_bb3914fa269c/tc_family_final_regime_aware_refinement_report.md`。
- 最终决策：C. Regime-aware rules overfit or overfiltered; revert to v3 baseline。
- `bp_shallow_cost_aware_admission_v3` 保留为 diagnostic baseline，但不进入 validation-prep；TC family 暂停继续局部 refinement。

## 2026-06-08 TC family cleanup and preservation

`trend_continuation_family` 当前已停止策略层小修小补，不进入 validation-prep、不 formalize、不进入 P6、不进入正式 proposal 队列。

当前最佳诊断快照为 `bp_shallow_cost_aware_admission_v3`：

- status: `diagnostic_best_snapshot_preserved`
- formal_candidate: false
- proposal_candidate: false
- p6_allowed: false
- live_trading_enabled: false
- refinement_status: stopped
- next_research: `simple_support_resistance_fixed_rr_baseline_pending_user_spec`

保留位置：

- snapshot: `storage/research_runs/trend_continuation_family/best_diagnostic_snapshot/tc_family_best_diagnostic_snapshot.md`
- machine summary: `storage/research_runs/trend_continuation_family/best_diagnostic_snapshot/tc_family_best_diagnostic_snapshot.json`
- cleanup report: `storage/research_runs/trend_continuation_family/best_diagnostic_snapshot/tc_family_cleanup_and_preservation_report.md`
- best variant artifact: `storage/research_runs/trend_continuation_family/cost_aware_refinement_with_trend_state/runs/20260605T173718Z_61df2053b9f1/variants/bp_shallow_cost_aware_admission_v3`

清理规则：

- 只清理已判定失败、重复 replay、被集中报告替代且不影响复现的 TC family intermediate variant artifacts。
- 必须保留 best snapshot、closed_trade rows、Full Audit、no-lookahead、metric recompute、regression baseline、manifest/fingerprint 和 shared lifecycle core。
- 不得删除 LR final evidence、Research Pipeline 基础设施、shared lifecycle engine 或 Obsidian 正式页面。
- 后续如重新研究 TC family，必须从保存的 diagnostic snapshot 和报告恢复上下文，不得把该 snapshot 当作 formal candidate 或 P6 准入证据。
