# 交易系统

这是一个面向 `BTC/USDT`、`ETH/USDT`、`XAUT/USDT` 的量化交易研究与模拟执行项目。当前版本处于早期框架阶段，核心目标是把交易判断拆成可计算、可回测、可解释的机器流程：

```text
趋势判断 -> 价格行为 -> 量价确认 -> 风控执行 -> 复盘进化
```

第一阶段只做历史回测、模拟盘和复盘报告，不接入真实资金自动下单。

## 当前框架

```text
D:\交易系统
├── README.md
├── 产品说明文档_v0.1.md
├── 三周期回测分层.md
├── 代理协作流程.md
├── 项目路线图.md
├── requirements.txt
├── scripts
│   └── okx_market_smoke.py
├── trading_system
│   ├── __init__.py
│   ├── timeframe_profiles.py
│   ├── data
│   │   ├── __init__.py
│   │   ├── history.py
│   │   ├── okx_cli.py
│   │   └── universe.py
│   └── indicators
│       ├── __init__.py
│       └── regime.py
└── tests
    ├── test_data_universe.py
    ├── test_data_history.py
    ├── test_okx_cli_market_data.py
    ├── test_regime_indicators.py
    └── test_timeframe_profiles.py
```

## 核心文档

### `产品说明文档_v0.1.md`

项目的产品级说明文档，定义系统定位、支持资产、策略主链路、风控原则、AI Agent 角色、技术形态和第一版成功标准。

### `三周期回测分层.md`

三周期回测方案的策略说明文档，固化 A/B/C 三组周期：

| 组别 | 入场周期 | 结构周期 | 趋势周期 | 定位 |
| --- | --- | --- | --- | --- |
| B 标准波段 | 15m | 1h | 4h | 默认主策略候选 |
| C 慢趋势 | 1h | 4h | 1d | 低频趋势与辅助过滤 |
| A 日内快节奏 | 5m | 15m | 1h | 高频机会验证，成本敏感 |

### `代理协作流程.md`

并行代理协作的总控流程文档，定义策划者、研究代理、执行代理的职责，以及每轮任务派发、报告、审核、测试和继续交付的规则。

### `项目路线图.md`

第一轮并行代理完成后的整合路线图，包含 OKX/Binance 数据源分层、指标层、历史行情仓库、回测/风控架构和下一轮任务拆分。

### `requirements.txt`

项目本地 Python 依赖清单。当前包含 `duckdb`，用于本地历史行情仓库。依赖应安装到 `D:\交易系统\.venv`，不建议安装到全局 Python。

## 代码模块

### `trading_system/timeframe_profiles.py`

三周期回测分层的工程化表达。

包含：

- `TimeframeProfile`：周期组配置，包含入场周期、结构周期、趋势周期、用途和资产优先级。
- `BacktestResultSummary`：单个周期组回测结果摘要。
- `ProfileDecision`：周期组是否可作为主策略候选的判定结果。
- `RankedProfileResult`：带评分和判定的排序结果。
- `list_default_profiles()`：返回默认周期组，顺序为 `B -> C -> A`。
- `get_profile(key)`：按 `A/B/C` 获取周期组。
- `required_backtest_metrics()`：列出回测引擎必须输出的指标。
- `evaluate_profile_result(...)`：执行 A 组成本淘汰、C 组样本不足降级等规则。
- `rank_profile_results(...)`：对多个周期组回测结果进行统一排序。

关键规则：

- 不使用 `1m` 作为主策略周期。
- A 组若手续费占毛利超过 `25%`，直接标记为 `rejected`。
- C 组若交易次数低于 `30`，标记为 `supporting_only`。
- B 组默认是主策略候选，但最终仍要看净利润、回撤、Profit Factor 和单笔期望。

### `trading_system/data/okx_cli.py`

OKX CLI 行情适配器，负责从已安装的 `okx` 命令读取公开市场数据。

当前支持：

- `get_ticker(inst_id)`：读取单个交易对的最新行情。
- `get_candles(inst_id, bar, limit, after=None, before=None)`：读取 K 线 OHLCV 数据，并支持历史分页参数。
- `get_instruments(inst_type, inst_id=None)`：读取交易对元数据，用于校验资产是否 live、tick size、lot size 等。

该模块只读取公开行情，不需要账户权限，也不会下单。测试中通过注入假的命令执行器来验证解析逻辑，避免单元测试依赖真实网络。

### `trading_system/data/universe.py`

资产宇宙和交易所命名模块。

当前固化：

- 默认交易标的：`BTC-USDT`、`ETH-USDT`、`XAUT-USDT`。
- 默认主数据源：`okx`。
- 预留校验数据源：`binance`。
- canonical symbol 与交易所 symbol 映射：例如 `BTC/USDT -> BTC-USDT -> BTCUSDT`。
- 三周期 profile 所需 OKX bar 并集：`5m`、`15m`、`1H`、`4H`、`1D`。

Binance 当前只作为后续 BTC/ETH 校验源预留，不作为主回测成交数据源。`XAUTUSDT` 是否可用必须通过 Binance exchangeInfo 动态校验，不能默认等同 OKX 的 `XAUT-USDT`。

### `trading_system/data/history.py`

历史 K 线仓库接口。

当前支持：

- `CandleRepository.save_many(...)`：按 `inst_id + bar + timestamp` 保存并去重。
- `CandleRepository.list_candles(...)`：按时间升序返回 K 线。
- `CandleRepository.latest_timestamp(...)`：查询某交易对某周期的最新时间戳。
- `required_bars_for_profiles(...)`：从三周期 profile 中提取 OKX 所需 K 线粒度并集。
- `DuckDbCandleRepository`：DuckDB 本地历史仓库，支持 `venue + inst_id + inst_type + bar + ts_ms` 去重、时间范围读取、confirmed K 线过滤、download_state 状态读写。
- `DownloadState`：记录每个 `venue + inst_type + inst_id + bar` 的下载进度、最近成功时间、错误信息和 CLI 版本。

当前规则是 OKX 作为主数据源，Binance 作为 BTC/ETH 校验源；不同交易所数据必须按 `venue` 隔离，不混合生成“综合成交价格”。

### `trading_system/indicators/regime.py`

市场体制判断的基础指标层。

当前支持：

- `true_range(...)`：真实波幅。
- `kaufman_efficiency_ratio(...)`：Kaufman 效率比率，用于衡量趋势效率。
- `choppiness_index(...)`：CHOP 指标，用于衡量震荡/混沌程度。
- `classify_regime(...)`：按 ER 和 CHOP 将市场分为高信噪趋势、随机混沌、均值回归/过渡状态。

这部分对应策略主链路里的“趋势判断”第一层。

### `scripts/okx_market_smoke.py`

手动冒烟测试脚本，用真实 OKX CLI 查询 `BTC-USDT`、`ETH-USDT`、`XAUT-USDT` 最新行情。

运行：

```powershell
python scripts\okx_market_smoke.py
```

## 测试说明

### `tests/test_timeframe_profiles.py`

覆盖三周期配置、指标清单、A 组成本淘汰、C 组样本不足降级和周期组排序。

### `tests/test_okx_cli_market_data.py`

覆盖 OKX ticker/candles 命令构造和 JSON 解析。

### `tests/test_data_history.py`

覆盖内存 K 线仓库、DuckDB K 线仓库、按 venue 隔离、去重覆盖、升序读取、confirmed 过滤、最新/最早时间戳查询、download_state 读写和 profile 所需 OKX bar 推导。

### `tests/test_data_universe.py`

覆盖默认资产、主数据源/校验数据源、timeframe 到 OKX bar 映射、默认 profile 所需 bar 并集，以及不纳入 `1m` 的约束。

### `tests/test_regime_indicators.py`

覆盖 True Range、Kaufman ER、CHOP、趋势/噪音/边界市场体制分类。

## 如何运行验证

在项目根目录执行：

```powershell
.\.venv\Scripts\python -B -m unittest discover -s tests -v
```

可选编译检查：

```powershell
.\.venv\Scripts\python -B -m compileall trading_system tests
```

## 后续模块规划

下一步建议按这个顺序扩展：

1. `data`：扩展 OKX 历史分页、instrument 元数据、DuckDB/Parquet 存储和增量下载。
2. `indicators`：补齐 ADX、EMA50/200、BOS/CHoCH、FVG、OB、停止量、缩量回踩。
3. `strategy`：生成趋势延续与流动性反转信号。
4. `risk`：仓位、止损、止盈、回撤、冷却和熔断。
5. `backtest`：无前瞻偏差撮合、成本模型、交易明细和周期组对比。
6. `reports`：日报、周报、策略健康报告和 Agent 复盘输入。

## 风险声明

本项目是量化研究与模拟交易工具，不构成投资建议。任何策略进入真实资金前，都必须经过长期回测、模拟盘验证、压力测试和人工审核。
