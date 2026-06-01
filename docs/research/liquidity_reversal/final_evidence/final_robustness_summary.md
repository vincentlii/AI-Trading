# Final Robustness Summary

## 结论

Restricted Variant B with `portfolio_heat_cap=0.05` is the final PR12 candidate.

| Cost tier | closed | total_R | net_R avg | PF |
|---|---:|---:|---:|---:|
| base | 183 | 85.070 | 0.465 | 7.80 |
| stress | 183 | 75.920 | 0.415 | 5.86 |
| harsh | 183 | 63.110 | 0.345 | 4.14 |
| extreme harsh | 183 | 48.470 | 0.265 | 2.91 |

## Exposure

| 指标 | unrestricted Variant B | Restricted Variant B |
|---|---:|---:|
| closed | 198 | 183 |
| max_concurrent_positions | 22 | 10 |
| same_direction_overlap_count | 558 | 303 |
| portfolio_heat_max | 0.11 | 0.05 |

## Profile

- C profile: formal scope。
- B profile: diagnostic-only。
- B/C candidate count is balanced, but B formal approval is much lower.

## Source

- `storage/backtest_cache/pr11h_fix/lr_robustness_fix_result.json`
- `storage/backtest_cache/pr11h_fix/lr_robustness_fix_report.md`
