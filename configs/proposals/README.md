# 配置 Proposal 目录

本目录只存放 Agent 或人工复盘提出的配置修改建议。

- proposal 不会自动生效。
- proposal 不得修改正式配置、策略代码、风控代码或真实交易权限。
- 正式参数变更必须经过回测验证、人工确认，并作为新的配置版本进入 Git。
- proposal 应说明证据窗口、建议改动、预期影响、风险和需要重新验证的指标。

## P4.5 JSON 格式

P4.5 v1 使用 JSON 保存结构化参数建议。字段保持可审计，不作为正式 preset 读取。

最小示例：

```json
{
  "auto_apply": false,
  "base_config_fingerprint": "<current fingerprint>",
  "base_config_version": "btc_eth_p4_4_v1",
  "base_preset_path": "configs/presets/btc_eth_p4_4.toml",
  "changes": [
    {
      "path": "ranking.min_trades_for_primary",
      "before": 30,
      "after": 40,
      "reason": "Require a larger sample before treating a layer as primary."
    }
  ],
  "evidence": {
    "window": "manual_review"
  },
  "expected_impact": "C profile will more often be marked supporting_only.",
  "proposal_id": "p4_5_example_min_trades",
  "risks": [
    "May demote useful low-frequency samples."
  ],
  "source": "agent",
  "title": "Tighten minimum sample size",
  "validation_plan": [
    "Run P4.5 proposal validation before manual promotion."
  ]
}
```

当前允许的 `changes[].path` 只覆盖 `risk.*`、`costs.*`、`execution.*`、`scan.profile_keys`、`strategy.enabled`、`strategy.enabled_setups` 和 `ranking.*`。不允许修改 `include.*`、正式配置路径、策略代码或真实交易权限。

验证命令：

```powershell
.\.venv\Scripts\python scripts\validate_p4_5_proposal.py --proposal configs\proposals\<proposal>.json
```
