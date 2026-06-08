---
type: agent-system
status: active
updated: 2026-06-08
tags:
  - domain/agent
  - codex/skills
---

# Codex项目Skills

结论：本项目的 Codex skills 只沉淀稳定流程，不沉淀仍在探索的策略 alpha。skills 默认 read-only 或 proposal-only，不得修改正式配置、绕过风控、进入 P6 或真实交易。

## 安装与发现

仓库内源文件位于 `.codex/skills/`。为了让 Codex 在新对话中自动发现，需要同步安装到个人 Codex skills 目录：

```powershell
.\scripts\sync_project_skills.ps1
```

dry-run 检查：

```powershell
.\scripts\sync_project_skills.ps1 -DryRun
```

技能采用 `trading-system-` 前缀，避免与全局通用 skills 冲突。

## 当前已沉淀 Skills

| skill | 用途 | 边界 |
| --- | --- | --- |
| `trading-system-research-pipeline-runner` | 标准化运行 Research Pipeline、manifest、artifact、diagnostics 和报告 | proposal-only；不 formalize；不改正式配置 |
| `trading-system-full-audit-gate-checker` | 检查 closed_trade-only metrics、lineage、no-lookahead、metric recompute、regression baseline | 只验证；不优化策略 |
| `trading-system-strategy-expansion-diagnostics` | 处理 raw candidates=0、候选过少、拒绝集中、near-miss 和受限 variants | adapter-driven；不写一次性脚本 |
| `trading-system-backtest-report-analyst` | 解释回测收益来源、MAE/MFE、成本敏感性、拒绝原因和集中风险 | 不把 diagnostic 当 formal evidence |
| `trading-system-obsidian-sync` | 阶段结束后同步项目规划、策略总览、待补齐清单和验证命令 | `AI Trading/` 为唯一长期知识源 |

## 不沉淀为 Skill 的内容

- Paper Review Loop：未来 P6 后规划，当前不实现。
- Hermes-like daily evolution：未来 P6 后规划，当前不实现。
- 实盘、下单、交易所 secret、自动 proposal apply、正式配置自动修改：禁止。
- `trend_continuation`、`compression_expansion`、`breakout_pullback` 的具体 alpha 规则：仍属研究对象，不写成自动化 skill。

## 当前项目状态口径

- LR Restricted Variant B 是 formal research candidate，但不是 live strategy；final evidence 只读保护。
- Research Pipeline 已 hardened 为通用研究框架。
- Full Audit Gate 已 generic-hardened。
- cross-run artifact reuse 已可用于后续调参和 expansion diagnostics。
- `trend_continuation` 冻结为 `strategy_definition_refactor_needed`。
- Trend Continuation Family 拆为 `compression_expansion`、`breakout_pullback`、`trend_pullback`。
- `compression_expansion` 是 diagnostic_candidate，不进入 P6。
- TC family 当前已收口，最佳 diagnostic snapshot 为 `bp_shallow_cost_aware_admission_v3`，不继续小参数优化。
- 下一步等待 simple support/resistance fixed-RR baseline 规格。

## 维护规则

- 新增 skill 前先确认流程已稳定，且不是策略 alpha。
- 修改 skill 时同步更新本页和 `AGENTS.md` 的入口说明。
- skill 只能封装流程、检查和报告要求；不能封装绕过风控的捷径。
- 安装后需验证个人 skills 目录中对应 `SKILL.md` 可读。
