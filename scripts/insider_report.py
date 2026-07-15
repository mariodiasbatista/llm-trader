#!/usr/bin/env python3
"""Preview SEC EDGAR Form 4 insider buy signals without executing trades."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from strategies.sec_insiders import fetch_insider_buys


def main():
    parser = argparse.ArgumentParser(description="Preview SEC insider buy signals")
    parser.add_argument("--days", "-d", type=int, default=1,
                        help="Days of Form 4 filings to scan (default: 1)")
    parser.add_argument("--min-value", type=int, default=100_000,
                        help="Minimum transaction value in $ (default: 100000)")
    parser.add_argument("--max-filings", type=int, default=200,
                        help="Max Form 4 filings to parse (default: 200)")
    parser.add_argument("--all-roles", action="store_true",
                        help="Include all insider roles, not just CEO/CFO/Director")
    args = parser.parse_args()

    print(f"\nFetching SEC Form 4 insider buys — last {args.days}d, min ${args.min_value:,}...")
    signals = fetch_insider_buys(
        days_back=args.days,
        min_transaction_value=args.min_value,
        max_filings=args.max_filings,
        require_high_conviction=not args.all_roles,
    )

    if not signals:
        print("No insider buy signals found.\n")
        return

    print(f"\nFound {len(signals)} insider buy signals:\n")
    print(f"  {'Ticker':<8} {'Filed':<12} {'Trade':<12} {'Insider':<30} {'Role':<25} {'Value':>12}")
    print("  " + "─" * 105)

    for s in sorted(signals, key=lambda x: x.get("_transaction_value", 0), reverse=True):
        ticker   = s.get("asset", {}).get("ticker", "?")
        pub_date = s.get("publishedDate", "?")
        tx_date  = s.get("txDate", "?")
        name     = s.get("politician", {}).get("name", "?")[:28]
        role     = s.get("_insider_role", "?")[:23]
        value    = s.get("_transaction_value", 0)
        print(f"  {ticker:<8} {pub_date:<12} {tx_date:<12} {name:<30} {role:<25} ${value:>11,.0f}")

    print()


if __name__ == "__main__":
    main()
