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
- 资产宇宙：OKX 作为第一版加密场内执行/回测源，Binance 作为 BTC/ETH 校验源预留。
- 可扩展标的物骨架：`InstrumentSpec`、`VenueSymbol`，并预留 `INDEX` 资产类别。
- DuckDB 历史 K 线仓库：按 `venue + inst_type + inst_id + bar + ts_ms` 隔离。
- OKX 历史 K 线下载器 v1：小批量下载 confirmed K 线并写入 DuckDB。
- 数据质量检查器 v1：检查空数据、缺口、重复、未确认 K 线、OHLC 异常和负成交量。
- 市场体制基础指标：True Range、Kaufman ER、CHOP、EMA、ATR、ADX/DMI、TTM Squeeze、regime 分类。
- 轻量指标注册表和策略插件注册表。
- 初始策略插件：`trend_price_volume_v1`，已能生成 `trend_continuation` 与 `liquidity_reversal` 标准信号候选。
- PA+VPA 多策略族蓝图 v1：已基于三份研究文档去重为 8 个自然语言策略规格，当前代码插件已实现其中 01/04 的 BTC/ETH OHLCV v1。
- 第一版回测/风控领域模型：订单意图、账户状态、成本估计、风险决策、模拟订单和持仓状态。
- P4.1 信号级回测闭环：`StrategySignal` 接入 `RiskEngine`，并完成最小无前瞻撮合、交易日志、权益曲线和汇总指标。
- P4.2 完整历史滚动信号扫描器 v1：按多标的、多周期滚动构建 `StrategyContext`，接入 P4.1 执行层，并输出 `strategy_family` / `setup_type` 分层统计。
- P4.3 高级出场模型 v1：支持 1R 减仓、真实盈亏平衡、Chandelier Exit、时间止损和结构化出场事件。
- 配置化地基 v1：P4.4 先使用 `configs/presets/btc_eth_p4_4.toml` 管理 BTC/ETH、风险、成本、策略启停、回测执行和周期排名参数。
- P4.4 BTC/ETH 三周期 A/B/C 批量回测排名 v1：读取 preset，调用 P4.2 滚动扫描器和 P4.3 高级出场执行层，输出分层指标、排名状态和 A 组成本淘汰结果。
- P4.5 参数 proposal 队列与回测验证入口 v1：结构化保存参数建议，只在内存中应用 patch，并复用 P4.4 路径验证，不自动修改正式配置。

下一小步：P5，本地 Streamlit 网页看板。

## 核心文档

只维护 4 份长期根文档：

- `README.md`：项目入口、当前状态、目录结构、安装与测试命令。
- `项目总规划.md`：最终愿景、阶段路线、当前完成度、下一小计划、风险边界。
- `策略规格.md`：策略系统总规范、插件接口、标准信号、风控边界。
- `代理协作流程.md`：策划者/代理协作规则、写入范围、TDD、验收格式。

具体策略文档放在各自策略目录中，例如：

- `trading_system/strategies/trend_price_volume_v1/strategy.md`
- `trading_system/strategies/pa_vpa_v1/README.md`
- `trading_system/strategies/pa_vpa_v1/specs/`

阶段完成后的状态更新主要写入 `项目总规划.md`。只有策略系统规则变化才更新 `策略规格.md`，具体策略变化优先更新对应策略目录的 `strategy.md`。

## 目录结构

```text
D:\交易系统
├── README.md
├── 项目总规划.md
├── 策略规格.md
├── 代理协作流程.md
├── requirements.txt
├── configs
│   ├── assets
│   │   └── btc_eth.toml
│   ├── costs
│   │   └── crypto_spot_research.toml
│   ├── presets
│   │   └── btc_eth_p4_4.toml
│   ├── proposals
│   │   └── README.md
│   ├── risk
│   │   └── default.toml
│   └── strategies
│       └── trend_price_volume_v1.toml
├── scripts
│   ├── check_data_quality.py
│   ├── download_okx_history.py
│   ├── okx_market_smoke.py
│   ├── run_btc_eth_p4_4_backtest.py
│   └── validate_p4_5_proposal.py
├── trading_system
│   ├── __init__.py
│   ├── timeframe_profiles.py
│   ├── backtest
│   │   ├── __init__.py
│   │   ├── batch.py
│   │   ├── execution.py
│   │   ├── proposal_validation.py
│   │   ├── risk.py
│   │   └── scanner.py
│   ├── config
│   │   ├── __init__.py
│   │   └── loader.py
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
│       ├── pa_vpa_v1
│       │   ├── README.md
│       │   ├── strategy_map.md
│       │   └── specs
│       │       ├── 01_liquidity_sweep_reclaim.md
│       │       ├── 02_stopping_volume_retest.md
│       │       ├── 03_absorption_box_break.md
│       │       ├── 04_breakout_pullback_continuation.md
│       │       ├── 05_failed_breakout_effort_result.md
│       │       ├── 06_climax_exhaustion_reversal.md
│       │       ├── 07_compression_expansion_breakout.md
│       │       └── 08_hvn_fvg_rejection_trap.md
│       └── trend_price_volume_v1
│           ├── __init__.py
│           ├── features.py
│           ├── strategy.md
│           └── strategy.py
└── tests
    ├── test_backtest_risk.py
    ├── test_backtest_scanner.py
    ├── test_backtest_execution.py
    ├── test_config_loader.py
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

| 文件/目录 | 中文名 | 用途 |
| --- | --- | --- |
| `README.md` | 项目入口说明 | 介绍项目状态、目录结构、安装依赖和常用命令。 |
| `项目总规划.md` | 项目总规划 | 记录 P0-P8 路线、当前完成度、下一步和未实现功能回补清单。 |
| `策略规格.md` | 策略系统总规范 | 定义策略插件架构、标准信号、三周期分层、风控边界和 PA+VPA 策略族。 |
| `代理协作流程.md` | 代理协作规则 | 记录主线程、sub-agent、模型、写入范围和验收规则。 |
| `requirements.txt` | Python 依赖清单 | 记录项目本地 `.venv` 需要安装的依赖。 |
| `configs/` | 配置目录 | 存放可审计的资产、风险、成本、策略和回测预设配置。 |
| `configs/presets/btc_eth_p4_4.toml` | BTC/ETH 回测预设 | P4.4 主配置入口，引用 BTC/ETH、风险、成本、策略和执行配置。 |
| `configs/proposals/` | 配置建议目录 | 存放 Agent 或人工提出的配置修改 proposal，不自动生效。 |
| `scripts/` | 脚本目录 | 放手动运行的工具脚本，例如下载行情、检查数据质量和 OKX 冒烟测试。 |
| `trading_system/timeframe_profiles.py` | 三周期配置 | 定义 A/B/C 三类入场、结构、趋势周期组合。 |
| `trading_system/backtest/risk.py` | 风控模型 | 定义订单意图、账户状态、成本估计、风控决策和持仓领域模型。 |
| `trading_system/backtest/execution.py` | 回测撮合执行 | 把策略信号接入风控，完成模拟撮合、交易日志、权益曲线和高级出场事件。 |
| `trading_system/backtest/scanner.py` | 历史滚动扫描器 | 从历史 K 线滚动构建策略上下文，生成信号，调用回测执行层并按策略族分层统计。 |
| `trading_system/backtest/batch.py` | 批量回测排名 | 串联 preset、滚动扫描器和执行层，输出 P4.4 排名、状态和成本淘汰结果。 |
| `trading_system/backtest/proposal_validation.py` | proposal 回测验证 | 把参数 proposal 转为内存 preset，并复用 P4.4 runner 对比 base/proposed 结果。 |
| `trading_system/config/loader.py` | 配置加载器 | 读取 TOML 配置，校验范围，并转换为回测、风控和扫描配置对象。 |
| `trading_system/config/proposals.py` | proposal 队列 | 读写 JSON 参数建议、校验允许字段、生成内存版 proposed preset。 |
| `trading_system/data/history.py` | 历史行情仓库 | 提供内存版和 DuckDB 版 K 线存储、查询和下载状态管理。 |
| `trading_system/data/okx_cli.py` | OKX 行情适配器 | 通过 OKX CLI 获取公开 ticker、K 线和 instruments。 |
| `trading_system/data/quality.py` | 数据质量检查 | 检查空数据、缺口、重复、未确认 K 线、OHLC 异常和负成交量。 |
| `trading_system/data/universe.py` | 资产宇宙 | 定义默认标的、交易所映射、资产类别和未来 Nasdaq 扩展入口。 |
| `trading_system/indicators/registry.py` | 指标注册表 | 暴露可复用指标元数据，供策略声明依赖。 |
| `trading_system/indicators/regime.py` | 市场体制指标 | 实现趋势、波动、效率和震荡相关基础指标。 |
| `trading_system/strategies/base.py` | 策略基础接口 | 定义 `Strategy`、`StrategyMetadata`、`StrategyContext` 和 `StrategySignal`。 |
| `trading_system/strategies/registry.py` | 策略注册表 | 管理策略注册、查询和列表输出。 |
| `trading_system/strategies/pa_vpa_v1/` | PA+VPA 策略蓝图 | 存放 8 个去重后的自然语言策略族规格，不直接执行。 |
| `trading_system/strategies/trend_price_volume_v1/` | 初始可执行策略 | 当前第一个策略插件，实现 04 放量突破回踩续攻和 01 流动性扫荡回收的 OHLCV v1。 |
| `tests/` | 测试目录 | 存放数据、指标、策略、风控和回测执行相关单元测试。 |

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

加载 P4.4 BTC/ETH 配置预设：

```powershell
.\.venv\Scripts\python -c "from trading_system.config import load_backtest_preset; p=load_backtest_preset('configs/presets/btc_eth_p4_4.toml'); print(p.config_version, p.config_fingerprint)"
```

运行 P4.4 BTC/ETH 三周期批量回测排名：

```powershell
.\.venv\Scripts\python scripts\run_btc_eth_p4_4_backtest.py
```

验证 P4.5 参数 proposal：

```powershell
.\.venv\Scripts\python scripts\validate_p4_5_proposal.py --proposal configs\proposals\<proposal>.json
```

配置只用于参数、资产范围、成本假设和策略启停，不改变策略状态机、风控执行逻辑或无前瞻撮合规则。

## 数据边界

- BTC/ETH 仍以 OKX 作为第一版主执行/回测价格源，Binance 作为校验源预留。
- 黄金和纳指不沿用加密资产的数据源模式，后续采用“传统金融主参考源 + 场内执行源 + 偏差校验机制 + 宏观/时段背景源”。
- `XAUT/USDT` 当前只是过渡研究标的和加密场内映射/执行源，不是全球黄金价格的唯一事实源。
- 黄金参考体系优先评估 COMEX `GC/MGC`、XAU/USD 和 LBMA Gold Price。
- 纳指参考体系优先评估 CME `NQ/MNQ`、Nasdaq-100 Index / `NDX` 和 `QQQ`。
- 不混合不同交易所 K 线生成“综合价格”。
- `XAUTUSDT` 是否可作为 Binance 校验源必须用 exchangeInfo 动态验证；XAUT 插针但外部黄金参考源未同步时，应标记为场内流动性异常。
- 纳斯达克指数等 `INDEX` 标的需要未来独立数据源 adapter，不进入 OKX 默认下载清单，也不使用低质量指数币或未授权 CFD 作为主参考源。
- API key、secret key、passphrase 不写入仓库，也不在聊天中收集。

## 风险声明

本项目是量化研究与模拟交易工具，不构成投资建议。任何策略进入真实资金前，都必须经过长期回测、模拟盘验证、压力测试和人工审核。
