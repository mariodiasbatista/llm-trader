"""
Market Hours Scheduler
Runs strategy checks only during NYSE trading hours (Mon–Fri 9:30–16:00 ET).
Provides a daily summary at market close.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytz
import schedule

from core.logger import log
from core.notifier import tlog, get_log_level, load_log_level, LEVEL_LEGEND

BASE = Path(__file__).parent.parent

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"
NY_TZ = pytz.timezone("America/New_York")


def _settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)["schedule"]


def is_market_open() -> bool:
    now = datetime.now(NY_TZ)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t


def _run_trailing_stop():
    if not is_market_open():
        return
    from strategies.trailing_stop import check_and_update
    from core.notifier import send_stop_alert, send_ladder_alert
    tlog("Trailing stop check...", 2)
    result = check_and_update()
    checked = len(result["checked"])
    stopped = result["stopped_out"]
    laddered = result["laddered"]
    msg = f"Checked {checked} positions"
    if stopped:
        msg += f" | STOPPED OUT: {', '.join(stopped)}"
        for item in result["checked"]:
            if item["symbol"] in stopped:
                send_stop_alert(
                    item["symbol"], item["price"], item["floor"],
                    item.get("entry", 0), item.get("qty", 0),
                )
    if laddered:
        msg += f" | Ladder buys: {len(laddered)}"
        for item in laddered:
            send_ladder_alert(item["symbol"], item["qty"], item["price"], 0)
    tlog(msg, 2)


def _run_wheel():
    if not is_market_open():
        return
    from strategies.wheel import check_and_manage
    tlog("Wheel check...", 2)
    result = check_and_manage()
    for action in result.get("actions", []):
        tlog(f"  {action}", 2)


def _run_analyze():
    if not is_market_open():
        return
    cfg = _settings()
    days = cfg.get("analyze_days", 2)
    min_val = cfg.get("analyze_min_disclosure_value", 15000)
    source = cfg.get("analyze_source", "web")
    tlog(f"AI analyze run (days={days} min_val=${min_val:,} source={source})...", 2)
    cmd = [
        sys.executable,
        str(BASE / "scripts" / "analyze_and_trade.py"),
        "--days", str(days),
        "--min-disclosure-value", str(min_val),
        "--source", source,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            tlog(f"  {line}", 1)  # debug — full subprocess output
    if result.returncode != 0 and result.stderr:
        tlog(f"analyze error: {result.stderr[:200]}", 3)


def _poll_telegram():
    """Check Telegram for approve/skip callbacks and text commands, then execute pending trades."""
    from core.notifier import poll_approvals, send_message, is_configured
    from core.alpaca import get_account, get_latest_price, market_buy
    from core.logger import load_state, save_state, log_trade
    from strategies.trailing_stop import check_and_update as trailing_check

    if not is_configured():
        return

    approvals = poll_approvals()
    if not approvals:
        return

    state = load_state()
    pending = state.get("pending_trades", {})
    acct = get_account()
    buying_power = float(acct.buying_power)

    for decision in approvals:
        action = decision["action"]
        trade_key = decision["trade_key"]
        trade = pending.pop(trade_key, None)

        if not trade:
            tlog(f"Telegram callback for unknown trade_key: {trade_key}", 3)
            continue

        ticker = trade["ticker"]
        strategy = trade["strategy"]

        if action == "skip":
            tlog(f"[{ticker}] Skipped via Telegram", 2)
            state.setdefault("copied_trades", []).append(trade_key)
            continue

        # Approved — re-fetch live price and execute
        try:
            price = get_latest_price(ticker)
            position_pct = trade.get("position_pct", 0.05)
            stop_floor = trade.get("stop_floor")
            shares = max(1, int(buying_power * position_pct / price))
            cost = shares * price

            if buying_power < cost:
                msg = f"Insufficient buying power for `{ticker}` (need ${cost:,.0f}, have ${buying_power:,.0f})"
                tlog(msg, 3)
                send_message(f"⚠️ {msg}")
                continue

            if strategy == "TRAILING_STOP":
                from core.alpaca import trailing_stop_sell
                market_buy(ticker, shares)
                if stop_floor is not None:
                    trailing_stop_sell(ticker, shares, stop_floor)
                log_trade(
                    "AI_BUY_TRAILING", ticker, shares, price,
                    f"strategy=TRAILING_STOP approved_via=telegram"
                    + (f" stop_floor={stop_floor}%" if stop_floor else "")
                )
                buying_power -= cost
                state.setdefault("copied_trades", []).append(trade_key)
                send_message(f"✅ *Bought* `{ticker}` — {shares} shares @ ${price:.2f}")
                tlog(f"[{ticker}] Telegram-approved TRAILING_STOP executed", 2)

            elif strategy == "WHEEL":
                from strategies.wheel import start_wheel
                result = start_wheel(ticker, contracts=1)
                log_trade(
                    "AI_START_WHEEL", ticker, 1, price,
                    f"strategy=WHEEL approved_via=telegram put_strike={result['put_strike']}"
                )
                state.setdefault("copied_trades", []).append(trade_key)
                send_message(f"✅ *Wheel started* `{ticker}` — put @ ${result['put_strike']:.2f}")
                tlog(f"[{ticker}] Telegram-approved WHEEL executed", 2)

        except Exception as e:
            tlog(f"[{ticker}] Telegram-approved execution failed: {e}", 3)
            send_message(f"❌ Execution failed for `{ticker}`: {e}")

    state["pending_trades"] = pending
    save_state(state)


def _run_daily_summary():
    from core.alpaca import get_account, get_positions
    from core.logger import load_state
    from core.notifier import send_summary
    acct = get_account()
    positions = get_positions()
    state = load_state()

    day_pnl = float(acct.equity) - float(acct.last_equity)
    log.info("=" * 55)
    log.info(f"DAILY SUMMARY — {datetime.now(NY_TZ).strftime('%Y-%m-%d')}")
    log.info(f"  Portfolio : ${float(acct.portfolio_value):>12,.2f}")
    log.info(f"  Cash      : ${float(acct.cash):>12,.2f}")
    log.info(f"  Day P&L   : ${day_pnl:>+12,.2f}")
    log.info(f"  Positions : {len(positions)}")
    pos_lines = []
    for p in positions:
        floor = state["positions"].get(p.symbol, {}).get("stop_floor")
        floor_str = f"  floor=${floor:.2f}" if floor else ""
        log.info(
            f"    {p.symbol:6s} {p.qty:>8} shares  "
            f"Today ${float(p.unrealized_intraday_pl):>+9.2f} ({float(p.unrealized_intraday_plpc)*100:>+5.1f}%)  "
            f"Total ${float(p.unrealized_pl):>+9.2f} ({float(p.unrealized_plpc)*100:>+5.1f}%){floor_str}"
        )
        pos_lines.append(
            f"`{p.symbol}` {p.qty}sh  "
            f"Today ${float(p.unrealized_intraday_pl):+.2f} ({float(p.unrealized_intraday_plpc)*100:+.1f}%)  "
            f"Total ${float(p.unrealized_pl):+.2f} ({float(p.unrealized_plpc)*100:+.1f}%){floor_str}"
        )
    log.info("=" * 55)

    # Send compact summary to Telegram — send_summary respects log level
    telegram_text = (
        f"*{datetime.now(NY_TZ).strftime('%Y-%m-%d')}*\n"
        f"Portfolio: ${float(acct.portfolio_value):,.2f}\n"
        f"Cash: ${float(acct.cash):,.2f}\n"
        f"Day P&L: ${day_pnl:+,.2f}\n"
        f"Positions: {len(positions)}"
    )
    if pos_lines:
        telegram_text += "\n" + "\n".join(pos_lines)
    send_summary(telegram_text)


def start():
    """Start the blocking scheduler. Ctrl+C to stop."""
    load_log_level()
    cfg = _settings()

    trailing_min = cfg.get("trailing_stop_interval_min", 5)
    wheel_min = cfg.get("wheel_interval_min", 15)
    analyze_min = cfg.get("analyze_interval_min", 30)
    summary_time = cfg.get("summary_time", "16:05")

    schedule.every(trailing_min).minutes.do(_run_trailing_stop)
    schedule.every(wheel_min).minutes.do(_run_wheel)
    schedule.every(analyze_min).minutes.do(_run_analyze)
    schedule.every().day.at(summary_time).do(_run_daily_summary)
    schedule.every(30).seconds.do(_poll_telegram)

    from core.notifier import is_configured, send_message, register_command
    register_command("/summary", "portfolio snapshot with today & total P&L", _run_daily_summary)
    telegram_status = "enabled" if is_configured() else "not configured"
    tlog(
        f"Scheduler started | trailing={trailing_min}min | "
        f"wheel={wheel_min}min | analyze={analyze_min}min | "
        f"summary={summary_time} ET | telegram={telegram_status} | "
        f"loglevel={get_log_level()}",
        2,
    )
    if is_configured():
        send_message(
            f"🚀 *LLM Trader started*\n"
            f"Scheduler running. Log level: `{get_log_level()}` — {LEVEL_LEGEND[get_log_level()]}\n"
            f"Send /help for available commands."
        )

    while True:
        schedule.run_pending()
        time.sleep(30)
