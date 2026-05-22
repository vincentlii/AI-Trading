---
type: process
status: active
updated: 2026-05-19
tags:
  - domain/backtest
  - domain/agent
---

# Proposal验证流程

结论：proposal 是建议，不是配置；未验证、未人工确认前不得进入确定性热路径。

## 流程

1. Agent 或人工生成 JSON proposal。
2. proposal 进入 `configs/proposals/`。
3. 通过 `trading_system.config.proposals` 校验允许字段。
4. 验证时只在内存中生成 proposed preset。
5. 复用 P4.4 回测路径对比 base/proposed。
6. 输出验证结果。
7. 人工确认后，才可能生成正式配置候选。

## 验证入口

```powershell
.\.venv\Scripts\python scripts\validate_p4_5_proposal.py --proposal configs\proposals\<proposal>.json
```

## 禁止事项

- 不自动修改正式配置。
- 不自动应用参数。
- 不绕过回测、样本量检查和成本检查。
