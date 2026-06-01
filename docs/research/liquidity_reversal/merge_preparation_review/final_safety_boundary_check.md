# Final Safety Boundary Check

## 结论

正式配置边界通过；但 merge 前必须人工复核 backtest/execution 相关 diff，确认它们属于已验证的 lineage / audit / research pipeline 支持，而不是未授权的策略参数放宽。

## 已确认通过

- `configs/strategies/liquidity_reversal.yaml` 只正式化 Restricted Variant B。
- `portfolio_heat_cap=0.05` 已写入正式候选配置。
- `profile_scope=C_only`。
- `diagnostic_profiles=[B]`。
- `live_trading_enabled=false`。
- unrestricted Variant B 未正式化。
- Full original family 未正式化。
- Tier 3 未正式化。
- PDH/PDL、EQH/EQL、rolling_range、runner、partial TP、structure target 均未进入正式主配置。
- final config regression passed。
- strategy regression check passed。
- full-audit passed。
- artifact validation passed。
- research_pipeline tests passed。

## 需要人工确认的 diff 区域

当前 tracked diff 包含：

- `trading_system/backtest/execution.py`
- `trading_system/backtest/scanner.py`
- `trading_system/config/loader.py`
- `trading_system/config/proposals.py`
- `trading_system/strategies/trend_price_volume_v1/features.py`
- `trading_system/strategies/trend_price_volume_v1/strategy.py`

其中 `trading_system/backtest/execution.py` 包含 execution identity、same-bar、MFE/MAE、time-cut、slippage diagnostics 等支持性改动。它们可能属于 PR11G-QA-fix / clean rebuild 所需，但 merge 前必须确认不是 RiskEngine 或成本模型放宽。

## RiskEngine / 成本 / 出场边界

当前 review 未发现 final LR config 放宽：

- RiskEngine。
- fee。
- funding。
- margin。
- notional cap。
- stop。
- target。

但因为工作区存在 execution/backtest 模块改动，不能用自动状态直接声明“整个分支没有执行层改动”。必须人工 review 这些 diff 后再 merge。

## Performance Row Boundary

已通过 full-audit：

- performance 只来自 `row_type=closed_trade`。
- proposal / diagnostic / summary rows excluded from performance。
- trade_id / execution_id lineage intact。
- no-lookahead lineage verifiable with accepted warnings。

## Blocking Merge Safety Items

- 不得 stage `.obsidian` plugin。
- 不得 stage `.claudian` local config。
- 不得 stage `storage/backtest_cache/**`。
- 不得 stage old PR11A-PR11H row-level artifacts。
- 不得 stage unrestricted Variant B as formal config。
