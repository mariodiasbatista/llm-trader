#!/usr/bin/env python3
"""
LLM Trader — Claude + Alpaca automated trading bot

Commands:
  status          Account overview
  check           All positions with stop floors and gaps
  trailing        Run one trailing stop check cycle
  scheduler       Start the automated scheduler (blocking)
  smart-money     Fetch recent politician trades
  analyze         AI analysis: Capitol Trades → Claude → execute strategy
  performance     Compare TRAILING_STOP vs WHEEL strategy P&L
  summary         End-of-day portfolio summary
  wheel <TICKER>  Start The Wheel on a stock manually

Examples:
  python main.py status
  python main.py check
  python main.py trailing
  python main.py analyze
  python main.py analyze --politicians "McCaul" "Pelosi" --days 14 --dry-run
  python main.py performance
  python main.py smart-money --politician "McCaul" --days 30
  python main.py wheel AAPL --contracts 2
  python main.py scheduler
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent


def run_script(script: str, extra_args: list = None):
    cmd = [sys.executable, str(BASE / "scripts" / script)]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(cmd)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0].lower()
    rest = args[1:]

    if command == "status":
        from core.alpaca import get_account
        acct = get_account()
        print(f"\nStatus          : {acct.status}")
        print(f"Portfolio Value : ${float(acct.portfolio_value):,.2f}")
        print(f"Cash            : ${float(acct.cash):,.2f}")
        print(f"Buying Power    : ${float(acct.buying_power):,.2f}")
        print(f"Day Trades      : {acct.daytrade_count}")
        print(f"PDT             : {acct.pattern_day_trader}\n")

    elif command == "check":
        run_script("check_positions.py")

    elif command == "trailing":
        run_script("run_trailing_stop.py")

    elif command == "scheduler":
        from scheduler.market_scheduler import start
        start()

    elif command == "smart-money":
        run_script("smart_money_report.py", rest)

    elif command == "summary":
        run_script("daily_summary.py")

    elif command == "analyze":
        run_script("analyze_and_trade.py", rest)

    elif command == "performance":
        run_script("strategy_performance.py")

    elif command == "wheel":
        run_script("setup_wheel.py", rest)

    else:
        print(f"Unknown command: {command}\n")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
