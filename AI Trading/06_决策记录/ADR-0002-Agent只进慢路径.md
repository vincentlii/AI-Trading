---
type: adr
adr: 0002
status: accepted
date: 2026-05-19
tags:
  - decision/adr
  - domain/agent
---

# ADR-0002-Agent只进慢路径

## 结论

Agent 只进入解释、复盘、红队审查、日报周报和 proposal，不进入买卖决策热路径。

## 背景

交易热路径必须确定性、可测试、可审计。LLM 输出存在不确定性，不适合作为直接交易决策来源。

## 决策

- System 1 执行确定性策略、风控和模拟盘。
- System 2 Agent 仅读取结构化日志和报告。
- Agent 生成的参数建议必须进入 proposal 队列。

## 后果

- 热路径可测试、可复现。
- Agent 价值集中在解释和优化建议。
