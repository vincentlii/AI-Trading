---
type: process
status: active
updated: 2026-06-02
tags:
  - domain/backtest
  - domain/agent
---

# Proposal验证流程

结论：proposal 是建议，不是配置；未验证、未人工确认前不得进入确定性热路径。LR 研究停止后，Research Pipeline / Full Audit Gate 仍是所有策略进入 formal candidate 前的主路径。

## 流程

1. Agent 或人工生成 JSON proposal。
2. proposal 进入 `configs/proposals/`。
3. 通过 `trading_system.config.proposals` 校验允许字段。
4. 验证时只在内存中生成 proposed preset。
5. 复用 P4.4 回测路径对比 base/proposed。
6. 输出验证结果。
7. 人工确认后，才可能生成正式配置候选。

## Research Pipeline 主路径

后续策略研究不再复制 PR11A-PR11H 临时脚本流，统一走：

1. strategy adapter / registry / CLI。
2. candidate schema / cache / lineage。
3. artifact reader / index / research run registry。
4. edge / tag / sizing diagnostics。
5. combined candidate proposal。
6. full-audit gate。
7. robustness validation。
8. final regression baseline。
9. proposal-to-formal decision log。

适用策略包括 `liquidity_reversal`、`trend_continuation`、`breakout_pullback`、`stopping_volume_retest` 以及后续 PA/VPA 策略。

## Full Audit Gate 硬规则

- performance metrics 只能来自 `row_type=closed_trade`。
- `proposal_candidate`、`sizing_diagnostic`、`diagnostic_only`、`summary_row` 不得进入 net_R、PF、MFE、MAE、drawdown。
- closed trade 必须具备 `trade_id`、`execution_id`、`candidate_id`、`event_id` 和可验证时间链路。
- no-lookahead 必须可验证：confirmed bar、feature cutoff、structure confirmed time、signal time、entry time、exit time 必须满足顺序约束。
- 指标必须能从 row-level artifact 重算，不能从 markdown summary 反推。
- 旧 PR11C-PR11G 产物只作为历史参考；最终决策以 clean rebuild、full-audit、robustness、exposure restriction 和 final evidence 为准。

## 验证入口

```powershell
.\.venv\Scripts\python scripts\validate_p4_5_proposal.py --proposal configs\proposals\<proposal>.json
```

## 运行记录

proposal 或批量回测脚本默认写入 `storage/backtest_runs/`：

- `index.jsonl`：每次运行的索引。
- `<run_id>/summary.json`：脚本参数、Git 状态、配置指纹、资产、策略、风控、成本和执行配置摘要。
- `<run_id>/rows.csv`：分组回测结果，便于横向比较。
- `<run_id>/preset_snapshot.json`：当次 preset 快照。

除非是临时调试，否则不要使用 `--no-record`。对比参数效果时以 `config_fingerprint`、`cost_tier`、`symbol/profile/setup/direction` 和 `rows.csv` 为主。

## 分层缓存回测

SWAP proposal 回测优先使用分层缓存：

1. `candidate_only`：创建 `context_features.jsonl` 和 `raw_candidates.jsonl`，只统计结构候选。
2. `filter_replay`：读取 raw candidates，重放 proposal、risk 和 contract risk 过滤，输出 `filter_results.jsonl` 与 `funnel_summary.csv`。
3. `gate_ablation`：基于同一批 raw candidates 输出各 gate 的输入、通过、拒绝和 top reject reason。
4. `full_backtest`：只对 formal approved 候选做完整 execution replay，并输出 `execution_results.jsonl`。

缓存复用规则：

- 只改 RVOL 阈值、CHoCH、reclaim、target R、risk、contract risk 阈值：复用 context 和 raw candidates，重跑 `filter_replay`。
- 改 ATR、swing、RVOL baseline、trend timeframe、CHoCH 结构定义：重建 context 和 raw candidates。
- 改成本、funding、出场、same-bar、partial TP、breakeven、time cut、margin/liquidation 模型：重跑 execution replay。
- shadow approval 只用于诊断，不得转成 formal approval。

reclaim RVOL 不再只作为单一硬拒绝阈值，应同时输出诊断分层：

- `reclaim_rvol <= 1.2`：`ideal_reclaim`。
- `1.2 < reclaim_rvol <= 1.6`：`acceptable_reclaim`，先进入诊断，不直接硬拒绝。
- `reclaim_rvol > 1.6`：`high_reclaim_rvol`，作为过热 reclaim 拒绝原因。

Candidate anatomy audit 用于解释 raw candidates 存在但 formal approved 为 0 的原因，只输出候选结构、entry、stop、ATR、target 和 reject 状态，不跑 `full_backtest`。
若 audit 显示 `invalidation_mode=structure_extreme_buffer` 但 `stop_formula_used=legacy_atr_buffer_*`，说明 raw candidate 生成层没有真正使用 proposal stop formula，下一阶段应先修 stop / invalidation 传参链路。

Stage 2 已修复 SWAP layered raw candidate 的 stop / invalidation 传参链路：`preset.execution.invalidation_mode` 和 `preset.execution.invalidation_buffer_atr` 必须进入 raw candidate 生成层。liquidity reversal 的 `stop_formula_used` 应为 `structure_extreme_buffer_long` 或 `structure_extreme_buffer_short`；若 fallback 到 legacy ATR buffer，必须记录 `stop_formula_fallback_reason`，不得静默 fallback。

Stage 2B 修复 entry reference / signal timing：liquidity reversal raw candidate 必须绑定 `sweep_timestamp_ms`、`reclaim_timestamp_ms`、`signal_timestamp_ms`、`entry_timestamp_ms`。`entry_reference_price` 使用 signal 后第一根 entry bar 的 open，并且只在当前扫描窗口正好对应这根 entry bar 时产出候选，避免历史 sweep/reclaim event 在后续窗口被重复生成。候选应输出 `candidate_lifecycle_status`、bar delay、`sweep_event_id` 和 dedup 统计。

Stage 3 使用 Fresh LR scanner 诊断真实新鲜事件链，不生成交易、不跑 `full_backtest`。事件链为 structure level -> sweep -> reclaim -> signal -> next entry candidate。wick、RVOL、CHoCH、trend 只作为 tag，不在 scanner 层硬拒绝。若 scanner 显示 structure levels 存在但全部 `expired_structure_levels` 且 sweep 为 0，下一步优先重设 structure level 定义，而不是恢复历史事件 replay。

Stage 4 重设 liquidity reversal 的 active structure source：默认不再用全历史 range high/low 作为 active liquidity pool。Fresh LR scanner 的 active source 优先为 `recent_swing` 和 `rolling_range`，并要求结构位满足 profile 级 age 限制、距离当前价格不超过 structure ATR 的 3.0 倍，且每个 asset/profile/direction 最多选 liquidity score 最高的 3 个 active levels。`equal_high_low` 和 `previous_day_high_low` 先作为诊断 source 输出，不作为默认 active candidate source。若 Stage 4 scanner 出现 sweep/reclaim/fresh candidates，再进入 Minimal LR v0 filter replay；若 active levels 有但 sweep 仍为 0，再诊断 sweep definition 或扩大窗口。

Stage 5 Minimal LR v0 filter replay 只使用 Stage 4 fresh candidates。v0 硬过滤只保留 direction、stop/target 可计算、min target R、`RiskEngine`、基础 contract risk 与 cost-after-R；wick、RVOL、CHoCH、trend、structure source 和 liquidity score 只作为 diagnostic tags，不作为硬拒绝。若 v0 已出现 formal approved，可以只对 formal approved rows 运行最小 execution replay；不得恢复旧历史 replay，也不得跑大规模 full backtest。

Stage 6 逐步恢复质量过滤器时，必须基于 Stage 5 的 fresh candidate/filter/execution artifact 做单因子诊断，不做暴力网格。恢复顺序为 CHoCH、trend alignment、wick、sweep RVOL、reclaim RVOL，再比较 Conservative / Balanced 组合。CHoCH、trend、RVOL 若在 artifact 中全为 false/unknown，不得把组合归零误判为策略无效，应先补齐对应 tag 数据链路。margin/stop-near 只做 shadow sensitivity，不得放宽正式 `RiskEngine`。

Stage 6B 补齐 fresh candidate 的质量 tag 数据链路：CHoCH、trend、sweep/reclaim RVOL、volume baseline、wick tier、liquidity score tier 都必须进入 artifact；无法计算时必须输出 missing reason。position sizing / margin diagnostics 应同时输出 risk-based sizing、notional-capped shadow sizing 和 stop-near reject shadow 口径，但这些 shadow 结果不得改变 formal approval。若补齐 tag 后只有 sweep RVOL 等单项改善 MFE/net_R，而组合样本过少，下一阶段应优先做 Stage 6C sizing proposal 或扩大样本，不直接进入 full backtest。

Stage 6C 建立 setup-specific sizing proposal 框架：`liquidity_reversal` 可以独立诊断 `notional_capped_risk_based`，但必须标记为 proposal-only，不能覆盖 formal `RiskEngine` approval。`trend_continuation` 只保留独立 sizing/stop/exit policy 占位，不得套用 liquidity reversal 的仓位规则。Stage 6C 报告必须同时输出 current risk-based 与 capped proposal 的 formal/proposal 区别、actual risk pct、risk utilization、notional cap hit、stop-near quality flag 和重点子组表现；若 capped 后 risk utilization 过低或 stop-near 多数属于 required notional far above cap，不得进入 Stage 7 full backtest。

Stage 6D 继续验证 capped sizing edge 时，低 actual risk 不能被机械拒绝，但也不能被视为已验证收益。报告必须按 actual risk、risk utilization、required notional/cap、MFE push 和 quality tag 组合分层，重点看 `MFE_R >= 0.5`、`MFE_R >= 1.0`、net return on notional 与 time cut rate。若 capped-only 候选没有 execution path，只能标记为 proposal-only / no execution，不得把 approved_count 当作 edge。若所有已执行组合仍无 `MFE_R >= 0.5`，下一阶段优先下载更多 SWAP 历史或升级 entry 逻辑，而不是进入 full backtest。

Stage 6E 在扩展 SWAP 历史后重跑 Fresh LR 链路，用于验证质量 tag 是否稳定提高 MFE。报告必须分窗口输出 fresh candidates、formal approved、capped proposal approved、closed trades、MFE_R 分布、net return on notional 和 time_cut_exit_rate。若 10000w/full history 因性能或人工中断未完成，不得用 3000w/5000w 替代最终结论；只能作为阶段性 evidence。若 `high_sweep_rvol + CHoCH true + high_wick` 等组合在更大样本中仍能保持 `MFE_R >= 0.5` 和 `MFE_R >= 1.0` 改善，才考虑 Stage 7 smoke；否则进入 Stage 6F Entry Confirmation Upgrade。

Stage 6E Aggregator 只聚合既有 Stage 6D/6E artifact，不重新扫描行情、不跑 full backtest。它按窗口比较 baseline、`high_sweep_rvol`、`CHOCH true`、`high_wick`、`high_sweep_rvol + CHOCH true + high_wick`、`displacement_after_reclaim`、`ETH C short`，并输出 closed trades、MFE、MFE>=0.5、MFE>=1.0、net_R、net return on notional、time cut 和 sample warning。Aggregator 的 `stage7_smoke_ready` 只表示“可准备 smoke 初验”，不代表策略可进入正式 Stage 7 或正式配置。

Stage 6F entry confirmation tags 只作为诊断字段，不作为硬过滤、不生成正式交易。Fresh LR candidate artifact 应输出 `displacement_after_reclaim`、`displacement_body_atr`、`choch_strength`、`pullback_retest_after_reclaim`、`second_push_after_reclaim`、`fvg_exists`、`fvg_midpoint`、`fvg_retest_hit` 和 missing reason。若这些 tag 能解释 MFE 提升，下一阶段再设计 entry confirmation；不得在 Stage 6F 前直接替换入场逻辑。

Stage 7 smoke framework 可以基于一个候选组合生成 smoke plan，例如 `high_sweep_rvol + CHOCH true + high_wick`。该框架必须输出成本、滑点、funding、MAE/MFE、exit reason、drawdown、same-bar ambiguity、long/short、asset/profile 分组，但默认 `formal_conclusion_enabled=false`，不得在 10000w/full confirmation 前给正式结论，也不得正式化 notional-capped sizing。

PR 11G-QA full audit gate 是进入 robustness 前的硬门槛。performance metric 只能来自 `row_type=closed_trade` 的 row-level artifact，且推荐 robustness rows 必须 100% 有 `trade_id`、`execution_id`、`candidate_id`、`event_id` 和可验证 no-lookahead 时间链路。`proposal_candidate`、`sizing_diagnostic`、`diagnostic_only`、`summary_row` 不得进入 net_R、PF、MFE、MAE、drawdown。若旧 artifact 缺少真实 execution identity，只能保留为历史 diagnostic，不得作为 robustness input。

PR 11G-Rebuild 后，LR robustness 前置输入必须以 `storage\backtest_cache\pr11g_clean_rebuild` 的 clean artifacts 为准；旧 PR11C / PR11D / PR11E / PR11F / PR11G / PR11G-fix / PR11G-QA-fix-3 产物只作为历史参考，不得作为最终 PR11H input。

```powershell
.\.venv\Scripts\python -B -m research_pipeline.cli.research full-audit --strategy liquidity_reversal --artifact-dir storage\backtest_cache\pr11g_clean_rebuild\lr_combined_fix --output-dir storage\backtest_cache\pr11g_clean_rebuild\full_audit
```

只有 full-audit `primary_decision` 为 A 或 B，才可进入 PR 11H robustness。

PR 11H robustness 通过收益压力测试不等于可以直接进入 PR 12。若 Variant B 在 base / stress / harsh / extreme harsh 下仍为正，但出现 profile、asset、direction 过度集中，或同向 overlap / concurrent portfolio heat 明显偏高，应选择 Primary Decision C，进入 PR11H-fix 做 regime / exposure restriction。当前 clean PR11H 结果为：Variant B base closed=198、total_net_R=94.815、PF=8.57；extreme_harsh total_net_R=55.215、PF=3.18；walk-forward 5/5 为正；Monte Carlo ruin-like=0；但 profile C 占 190/198、max_concurrent_positions=22、same_direction_overlap_count=558、portfolio_heat_max=0.11，因此不得直接进入 PR12。

PR11H-fix 必须先解释 profile concentration，再验证 exposure restriction。当前 clean PR11H-fix 结果显示：B/C fresh candidates 基本相当（B=2828，C=2824），不是 B profile 无机会；但 B formal approved 只有 13，C formal approved 为 404，集中主要来自 formal risk / quality gate 通过率差异，而不是 writer / join / execution mapping 丢失。Variant B unrestricted 为 closed=198、total_net_R=94.815、PF=8.57、max_concurrent_positions=22、same_direction_overlap_count=558、portfolio_heat_max=0.11；`portfolio_heat_cap_5pct` 后为 closed=183、total_net_R=85.070、PF=7.80、max_concurrent_positions=10、same_direction_overlap_count=303、portfolio_heat_max=0.05。该结果只能作为 PR12 候选输入；Session_HL、dynamic_time_cut 或 quality_aware_capped_sizing 不得脱离 Restricted Variant B 泛化为通用正式规则。

历史 PR12 曾将 Restricted Variant B 设为 formal research candidate；该结论已被后续 causal timestamp audit 与正确语义双轨复验推翻。`configs/strategies/liquidity_reversal.yaml` 当前为 `research_stopped`，历史 final baseline 只读保留，不得恢复为正式配置或实盘策略。

## 禁止事项

- 不自动修改正式配置。
- 不自动应用参数。
- 不绕过回测、样本量检查和成本检查。

## 参数研究沉淀

历史调参材料已归档。长期保留以下 proposal 判断规则：

- ToD/DoW RVOL、log-volume EWMA、结构止损、MAE/MFE、same-bar 悲观处理、walk-forward / overfit 检查等方向可以进入 proposal 或沙盒验证。
- 直接降低成本假设、提高风险暴露、绕过 RiskEngine、把 shadow cap 当正式 approval，均不得作为优化手段。
- Taker ratio、CVD/OI、订单簿等外部数据在未建立可靠本地历史数据源前，不得作为回测运行时动态依赖。
- 参数报告不能只看净利润，必须同时输出样本量、reject_reason、成本压力、MAE/MFE、exit reason 和 same-bar 审计。
