#!/usr/bin/env python3
"""Fetch and display recent politician stock disclosures from Capitol Trades."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.smart_money import fetch_trades, format_summary


def main():
    parser = argparse.ArgumentParser(description="Smart Money Tracker")
    parser.add_argument("--politician", "-p", help="Filter by politician name (partial match)")
    parser.add_argument("--days", "-d", type=int, default=7, help="Days back to look (default 7)")
    parser.add_argument("--buy-only", action="store_true", help="Show only buy transactions")
    parser.add_argument("--source", choices=["auto", "api", "web"], default="auto",
                        help="Data source: auto (default), api, or web scrape")
    args = parser.parse_args()

    print(f"\nFetching last {args.days} days of disclosures" +
          (f" for '{args.politician}'" if args.politician else "") +
          f" [source={args.source}]...\n")

    trades = fetch_trades(days_back=args.days, politician_name=args.politician,
                          source=args.source)

    if args.buy_only:
        trades = [t for t in trades if "buy" in t.get("txType", "").lower()]

    print(format_summary(trades))
    print(f"\nTotal: {len(trades)} trades\n")


if __name__ == "__main__":
    main()
