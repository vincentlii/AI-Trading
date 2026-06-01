# Merge Content Summary

## 结论

merge 到 master 后，应只表达一个正式策略结论：LR Restricted Variant B 成为当前 formalized research candidate，但 `live_trading_enabled=false`。

## Master 将包含

- Restricted Variant B 正式候选配置。
- `portfolio_heat_cap=0.05`。
- C profile formal scope。
- B profile diagnostic-only。
- Full Audit Gate。
- final regression baseline。
- final research memo。
- Research Pipeline 统一入口和 adapter/runner/report 基础设施。
- cleanup / legacy / rollback 规则。

## 正式候选

| 项目 | 状态 |
|---|---|
| Tier 1 + Positive Tier 2 | formalized candidate |
| Session_HL | 仅限 Restricted Variant B |
| dynamic_time_cut | 仅限 Restricted Variant B |
| quality_aware_capped_sizing | 仅限 Restricted Variant B |
| C profile | formal scope |
| B profile | diagnostic-only |

## 不会包含为正式策略

- unrestricted Variant B。
- Full original family。
- Tier 3。
- rolling_range 主配置。
- PDH/PDL active source。
- EQH/EQL active source。
- runner exit。
- partial TP。
- structure target。
- unexecuted proposal rows。

## 后续工作流

后续策略研究应走：

```powershell
python -m research_pipeline.cli.research full-audit --strategy <strategy> --artifact-dir <dir> --output-dir <dir>
python -m research_pipeline.cli.research lr-robustness-validation --artifact-dir <dir> --output-dir <dir>
python -m research_pipeline.cli.research lr-robustness-fix --artifact-dir <dir> --output-dir <dir>
```

未来可再统一为：

```powershell
python -m research_pipeline.cli.research run --strategy <strategy> --config <config> --mode full-research
python -m research_pipeline.cli.research robustness --strategy <strategy> --artifact-dir <dir>
```
