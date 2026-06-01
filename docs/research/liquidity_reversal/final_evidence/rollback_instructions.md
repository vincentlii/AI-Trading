# Rollback Instructions

## 触发条件

出现以下任一情况，回滚 PR12 formal config：

- final config regression failed。
- full-audit blocking issue。
- artifact validation failed。
- final config 与 `final_regression_baseline.json` 不一致。
- live/sim integration 发现 RiskEngine、fee、funding、margin、stop 或 target 被意外改变。

## 回滚方式

1. 停用 `configs/strategies/liquidity_reversal.yaml`。
2. 回退到 `configs/strategies/trend_price_volume_swap_proposal.toml` 作为研究配置参考。
3. 使用 Variant A Tier 1 only 作为 regression baseline 对照。
4. 保留 `storage/research_runs/liquidity_reversal/final/` 作为审计记录。
5. 重新运行 full-audit 与 final config regression。

## 不得做

- 不得用 unrestricted Variant B 替代。
- 不得启用 B profile 主配置。
- 不得绕过 `portfolio_heat_cap=0.05`。
