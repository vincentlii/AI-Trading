# 交易系统

结论：本仓库的长期项目知识以 `AI Trading/` Obsidian vault 为准；根目录文档只保留入口、常用命令和恢复提示。

## 权威目录

- 项目驾驶舱与风险边界：`AI Trading/00_项目驾驶舱/`
- 长期记忆、架构、开发约定、验证命令：`AI Trading/01_长期记忆/`
- 路线、进度、待补齐项、里程碑：`AI Trading/02_路线与进度/`
- 策略规格、策略研究、策略族：`AI Trading/03_策略研究中心/`
- 数据源、市场结构、数据质量：`AI Trading/04_数据与市场结构/`
- 回测、风控、模拟盘、proposal：`AI Trading/05_回测风控与模拟盘/`
- ADR 与长期决策：`AI Trading/06_决策记录/`
- Agent 协作规则：`AI Trading/07_Agent协作/`
- 复盘与报告：`AI Trading/08_复盘与报告/`
- RAG 与 MCP 准备：`AI Trading/09_RAG与MCP准备/`
- 历史草稿与原始资料：`AI Trading/99_归档/`

## 核心链路

```text
MarketRegime -> PriceActionSetup -> VolumePriceConfirmation -> RiskDecision -> SimulatedOrder -> PositionState
```

## 常用命令

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

运行单元测试：

```powershell
.\.venv\Scripts\python -B -m unittest discover -s tests -v
```

编译检查：

```powershell
.\.venv\Scripts\python -B -m compileall trading_system tests scripts
```

文档格式检查：

```powershell
git diff --check
```

数据质量检查：

```powershell
.\.venv\Scripts\python scripts\check_data_quality.py
```

启动本地 Streamlit 看板：

```powershell
.\.venv\Scripts\streamlit run app.py
```

## 风险声明

本项目是量化研究、回测、模拟盘与复盘工具，不构成投资建议。真实交易接口默认关闭；Agent 只能做解释、复盘、红队审查和 proposal，不得绕过风控或触发真实交易。

## 更新规则

根目录文档只更新入口路径、恢复说明和常用命令。长期事实、阶段状态、架构、策略、风控、Agent 规则和待补齐项必须写入 `AI Trading/` 对应权威目录。
