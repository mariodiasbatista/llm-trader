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
from core.notifier import tlog, get_log_level, load_log_level, LEVEL_LEGEND, escape_md

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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        tlog("analyze timed out after 5 minutes — skipping cycle", 3)
        return
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            if line.strip():
                tlog(f"  {line}", 1)  # debug — full subprocess output
    if result.returncode != 0 and result.stderr:
        tlog(f"analyze error: {escape_md(result.stderr[:200])}", 3)


def _poll_telegram():
    """Check Telegram for approve/skip callbacks and text commands, then execute pending trades."""
    from core.notifier import poll_approvals, send_message, is_configured
    from core.alpaca import get_account, get_latest_price, market_buy
    from core.logger import load_state, save_state, log_trade, state_lock

    if not is_configured():
        return

    approvals = poll_approvals()
    if not approvals:
        return

    acct = get_account()
    buying_power = float(acct.buying_power)

    with state_lock():
        state = load_state()
        pending = state.get("pending_trades", {})

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
                send_message(f"❌ Execution failed for `{ticker}`: {escape_md(str(e))}")

        state["pending_trades"] = pending
        save_state(state)


def _todays_activity() -> dict:
    """Return today's buy and sell tickers read from trades.log."""
    from core.logger import TRADE_LOG
    today = datetime.now(NY_TZ).strftime("%Y-%m-%d")
    buys, sells = [], []
    if not TRADE_LOG.exists():
        return {"buys": buys, "sells": sells}
    with open(TRADE_LOG) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except Exception:
                continue
            if not entry.get("ts", "").startswith(today):
                continue
            action = entry.get("action", "")
            symbol = entry.get("symbol", "")
            if action in ("AI_BUY_TRAILING", "AI_START_WHEEL", "LADDER_BUY"):
                buys.append(symbol)
            elif action in ("STOP_SELL", "TAKE_PROFIT"):
                sells.append(symbol)
    return {"buys": buys, "sells": sells}


def _run_daily_summary():
    from core.alpaca import get_account, get_positions
    from core.logger import load_state
    from core.notifier import send_summary
    acct = get_account()
    positions = get_positions()
    state = load_state()

    day_pnl = float(acct.equity) - float(acct.last_equity)
    day_icon = "🟢" if day_pnl >= 0 else "🔴"

    log.info("=" * 55)
    log.info(f"DAILY SUMMARY — {datetime.now(NY_TZ).strftime('%Y-%m-%d')}")
    log.info(f"  Portfolio : ${float(acct.portfolio_value):>12,.2f}")
    log.info(f"  Cash      : ${float(acct.cash):>12,.2f}")
    log.info(f"  Day P&L   : ${day_pnl:>+12,.2f}")
    log.info(f"  Positions : {len(positions)}")
    for p in positions:
        floor = state.get("positions", {}).get(p.symbol, {}).get("stop_floor")
        floor_str = f"  floor=${floor:.2f}" if floor else ""
        log.info(
            f"    {p.symbol:6s} {p.qty:>8} shares  "
            f"Today ${float(p.unrealized_intraday_pl):>+9.2f} ({float(p.unrealized_intraday_plpc)*100:>+5.1f}%)  "
            f"Total ${float(p.unrealized_pl):>+9.2f} ({float(p.unrealized_plpc)*100:>+5.1f}%){floor_str}"
        )
    log.info("=" * 55)

    lines = [
        f"📊 *Portfolio — {datetime.now(NY_TZ).strftime('%Y-%m-%d %H:%M')} ET*\n",
        f"💼 *Account*",
        f"Portfolio:     ${float(acct.portfolio_value):>12,.2f}",
        f"Cash:          ${float(acct.cash):>12,.2f}",
        f"Buying Power:  ${float(acct.buying_power):>12,.2f}",
        f"Day P&L:       {day_icon} ${day_pnl:>+,.2f}",
    ]
    if positions:
        lines.append(f"\n📈 *Positions*")
        for p in positions:
            floor = state.get("positions", {}).get(p.symbol, {}).get("stop_floor")
            total_pl = float(p.unrealized_pl)
            today_pl = float(p.unrealized_intraday_pl)
            total_pct = float(p.unrealized_plpc) * 100
            today_pct = float(p.unrealized_intraday_plpc) * 100
            total_icon = "🟢" if total_pl >= 0 else "🔴"
            floor_str = f"  Stop ${floor:.2f}" if floor else ""
            lines.append(
                f"`{p.symbol}` {p.qty}sh @ ${float(p.avg_entry_price):.2f} → ${float(p.current_price):.2f}\n"
                f"  {total_icon} Total ${total_pl:+,.2f} ({total_pct:+.1f}%)  "
                f"Today ${today_pl:+,.2f} ({today_pct:+.1f}%){floor_str}"
            )
    else:
        lines.append("\n_No open positions._")

    activity = _todays_activity()
    buys_str  = ", ".join(f"`{s}`" for s in activity["buys"])  or "none"
    sells_str = ", ".join(f"`{s}`" for s in activity["sells"]) or "none"
    lines.append(
        f"\n📋 *Today's Activity*\n"
        f"Positions open:  {len(positions)}\n"
        f"Buys today:      {len(activity['buys'])} — {buys_str}\n"
        f"Sells today:     {len(activity['sells'])} — {sells_str}"
    )

    send_summary("\n".join(lines))


def _build_schedule_message() -> str:
    cfg = _settings()
    trailing_min = cfg.get("trailing_stop_interval_min", 5)
    wheel_min = cfg.get("wheel_interval_min", 15)
    analyze_min = cfg.get("analyze_interval_min", 30)
    summary_time = cfg.get("summary_time", "16:05")
    market_open = cfg.get("market_open", "09:30")
    market_close = cfg.get("market_close", "16:00")

    now = datetime.now(NY_TZ)
    now_t = now.time()

    def _t(s: str):
        return datetime.strptime(s, "%H:%M").time()

    def _fmt(s: str) -> str:
        return datetime.strptime(s, "%H:%M").strftime("%-I:%M %p")

    open_t, close_t, summary_t = _t(market_open), _t(market_close), _t(summary_time)

    def _status(start, end=None):
        if end:
            if now_t < start:   return "⬜"
            if now_t <= end:    return "🔄"
            return "✅"
        return "✅" if now_t >= start else "⬜"

    rows = [
        (_status(open_t),              f"{_fmt(market_open)}",                      "Market Open"),
        (_status(open_t, close_t),     f"{_fmt(market_open)}–{_fmt(market_close)}", f"Trailing Stop (every {trailing_min}m)"),
        (_status(open_t, close_t),     f"{_fmt(market_open)}–{_fmt(market_close)}", f"Wheel Monitor (every {wheel_min}m)"),
        (_status(open_t, close_t),     f"{_fmt(market_open)}–{_fmt(market_close)}", f"AI Analyze (every {analyze_min}m)"),
        (_status(close_t),             f"{_fmt(market_close)}",                     "Market Close"),
        (_status(summary_t),           f"{_fmt(summary_time)}",                     "Daily Summary"),
    ]

    day_str = now.strftime("%A %Y-%m-%d")
    now_str = now.strftime("%-I:%M %p ET")
    lines = [f"📅 *LLM Trader — {day_str}*\n"]
    for icon, time_label, label in rows:
        lines.append(f"{icon}  `{time_label}`  {label}")
    lines.append(f"\n🕐 Now: {now_str}")
    return "\n".join(lines)


def _send_schedule() -> None:
    from core.notifier import send_message
    send_message(_build_schedule_message())


_PID_FILE = BASE / "logs" / "scheduler.pid"


def _enforce_single_instance():
    """Kill any previous scheduler instance and write current PID to disk."""
    import os, signal
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            if old_pid != os.getpid():
                os.kill(old_pid, signal.SIGTERM)
                log.info(f"Terminated previous scheduler instance (PID {old_pid})")
        except (ProcessLookupError, ValueError):
            pass  # process already gone
    _PID_FILE.write_text(str(os.getpid()))


def start():
    """Start the blocking scheduler. Ctrl+C to stop."""
    _enforce_single_instance()
    load_log_level()
    cfg = _settings()

    trailing_min = cfg.get("trailing_stop_interval_min", 5)
    wheel_min = cfg.get("wheel_interval_min", 15)
    analyze_min = cfg.get("analyze_interval_min", 30)
    summary_time = cfg.get("summary_time", "16:05")

    # Clear any pending_trades left over from a previous run — they're stale
    from core.logger import load_state, save_state, state_lock
    with state_lock():
        state = load_state()
        if state.get("pending_trades"):
            tlog(f"Clearing {len(state['pending_trades'])} stale pending trades from previous session", 2)
            state["pending_trades"] = {}
            save_state(state)

    schedule.every(trailing_min).minutes.do(_run_trailing_stop)
    schedule.every(wheel_min).minutes.do(_run_wheel)
    schedule.every(analyze_min).minutes.do(_run_analyze)
    schedule.every().day.at(summary_time).do(_run_daily_summary)
    schedule.every(1).minutes.do(_poll_telegram)

    from core.notifier import is_configured, send_message, register_command
    register_command("/summary", "full portfolio snapshot with entry prices and stops", _run_daily_summary)
    register_command("/schedule", "show today's trading schedule with live status", _send_schedule)
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

    # Run trailing stop immediately on startup (don't wait for first interval)
    _run_trailing_stop()

    while True:
        schedule.run_pending()
        time.sleep(30)
