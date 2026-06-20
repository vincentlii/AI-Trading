# LR Causal Rebuild Invalidation Notice

## 结论

2026-06-21 起，Restricted Variant B 不再是 formal research candidate。原 final evidence 保持原样，只作为历史审计记录；本通知不重写历史报告。

正确 bar-close、entry、path-order、成本和 RiskEngine 语义下：

- historical causal repair：5,078 笔，`total_net_R=-356.64`，`PF=0.722`。
- rebuilt 1H event + 15m confirmation：223 笔，`total_net_R=-23.26`，`PF=0.724`。
- v3 confirmation 的表面 path-order 改善主要来自 confirmation chase 与 R geometry。
- holdout 未访问，`live_trading_enabled=false`。

当前权威状态见 `AI Trading/03_策略研究中心/策略族/01_liquidity_sweep_reclaim.md`；机器快照见同目录 `lr_research_stop_snapshot.json`。
