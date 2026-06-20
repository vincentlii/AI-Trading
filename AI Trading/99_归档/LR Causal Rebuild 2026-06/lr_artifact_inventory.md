# LR Artifact Inventory

## 结论

本次为纯只读分析。没有重跑 scanner、Entry Tournament 或 holdout，没有生成新交易。以下 hash 均为本次读取时的 SHA-256。

## Multi-Timeframe + VPA

根目录：`storage/research_runs/liquidity_reversal/multitimeframe_vpa_v1/multitimeframe_events_development_2020-12-31_2024-11-30`

| Artifact | SHA-256 | 层级 | 用途 | 重跑 |
|---|---|---|---|---|
| `artifact_index.json` | `8467a314bb1d3d979f4a220b90048594ca5f18619753cd8d5313eead5d10af97` | index | 完整性与 lineage | 否 |
| `run_manifest.json` | `aca13dbf0d8e2e987ad7207b3a827772e25c79d71f4b8ea216c3d4a17cfd68c0` | manifest | 数据边界、schema、配置 | 否 |
| `lr_multitimeframe_event_result.json` | `dc276deaf3521876ff73ce30a5ce86744b4ce07c03c423dd7b76265be01a1580` | result | 运行边界与总数 | 否 |
| `level_rows.jsonl` | `b3a66deb5b59d766828f62aef71faf2f0e4732a6158fb19e15ab68ee724299e6` | row-level | causal level 定义 | 否 |
| `event_rows.jsonl` | `306c812a43a5a1852e92d16d04a1c3021a3c8ce74be4772a3cf950dc1590126e` | row-level | event、level、span、时间 | 否 |
| `vpa_feature_rows.jsonl` | `9f633b70c270df11c0eea5bf3d34255b52edde3fd0c698561833bb132c6db5fa` | row-level | causal VPA features | 否 |
| `diagnostic_label_rows.jsonl` | `2f3246f0fd33b932fa33229b2b4ff9c0905f70c2d02addade7d56090c4119d6f` | row-level | post-signal diagnostic labels | 否 |
| `anatomy_rows.jsonl` | `7a18cedc05c3dadfe8ebb0a0a60f60c8f17aad131ebdb8831965fd17cdae4c94` | row-level | forward R、MFE/MAE、path order | 否 |
| `summary_rows.jsonl` | `f8eb8d2a8f2d5b931932e8da1cd4de13d310293ab170e86dc17fefbb86d039e1` | summary | 原始汇总交叉检查 | 否 |
| `causality_audit.json` | `d97c39eeedcbbfb5c255ef6aefa030c9ad3eece00970b710d06e2aac6a0dfde7` | audit | no-lookahead、holdout、determinism | 否 |
| `lr_multitimeframe_vpa_causal_event_report.md` | `affd2dd6e00bb3b4598105f5885be79913f016717eb1a83d86939d55ebc98c51` | report | 已有研究结论 | 否 |

## Causal Entry Tournament v2

根目录：`storage/research_runs/liquidity_reversal/entry_tournament_v2/entry_tournament_development_2020-12-31_2024-11-30`

| Artifact | SHA-256 | 层级 | 用途 | 重跑 |
|---|---|---|---|---|
| `artifact_index.json` | `71d715e5fba12c8937d37a8c9b6e01d7ee816378c8d3830312df9bd626f3d4c7` | index | 完整性与 lineage | 否 |
| `run_manifest.json` | `a75d00f92142acc2efa958baae2ce5bf31681b16d4bc3fa5d9afc25b7fa26d10` | manifest | source schema、entry/cost/risk 边界 | 否 |
| `lr_entry_tournament_result.json` | `183796a37bb9a3a28df9388fbee4a97620bb54ad49cbf46c7682e52ae22406b4` | result | 漏斗与无 winner 状态 | 否 |
| `candidate_rows.jsonl` | `e9c5f183f1f20d443b74003c57ce2cb7edfcea4a8b2e9b607abeb3bb440e03c4` | row-level | order decision、fill/missed、entry geometry | 否 |
| `filter_results.jsonl` | `565eebbf61dbd5d0da41aed219792222431e5d40c1611e58a363ed43f3d07558` | row-level | RiskEngine/admission 拒绝 | 否 |
| `execution_rows.jsonl` | `361fa481c1c5de1e294fcc613cfbe39f189292e51d6a3e28e52b23d302d7c42e` | row-level | 真实 entry/stop/cost/RiskEngine | 否 |
| `variant_closed_trade_rows.jsonl` | `361fa481c1c5de1e294fcc613cfbe39f189292e51d6a3e28e52b23d302d7c42e` | row-level | proposal-only closed trades | 否 |
| `variant_summary_rows.jsonl` | `74db60b9ef8138d043e5f207f097a05e9e2000f9bf9e3fd451bbb98d50c69032` | summary | variant/family/cost 汇总 | 否 |
| `robustness_rows.jsonl` | `0d47e7893ffd47254772acfa58392bd025c8a6f79100468a805b2301703df2e8` | summary | stress/harsh 成本 | 否 |
| `lr_entry_tournament_report.md` | `f096e4e3c711962cf18ab311e7fdbc0d92f4689e2f349e20342bebf25e2b1ee1` | report | 已有 tournament 结论 | 否 |

## 边界检查

- Multi-Timeframe causality audit：`pass`，`0` violations，`holdout_accessed=false`。
- Multi-Timeframe 仅是 diagnostic event evidence；其 `execution_rows` 与 `closed_trade_rows` 为空，不得解释为交易绩效。
- Tournament v2 仅使用 `cost_tier=base` 的 `closed_trade=true` rows 归因实际执行；stress/harsh 只作已有稳健性背景。
- Tournament v2 没有 selected winner，Full Audit 状态仍是 `not_run_no_selected_variant`。
- Restricted Variant B 继续 suspended，本次未读取其绩效作为证据。
