# PR12 Final Evidence Preparation + Commit Boundary Confirmation

## 1. Executive Summary

Primary Decision = A：final evidence 已准备好，commit boundary 清楚，可以等待人工确认后按 5 个 commit 顺序 staging / commit。

本阶段已完成：

- 创建 / 更新 `docs/research/liquidity_reversal/final_evidence/`。
- 从 `storage/research_runs/liquidity_reversal/final/` 复制 11 个指定小型 final evidence 文件。
- 未复制 `storage/backtest_cache/**`。
- 未复制 row-level `jsonl`。
- 未复制 Monte Carlo row-level output。
- 未复制 `full_audit/*.jsonl`。
- 未复制 old PR11A-PR11H 过程 artifacts。
- 未执行 `git add`。
- 未 commit / merge / tag。

仍需人工确认：

- Commit 1 / 2 / 3 的 execution / config / strategy semantic diff 是否按 split commit plan 分拆提交。
- final evidence 是否按 docs 路径纳入 Commit 5。

## 2. Final Evidence Directory Status

目标目录：

- `docs/research/liquidity_reversal/final_evidence/`

来源目录：

- `storage/research_runs/liquidity_reversal/final/`

复制结果：

| File | Status | Bytes |
|---|---:|---:|
| `artifact_index.json` | copied | 6492 |
| `cleanup_manifest.md` | copied | 995 |
| `final_full_audit_report.md` | copied | 735 |
| `final_regression_baseline.json` | copied | 3130 |
| `final_robustness_summary.md` | copied | 888 |
| `final_test_results.md` | copied | 1801 |
| `legacy_migration_manifest.md` | copied | 1095 |
| `merge_readiness_report.md` | copied | 1011 |
| `proposal_to_formal_decision_log.md` | copied | 2282 |
| `research_run_registry.json` | copied | 1138 |
| `rollback_instructions.md` | copied | 893 |

Missing files:

- None.

## 3. Forbidden Artifact Check

已检查 `docs/research/liquidity_reversal/final_evidence/`。

未发现：

- `.jsonl`
- `.csv`
- `storage/backtest_cache/**`
- Monte Carlo row-level output
- old PR11A-PR11H row-level artifacts
- broken lineage artifacts
- old proposal/debug rows

说明：

- `final_full_audit_report.md` 是允许纳入的小型 final audit report。
- 禁止项是 `full_audit/*.jsonl` 和 row-level 明细，不是 final audit markdown summary。

## 4. Commit 1 Confirmation Checklist

Commit 1: `Execution lineage / audited replay support`

待人工确认项：

- [ ] RiskEngine 未放宽。
- [ ] fee / funding / margin / notional cap 未放宽。
- [ ] same-bar 仍保持 conservative / pessimistic。
- [ ] `spread_slippage_rate` 是额外成本建模，不是降低成本。
- [ ] time-cut 只在 validated proposal / diagnostics replay 中使用。
- [ ] live path 不受影响。
- [ ] `trade_id` / `execution_id` 是 execution lineage 支持，不是后置伪造。
- [ ] `candidate_id` / `event_id` lineage 可追溯。

建议包含：

- `trading_system/backtest/execution.py`
- `tests/test_backtest_execution.py`

确认后建议运行：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_backtest_execution -v
git diff --cached --check
```

## 5. Commit 2 Confirmation Checklist

Commit 2: `Research / proposal config schema`

待人工确认项：

- [ ] 只是扩展 research/proposal config surface。
- [ ] proposal 不能绕过 full-audit。
- [ ] proposal 不能绕过 regression。
- [ ] proposal 不能绕过 human approval。
- [ ] proposal approval 不等于 formal approval。
- [ ] 不自动放宽正式风控。
- [ ] cost tier / funding mode 只用于 research/proposal cost stress。
- [ ] strategy profile / parameter grid / volume config 不自动进入 live/formal path。

建议包含：

- `trading_system/config/__init__.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`
- `configs/assets/btc_eth_swap.toml`
- `configs/costs/crypto_swap_research.toml`
- `configs/presets/btc_eth_swap_proposal.toml`
- `configs/strategies/trend_price_volume_swap_proposal.toml`
- `tests/test_config_loader.py`

确认后建议运行：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_config_loader -v
git diff --cached --check
```

## 6. Commit 3 Confirmation Checklist

Commit 3: `Strategy feature support for validated LR research`

待人工确认项：

- [ ] confirmed candle / no-lookahead 是修复，不是信号放宽。
- [ ] `structure_extreme_buffer` 属于 clean rebuild 已验证支持。
- [ ] asset-specific LR parameters 属于 clean rebuild 已验证支持。
- [ ] TOD/DOW volume baseline 属于 clean rebuild 已验证支持。
- [ ] 未默认启用 PDH/PDL。
- [ ] 未默认启用 EQH/EQL。
- [ ] 未正式化 rolling_range。
- [ ] 未正式化 runner。
- [ ] 未正式化 partial TP。
- [ ] 未正式化 structure target。
- [ ] `live_trading_enabled=false` 保持。
- [ ] context features 传入 setup detection 不会启用未验证 expansion。

建议包含：

- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
- `trading_system/strategies/trend_price_volume_v1/candidates.py`，仅在确认属于 validated LR research support 后纳入。
- `tests/test_trend_price_volume_features.py`

确认后建议运行：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_trend_price_volume_features -v
git diff --cached --check
```

## 7. Staging Readiness

Final evidence readiness:

- Ready.
- 11 / 11 指定文件已复制到 docs 路径。
- Missing = none。

Commit boundary readiness:

- Commit 1 边界清楚，但需人工确认 execution semantic 风险。
- Commit 2 边界清楚，但需人工确认 proposal config boundary。
- Commit 3 边界清楚，但需人工确认 strategy feature semantic 风险。
- Commit 4 边界清楚，注意排除 `__pycache__` / `.pyc`。
- Commit 5 边界清楚，现在 final evidence 已准备好。

仍存在的人工确认问题：

- `trading_system/strategies/trend_price_volume_v1/candidates.py` 是否纳入 Commit 3。
- `trading_system/backtest/contract_risk.py`、`layered_cache.py`、`layered_pipeline.py` 是否全部属于 Commit 4 框架能力。
- `trading_system/data/download.py`、`trading_system/data/history.py`、`scripts/check_data_quality.py`、`scripts/download_okx_history.py` 是否与 PR12 直接相关；否则不应纳入本轮 commit。
- optional docs 是否纳入 Commit 5，需人工确认。

## 8. Safety Boundary Confirmation

当前确认：

- final config = Restricted Variant B。
- `portfolio_heat_cap=0.05`。
- C profile formal scope。
- B profile diagnostic-only。
- `live_trading_enabled=false`。
- unrestricted Variant B 未正式化。
- Full original family 未正式化。
- Tier 3 未正式化。
- rolling_range 未正式化。
- PDH/PDL 未正式化。
- EQH/EQL 未正式化。
- runner 未正式化。
- partial TP 未正式化。
- structure target 未正式化。
- unexecuted proposal rows 不进入 performance。
- proposal / diagnostic / summary rows 不进入 performance。

未做事项：

- 未执行 staging。
- 未 commit。
- 未 merge。
- 未 tag。
- 未删除文件。
- 未继续调参。
- 未开始 trend_continuation。

## 9. Next Step

Next Step:

- 人工确认 Commit 1 / 2 / 3 checklist。
- 人工确认 `candidates.py`、contract risk / layered pipeline、data/download 相关文件归属。
- 确认后按 `split_commit_plan.md` 的 5 个 commit 顺序 staging / commit。

禁止推荐 merge / tag。
