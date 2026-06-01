# PR12 High-Risk Diff Triage Report

## 1. Executive Summary

当前不建议直接进入 staging。

Go / No-Go Decision = B：部分 diff 需要拆分 commit。

主要判断：

- `trading_system/backtest/scanner.py` 基本是 reporting / grouping diagnostics，可纳入主包。
- `trading_system/backtest/execution.py` 是 PR11G-QA / clean rebuild / full-audit 的关键修复，但同时引入 execution identity、time-cut、MFE/MAE、spread slippage 等执行语义扩展，应单独提交并显式说明。
- `trading_system/config/loader.py` 与 `trading_system/config/proposals.py` 扩展了 research/proposal config surface，不是纯 lineage，应单独提交。
- `trading_system/strategies/trend_price_volume_v1/features.py` 与 `strategy.py` 包含 confirmed candle / no-lookahead 修复，也包含 liquidity reversal invalidation、volume baseline、asset-specific parameters 等策略语义变更，应单独提交。
- 相关 tests 已覆盖关键行为，但这些 tests 证明“当前实现可运行”，不等于这些语义变更可以无说明混入 finalization commit。

已验证：

- 当前分支：`codex/proposal-diagnostics`。
- 未执行 staging、commit、merge、tag。
- 目标测试通过：`python -B -m unittest tests.test_backtest_execution tests.test_config_loader tests.test_trend_price_volume_features -v`，共 46 tests OK。

需要人工确认项：

- `execution.py` 中 time-cut 与 spread slippage 是否只作为已验证 Restricted Variant B / diagnostics 使用。
- `config/proposals.py` 扩大的 proposal change paths 是否仍受 human approval、full-audit、regression gate 约束。
- `features.py` 的 invalidation / target / volume baseline / asset-specific parameters 是否确认为 clean rebuild 已验证范围，不作为未授权默认策略放宽。
- live path 是否不会因这些 strategy/config 扩展自动启用 proposal-only 行为。

## 2. File-by-file Diff Triage

### 2.1 `trading_system/backtest/execution.py`

Decision: C. Split into separate commit.

Risk level: High.

修改目的：

- 为 execution / closed trade 增加 `trade_id`、`execution_id`、`candidate_id`、`event_id`。
- 将 candidate/event lineage 传入 fill result。
- 增加 MAE/MFE、R path、same-bar、forced pessimistic exit、entry/exit same bar 等 audit diagnostics。
- 增加 `spread_slippage_rate` 成本项。
- 增加 liquidity reversal `reversal_time_cut_bars` / `reversal_time_cut_min_mfe_r` time-cut exit。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。execution identity、closed_trade lineage、same-bar audit、MFE/MAE recompute 都是 full-audit gate 必需能力。
- 但 time-cut 和 spread slippage 已超出纯 lineage，属于 execution / cost semantics 扩展。

边界判断：

- 是否影响 RiskEngine：未看到直接修改 RiskEngine；risk approval 仍通过原 `RiskDecision` / approved order。
- 是否影响 fee / funding / margin / notional cap：未看到 margin / notional cap 放宽；fee/funding 未降低。新增 `spread_slippage_rate` 会增加 slippage cost，默认值为 `0.0`，属于更细成本模型，不是成本降低。
- 是否影响 stop / target / exit：影响 exit。新增 LR time-cut exit，默认 `reversal_time_cut_bars=0` 时关闭，但在 proposal config 中可启用。
- 是否影响 same-bar / slippage / liquidation 假设：same-bar 仍保留 conservative stop-first，并新增 `forced_pessimistic_exit` 标记；未看到 same-bar 放宽。slippage新增项是加法，不是降低。未看到 liquidation 放宽。
- 是否影响 live trading path：文件属于 backtest execution。未看到 live order path 修改，但如果 live path复用该 backtest config，需要人工确认不会启用。
- 是否改变策略信号语义：不改变 entry signal 生成；但会改变被启用时的 exit/cost replay 结果。

Test coverage:

- `test_fill_has_execution_identity_from_candidate_context`
- `test_same_bar_target_and_stop_uses_conservative_stop_first`
- `test_liquidity_reversal_time_cut_exits_when_early_mfe_is_too_low`
- `test_liquidity_reversal_time_cut_does_not_override_stop_first`
- `test_excursion_diagnostics_record_mae_mfe_and_r_path_for_long_and_short`
- 目标测试已通过。

Recommended action:

- 单独提交为 `execution lineage and audited replay diagnostics`。
- 提交说明必须写明：RiskEngine 未改、same-bar 仍 pessimistic、spread slippage 不降低成本、time-cut 只在已验证 proposal config 中启用。

### 2.2 `trading_system/backtest/scanner.py`

Decision: A. Safe to include.

Risk level: Low.

修改目的：

- 在 group summary 中加入 direction、inst_type、inst_id、contract mode、long/short count、long/short expectancy。
- 增强 SWAP / long-short / asset grouping diagnostics。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。用于分组诊断、profile/asset/direction 风险审查和 merge review。

边界判断：

- 是否影响 RiskEngine：否。
- 是否影响 fee / funding / margin / notional cap：否。
- 是否影响 stop / target / exit：否。
- 是否影响 same-bar / slippage / liquidation 假设：否。
- 是否影响 live trading path：否，scanner/reporting 层。
- 是否改变策略信号语义：否。

Test coverage:

- 相关 backtest scanner tests 未在本轮最小测试中单独重跑。
- 该 diff 为 summary/grouping 层，风险较低。

Recommended action:

- 可随 research pipeline / reporting commit 纳入。

### 2.3 `trading_system/config/loader.py`

Decision: C. Split into separate commit.

Risk level: High.

修改目的：

- 增加 SWAP contract metadata：`contract_mode`、`allow_short`。
- 增加 cost tier schema：`spread_slippage_rate`、`funding_mode`、`cost_model_tiers`。
- 增加 execution proposal 参数：invalidation mode/buffer、time-cut candidates、breakeven threshold。
- 增加 strategy parameters、parameter grid、profile status、volume config。
- 将新增字段映射到 backtest execution config。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。clean rebuild、cost stress、dynamic_time_cut、quality-aware proposal、profile scope、volume baseline 都依赖这些配置字段。
- 但这是 config schema 扩展，不是纯审计 lineage。

边界判断：

- 是否影响 RiskEngine：未直接修改 RiskEngine。
- 是否影响 fee / funding / margin / notional cap：影响 cost config surface。新增字段本身不降低成本，且校验 non-negative；但允许配置更多成本层，需要 human approval 和 regression gate。
- 是否影响 stop / target / exit：影响。`invalidation_mode`、`invalidation_buffer_atr`、`reversal_time_cut_*` 会影响 stop/exit proposal when configured。
- 是否影响 same-bar / slippage / liquidation 假设：可能影响 slippage modeling；未看到 same-bar/liquidation 放宽。
- 是否影响 live trading path：如果 live config loader 共用，存在潜在影响；当前 final config `live_trading_enabled=false`，仍需人工确认 live path 不读取并启用这些 proposal fields。
- 是否改变策略信号语义：间接改变，通过 strategy parameters / volume / profile status。

Test coverage:

- `test_loads_swap_proposal_preset_with_bc_primary_profiles_and_contract_metadata`
- 目标测试已通过。

Recommended action:

- 单独提交为 `research config schema for swap proposal and audit gates`。
- 提交说明必须写明：新增字段只扩展 research/proposal 配置面，不自动绕过 full-audit / regression / human approval。

### 2.4 `trading_system/config/proposals.py`

Decision: C. Split into separate commit.

Risk level: High.

修改目的：

- 扩展 allowed proposal change paths，允许 proposal 修改 cost tiers、funding mode、execution invalidation/time-cut candidates、strategy parameters/profile/volume。
- 增加 `CostTierConfig` tuple normalization。
- 增加新增 cost fields 的 non-negative validation。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。PR11E/11F/11G 的 proposal-only exit/sizing/cost tiers 需要这类 proposal config surface。
- 但它扩大了 proposal 可修改范围，必须单独 review。

边界判断：

- 是否影响 RiskEngine：未直接修改 RiskEngine。
- 是否影响 fee / funding / margin / notional cap：允许 proposal 改 cost fields，但仍有 non-negative 与 fee upper bound validation；不等于自动降低成本。
- 是否影响 stop / target / exit：允许 proposal 改 execution invalidation/time-cut candidates，属于策略研究配置面扩展。
- 是否影响 same-bar / slippage / liquidation 假设：可影响 slippage tier；未看到 same-bar/liquidation 放宽。
- 是否影响 live trading path：取决于 proposal application path。必须确认 proposal 不会自动进入 live/formal config。
- 是否改变策略信号语义：间接可能改变，需要 gate。

Test coverage:

- `tests/test_config_loader.py` 覆盖 cost tiers 加载。
- proposal-specific tests 未在本轮最小测试中重跑。

Recommended action:

- 单独提交。
- 提交说明必须写明：proposal 可以入队，但不能绕过 full-audit、regression、human approval；proposal approval 不等于 formal approval。

### 2.5 `trading_system/strategies/trend_price_volume_v1/features.py`

Decision: C. Split into separate commit.

Risk level: High.

修改目的：

- 将 `context_features` 传入 setup detection。
- 强化 confirmed candle 使用路径。
- 增加 TOD/DOW log EWMA volume baseline 与 fallback evidence。
- 增加 asset-specific liquidity reversal parameters。
- 增加 `reclaim_rvol_max`、CHOCH requirement flags、invalidation mode/buffer。
- 将 liquidity reversal invalidation 从 fixed ATR buffer 扩展为 `structure_extreme_buffer` mode。
- 在 evidence 中输出 reclaim、structure、volume baseline 等诊断字段。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 部分是。confirmed candle、volume baseline evidence、structure_extreme_buffer、asset-specific LR parameters 是 clean rebuild 的研究配置和 no-lookahead 诊断基础。
- 但该文件直接影响策略信号与 stop/target 语义，不能归入纯 diagnostics。

边界判断：

- 是否影响 RiskEngine：否。
- 是否影响 fee / funding / margin / notional cap：否。
- 是否影响 stop / target / exit：影响 stop/target。`_invalidation_level` 会改变 LR invalidation 与 target distance when configured。
- 是否影响 same-bar / slippage / liquidation 假设：否。
- 是否影响 live trading path：可能影响 strategy signal path；虽然 final config live disabled，但该模块可能被 live strategy import。
- 是否改变策略信号语义：是。volume baseline、asset-specific parameters、reclaim RVOL、invalidation mode 都可能改变 signal acceptance or setup fields when configured。

Test coverage:

- `test_strategy_parameters_resolve_asset_specific_liquidity_overrides`
- `test_structure_extreme_buffer_invalidation_uses_sweep_extreme_plus_small_atr_buffer`
- `test_tod_dow_log_ewma_rvol_uses_prior_bucket_only_and_reports_fallback`
- `test_tod_dow_log_ewma_rvol_falls_back_when_bucket_is_too_small`
- existing confirmed candle and LR detection tests。
- 目标测试已通过。

Recommended action:

- 单独提交为 `liquidity reversal confirmed-feature and proposal parameter support`。
- 需要明确写入 commit / PR notes：默认 `invalidation_mode="atr_buffer"` 保留旧默认；`structure_extreme_buffer` 只由 validated config 启用；未启用 PDH/PDL、EQH/EQL、rolling_range 主路径。

### 2.6 `trading_system/strategies/trend_price_volume_v1/strategy.py`

Decision: C. Split into separate commit.

Risk level: Medium.

修改目的：

- 将 `context.features` 传入 `detect_price_action_setup`，使 strategy parameters、volume baseline、asset/profile context 可用于 setup detection。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。否则 loader 中的 strategy parameters / volume config 无法到达 feature detection。

边界判断：

- 是否影响 RiskEngine：否。
- 是否影响 fee / funding / margin / notional cap：否。
- 是否影响 stop / target / exit：间接影响，因为 context-driven params 可改变 invalidation/time/volume 相关 setup behavior。
- 是否影响 same-bar / slippage / liquidation 假设：否。
- 是否影响 live trading path：可能影响 live strategy path if enabled；当前 `live_trading_enabled=false`，但仍应单独说明。
- 是否改变策略信号语义：是，context-driven setup detection 会改变策略语义 when context contains new params。

Test coverage:

- `tests/test_trend_price_volume_features.py` 覆盖 features 层。
- strategy wrapper 层未在本轮最小测试中单独证明 live path 不受影响。

Recommended action:

- 与 `features.py` 放在同一个单独 commit。
- 不应混入 purely audit/reporting commit。

### 2.7 `tests/test_backtest_execution.py`

Decision: B. Include but needs explicit note.

Risk level: Low.

修改目的：

- 覆盖 execution identity、same-bar pessimistic diagnostics、LR time-cut、MFE/MAE/R path diagnostics。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。

边界判断：

- 不修改生产逻辑。
- 测试覆盖的是 `execution.py` 中高风险行为。

Test coverage:

- 本轮已重跑，通过。

Recommended action:

- 与 `execution.py` 的单独 commit 一起提交。

### 2.8 `tests/test_config_loader.py`

Decision: B. Include but needs explicit note.

Risk level: Low.

修改目的：

- 覆盖 SWAP proposal preset、B/C profiles、contract metadata、cost tiers、invalidation buffer、volume settings。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。

边界判断：

- 不修改生产逻辑。
- 覆盖 config schema 扩展。

Test coverage:

- 本轮已重跑，通过。

Recommended action:

- 与 config schema / proposal config commit 一起提交。

### 2.9 `tests/test_trend_price_volume_features.py`

Decision: B. Include but needs explicit note.

Risk level: Low.

修改目的：

- 覆盖 asset-specific LR parameters。
- 覆盖 `structure_extreme_buffer` invalidation。
- 覆盖 TOD/DOW log EWMA volume baseline 与 fallback。
- 继续覆盖 confirmed candle behavior。

是否 PR11G-QA / clean rebuild / full-audit 所需：

- 是。

边界判断：

- 不修改生产逻辑。
- 覆盖 strategy feature 语义变化。

Test coverage:

- 本轮已重跑，通过。

Recommended action:

- 与 `features.py` / `strategy.py` 的单独 commit 一起提交。

## 3. Safety Boundary Result

当前审查结论：safety boundary 没有发现明确失败，但需要按拆分提交保留审计线索。

逐项确认：

- RiskEngine 未放宽：未看到 `RiskEngine` 或 risk approval 逻辑被直接放宽。
- fee / funding / margin / notional cap 未放宽：未看到 fee/funding 降低或 margin/notional cap 放宽。新增 `spread_slippage_rate` 是额外 slippage 成本项，默认 `0.0`。
- stop / target / exit 未未授权修改：存在 stop/target/exit 语义扩展。它们来自 clean rebuild 所需 proposal support，但必须单独提交并说明，不应无说明混入 finalization commit。
- same-bar / slippage / liquidation 未放宽：same-bar 仍 conservative stop-first，并新增 forced pessimistic audit 字段；未看到 liquidation 放宽。
- live path 未启用：final config `live_trading_enabled=false`。但 `features.py` / `strategy.py` 是策略路径代码，仍需人工确认 live runtime 不读取并启用 proposal-only params。
- final config 仍等于 Restricted Variant B：`configs/strategies/liquidity_reversal.yaml` 当前为 `config_version: pr12_final_restricted_variant_b`，`profile_scope: C_only`，`portfolio_heat_cap: 0.05`，B profile diagnostic-only。
- proposal / diagnostic / summary rows 不进入 performance：依赖 full-audit gate 与 clean rebuild artifacts；本轮未发现反向 diff。

## 4. Staging Recommendation

### Safe to stage now

- `trading_system/backtest/scanner.py`
- `research_pipeline/` audit/reporting/registry/robustness code
- final memo / merge preparation docs
- final LR config and backlog docs, after final evidence path is chosen

### Stage only after human confirmation

- `trading_system/backtest/execution.py`
- `tests/test_backtest_execution.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`
- `tests/test_config_loader.py`
- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`
- `tests/test_trend_price_volume_features.py`

### Split to separate commit

Recommended split:

1. `execution lineage and audited replay diagnostics`
   - `trading_system/backtest/execution.py`
   - `tests/test_backtest_execution.py`

2. `research proposal config schema`
   - `trading_system/config/loader.py`
   - `trading_system/config/proposals.py`
   - `tests/test_config_loader.py`

3. `liquidity reversal confirmed feature and proposal params`
   - `trading_system/strategies/trend_price_volume_v1/features.py`
   - `trading_system/strategies/trend_price_volume_v1/strategy.py`
   - `tests/test_trend_price_volume_features.py`

4. `research reporting and scanner diagnostics`
   - `trading_system/backtest/scanner.py`
   - relevant report / scanner tests if applicable

5. `PR12 final formalization evidence`
   - final config
   - final memo
   - final evidence
   - final regression / audit / robustness docs

### Do not stage

- `.obsidian/workspace.json`
- `AI Trading/.obsidian/plugins/**`
- `AI Trading/.claudian/**`
- `AI Trading/99_归档/**`
- `storage/backtest_cache/**`
- old PR11A-PR11H row-level artifacts
- broken lineage artifacts
- old proposal/debug rows
- obsolete reports
- temporary `jsonl` / `csv` / `md`
- `__pycache__/`
- `.pyc`

## 5. Final Evidence Recommendation

推荐采用 docs final evidence 方案。

Preferred:

- 将小型 final evidence 复制到 `docs/research/liquidity_reversal/final_evidence/` 后提交。

原因：

- `storage/` 被 `.gitignore` 忽略，直接从 storage 纳入需要 force-add，误操作风险高。
- docs 路径更适合 code review 和长期追溯。
- 可以明确只提交小型 evidence，不携带 row-level artifacts。

不建议：

- 直接 force-add `storage/`。

禁止纳入：

- `storage/backtest_cache/**`
- row-level `jsonl` 大文件
- Monte Carlo row-level output
- `full_audit/*.jsonl`
- 临时过程 artifacts

备选：

- 如必须保留原 storage 路径，只能精确 force-add 小型 final 文件，不能 force-add 目录。

## 6. Go / No-Go Decision

Primary Decision = B：部分 diff 需要拆分 commit。

理由：

- 高风险 diff 多数可以解释为 clean rebuild / full-audit / robustness 所需，但它们不是同一类改动。
- `execution.py`、config schema、strategy features 都可能影响 research replay 或 strategy semantics，应拆分提交以便 review。
- 目标测试已通过，但不能替代人工确认 proposal boundary 和 live path isolation。

Next Step:

- 继续 PR12 cleanup / diff review。
- 人工确认拆分 commit 方案。
- 确认 final evidence 复制到 docs 还是精确 force-add 小型 storage final files。
- 确认后再按白名单 staging。

禁止推荐 merge / tag。
