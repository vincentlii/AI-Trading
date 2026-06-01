# Stage 7 Smoke Full Backtest Framework

- combo=CHOCH true
- selected_candidates=376
- cost_tiers=base,stress,harsh
- status=framework_only
- proposal_only=true
- formal_conclusion_enabled=false

## Required Outputs
- cost_tier
- fee
- spread
- slippage
- funding_paid_or_received
- mae_R
- mfe_R
- exit_reason
- max_drawdown
- same_bar_ambiguous_count
- direction
- asset
- profile

## Grouped Preview
- base BTC C long: selected=49 closed=49 MFE=0.5772014665171988 net_R=0.10506741067817911 exit=time_cut_exit same_bar=0
- base BTC C short: selected=36 closed=36 MFE=0.33590941976106925 net_R=-0.029918728041823914 exit=time_cut_exit same_bar=0
- base ETH B long: selected=6 closed=6 MFE=0.8979946939342042 net_R=0.361115918066409 exit=time_exit same_bar=0
- base ETH B short: selected=6 closed=6 MFE=0.31072073710979625 net_R=-0.1448935794459425 exit=time_cut_exit same_bar=0
- base ETH C long: selected=121 closed=121 MFE=0.9230572411219139 net_R=0.3085579176324297 exit=time_cut_exit same_bar=0
- base ETH C short: selected=158 closed=158 MFE=0.5965366696258013 net_R=0.0940218917759998 exit=time_cut_exit same_bar=0
- harsh BTC C long: selected=49 closed=49 MFE=0.5772014665171988 net_R=0.10506741067817911 exit=time_cut_exit same_bar=0
- harsh BTC C short: selected=36 closed=36 MFE=0.33590941976106925 net_R=-0.029918728041823914 exit=time_cut_exit same_bar=0
- harsh ETH B long: selected=6 closed=6 MFE=0.8979946939342042 net_R=0.361115918066409 exit=time_exit same_bar=0
- harsh ETH B short: selected=6 closed=6 MFE=0.31072073710979625 net_R=-0.1448935794459425 exit=time_cut_exit same_bar=0
- harsh ETH C long: selected=121 closed=121 MFE=0.9230572411219139 net_R=0.3085579176324297 exit=time_cut_exit same_bar=0
- harsh ETH C short: selected=158 closed=158 MFE=0.5965366696258013 net_R=0.0940218917759998 exit=time_cut_exit same_bar=0
- stress BTC C long: selected=49 closed=49 MFE=0.5772014665171988 net_R=0.10506741067817911 exit=time_cut_exit same_bar=0
- stress BTC C short: selected=36 closed=36 MFE=0.33590941976106925 net_R=-0.029918728041823914 exit=time_cut_exit same_bar=0
- stress ETH B long: selected=6 closed=6 MFE=0.8979946939342042 net_R=0.361115918066409 exit=time_exit same_bar=0
- stress ETH B short: selected=6 closed=6 MFE=0.31072073710979625 net_R=-0.1448935794459425 exit=time_cut_exit same_bar=0
- stress ETH C long: selected=121 closed=121 MFE=0.9230572411219139 net_R=0.3085579176324297 exit=time_cut_exit same_bar=0
- stress ETH C short: selected=158 closed=158 MFE=0.5965366696258013 net_R=0.0940218917759998 exit=time_cut_exit same_bar=0

This framework does not run Stage 7 conclusions and does not formalize capped sizing.
# Stage 7 Smoke Full Backtest Framework

- combo=displacement_after_reclaim
- selected_candidates=137
- cost_tiers=base,stress,harsh
- status=framework_only
- proposal_only=true
- formal_conclusion_enabled=false

## Required Outputs
- cost_tier
- fee
- spread
- slippage
- funding_paid_or_received
- mae_R
- mfe_R
- exit_reason
- max_drawdown
- same_bar_ambiguous_count
- direction
- asset
- profile

## Grouped Preview
- base BTC C long: selected=18 closed=18 MFE=1.1316264078137872 net_R=0.47527491585737347 exit=time_exit same_bar=0
- base BTC C short: selected=12 closed=12 MFE=0.6470808455108953 net_R=0.14630985082063278 exit=time_exit same_bar=0
- base ETH B long: selected=2 closed=2 MFE=1.356594892669666 net_R=0.8045156651069025 exit=time_exit same_bar=0
- base ETH B short: selected=4 closed=4 MFE=0.3748394259384094 net_R=-0.14025174885659125 exit=time_cut_exit same_bar=0
- base ETH C long: selected=54 closed=54 MFE=1.3453037120492009 net_R=0.5629593224051315 exit=time_exit same_bar=0
- base ETH C short: selected=47 closed=47 MFE=0.8079428471951192 net_R=0.26513842180268266 exit=time_exit same_bar=0
- harsh BTC C long: selected=18 closed=18 MFE=1.1316264078137872 net_R=0.47527491585737347 exit=time_exit same_bar=0
- harsh BTC C short: selected=12 closed=12 MFE=0.6470808455108953 net_R=0.14630985082063278 exit=time_exit same_bar=0
- harsh ETH B long: selected=2 closed=2 MFE=1.356594892669666 net_R=0.8045156651069025 exit=time_exit same_bar=0
- harsh ETH B short: selected=4 closed=4 MFE=0.3748394259384094 net_R=-0.14025174885659125 exit=time_cut_exit same_bar=0
- harsh ETH C long: selected=54 closed=54 MFE=1.3453037120492009 net_R=0.5629593224051315 exit=time_exit same_bar=0
- harsh ETH C short: selected=47 closed=47 MFE=0.8079428471951192 net_R=0.26513842180268266 exit=time_exit same_bar=0
- stress BTC C long: selected=18 closed=18 MFE=1.1316264078137872 net_R=0.47527491585737347 exit=time_exit same_bar=0
- stress BTC C short: selected=12 closed=12 MFE=0.6470808455108953 net_R=0.14630985082063278 exit=time_exit same_bar=0
- stress ETH B long: selected=2 closed=2 MFE=1.356594892669666 net_R=0.8045156651069025 exit=time_exit same_bar=0
- stress ETH B short: selected=4 closed=4 MFE=0.3748394259384094 net_R=-0.14025174885659125 exit=time_cut_exit same_bar=0
- stress ETH C long: selected=54 closed=54 MFE=1.3453037120492009 net_R=0.5629593224051315 exit=time_exit same_bar=0
- stress ETH C short: selected=47 closed=47 MFE=0.8079428471951192 net_R=0.26513842180268266 exit=time_exit same_bar=0

This framework does not run Stage 7 conclusions and does not formalize capped sizing.
