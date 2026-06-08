---
type: agent-system
status: active
updated: 2026-06-08
tags:
  - domain/agent
  - agent/recovery
---

# Agent协作总览

结论：Agent 分为策划者、研究代理、执行代理、复盘代理和未来 Hermes Agent；所有 Agent 都不得越过风控、Full Audit Gate 和人工审批边界。

## 角色

| 角色 | 职责 | 写入权限 |
| --- | --- | --- |
| 策划者 | 维护主线、拆任务、整合、验证 | 可写，但需遵守项目边界 |
| 研究代理 | 只读调研、分析、提出任务 | 不写文件 |
| 执行代理 | 小范围代码落地 | 仅限明确写入范围 |
| 复盘代理 | 读取日志和报告，解释、复盘、红队 | 不写热路径 |
| Hermes Agent | 云端任务编排、日报周报、异常提醒 | 未来按审批流程 |

## 任务模板

- [[Codex任务交接模板]]
- [[研究代理模板]]
- [[执行代理模板]]
- [[复盘代理模板]]
- [[Codex项目Skills]]

## 项目 Codex Skills

当前已沉淀 5 个项目专属 Codex skills，源文件位于 `.codex/skills/`，同步安装命令为 `.\scripts\sync_project_skills.ps1`。

| skill | 当前用途 |
| --- | --- |
| `trading-system-research-pipeline-runner` | 运行标准 Research Pipeline 研究流程 |
| `trading-system-full-audit-gate-checker` | 检查 Full Audit Gate 和 closed_trade-only metrics |
| `trading-system-strategy-expansion-diagnostics` | 处理 raw candidates=0、候选过少和 near-miss diagnostics |
| `trading-system-backtest-report-analyst` | 分析回测报告、MAE/MFE、成本敏感和拒绝原因 |
| `trading-system-obsidian-sync` | 阶段结束后同步 Obsidian 长期事实 |

这些 skills 只封装稳定流程，不封装策略 alpha；默认 read-only 或 proposal-only，不得修改正式配置、绕过风控、进入 P6 或真实交易。

## 硬规则

- Agent 不生成真实订单。
- Agent 不自动改正式配置。
- Agent 不绕过 RiskEngine。
- Agent 参数建议必须进入 proposal。
- Agent 不得把 proposal / diagnostic / summary rows 当作收益表现。
- Agent 不得把 formal research candidate 描述为 live trading strategy。
- Agent 不得在未经 full-audit、robustness、exposure restriction 和人工确认前修改正式配置。
- 执行代理必须知道自己不是唯一在代码库工作的代理。

## Research Pipeline 协作规则

- 后续策略研究优先使用统一 Research Pipeline，不复制 PR11A-PR11H 临时脚本流。
- full-audit failed 时，不得继续推进 robustness 或 formalization。
- performance metric 必须能追溯到 `row_type=closed_trade`，并具备 execution / candidate / event / timeseries lineage。
- 旧 PR11C-PR11G LR 产物只可作为历史参考，不得作为最终决策依据。
- trend_continuation、breakout_pullback、stopping_volume_retest 等新策略启动前，应先确认 adapter、artifact、audit 和 regression baseline 路径。
- Paper Review Loop 与 Hermes-like daily evolution 仅作为未来 P6 后规划，当前不得作为自动研究或自动交易流程启动。

## 写入规则

- 长期协作规则只更新本页和相关 Agent 模板。
- 根目录 `代理协作流程.md` 只保留薄入口。
- 阶段状态写入 [[当前阶段-P6]] 和 [[当前完成度]]。
- 待执行任务写入 [[待补齐清单]]。

## 权威来源

完整协作规则以本页和相关模板为准；根目录文档只做入口。
