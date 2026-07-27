"""
Parse logs/trades.log into per-ticker TRAILING_STOP position records.

Moved out of scripts/backtest.py so both the original scenario-diff CLI and
the new sweep/replay tooling share one implementation of "what actually
happened," instead of drifting apart.
"""
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

TRADES_LOG = Path(__file__).parent.parent / "logs" / "trades.log"


def parse_trades_log(path: Path = TRADES_LOG) -> list[dict]:
    """Return list of trade dicts from trades.log."""
    trades = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return trades


def build_positions(trades: list[dict]) -> list[dict]:
    """
    Aggregate all TRAILING_STOP buys and their exit events per ticker.
    Returns a list of position dicts, one per ticker. Multi-buy positions
    (ladder buys, repeated same-day buys) are merged into one weighted-average entry.
    """
    buys_by_ticker = defaultdict(list)
    exits_by_ticker = defaultdict(list)

    for t in trades:
        sym = t["symbol"]
        action = t["action"]
        price = float(t["price"])
        qty = float(t["qty"])
        ts = t["ts"]
        notes = t.get("notes", "")

        if action == "AI_BUY_TRAILING" and "TRAILING_STOP" in notes:
            buys_by_ticker[sym].append({"ts": ts, "price": price, "qty": qty, "notes": notes})
        elif action in ("STOP_SELL", "TAKE_PROFIT") and not sym.startswith("T26"):
            # Exclude options exits (OCC symbols like T260529P00024000) — those
            # belong to WHEEL, not TRAILING_STOP.
            exits_by_ticker[sym].append({"ts": ts, "price": price, "qty": qty, "action": action})

    # Telegram-approved buys carry no "TRAILING_STOP" tag but are managed the same way.
    for t in trades:
        sym = t["symbol"]
        action = t["action"]
        price = float(t["price"])
        qty = float(t["qty"])
        ts = t["ts"]
        notes = t.get("notes", "")

        if action == "AI_BUY_TRAILING" and "approved_via=telegram" in notes and sym not in buys_by_ticker:
            buys_by_ticker[sym].append({"ts": ts, "price": price, "qty": qty, "notes": notes})

    positions = []
    for sym, buys in sorted(buys_by_ticker.items()):
        exits = exits_by_ticker.get(sym, [])
        total_cost = sum(b["qty"] * b["price"] for b in buys)
        total_qty = sum(b["qty"] for b in buys)
        avg_entry = total_cost / total_qty if total_qty else 0

        first_buy_ts = buys[0]["ts"]
        first_buy_dt = datetime.fromisoformat(first_buy_ts[:19])
        first_buy_date = first_buy_dt.date()

        exit_qty = sum(e["qty"] for e in exits)
        is_open = exit_qty < total_qty * 0.99  # 1% tolerance for float

        if exits:
            exit_cost = sum(e["qty"] * e["price"] for e in exits)
            exit_price_avg = exit_cost / exit_qty if exit_qty else None
            exit_ts = exits[-1]["ts"]
        else:
            exit_price_avg = None
            exit_ts = None

        positions.append({
            "symbol": sym,
            "buys": buys,
            "exits": exits,
            "total_qty": total_qty,
            "total_cost": total_cost,
            "avg_entry": avg_entry,
            "first_buy_ts": first_buy_ts,
            "first_buy_date": first_buy_date,
            "is_open": is_open,
            "exit_price": exit_price_avg,
            "exit_ts": exit_ts,
        })

    return positions


def compute_realized_pnl(pos: dict) -> float | None:
    """Realized P&L for a closed position (None for still-open positions)."""
    if pos["is_open"] or not pos["exits"]:
        return None
    sold_qty = sum(e["qty"] for e in pos["exits"])
    sold_cost = sum(e["qty"] * e["price"] for e in pos["exits"])
    entry_cost_for_sold = pos["avg_entry"] * sold_qty
    return sold_cost - entry_cost_for_sold


def bucket_key(date) -> str:
    return f"{date.year:04d}-{date.month:02d}"
