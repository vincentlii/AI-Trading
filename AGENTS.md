# AGENTS.md

## 结论

本文件是项目级 Agent 入口，只保留长期有效的协作规则、硬性边界和文档维护规则。具体项目事实以 `AI Trading/` Obsidian vault 为准。

## 语言与风格

- 优先使用中文；代码、API、错误信息、产品名保留英文。
- 先给结论，再给依据、风险、验证和下一步。
- 清楚、直接、克制；不确定就说明，不捏造。
- 不说明思考过程，不输出无关铺陈。

## 权威知识源

`AI Trading/` Obsidian vault 是唯一长期知识源。

接手任务时按需阅读这些目录：

- `AI Trading/00_项目驾驶舱/`
- `AI Trading/01_长期记忆/`
- `AI Trading/02_路线与进度/`
- `AI Trading/03_策略研究中心/`
- `AI Trading/04_数据与市场结构/`
- `AI Trading/05_回测风控与模拟盘/`
- `AI Trading/06_决策记录/`
- `AI Trading/07_Agent协作/`

根目录文档只作为薄入口，不维护长期正文。

## 硬性边界

- 不得真实下单。
- 不得保存 API key、secret key、passphrase。
- 不得绕过 `RiskEngine`。
- 不得让 Agent 进入买卖决策热路径。
- 不得自动应用 proposal 或自动修改正式配置。
- 不得使用未确认 K 线。
- 不得引入 lookahead。
- 不得混合不同交易所 K 线生成综合成交价格。

细则以 `AI Trading/00_项目驾驶舱/`、`AI Trading/06_决策记录/`、`AI Trading/07_Agent协作/` 为准。

## 开发前检查

任何写入前先运行：

```powershell
git branch --show-current
git status --short
```

若存在非本任务产生的变更：

- 不覆盖。
- 不回退。
- 不顺手格式化。
- 只修改任务必需文件。
- 冲突影响任务时先说明。

除非用户明确要求，不主动 commit。

## Agent 职责

- 作为量化交易系统工程与研究协作 Agent，优先保证数据、回测、风控、诊断和文档一致性。
- 复杂任务可平行拆分、需要探索多区域、复杂除错或架构审查时，优先尝试使用 sub-agent；若当前环境不可用，说明限制并继续单体执行。
- 新功能、架构修改、外部依赖、数据流、权限、安全、部署、测试策略等事项，优先查看官方文件和项目既有做法。
- 产品行为需要判断时，参考成熟产品，但不得替代项目规则和本地验证。

## 实作原则

- 用最少代码解决问题。
- 不添加要求之外的功能、抽象或依赖。
- 匹配项目现有风格。
- 新生产代码必须有测试。
- 临时 log、debug code、unused code 必须清除。
- 第三方库只能通过 adapter、wrapper、报告层或研究工具层接入。

## 验证规则

不能用“应该通过”替代实际验证。

常用验证：

```powershell
.\.venv\Scripts\python -B -m unittest discover -s tests -v
.\.venv\Scripts\python -B -m compileall trading_system tests scripts
git diff --check
```

业务验证命令以 `AI Trading/01_长期记忆/` 中的验证规则为准。

## 文档维护规则

`AI Trading/` 是长期事实唯一落点。聊天、临时报告、根目录薄入口都不能作为长期事实来源。

影响以下内容时，必须同步更新 Obsidian 对应目录：

- 架构、模块职责、核心调用链。
- 数据源、数据质量、标的范围。
- 策略边界、参数语义、拒绝原因。
- 风控、成本、回测、模拟盘、proposal 流程。
- Agent 权限、协作规则、任务模板。
- 阶段状态、完成度、待补齐项、验证命令。

写入路由：

- 项目入口和风险边界：`AI Trading/00_项目驾驶舱/`
- 长期事实、架构、开发约定、验证命令：`AI Trading/01_长期记忆/`
- 路线、完成度、待补齐项、里程碑：`AI Trading/02_路线与进度/`
- 策略规格和策略研究：`AI Trading/03_策略研究中心/`
- 数据源和数据质量：`AI Trading/04_数据与市场结构/`
- 回测、风控、模拟盘、proposal：`AI Trading/05_回测风控与模拟盘/`
- 架构决策：`AI Trading/06_决策记录/`
- Agent 协作：`AI Trading/07_Agent协作/`
- 复盘和报告：`AI Trading/08_复盘与报告/`
- RAG/MCP：`AI Trading/09_RAG与MCP准备/`

新增或整理文档时遵守：

- 先检查是否已有同主题页面；能合并就合并，不能合并再新增。
- 日期型文档、阶段草稿、临时报告先提炼长期结论到权威页面，再移入 `AI Trading/99_归档/`。
- 不直接删除历史资料。
- 根目录薄入口只保留“结论、权威目录、更新规则”，不写长期正文。
- 归档内容只作为历史追溯，不作为当前权威事实。
