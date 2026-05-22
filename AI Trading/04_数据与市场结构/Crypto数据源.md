---
type: data-source
asset_class: crypto
status: active
updated: 2026-05-19
tags:
  - domain/data
---

# Crypto数据源

结论：BTC/ETH 当前以 OKX 作为第一版主执行/回测价格源，Binance 作为校验源预留。

## 当前规则

- OKX：第一版主执行/回测价格源。
- Binance：BTC/ETH 校验源，用于缺口、异常和价格偏差检查。
- 不混合 OKX 与 Binance K 线生成综合成交价格。
- funding、open interest、链上和新闻只能作为特征、过滤器或复盘依据。

## 当前代码入口

- `trading_system/data/okx_cli.py`
- `trading_system/data/history.py`
- `trading_system/data/quality.py`
- `trading_system/data/universe.py`
