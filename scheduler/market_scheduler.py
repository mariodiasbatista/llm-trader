"""
Market Hours Scheduler
Runs strategy checks only during NYSE trading hours (Mon–Fri 9:30–16:00 ET).
Provides a daily summary at market close.
"""
import json
import time
from datetime import datetime
from pathlib import Path

import pytz
import schedule

from core.logger import log

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
    log.info("Trailing stop check...")
    result = check_and_update()
    checked = len(result["checked"])
    stopped = result["stopped_out"]
    laddered = result["laddered"]
    msg = f"Checked {checked} positions"
    if stopped:
        msg += f" | STOPPED OUT: {', '.join(stopped)}"
    if laddered:
        msg += f" | Ladder buys: {len(laddered)}"
    log.info(msg)


def _run_wheel():
    if not is_market_open():
        return
    from strategies.wheel import check_and_manage
    log.info("Wheel check...")
    result = check_and_manage()
    for action in result.get("actions", []):
        log.info(f"  {action}")


def _run_smart_money():
    from strategies.smart_money import check_and_copy
    log.info("Smart money check...")
    result = check_and_copy()
    log.info(
        f"  {result.get('trades_found', 0)} trades found, "
        f"{result.get('buy_signals', 0)} buy signals, "
        f"{len(result.get('actions', []))} copied"
    )


def _run_daily_summary():
    from core.alpaca import get_account, get_positions
    from core.logger import load_state
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
    for p in positions:
        floor = state["positions"].get(p.symbol, {}).get("stop_floor")
        floor_str = f"  floor=${floor:.2f}" if floor else ""
        log.info(
            f"    {p.symbol:6s} {p.qty:>8} shares  "
            f"P&L ${float(p.unrealized_pl):>+9.2f} "
            f"({float(p.unrealized_plpc)*100:>+5.1f}%){floor_str}"
        )
    log.info("=" * 55)


def start():
    """Start the blocking scheduler. Ctrl+C to stop."""
    cfg = _settings()

    trailing_min = cfg.get("trailing_stop_interval_min", 5)
    wheel_min = cfg.get("wheel_interval_min", 15)
    smart_money_min = cfg.get("smart_money_interval_min", 60)
    summary_time = cfg.get("summary_time", "16:05")

    schedule.every(trailing_min).minutes.do(_run_trailing_stop)
    schedule.every(wheel_min).minutes.do(_run_wheel)
    schedule.every(smart_money_min).minutes.do(_run_smart_money)
    schedule.every().day.at(summary_time).do(_run_daily_summary)

    log.info(
        f"Scheduler started | trailing={trailing_min}min | "
        f"wheel={wheel_min}min | smart_money={smart_money_min}min | "
        f"summary={summary_time} ET"
    )

    while True:
        schedule.run_pending()
        time.sleep(30)
