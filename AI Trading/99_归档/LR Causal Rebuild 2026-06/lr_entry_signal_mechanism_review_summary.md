---
type: research-report
status: diagnostic-complete
updated: 2026-06-20
tags:
  - strategy/liquidity-reversal
  - research/causal
  - research/entry-signal
---

# LR Entry Signal Mechanism Review Summary

## 结论

本次只读复盘确认：当前 LR 上游不是完全无方向性，而是**事件定义过宽，缺少对“真实流动性、快速失败突破、先有利路径”的联合确认**。这导致 diagnostic median R 轻微为正，但 invalidation-first 仍近 50%；进入真实执行后 gross edge 只剩 +0.081R，被 0.228R 成本稳定翻为 -0.147R。

可以进入一个极小的 Entry Signal v3 smoke，但它只能验证由机制推导的 `1H same-bar + PDH/PDL/confirmed swing + 单一 15m structural confirmation`，不得扩展网格或重开下游优化。

## 研究问题回答

### 1. 当前 LR 上游信号最大问题是什么？

是 event definition 过宽。仅有“穿越 level + close 收回”不足以证明 failure auction。全体 240m/1200m median R 为 0.096/0.120，但 1200m invalidation-first 为 49.59%，MFE/MAE 中位数几乎对称。

### 2. 15m 的问题是周期太低、信号太宽，还是路径噪声太大？

三者相关，但主因是**信号太宽导致路径噪声大**，不是 15m 天然无效。15m 的 240m median R 最高，但 MFE/MAE 为 2.646R/2.670R；它适合做 execution/micro-confirmation，不适合同时承担 level sweep、reclaim、signal 和 entry 全部定义。

### 3. 1H same-bar reclaim 是否更符合失败突破机制？

**形态语义上是，路径证据上尚未证明更优。** Same-bar 的 sweep 深度中位数仅 0.307 ATR，reclaim 收回 0.430 ATR，最像快速 failure auction；但 invalidation-first 仍为 50.02%。2/3-bar reclaim 路径表面更好，但它们是延迟反转，不能与 same-bar 合并或作 winner。

### 4. PDH/PDL 与 confirmed swing 是否比 Session H/L 更接近真实流动性？

**是。** PDH/PDL 具有日历周期和全市场共识，confirmed swing 具有 causal 结构语义。Session H/L 产生 16,330 events，其中 12,789 个无其他 level confluence，且现实现是泛化已完成 8h block。它若继续，必须增加 first touch、明确 active session 和 PDH/PDL/swing confluence，不再独立放行。

### 5. VPA 更像有效真伪识别，还是只是弱诊断？

目前是**弱到中等的诊断/真伪 attribution**。Normal/elevated volume/range 往往好于 extreme，但关系非单调。Reclaim volume q4 的 +1R-first 仅 45.91%，说明极端量也可能是趋势延续或已走完。它可用固定 bins 进行下一步 attribution，不能直接变成 gate/score。

### 6. Anatomy 正、execution 负的主要损耗层在哪里？

是多层共同作用：

1. 上游 path edge 弱，invalidation-first 近 50%。
2. Limit/retest 产生 adverse selection，MSS 则中位追价 0.54-0.81 ATR。
3. Stop near/far 与 min actual risk 造成大量 admission 拒绝，98.36% 入选交易仍被 notional cap。
4. 最终 gross edge 只有 +0.081R，base cost 0.228R 是直接翻负层。

RiskEngine、cost、stop boundary 都不应放宽；应先提高上游 gross edge。

### 7. 下一步是否可以进入一个很小的 Entry Signal v3 smoke？

**可以，但只是 development-only 机制 smoke，不是 Entry Tournament。** 不访问 holdout，不生成正式策略，不进入 exit/sizing/quality gate 优化。

### 8. v3 smoke 只允许测试哪些最小信号？

- 1H same-bar sweep/reclaim。
- PDH/PDL 和 causal confirmed swing，分开报告，不组网格。
- 一个预注册的 15m structural confirmation，最多 4 bars。
- VPA 仅使用已有 fixed bins 做 attribution，不过滤。
- Session H/L 仅作 first-touch/active-window/confluence attribution，不作独立信号。
- 主验收是 path-order 改善及跨年、BTC/ETH、long/short 一致性，不是小分组收益。

## 边界与状态

- 本次未重跑 scanner 或 Tournament，未读取 holdout，未生成新交易。
- Multi-Timeframe causality audit 仍为 `pass`，Tournament v2 仍无 selected winner。
- Restricted Variant B 继续 suspended。
- 下一步必须先写 v3 smoke 预注册规格，不得自动扩展变体。

## 分报告

- `lr_artifact_inventory.md`
- `missing_data_manifest.md`
- `lr_level_mechanism_review.md`
- `lr_sweep_reclaim_mechanism_review.md`
- `lr_vpa_effort_result_review.md`
- `lr_path_order_review.md`
- `lr_anatomy_to_execution_loss_review.md`
- `lr_next_entry_signal_definition.md`
