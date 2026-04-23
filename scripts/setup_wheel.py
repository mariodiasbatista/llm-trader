#!/usr/bin/env python3
"""Start The Wheel strategy on a stock (interactive)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from core.alpaca import get_latest_price, get_account
from strategies.wheel import start_wheel


def main():
    parser = argparse.ArgumentParser(description="Start Wheel Strategy on a stock")
    parser.add_argument("symbol", help="Ticker symbol e.g. AAPL")
    parser.add_argument("--contracts", "-c", type=int, default=1,
                        help="Number of option contracts (1 contract = 100 shares)")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    acct = get_account()
    price = get_latest_price(symbol)
    cash_needed = price * 100 * args.contracts
    cash_available = float(acct.cash)

    print(f"\n{symbol} current price : ${price:.2f}")
    print(f"Cash needed (to secure put) : ${cash_needed:,.2f}")
    print(f"Cash available              : ${cash_available:,.2f}")

    if cash_available < cash_needed:
        print(f"\nWarning: You don't have enough cash to fully secure this put.")
        proceed = input("Continue anyway? (y/N): ").strip().lower()
        if proceed != "y":
            print("Aborted.")
            return

    confirm = input(
        f"\nSell {args.contracts} cash-secured put(s) on {symbol}? (y/N): "
    ).strip().lower()

    if confirm == "y":
        result = start_wheel(symbol, contracts=args.contracts)
        print(f"\nWheel started on {symbol}")
        print(f"  Stage   : {result['stage']}")
        print(f"  Strike  : ${result['put_strike']:.2f}")
        print(f"  Expiry  : {result['expiry']}")
        print(f"  Option  : {result['option_symbol']}\n")
    else:
        print("Aborted.")


if __name__ == "__main__":
    main()
