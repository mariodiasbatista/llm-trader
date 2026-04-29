#!/usr/bin/env python3
"""
AI-Powered Trading Analysis Pipeline
Flow: Capitol Trades data → Claude Opus 4.7 decision → Strategy execution → Performance log

Claude decides: TRAILING_STOP (buy shares + trailing floor) or WHEEL (sell puts for premium)
or SKIP (pass on the signal). Every decision and outcome is logged for performance comparison.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import argparse
from datetime import datetime

from core.alpaca import get_account, get_positions, market_buy, get_latest_price, trailing_stop_sell
from core.logger import load_state, save_state, log_trade, log
from core.notifier import is_configured as telegram_configured, send_message, send_insufficient_funds_alert
from strategies.smart_money import fetch_trades, fetch_large_trades
from strategies.wheel import start_wheel
from agents.claude_advisor import get_recommendation


def _days_since(tx_date_str: str) -> int:
    try:
        return (datetime.now() - datetime.strptime(tx_date_str, "%Y-%m-%d")).days
    except Exception:
        return 999


def main():
    parser = argparse.ArgumentParser(description="AI Capitol Trades analyzer")
    parser.add_argument("--politicians", "-p", nargs="+",
                        help="Filter by politician name (default: watch ALL trades by size)")
    parser.add_argument("--min-disclosure-value", type=int, default=0,
                        help="Minimum $ value of politician's disclosed trade (default: 0 = all)")
    parser.add_argument("--days", "-d", type=int, default=7, help="Days of history to scan")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show Claude's decisions without executing trades")
    parser.add_argument("--source", choices=["auto", "api", "web"], default="auto",
                        help="Data source: auto (default), api, or web scrape")
    parser.add_argument("--stop-floor", type=float, default=None,
                        help="Native Alpaca trailing stop %% after buy (e.g. 5 = 5%%). "
                             "If omitted, uses polling logic via 'python main.py trailing'")
    args = parser.parse_args()

    if args.politicians:
        # Politician-specific mode
        log.info(f"Scanning Capitol Trades for politicians: {', '.join(args.politicians)}")
        raw = []
        for pol in args.politicians:
            raw.extend(fetch_trades(days_back=args.days, politician_name=pol,
                                    source=args.source))
        buy_signals = [t for t in raw if "buy" in t.get("txType", "").lower()]
    else:
        # Size-based mode — catches important moves regardless of politician identity
        log.info(f"Scanning ALL Capitol Trades ≥ ${args.min_disclosure_value:,} (last {args.days}d)")
        buy_signals = fetch_large_trades(min_size=args.min_disclosure_value, days_back=args.days,
                                         source=args.source)

    log.info(f"{len(buy_signals)} buy signals to analyze")

    if not buy_signals:
        print("\nNo buy signals found for the selected politicians and timeframe.\n")
        return

    acct = get_account()
    buying_power = float(acct.buying_power)
    existing_tickers = [p.symbol for p in get_positions()]
    state = load_state()
    results = []
    tokens_saved_total = 0

    for trade in buy_signals:
        ticker = trade.get("asset", {}).get("ticker", "")
        if not ticker or not ticker.replace(".", "").isalpha():
            continue

        # Skip already-processed signals
        trade_key = (
            f"{trade.get('txDate')}_{ticker}_{trade.get('politician', {}).get('id', '')}"
        )
        if trade_key in state.get("copied_trades", []):
            log.info(f"[{ticker}] Already processed — skipping")
            continue

        try:
            price = get_latest_price(ticker)
        except Exception as e:
            log.warning(f"[{ticker}] Cannot get price: {e}")
            continue

        market_ctx = {
            "price": price,
            "buying_power": buying_power,
            "existing_positions": existing_tickers,
            "days_since_disclosure": _days_since(trade.get("txDate", "")),
        }

        log.info(f"[{ticker}] Asking Claude for strategy recommendation...")
        rec = get_recommendation(trade, market_ctx)

        strategy = rec.get("strategy", "SKIP")
        confidence = rec.get("confidence", 0)
        reasoning = rec.get("reasoning", "")
        position_pct = rec.get("suggested_position_size_pct", 0.05)
        key_risk = rec.get("key_risk", "")
        politician_name = trade.get("politician", {}).get("name", "Unknown")
        cache_hit = rec.get("_cache_hit", False)
        tokens_saved = rec.get("_tokens_saved", 0)
        tokens_saved_total += tokens_saved

        result = {
            "ticker": ticker,
            "politician": politician_name,
            "tx_date": trade.get("txDate"),
            "strategy": strategy,
            "confidence": confidence,
            "reasoning": reasoning,
            "price": price,
            "executed": False,
        }

        cache_str = " [cache ✓]" if cache_hit else ""
        print(f"\n{'─'*60}")
        print(f"  Ticker     : {ticker}")
        print(f"  Politician : {politician_name}")
        print(f"  Price      : ${price:.2f}")
        print(f"  Strategy   : {strategy} ({confidence}% confidence){cache_str}")
        print(f"  Reasoning  : {reasoning}")
        print(f"  Risk       : {key_risk}")

        if strategy == "SKIP":
            log.info(f"[{ticker}] SKIP — {reasoning[:80]}")
            results.append(result)
            continue

        if args.dry_run:
            print(f"  [DRY RUN]  : Would execute {strategy} — skipping actual trade")
            results.append(result)
            continue

        # Execute immediately
        shares_budget = buying_power * position_pct
        shares_to_buy = max(1, int(shares_budget / price))
        cost = shares_to_buy * price

        if buying_power < cost:
            log.warning(f"[{ticker}] Skipping — need ${cost:.0f}, have ${buying_power:.0f}")
            if telegram_configured():
                send_insufficient_funds_alert(ticker, cost, buying_power)
            results.append(result)
            continue

        try:
            if strategy == "TRAILING_STOP":
                market_buy(ticker, shares_to_buy)
                stop_note = ""
                if args.stop_floor is not None:
                    trailing_stop_sell(ticker, shares_to_buy, args.stop_floor)
                    stop_note = f" + native trailing stop {args.stop_floor}%"
                log_trade(
                    "AI_BUY_TRAILING", ticker, shares_to_buy, price,
                    f"strategy=TRAILING_STOP confidence={confidence}% "
                    f"pol={politician_name} reasoning={reasoning[:60]}"
                    + (f" stop_floor={args.stop_floor}%" if args.stop_floor else "")
                )
                buying_power -= cost
                state.setdefault("copied_trades", []).append(trade_key)
                result.update({"executed": True, "shares": shares_to_buy})
                print(f"  EXECUTED   : Bought {shares_to_buy} shares @ ${price:.2f}{stop_note}")
                if telegram_configured():
                    send_message(
                        f"✅ *Bought* `{ticker}` — {shares_to_buy} shares @ ${price:.2f}{stop_note}\n"
                        f"Strategy: TRAILING_STOP ({confidence}%) | {politician_name}"
                    )

            elif strategy == "WHEEL":
                wheel_result = start_wheel(ticker, contracts=1)
                log_trade(
                    "AI_START_WHEEL", ticker, 1, price,
                    f"strategy=WHEEL confidence={confidence}% "
                    f"pol={politician_name} put_strike={wheel_result['put_strike']}"
                )
                state.setdefault("copied_trades", []).append(trade_key)
                result.update({"executed": True, "put_strike": wheel_result.get("put_strike")})
                print(f"  EXECUTED   : Wheel started — put @ ${wheel_result['put_strike']:.2f}")
                if telegram_configured():
                    send_message(
                        f"✅ *Wheel started* `{ticker}` — put @ ${wheel_result['put_strike']:.2f}\n"
                        f"Strategy: WHEEL ({confidence}%) | {politician_name}"
                    )

        except Exception as e:
            log.error(f"[{ticker}] Execution failed: {e}")
            if telegram_configured():
                send_message(f"❌ Execution failed for `{ticker}`: {e}")

        results.append(result)

    save_state(state)

    # Print run summary
    executed = [r for r in results if r.get("executed")]
    skipped = [r for r in results if r.get("strategy") == "SKIP"]
    trailing = [r for r in executed if r.get("strategy") == "TRAILING_STOP"]
    wheel = [r for r in executed if r.get("strategy") == "WHEEL"]

    print(f"\n{'═'*60}")
    print(f"  RUN SUMMARY")
    print(f"  Signals analyzed    : {len(results)}")
    print(f"  Executed trades     : {len(executed)}")
    print(f"    → Trailing Stop   : {len(trailing)}")
    print(f"    → Wheel           : {len(wheel)}")
    print(f"  Skipped by Claude   : {len(skipped)}")
    if tokens_saved_total:
        print(f"  Cache tokens saved  : {tokens_saved_total:,} (≈90% cost reduction on system prompt)")
    print(f"{'═'*60}\n")
    print("Run 'python main.py performance' to compare strategy results.")


if __name__ == "__main__":
    main()
