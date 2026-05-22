---
type: data-source
asset_class: nasdaq
status: active
updated: 2026-05-19
tags:
  - domain/data
---

# Nasdaq数据源

结论：Nasdaq 不使用低质量指数币、指数代币、未授权 CFD 或加密场内映射资产作为主参考源。

## 参考体系

| 来源 | 角色 |
| --- | --- |
| CME `NQ/MNQ` | 接近实时、流动性更强的可交易参考 |
| Nasdaq-100 Index / `NDX` | 指数基准和成分股事实源 |
| `QQQ` | 美股 RTH 时段校验源和流动性参考 |

## 后续需求

- 独立数据源 adapter。
- RTH/ETH session 标记。
- 宏观事件标签。
- 主市场健康状态。
- 跨市场偏差检查。
