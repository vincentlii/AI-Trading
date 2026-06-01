# Liquidity Reversal Final Research Memo

## 结论

本轮 LR 研究正式化对象为 Restricted Variant B：Tier 1 + Positive Tier 2，并强制 `portfolio_heat_cap_5pct`。正式适用范围限定为 C profile；B profile 保留 diagnostic-only。

本 memo 只以 clean rebuild、full-audit、PR11H robustness、PR11H-fix exposure restriction 的结果为准。旧 PR11C-PR11G artifacts 仅作历史参考。

## 最终组合

| 项目 | 正式状态 |
|---|---|
| Session_HL + attempt_4 displacement + fixed_2R_time_cut + current risk sizing | Tier 1 |
| recent_swing + attempt_4 displacement + dynamic_time_cut + quality-aware capped sizing | Tier 1 |
| Session_HL + attempt_3 CHOCH/MSS + dynamic_time_cut + quality-aware capped sizing | Positive Tier 2 |
| portfolio_heat_cap_5pct | 必需正式限制 |
| C profile | 正式适用范围 |
| B profile | diagnostic-only |

## 关键指标

| 方案 | closed | total_R | net_R avg | PF | max concurrent | same-direction overlap | heat |
|---|---:|---:|---:|---:|---:|---:|---:|
| Restricted Variant B | 183 | 85.070 | 0.465 | 7.80 | 10 | 303 | 0.05 |
| Variant B unrestricted | 198 | 94.815 | 0.479 | 8.57 | 22 | 558 | 0.11 |
| Variant A Tier 1 only | 131 | 73.222 | 0.559 | 17.62 | 21 | 370 | 0.105 |

Restricted Variant B 比 unrestricted 牺牲部分 total_R，但显著降低 portfolio heat 与并发风险，因此是 PR12 的正式候选。

## 阶段结论

| 方向 | 结论 |
|---|---|
| Attempt | attempt_4 displacement 是主 setup；attempt_3 CHOCH/MSS 是覆盖型补充 |
| Structure | Session_HL 进入 Restricted Variant B；PDH/PDL 与 EQH/EQL 保留 diagnostic |
| Exit | dynamic_time_cut 只在 Restricted Variant B 内正式化；fixed_2R_time_cut 保留 baseline |
| Sizing | quality-aware capped sizing 只在 Restricted Variant B 内正式化；B profile 不进入主配置 |
| Combined | Tier 1 + positive Tier 2 有组合价值，但必须加 `portfolio_heat_cap=0.05` |

## Profile 结论

B profile 不是没有候选：B fresh candidates 为 2828，C 为 2824。集中原因是 formal approval 差异：B formal approved 为 13，C 为 404。未发现 B profile writer / join / execution mapping 丢失。

因此 B profile 暂不进入正式主配置，只保留 diagnostic-only。后续若要启用 B profile，必须单独修复 approval bottleneck 并重跑 full-audit 与 robustness。

## 保留 Diagnostic / Backlog

- B profile enablement。
- PDH/PDL active source。
- EQH/EQL active source。
- rolling_range 组合。
- runner / partial TP / structure target exit。
- Tier 3 fallback family。
- trend_continuation 未来研究。

## 风险限制

- 不得使用 unrestricted Variant B。
- 不得使用 Full original family。
- 不得把 proposal / diagnostic / summary rows 纳入 performance。
- performance 必须来自 `row_type=closed_trade`。
- `portfolio_heat_cap=0.05` 是正式候选的一部分，不是可选优化。

## 复现

```powershell
.\.venv\Scripts\python.exe -m research_pipeline.cli.research full-audit --strategy liquidity_reversal --artifact-dir storage\backtest_cache\pr11g_clean_rebuild\lr_combined_fix --output-dir storage\research_runs\liquidity_reversal\final\full_audit
.\.venv\Scripts\python.exe -m research_pipeline.cli.research lr-robustness-fix --artifact-dir storage\backtest_cache\pr11g_clean_rebuild\lr_combined_fix --output-dir storage\backtest_cache\pr11h_fix --monte-carlo-seeds 1000
.\.venv\Scripts\python.exe -B -m unittest tests.test_liquidity_reversal_final_config -v
```
