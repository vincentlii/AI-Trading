# LR Causal Rebuild Cleanup Manifest

## 结论

2026-06-21 完成 LR 停止归档。保留 6 个关键完整运行，删除 11 个被替代运行、一个空 smoke cache 和一个拒绝访问临时目录，共释放已计量 research/cache 数据 277,970,768 bytes。

## KEEP

- `storage/research_runs/liquidity_reversal/final/`
- `storage/research_runs/liquidity_reversal/setup_specific_v2/`
- `storage/research_runs/liquidity_reversal/causal_rebuild_v4/`
- `storage/research_runs/liquidity_reversal/entry_tournament_v2/`
- `storage/research_runs/liquidity_reversal/multitimeframe_vpa_v1/`
- `storage/research_runs/liquidity_reversal/restricted_variant_b_causal_retest_v1/`
- `docs/research/liquidity_reversal/final_evidence/`
- `AI Trading/99_归档/LR Causal Rebuild 2026-06/`

## DELETE COMPLETED

- `causal_rebuild_v1`
- `causal_rebuild_v1_smoke`
- `causal_rebuild_v1_smoke_fix`
- `causal_rebuild_v2`
- `causal_rebuild_v3_smoke`
- `causal_rebuild_v4_smoke`
- `entry_tournament_v1_smoke`
- `entry_tournament_v2_smoke`
- `multitimeframe_event_smoke_a`
- `multitimeframe_event_smoke_b`
- `setup_specific_v1`
- `storage/backtest_cache/lr_formal_smoke_verify`
- `tmplj5l5pa9`

## 边界

- Holdout 未访问。
- 历史 final evidence 未重写，只新增失效通知。
- Stashes 和 `research/lr-exits` 分支保留为回滚点。
- `.obsidian/workspace.json` 和无关用户改动未纳入清理或提交。
