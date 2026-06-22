# TC BP First Pullback Geometry v2 Smoke

## 结论

Decision: `semantic_filter_overfit_sample_collapse`。

## 数据与语义

- 从 raw OHLCV 重扫；未复用旧 event/candidate/filter/execution 缓存。
- Development smoke: `2024-07-01` 至 `2024-11-30`；所有查询和 diagnostic label 均截止于封存 holdout 前。
- 4H strict causal breakout/acceptance/first-pullback lifecycle + 15m BOS。
- 本轮只有 semantic diagnostic 和视觉门；execution/closed trade 为空。

## Balanced 主信号

- events / unique: 34 / 34
- 4h / 12h median signed return: 0.0732% / -0.0317%
- +1R-first / invalidation-first: 55.88% / 35.29%
- median / p90 signal-to-level ATR: 1.033828013692117 / 1.4529582362783384
- confirmation chase / second pullback / late extension: 26.47% / 17.65% / 58.82%
- causality audit: `pass`
- execution: `not_run_signal_gate_failed`

## Setup 对照

| setup | rows | unique | 4h median | 12h median | +1R first | invalidation first |
|---|---:|---:|---:|---:|---:|---:|
| strict_level_retest_v1 | 47 | 47 | 0.1493% | 0.3982% | 57.45% | 38.30% |
| strict_shallow_pullback_v1 | 75 | 75 | -0.0032% | 0.1904% | 33.33% | 29.33% |
| strict_shallow_pullback_v2_balanced | 34 | 34 | 0.0732% | -0.0317% | 55.88% | 35.29% |
| strict_shallow_pullback_v2_clean | 9 | 9 | -0.5293% | -0.0133% | 44.44% | 44.44% |

## Physical Candidate Funnel

- level alternatives before dedup: 16864
- physical candidates: 323
- `accepted`: 7
- `accepted_with_visual_risk`: 27
- `bos_failed_before_confirmation`: 1
- `bos_no_confirmation`: 39
- `confirmation_chase_hard_cap`: 5
- `deep_reentry_inside_range`: 45
- `late_or_second_pullback`: 1
- `post_breakout_extension_too_far`: 103
- `pullback_too_deep`: 68
- `signal_outside_development_window`: 27

## 分组

| dimension | value | n | 4h median | 12h median |
|---|---|---:|---:|---:|
| asset | BTC-USDT-SWAP | 87 | -0.003194916532810746 | -0.20811138518041952 |
| asset | ETH-USDT-SWAP | 78 | 0.21180851630656794 | 0.5622382022726058 |
| direction | long | 109 | 0.1492859376169694 | 0.1381411499777684 |
| direction | short | 56 | -0.1699897463013458 | 0.2120197744377279 |
| overall | all | 165 | 0.030716723549483734 | 0.19038200856382187 |
| setup | strict_level_retest_v1 | 47 | 0.1492859376169694 | 0.3981972292643034 |
| setup | strict_shallow_pullback_v1 | 75 | -0.003194916532810746 | 0.19038200856382187 |
| setup | strict_shallow_pullback_v2_balanced | 34 | 0.07318135940228518 | -0.031730944444490525 |
| setup | strict_shallow_pullback_v2_clean | 9 | -0.5293159609120598 | -0.013305665996105645 |

## 限制

本轮不是交易绩效；visual score 仅用于诊断和图审，不参与过滤。未优化 confirmation、exit、sizing、quality gate、RiskEngine 或成本参数。
