# LR Setup-Specific v2 开发集审计

## 结论

LR Setup-Specific v2 在开发集上未通过验收，近 18 个月 holdout 必须继续封存。

本轮不是“只有 18 笔交易”，而是测试了 18 个 variant。单个 variant 实际产生 4 至 1,842 笔交易；最终组合为 0，是因为选择器发现全部 variant 为负收益后排除了 3 个 setup。

从 v1、v2 与 Restricted Variant B 的代码和产物重新对账后，原 183 笔高收益结果不能继续作为可信因果基线。核心原因是旧 scanner 把 4h bar 的开盘时间当作确认时间，并在该 bar 真正收盘前入场；旧 dynamic time cut、exposure cap 和重复事件口径又进一步放大了结果。Restricted Variant B 应暂停作为 formal research candidate，等待 causal clean rebuild。

## 研究边界

- 开发集：`2020-12-31` 至 `2024-11-30`。
- holdout：近 18 个月，继续封存，未运行。
- v2 入场：4h bar 真正确认后，使用下一根严格晚于信号的 15m bar 开盘价。
- 模式：proposal-only，`formal_conclusion_enabled=false`。

## 根因一：4h 确认时间 lookahead

旧实现直接使用 4h candle 的 `timestamp_ms` 作为 `sweep_time`、`reclaim_time` 和 `signal_time`。该时间是 bar 起点，不是包含 high、low、close 和 volume 的 bar 完成时间。随后 `_next_entry` 选择时间戳大于 signal 的下一根 1h bar，导致策略在 4h 信号真正确认前 3 小时入场。

v1 和 v2 候选可以一一匹配 `14,647/14,650` 行：

| 对账项 | v1 | v2 | 差异 |
|---|---:|---:|---:|
| signal time | 4h bar 起点 | 4h bar 完成时间 | v2 晚 240 分钟 |
| entry delay after recorded signal | 60 分钟 | 15 分钟 | 口径不同 |
| 实际 entry time | 4h bar 起点后 60 分钟 | 4h bar 完成后 15 分钟 | v2 晚 195 分钟 |
| entry price difference | - | - | 中位数 115.6 bps，P90 342.9 bps |

在 v1 最终选中的 7,066 笔 base 交易中，旧入场到真实确认后入场之间的顺向移动为：

- 平均 `0.7066R`。
- 中位数 `0.5112R`。
- `86.74%` 已经顺向移动。
- `50.69%` 已经移动至少 `0.5R`。
- `26.55%` 已经移动至少 `1R`。
- 该提前移动与 v1 最终 `net_R` 的相关系数为 `0.59`。

旧结果的主要收益已经发生在信号尚未真正确认、实盘无法预知的区间。

## 单变量复现

将 v1 和 v2 候选交给完全相同的当前 15m 执行器、RiskEngine、score 50 gate、hard reject sizing 和 base 成本，只改变确认与入场时点：

| setup | 旧提前入场 trades / total R / avg R | 因果入场 trades / total R / avg R |
|---|---|---|
| Session HL attempt 4 fixed | 247 / `+87.36R` / `+0.354R` | 641 / `-34.02R` / `-0.053R` |
| Recent swing attempt 4 dynamic | 173 / `+49.40R` / `+0.286R` | 456 / `-30.41R` / `-0.067R` |
| Session HL attempt 3 dynamic | 840 / `+133.92R` / `+0.159R` | 1,557 / `-70.44R` / `-0.045R` |

因此主因不是质量门、RiskEngine、成本模型或 15m 执行器，而是旧确认时间允许提前入场。

## 根因二：旧 dynamic time cut 使用事后 MFE

旧 `dynamic_time_cut` 没有逐 bar 执行，而是读取整笔基础交易的 `mfe_R` 后重写结果：

- `MFE >= 1.5R` 时直接记为 `min(MFE, 2R)`。
- `MFE >= 0.5R` 时保证至少 `+0.25R`。
- 没有验证 MFE 是否在 momentum deadline 前发生。

在 v2 因果入场不变时做退出消融：

| setup | 真实逐 bar dynamic | 固定 2R / 20h | 旧事后 MFE 重写 |
|---|---:|---:|---:|
| Recent swing attempt 4 | `-30.41R` | `-35.51R` | `-6.70R` |
| Session HL attempt 3 | `-70.44R` | `-83.94R` | `+41.82R` |

旧 MFE 重写可把本来亏损的 Session HL attempt 3 直接变成正收益，属于第二个明确的结果放大来源。

## 根因三：旧 exposure cap 使用未来收益排序

旧 `_apply_exposure_cap` 按 `(entry_time, -net_R)` 排序。相同入场时点发生 heat 冲突时，会优先保留事后收益更高的交易。

在 v1 可恢复的 pre-heat 行上重放：

- 因果顺序：`3,630.11R`。
- 旧收益排序：`3,641.37R`。
- 仅排序方式就额外增加约 `11.26R`。

原 183 笔逐笔 artifact 已缺失，无法精确重算该偏差对 Restricted Variant B 的影响，但实现本身不满足 no-lookahead。

## 根因四：旧 duplicate_event_count 口径无效

旧 `event_key` 直接使用 `event_id`，而 `event_id` 包含 structure source、level type 和 level price。同一市场 sweep/reclaim 被多个结构位描述时，会得到不同 event id，因此报告中的 `duplicate_event_count=0` 不能证明没有重复市场信号。

按 `(instrument, profile, direction, sweep_time, reclaim_time)` 重算 v1 base 交易：

- closed trades：7,066。
- unique physical signals：4,169。
- 重复增加的交易：2,897。
- 有重复的 signal：1,953。
- 单一 signal 最大重复 6 次。

## 质量门与风控判断

v2 不是被质量门过滤到没有交易。score 50 hard-reject 分别产生 641、456、1,557 笔交易，数量高于旧同口径 hard-reject 的 392、231、1,322 笔。

当前质量分数对因果入场后的收益方向没有正向排序能力。三个 setup 从 score 50 提高到 60、70 后，平均 R 反而持续恶化。主要原因是 displacement 与 CHOCH 强度在旧提前入场模型中代表未来优势；改为 bar 收盘后入场时，它们更多代表价格已经走完、入场追价。

base 成本约消耗 `0.049R` 每笔，但不是唯一原因：

- Session HL attempt 4 因果入场 gross average R 为 `-0.0039R`。
- Recent swing attempt 4 gross average R 为 `-0.0169R`。
- Session HL attempt 3 gross average R 为 `+0.0040R`。

即使忽略成本，当前 setup 也接近零或负毛期望。限价单可以降低成本，但不足以恢复旧版约 `0.16R` 至 `0.35R` 的单笔优势。

动态缩仓本身没有逻辑错误，但 sizing 只能控制风险和组合波动，不能把负的单笔 R 期望变成正值。

## Full Audit 缺口

旧 Full Audit 只比较时间字段的数值顺序，没有验证 candle timestamp 是否代表 bar 起点，也没有验证 dynamic exit 是否使用未来 MFE。`bar_confirmed_true` 与 `no_lookahead_safe` 检查只验证字段存在，没有验证字段值和语义。

Restricted Variant B baseline 指向的逐笔证据目录 `storage/backtest_cache/pr11g_clean_rebuild` 与 `pr11h_fix` 当前不存在，因此 183 笔无法闭环复算。

v2 Full Audit 同样未通过：最终组合无 `closed_trade`，各 variant 也没有保存逐笔 closed-trade artifact，导致失败后的交易级审计不完整。

## 决策

1. 不运行 v2 holdout。
2. 暂停把 Restricted Variant B 的 183 笔、`85.07R`、PF `7.80` 作为可信正式研究证据。
3. 不回退到旧 signal timestamp 或旧 MFE exit；这会恢复收益，但会重新引入 lookahead。
4. 先修复审计语义、逐笔 variant artifact 和 causal exposure ordering，再重新研究 setup。
5. 下一轮重点不是继续调整 score threshold，而是把 4h setup 改造成可实盘观察的低时间级别确认：4h 仅提供已确认结构背景，15m/1h 提供 CHOCH、reclaim 或 pullback trigger。
