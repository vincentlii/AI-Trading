---
type: mcp-plan
status: draft
updated: 2026-05-19
tags:
  - rag/summary
---

# MCP接入候选

结论：MCP/Hermes 接入应先服务只读检索、报告生成和 proposal 流程，不应直接控制交易。

## 候选能力

| 能力 | 阶段 | 权限 |
| --- | --- | --- |
| Vault 检索 | P6 | 只读 |
| 回测报告读取 | P6 | 只读 |
| 模拟盘日志读取 | P6 | 只读 |
| proposal 生成 | P6/P7 | 写入 `configs/proposals/`，需审批 |
| 日报/周报生成 | P8 | 写报告，不改热路径 |
| 异常提醒 | P8 | 只提醒，不下单 |

## 禁止

- 直接下单。
- 自动应用参数。
- 修改正式配置。
- 读取或保存 API secret。
