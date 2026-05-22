---
type: strategy-family
strategy_family: stopping_volume_retest
status: research_only
updated: 2026-05-19
tags:
  - strategy/pa-vpa
  - strategy/research-only
---

# 02_stopping_volume_retest

结论：研究蓝图已存在，尚未代码化。

## 定位

停止量后缩量二次测试，用于识别强抛压或强买盘被吸收后的供需枯竭。

## 趋势角色

软过滤 / 局部结构确认。不用慢趋势硬否决，重点看停止量后的二次测试质量。

## 实现前置

- 停止量识别。
- 缩量二次测试定义。
- Swing / Equal High Low 层级。
- Volume Z-Score 和 Spread Ratio。

## 风险

- 容易把普通回踩误判为停止量。
- 样本量可能不足。
- 需要和 01、06 分清边界。
