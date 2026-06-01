# Strategy Adapters

## Conclusion

Strategy adapters are the strategy-facing integration layer for `research_pipeline`.

PR 10 only connects `liquidity_reversal` as a proposal-only adapter for read-only artifact, aggregation, edge, sizing, smoke-plan, and regression summary workflows.

## Liquidity Reversal Status

- `status = proposal_only`
- `proposal_only = true`
- `formal_conclusion_enabled = false`
- supported assets: `BTC`, `ETH`
- supported market: `SWAP`
- supported profiles: `B`, `C`
- primary combo: `displacement_after_reclaim`
- smoke-ready combos: `CHOCH true`, `displacement_after_reclaim`

## Boundaries

PR 10 does not migrate or run:

- fresh scanner;
- filter replay;
- real sizing engine;
- execution replay;
- full backtest.

The adapter keeps these methods disabled with `NotImplementedError`.

## Capped Sizing

`notional_capped_risk_based` remains proposal-only. Proposal approval is not formal approval.

## Roadmap

LR proposal tuning and validation remain PR 11.

Legacy cleanup, merge to master, and stable tagging remain PR 12.
