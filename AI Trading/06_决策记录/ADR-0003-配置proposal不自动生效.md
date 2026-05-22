---
type: adr
adr: 0003
status: accepted
date: 2026-05-19
tags:
  - decision/adr
---

# ADR-0003-配置proposal不自动生效

## 结论

参数 proposal 只作为建议文件存在，不自动修改正式配置，不自动影响策略执行。

## 背景

参数直接影响回测结果、模拟盘表现和未来实盘风险。自动应用参数会破坏审计、复现和回滚能力。

## 决策

- proposal 存入 `configs/proposals/`。
- 验证时只在内存中应用 patch。
- 必须经过回测、成本检查、样本量检查和人工确认。

## 后果

- 保持配置可审计。
- 增加参数变更流程成本，但降低隐性风险。
