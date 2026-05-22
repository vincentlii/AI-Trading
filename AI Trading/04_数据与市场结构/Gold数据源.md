---
type: data-source
asset_class: gold
status: active
updated: 2026-05-19
tags:
  - domain/data
---

# Gold数据源

结论：XAUT/USDT 只是加密场内映射/执行源，不是全球黄金唯一事实源。

## 参考体系

| 来源 | 角色 |
| --- | --- |
| COMEX `GC/MGC` | 高频价格发现和可交易参考 |
| XAU/USD | 全球现货参考 |
| LBMA Gold Price | AM/PM 慢速权威基准 |
| XAUT/USDT | 加密场内映射资产或执行价格源 |

## 风险规则

- XAUT 插针但外部黄金参考源未同步时，标记为 `venue_liquidity_anomaly`。
- 不得把 XAUT/USDT 单一场内异常解释为全球黄金趋势破位。
- 后续需要建立跨市场偏差检查器。
