from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.config import load_backtest_preset
from trading_system.backtest.layered_pipeline import run_layered_proposal
from trading_system.data.history import DuckDbCandleRepository

def main():
    base_preset_path = PROJECT_ROOT / "configs/presets/btc_eth_swap_lr_formal.toml"
    base_strategy_path = PROJECT_ROOT / "configs/strategies/trend_price_volume_lr_formal.toml"
    db_path = PROJECT_ROOT / "storage/history.duckdb"
    cache_dir = PROJECT_ROOT / "storage/backtest_cache_lr_research"
    
    repository = DuckDbCandleRepository(db_path)
    
    with open(base_preset_path, "r", encoding="utf-8") as f:
        preset_text = f.read()
        
    with open(base_strategy_path, "r", encoding="utf-8") as f:
        strategy_text = f.read()
        
    r_multiples = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    
    results = []
    
    for r in r_multiples:
        print(f"\n--- Running LR target_r = {r} ---")
        
        # Modify strategy text by inserting lr_target_r right after the section header
        strat_copy = strategy_text.replace(
            "[parameters.liquidity_reversal.assets.BTC]\n",
            f"[parameters.liquidity_reversal.assets.BTC]\nlr_target_r = {r}\n"
        ).replace(
            "[parameters.liquidity_reversal.assets.ETH]\n",
            f"[parameters.liquidity_reversal.assets.ETH]\nlr_target_r = {r}\n"
        )
            
        temp_strat_path = PROJECT_ROOT / f"configs/strategies/temp_lr_{r}.toml"
        with open(temp_strat_path, "w", encoding="utf-8") as f:
            f.write(strat_copy)
            
        # Modify preset text
        preset_copy = preset_text.replace(
            'strategy = "configs/strategies/trend_price_volume_lr_formal.toml"',
            f'strategy = "configs/strategies/temp_lr_{r}.toml"'
        )
        
        temp_preset_path = PROJECT_ROOT / f"configs/presets/temp_lr_preset_{r}.toml"
        with open(temp_preset_path, "w", encoding="utf-8") as f:
            f.write(preset_copy)
            
        # Load preset and run
        preset = load_backtest_preset(temp_preset_path)
        layered = run_layered_proposal(
            repository=repository,
            preset=preset,
            mode="full_backtest",
            cache_dir=cache_dir,
            cost_tiers=("base",),
            force_execution=True,
        )
        
        # Collect results
        for row in layered.summary_rows:
            if row["cost_tier"] == "base" and row["profile"] == "C":
                results.append({
                    "Target R": r,
                    "Asset": row["asset"],
                    "Trades": row["trades"],
                    "Win Rate": f"{row['win_rate']:.2%}",
                    "Net R": row["net_r"],
                    "Max DD R": row["max_dd_r"],
                    "Expectancy R": row["expectancy_r"],
                    "Profit Factor": row["profit_factor"],
                })
                
        # Cleanup temp files
        temp_strat_path.unlink(missing_ok=True)
        temp_preset_path.unlink(missing_ok=True)
                
    print("\n\n--- RESEARCH RESULTS ---")
    print(f"{'Target R':<10} {'Asset':<8} {'Trades':<8} {'Win Rate':<10} {'Net R':<10} {'Max DD R':<10} {'Exp R':<8} {'PF':<8}")
    for res in results:
        print(f"{res['Target R']:<10} {res['Asset']:<8} {res['Trades']:<8} {res['Win Rate']:<10} {res['Net R']:<10.2f} {res['Max DD R']:<10.2f} {res['Expectancy R']:<8.2f} {res['Profit Factor']:<8.2f}")

if __name__ == "__main__":
    main()
