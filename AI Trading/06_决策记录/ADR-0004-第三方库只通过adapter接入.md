---
type: adr
status: accepted
updated: 2026-05-20
tags:
  - decision/adr
  - domain/integration
---

# ADR-0004-第三方库只通过adapter接入

## 结论

第三方库只能通过 adapter、wrapper、报告层或研究工具层接入，不得污染策略、风控、撮合、持仓、交易日志、复盘日志和 proposal 审批主链路。

## 背景

项目已经形成 P4 回测、P5 看板和 P6 模拟盘边界。通用能力可以复用成熟库，但策略语义、风控口径和无前瞻撮合是核心资产，不能被外部框架替代。

## 选项

| 选项 | 优点 | 缺点 |
| --- | --- | --- |
| 全部自研 | 边界最清楚 | 看板、报告、基础指标会重复造轮子 |
| 引入完整交易框架 | 现成能力多 | 会冲击现有核心链路和权限边界 |
| 第三方库只通过 adapter 接入 | 复用通用能力，同时保留核心模型 | 需要维护边界文档和测试 |

## 决策

采用第三种方案。

- QuantStats / empyrical 只进入报告层和 P5 展示层。
- TA-Lib / pandas-ta 只通过指标 wrapper 做基础指标校验或少量通用指标试点。
- vectorbt 只作为后续离线研究和参数扫描候选。
- OpenBB 只作为非加密资产研究探索接口候选。
- CME、Databento、IBKR 等未来可作为严肃价格源 adapter 候选，但不得与 OKX/Binance 混成综合成交价。

## 后果

- 正面影响：降低重复造轮子成本，P5 可复用成熟 tear sheet 和指标展示。
- 代价：每个库都需要 adapter、边界文档和回归测试。
- 风险：外部库升级可能改变指标或报告口径，必须用 golden sample 和项目主口径校验。

## 验证

- 新库接入前必须写明用途、输入输出、禁止进入的核心对象、风险和回退方式。
- 指标 wrapper 必须有固定样本测试。
- 报告 adapter 必须证明项目 `BacktestSummary`、ranking、成本淘汰和风控拒绝原因仍是主口径。
- 升级外部库后必须运行指标 wrapper 测试、策略信号测试、P4 回测测试和 P5 dashboard 测试。
