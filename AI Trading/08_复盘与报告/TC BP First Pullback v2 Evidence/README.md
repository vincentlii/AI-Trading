# TC BP First Pullback v2 Evidence

本目录是 `tc_bp_strict_causal_smoke.v2` 的完整只读研究证据包，数据窗口为 2024-07-01 至 2024-11-30，BTC/ETH USDT SWAP，未读取封存 holdout。

## 阅读顺序

1. `tc_bp_strict_causal_smoke_v2_report.md`：结论和 setup 对照。
2. `run_manifest.json`：参数、决策、physical candidate funnel 和核心指标。
3. `causality_audit.json`：时间语义与 holdout 审计。
4. `tc_bp_strict_visual_review.html`：20笔 balanced 事件的 4H lifecycle + 15m BOS 双图审入口。
5. `event_rows.jsonl`、`pullback_candidate_rows.jsonl`、`visual_geometry_rows.jsonl`、`diagnostic_label_rows.jsonl`：row-level 复核材料。
6. `artifact_index.json`：文件 hash 与完整性记录。索引中的绝对路径是原运行机器路径；GitHub 阅读时以本目录相对路径为准。

## 证据边界

- 本轮是 semantic/directional diagnostic，不是正式交易绩效。
- `execution_rows.jsonl` 与 `closed_trade_rows.jsonl` 为空。
- visual score、未来收益和 path-order 都是 diagnostic，不得解释成可交易 feature。
- Decision 为 `semantic_filter_overfit_sample_collapse`；禁止据此进入 execution 或四年扫描。
