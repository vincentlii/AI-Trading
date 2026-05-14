# 交易系统

面向 `BTC/USDT`、`ETH/USDT`、`XAUT/USDT` 的量化交易研究、回测、模拟盘和复盘系统，并预留未来接入纳斯达克指数等非 OKX 标的。

当前阶段只做公开行情、历史回测、模拟盘准备和策略研究，不接入真实资金自动下单。

```text
MarketRegime -> PriceActionSetup -> VolumePriceConfirmation -> RiskDecision -> SimulatedOrder -> PositionState
```

## 当前状态

已完成：

- Git 版本控制与本地 `.venv` 依赖环境。
- 三周期回测分层：A 日内快节奏、B 标准波段、C 慢趋势。
- OKX 公开行情适配器：ticker、candles、instruments。
- 资产宇宙：OKX 主数据源，Binance 作为 BTC/ETH 校验源预留。
- 可扩展标的物骨架：`InstrumentSpec`、`VenueSymbol`，并预留 `INDEX` 资产类别。
- DuckDB 历史 K 线仓库：按 `venue + inst_type + inst_id + bar + ts_ms` 隔离。
- OKX 历史 K 线下载器 v1：小批量下载 confirmed K 线并写入 DuckDB。
- 数据质量检查器 v1：检查空数据、缺口、重复、未确认 K 线、OHLC 异常和负成交量。
- 市场体制基础指标：True Range、Kaufman ER、CHOP、EMA、ATR、ADX/DMI、TTM Squeeze、regime 分类。
- 轻量指标注册表和策略插件注册表。
- 初始策略插件：`trend_price_volume_v1`，已能生成 `trend_continuation` 与 `liquidity_reversal` 标准信号候选。
- 第一版回测/风控领域模型：订单意图、账户状态、成本估计、风险决策、模拟订单和持仓状态。
- P4.1 信号级回测闭环：`StrategySignal` 接入 `RiskEngine`，并完成最小无前瞻撮合、交易日志、权益曲线和汇总指标。

下一小步：P4.2 完整历史滚动信号扫描器。

## 核心文档

只维护 4 份长期根文档：

- `README.md`：项目入口、当前状态、目录结构、安装与测试命令。
- `项目总规划.md`：最终愿景、阶段路线、当前完成度、下一小计划、风险边界。
- `策略规格.md`：策略系统总规范、插件接口、标准信号、风控边界。
- `代理协作流程.md`：策划者/代理协作规则、写入范围、TDD、验收格式。

具体策略文档放在各自策略目录中，例如：

- `trading_system/strategies/trend_price_volume_v1/strategy.md`

阶段完成后的状态更新主要写入 `项目总规划.md`。只有策略系统规则变化才更新 `策略规格.md`，具体策略变化优先更新对应策略目录的 `strategy.md`。

## 目录结构

```text
D:\交易系统
├── README.md
├── 项目总规划.md
├── 策略规格.md
├── 代理协作流程.md
├── requirements.txt
├── scripts
│   ├── check_data_quality.py
│   ├── download_okx_history.py
│   └── okx_market_smoke.py
├── trading_system
│   ├── __init__.py
│   ├── timeframe_profiles.py
│   ├── backtest
│   │   ├── __init__.py
│   │   ├── execution.py
│   │   └── risk.py
│   ├── data
│   │   ├── __init__.py
│   │   ├── history.py
│   │   ├── okx_cli.py
│   │   ├── quality.py
│   │   └── universe.py
│   ├── indicators
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   └── regime.py
│   └── strategies
│       ├── __init__.py
│       ├── base.py
│       ├── registry.py
│       └── trend_price_volume_v1
│           ├── __init__.py
│           ├── features.py
│           ├── strategy.md
│           └── strategy.py
└── tests
    ├── test_backtest_risk.py
    ├── test_backtest_execution.py
    ├── test_data_history.py
    ├── test_data_quality.py
    ├── test_data_universe.py
    ├── test_indicator_registry.py
    ├── test_okx_cli_market_data.py
    ├── test_okx_history_download.py
    ├── test_regime_extended_indicators.py
    ├── test_regime_indicators.py
    ├── test_strategy_registry.py
    ├── test_trend_price_volume_features.py
    ├── test_trend_price_volume_strategy.py
    └── test_timeframe_profiles.py
```

## 安装依赖

项目依赖安装到本地 `.venv`，不建议安装到全局 Python：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

当前依赖：

- `duckdb`：本地历史行情仓库。

## 常用命令

运行单元测试：

```powershell
.\.venv\Scripts\python -B -m unittest discover -s tests -v
```

编译检查：

```powershell
.\.venv\Scripts\python -B -m compileall trading_system tests
```

OKX 公开行情冒烟测试：

```powershell
.\.venv\Scripts\python scripts\okx_market_smoke.py
```

下载 OKX 最近一页历史 K 线到 DuckDB：

```powershell
.\.venv\Scripts\python scripts\download_okx_history.py --limit 10 --max-pages 1
```

如果 `okx` 不在 PATH 中，可显式传入命令路径：

```powershell
.\.venv\Scripts\python scripts\download_okx_history.py --limit 10 --max-pages 1 --okx-command "C:\Users\85394\AppData\Roaming\npm\okx.cmd"
```

检查本地 DuckDB 历史 K 线质量：

```powershell
.\.venv\Scripts\python scripts\check_data_quality.py
```

## 数据边界

- OKX 是第一版主数据源。
- Binance 只作为 BTC/ETH 校验源预留，不参与主回测成交价格。
- 不混合不同交易所 K 线生成“综合价格”。
- `XAUTUSDT` 是否可作为 Binance 校验源必须用 exchangeInfo 动态验证。
- 纳斯达克指数等 `INDEX` 标的需要未来独立数据源 adapter，不进入 OKX 默认下载清单。
- API key、secret key、passphrase 不写入仓库，也不在聊天中收集。

## 风险声明

本项目是量化研究与模拟交易工具，不构成投资建议。任何策略进入真实资金前，都必须经过长期回测、模拟盘验证、压力测试和人工审核。
