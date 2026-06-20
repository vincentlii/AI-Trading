---
name: trading-system-obsidian-sync
description: Use when synchronizing this trading project's Obsidian vault after research, audit, cleanup, planning, architecture, validation, or agent workflow changes.
---

# Trading System Obsidian Sync

## Purpose

Keep `AI Trading/` as the single long-term knowledge source. Root docs stay as thin entry points. Chat summaries and temporary reports are not authoritative until distilled into Obsidian.

## Inputs

- Completed task or research decision.
- Affected modules, strategies, or workflow boundaries.
- Artifact paths and run ids.
- Current status labels.
- Verification commands and results.

## Write Routes

- Project entry and risk boundaries: `AI Trading/00_项目驾驶舱/`
- Long-term facts, architecture, conventions, validation: `AI Trading/01_长期记忆/`
- Roadmap, maturity, backlog: `AI Trading/02_路线与进度/`
- Strategy specs and research: `AI Trading/03_策略研究中心/`
- Data and market structure: `AI Trading/04_数据与市场结构/`
- Backtest, risk, P6, proposal: `AI Trading/05_回测风控与模拟盘/`
- Architecture decisions: `AI Trading/06_决策记录/`
- Agent collaboration and skills: `AI Trading/07_Agent协作/`
- Reviews and reports: `AI Trading/08_复盘与报告/`
- RAG / MCP planning: `AI Trading/09_RAG与MCP准备/`

## Workflow

1. Check existing pages before adding new ones.
2. Update current status, not only historical narrative.
3. Mark old PR artifacts, legacy wrappers, and failed variants as historical reference when needed.
4. Keep strategy status labels explicit: formal candidate, diagnostic candidate, backlog, frozen, or stopped.
5. Add artifact paths only when they are needed for recovery or audit.
6. Keep Paper Review Loop and Hermes-like evolution as future P6+ planning unless explicitly started.
7. Run a grep check for forbidden state flips before finishing.
8. When research stops, preserve a machine-readable evidence map and cleanup manifest, archive detailed stage reports, and update every active page that still claims a superseded candidate status.

## Forbidden

- Do not mark diagnostic snapshots as formal candidates.
- Do not imply P6 or live trading readiness.
- Do not rewrite LR final evidence.
- Do not delete historical evidence when invalidating it; add a supersession notice and keep the original artifacts read-only.
- Do not create many parallel v1 pages when an existing page can be updated.
