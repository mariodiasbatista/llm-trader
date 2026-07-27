#!/usr/bin/env python3
"""
AI-Powered Trading Analysis Pipeline
Flow: SEC EDGAR Form 4 insider buys → Claude decision → Strategy execution → Performance log

Claude decides: TRAILING_STOP (buy shares + trailing floor) or WHEEL (sell puts for premium)
or SKIP. Every decision and outcome is logged for performance comparison.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import argparse
from datetime import datetime

from core.alpaca import get_account, get_positions, market_buy, get_latest_price, trailing_stop_sell
from core.logger import load_state, save_state, log_trade, log, state_lock
from core.notifier import is_configured as telegram_configured, send_message, send_insufficient_funds_alert, escape_md
from strategies.sec_insiders import fetch_insider_buys
from strategies.wheel import start_wheel
from agents.claude_advisor import get_recommendation


def _days_since(date_str: str) -> int:
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return 999


def main():
    parser = argparse.ArgumentParser(description="AI SEC insider trades analyzer")
    parser.add_argument("--days", "-d", type=int, default=1,
                        help="Days of Form 4 filings to scan (default: 1)")
    parser.add_argument("--min-value", type=int, default=0,
                        help="Minimum $ value of insider's open-market purchase (default: from settings)")
    parser.add_argument("--max-filings", type=int, default=400,
                        help="Max Form 4 filings to parse per run (rate-limit cap, default: 200)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show Claude's decisions without executing trades")
    parser.add_argument("--all-roles", action="store_true",
                        help="Include all insider roles, not just CEO/CFO/Director (default: high-conviction only)")
    parser.add_argument("--stop-floor", type=float, default=None,
                        help="Native Alpaca trailing stop %% after buy (e.g. 5 = 5%%). "
                             "If omitted, uses polling logic via 'python main.py trailing'")
    args = parser.parse_args()

    _cfg_path = Path(__file__).parent.parent / "config" / "settings.json"
    _cfg = json.loads(_cfg_path.read_text())
    _analyze_cfg = _cfg.get("analyze", {})
    _insiders_cfg = _cfg.get("sec_insiders", {})

    size_up             = _analyze_cfg.get("size_up", False)
    max_position_usd    = _analyze_cfg.get("max_position_usd", None)
    stop_cooldown_days  = _analyze_cfg.get("stop_cooldown_days", 0)
    max_txdate_age_days = _analyze_cfg.get("max_txdate_age_days", 0)
    min_entry_price     = _analyze_cfg.get("min_entry_price", 0)

    min_value = args.min_value or _insiders_cfg.get("min_transaction_value", 100_000)
    require_high_conviction = not args.all_roles

    log.info(
        f"Scanning SEC EDGAR Form 4 filings — last {args.days}d, "
        f"min value ${min_value:,}, high-conviction={require_high_conviction}"
    )

    buy_signals = fetch_insider_buys(
        days_back=args.days,
        min_transaction_value=min_value,
        max_filings=args.max_filings,
        require_high_conviction=require_high_conviction,
    )

    log.info(f"{len(buy_signals)} insider buy signals to analyse")

    if not buy_signals:
        print("\nNo insider buy signals found for the selected timeframe.\n")
        return

    acct = get_account()
    buying_power     = float(acct.buying_power)
    open_positions   = get_positions()
    existing_tickers = [p.symbol for p in open_positions]
    position_value   = {p.symbol: float(p.qty) * float(p.current_price) for p in open_positions}
    state = load_state()

    def _mark_processed(key: str):
        """Persist a single trade_key to copied_trades immediately — survives mid-run crashes."""
        with state_lock():
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            fresh = load_state()
            if key not in fresh.get("copied_trades", []):
                fresh.setdefault("copied_trades", []).append(key)
            fresh["copied_trades"] = [
                k for k in fresh["copied_trades"] if k[:10] >= cutoff
            ]
            save_state(fresh)

    results = []
    tokens_saved_total = 0
    seen_this_run: set = set()
    stopped_out_dates = state.get("stopped_out", {})

    for trade in buy_signals:
        ticker = trade.get("asset", {}).get("ticker", "")
        if not ticker or not ticker.replace(".", "").isalpha():
            continue

        trade_key = (
            f"{trade.get('txDate')}_{ticker}_{trade.get('politician', {}).get('id', '')}"
        )
        if trade_key in state.get("copied_trades", []) or trade_key in seen_this_run:
            log.info(f"[{ticker}] Already processed — skipping")
            continue
        seen_this_run.add(trade_key)

        # Form 4 filing lag is max 2 business days — signals older than days+3 are stale.
        pub_date = trade.get("publishedDate") or trade.get("txDate", "")
        if _days_since(pub_date) > args.days + 3:
            log.info(f"[{ticker}] Signal too old (pub={pub_date}) — skipping")
            _mark_processed(trade_key)
            continue

        # Reject underlying trades older than max_txdate_age_days if configured.
        if max_txdate_age_days > 0:
            tx_date = trade.get("txDate", "")
            tx_age = _days_since(tx_date)
            if tx_age > max_txdate_age_days:
                log.info(f"[{ticker}] Trade too old (txDate={tx_date}, {tx_age}d) — skipping")
                _mark_processed(trade_key)
                continue

        # Cooldown: skip tickers recently stopped out.
        if stop_cooldown_days > 0 and ticker in stopped_out_dates:
            days_since_stop = _days_since(stopped_out_dates[ticker])
            if days_since_stop < stop_cooldown_days:
                log.info(
                    f"[{ticker}] Cooldown active — stopped {days_since_stop}d ago, "
                    f"skipping for {stop_cooldown_days - days_since_stop}d more"
                )
                continue

        # Position size guard.
        if ticker in existing_tickers:
            if not size_up:
                log.info(f"[{ticker}] Already in portfolio — size_up=false, skipping")
                continue
            if max_position_usd is not None and position_value.get(ticker, 0) >= max_position_usd:
                log.info(
                    f"[{ticker}] Position cap reached "
                    f"(${position_value[ticker]:,.0f} >= ${max_position_usd:,.0f}) — skipping"
                )
                continue

        try:
            price = get_latest_price(ticker)
        except Exception as e:
            log.warning(f"[{ticker}] Cannot get price: {e}")
            continue

        # Backtest-driven filter: post-migration losses clustered heavily in thin,
        # sub-$20 micro-caps — a price floor was the single largest lever the
        # parameter sweep found for improving realized P&L.
        if min_entry_price > 0 and price < min_entry_price:
            log.info(f"[{ticker}] Price ${price:.2f} below min_entry_price ${min_entry_price:.2f} — skipping")
            _mark_processed(trade_key)
            continue

        market_ctx = {
            "price":                 price,
            "buying_power":          buying_power,
            "existing_positions":    existing_tickers,
            "days_since_disclosure": _days_since(trade.get("txDate", "")),
        }

        insider_name = trade.get("politician", {}).get("name", "Unknown")
        insider_role = trade.get("_insider_role", "Officer")
        tx_value     = trade.get("_transaction_value", 0)

        log.info(
            f"[{ticker}] {insider_role} {insider_name} bought ${tx_value:,.0f} — "
            f"asking Claude for strategy..."
        )
        rec = get_recommendation(trade, market_ctx)

        strategy     = rec.get("strategy", "SKIP")
        confidence   = rec.get("confidence", 0)
        reasoning    = rec.get("reasoning", "")
        position_pct = rec.get("suggested_position_size_pct", 0.05)
        key_risk     = rec.get("key_risk", "")
        cache_hit    = rec.get("_cache_hit", False)
        tokens_saved = rec.get("_tokens_saved", 0)
        tokens_saved_total += tokens_saved

        result = {
            "ticker":     ticker,
            "insider":    f"{insider_name} ({insider_role})",
            "tx_date":    trade.get("txDate"),
            "tx_value":   tx_value,
            "strategy":   strategy,
            "confidence": confidence,
            "reasoning":  reasoning,
            "price":      price,
            "executed":   False,
        }

        cache_str = " [cache ✓]" if cache_hit else ""
        print(f"\n{'─'*60}")
        print(f"  Ticker     : {ticker}")
        print(f"  Insider    : {insider_name} — {insider_role}")
        print(f"  Bought     : ${tx_value:,.0f} on {trade.get('txDate')}  (filed {pub_date})")
        print(f"  Price      : ${price:.2f}")
        print(f"  Strategy   : {strategy} ({confidence}% confidence){cache_str}")
        print(f"  Reasoning  : {reasoning}")
        print(f"  Risk       : {key_risk}")

        if strategy == "SKIP":
            log.info(f"[{ticker}] SKIP — {reasoning[:80]}")
            results.append(result)
            # Do NOT mark processed — re-evaluate next cycle while signal is still fresh.
            continue

        if args.dry_run:
            print(f"  [DRY RUN]  : Would execute {strategy} — skipping actual trade")
            results.append(result)
            continue

        # Execute immediately
        shares_budget = buying_power * position_pct
        shares_to_buy = max(1, int(shares_budget / price))
        cost          = shares_to_buy * price

        if buying_power < cost:
            log.warning(f"[{ticker}] Skipping — need ${cost:.0f}, have ${buying_power:.0f}")
            if telegram_configured():
                send_insufficient_funds_alert(ticker, cost, buying_power)
            results.append(result)
            continue

        try:
            if strategy == "TRAILING_STOP":
                order = market_buy(ticker, shares_to_buy)
                fill_price = float(order.filled_avg_price) if order.filled_avg_price is not None else price
                unconfirmed_note = "" if order.filled_avg_price is not None else " unconfirmed_fill=true"
                stop_note = ""
                if args.stop_floor is not None:
                    trailing_stop_sell(ticker, shares_to_buy, args.stop_floor)
                    stop_note = f" + native trailing stop {args.stop_floor}%"
                log_trade(
                    "AI_BUY_TRAILING", ticker, shares_to_buy, fill_price,
                    f"strategy=TRAILING_STOP confidence={confidence}% "
                    f"insider={insider_name} role={insider_role} "
                    f"value=${tx_value:,.0f} reasoning={reasoning[:60]}"
                    + (f" stop_floor={args.stop_floor}%" if args.stop_floor else "")
                    + unconfirmed_note
                )
                buying_power -= cost
                result.update({"executed": True, "shares": shares_to_buy})
                print(f"  EXECUTED   : Bought {shares_to_buy} shares @ ${fill_price:.2f}{stop_note}")
                if telegram_configured():
                    send_message(
                        f"✅ *Bought* `{ticker}` — {shares_to_buy} shares @ ${fill_price:.2f}{escape_md(stop_note)}\n"
                        f"Strategy: `TRAILING_STOP` ({confidence}%) | {escape_md(insider_name)} ({escape_md(insider_role)})"
                    )

            elif strategy == "WHEEL":
                wheel_result = start_wheel(ticker, contracts=1)
                if not wheel_result.get("put_strike"):
                    log.warning(f"[{ticker}] WHEEL skipped — no liquid put available")
                    results.append(result)
                    continue
                log_trade(
                    "AI_START_WHEEL", ticker, 1, price,
                    f"strategy=WHEEL confidence={confidence}% "
                    f"insider={insider_name} put_strike={wheel_result['put_strike']}"
                )
                result.update({"executed": True, "put_strike": wheel_result.get("put_strike")})
                print(f"  EXECUTED   : Wheel started — put @ ${wheel_result['put_strike']:.2f}")
                if telegram_configured():
                    send_message(
                        f"✅ *Wheel started* `{ticker}` — put @ ${wheel_result['put_strike']:.2f}\n"
                        f"Strategy: WHEEL ({confidence}%) | {escape_md(insider_name)}"
                    )

        except Exception as e:
            log.error(f"[{ticker}] Execution failed: {e}")
            if telegram_configured():
                send_message(f"❌ Execution failed for `{ticker}`: {escape_md(str(e))}")
        finally:
            _mark_processed(trade_key)

        results.append(result)

    # ── Run summary ────────────────────────────────────────────────────────────
    executed = [r for r in results if r.get("executed")]
    skipped  = [r for r in results if r.get("strategy") == "SKIP"]
    trailing = [r for r in executed if r.get("strategy") == "TRAILING_STOP"]
    wheel    = [r for r in executed if r.get("strategy") == "WHEEL"]

    print(f"\n{'═'*60}")
    print(f"  RUN SUMMARY")
    print(f"  Signals analysed    : {len(results)}")
    print(f"  Executed trades     : {len(executed)}")
    print(f"    -> Trailing Stop  : {len(trailing)}")
    print(f"    -> Wheel          : {len(wheel)}")
    print(f"  Skipped by Claude   : {len(skipped)}")
    if tokens_saved_total:
        print(f"  Cache tokens saved  : {tokens_saved_total:,} (~90% cost reduction on system prompt)")
    print(f"{'═'*60}\n")
    print("Run 'python main.py performance' to compare strategy results.")


if __name__ == "__main__":
    main()
