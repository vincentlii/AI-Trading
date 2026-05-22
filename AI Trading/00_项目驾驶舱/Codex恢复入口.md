---
type: recovery
status: current
updated: 2026-05-22
tags:
  - agent/recovery
  - status/current
---

# Codex恢复入口

结论：接手本项目时先读 Obsidian 权威页；根目录文档只做薄入口，不再作为长期事实正文。

## 5 分钟恢复路径

1. 读 [[项目驾驶舱]]，确认当前阶段、权威源和禁止事项。
2. 读 [[当前阶段-P6]]，确认 P6 前置审查/补齐口径。
3. 读 [[待补齐清单]]，确认立即补齐、模拟盘前必须补齐和后续增强项。
4. 读 [[策略规格]] 与 [[trend_price_volume_v1]]，确认当前策略边界。
5. 读 [[开发约定]]、[[测试与验证命令]]、[[Agent协作总览]]，确认协作和验证规则。

## 当前项目一句话

本项目是面向 BTC/USDT、ETH/USDT、XAUT/USDT 的量化交易研究、回测、模拟盘和复盘系统；当前处于 P6 前置审查/补齐阶段，正式模拟盘暂缓。

## 热路径

```text
MarketRegime -> PriceActionSetup -> VolumePriceConfirmation -> RiskDecision -> SimulatedOrder -> PositionState
```

## 硬约束

- 不接入未经人工审批的真实资金自动下单。
- 不在聊天、Vault 或仓库中保存 API key、secret key、passphrase。
- Agent 只做解释、复盘、红队审查和 proposal，不直接改正式参数，不生成真实订单。
- 正式配置进入 Git；参数建议进入 `configs/proposals/`，经回测和人工确认后才可落地。
- 不混合不同交易所 K 线生成综合成交价格。
- 不使用 `1m` 作为主策略周期。

## 验证命令

详见 [[测试与验证命令]]。

文档类小任务至少运行：

```powershell
git diff --check
```

## 根目录薄入口

- `README.md`
- `项目总规划.md`
- `策略规格.md`
- `代理协作流程.md`
- `开发记录.md`

这些文件只用于恢复入口和命令索引；长期事实以 `AI Trading/` vault 为准。
