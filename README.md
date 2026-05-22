# 交易系统

结论：本仓库的长期项目知识已迁移到 `AI Trading/` Obsidian vault；本文件只保留项目入口、当前阶段和常用命令。

## 当前阶段

当前处于 P6 前置审查/补齐阶段，正式 P6 模拟盘暂缓。

优先处理：

- 策略逻辑清晰度修复。
- `trend_price_volume_v1` v1 边界澄清。
- P5.2 量价拒绝、风控拒绝、Near Miss、`stop_distance/ATR` 诊断验收。
- P6 模拟盘事件循环前置能力补齐。

## Obsidian 权威源

`AI Trading/` 是唯一长期知识源。后续阶段状态、策略规格、开发记录、Agent 协作流程和待补齐清单优先只更新 Obsidian。

接手项目时先读：

- `AI Trading/00_项目驾驶舱/项目驾驶舱.md`
- `AI Trading/00_项目驾驶舱/Codex恢复入口.md`
- `AI Trading/00_项目驾驶舱/当前阶段-P6.md`
- `AI Trading/02_路线与进度/待补齐清单.md`
- `AI Trading/03_策略研究中心/策略规格.md`
- `AI Trading/03_策略研究中心/trend_price_volume_v1.md`
- `AI Trading/01_长期记忆/开发约定.md`
- `AI Trading/07_Agent协作/Agent协作总览.md`

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
.\.venv\Scripts\python -B -m compileall trading_system tests
```

文档格式检查：

```powershell
git diff --check
```

检查本地 DuckDB 历史 K 线质量：

```powershell
.\.venv\Scripts\python scripts\check_data_quality.py
```

启动 P5 本地 Streamlit 看板：

```powershell
.\.venv\Scripts\streamlit run app.py
```

检查 P5 看板健康状态：

```powershell
.\.venv\Scripts\python scripts\check_p5_dashboard.py
```

## 风险声明

本项目是量化研究与模拟交易工具，不构成投资建议。真实交易接口默认关闭；LLM/Agent 只能做解释、复盘、红队审查和 proposal，不得绕过风控或触发真实交易。
