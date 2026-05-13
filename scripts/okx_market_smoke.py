from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_system.data.okx_cli import OkxCliMarketData


def main() -> None:
    client = OkxCliMarketData(okx_command=r"C:\Users\85394\AppData\Roaming\npm\okx.cmd")
    for inst_id in ("BTC-USDT", "ETH-USDT", "XAUT-USDT"):
        ticker = client.get_ticker(inst_id)
        print(f"{ticker.inst_id}: last={ticker.last} 24h_high={ticker.high_24h} 24h_low={ticker.low_24h}")


if __name__ == "__main__":
    main()
