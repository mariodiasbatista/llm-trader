#!/usr/bin/env python3
"""Show all open positions with trailing stop state."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tabulate import tabulate
from core.alpaca import get_account, get_positions
from core.logger import load_state

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def main():
    acct = get_account()
    positions = get_positions()
    state = load_state()
    cfg = json.load(open(SETTINGS_FILE))["trailing_stop"]
    profit_target_pct = cfg.get("profit_target_pct", 0)

    day_pnl = float(acct.equity) - float(acct.last_equity)
    print(f"\n{'─'*60}")
    print(f"  Portfolio Value : ${float(acct.portfolio_value):>12,.2f}")
    print(f"  Cash Available  : ${float(acct.cash):>12,.2f}")
    print(f"  Buying Power    : ${float(acct.buying_power):>12,.2f}")
    print(f"  Day P&L         : ${day_pnl:>+12,.2f}")
    print(f"{'─'*60}\n")

    if not positions:
        print("No open positions.\n")
        return

    rows = []
    for p in positions:
        sym = p.symbol
        ps = state["positions"].get(sym, {})
        floor = ps.get("stop_floor") or 0
        price = float(p.current_price)
        entry = float(p.avg_entry_price)
        gain_pct = (price - entry) / entry * 100
        stop_active = ps.get("profit_stop_active", False)

        if stop_active and floor:
            stop_status = f"ACTIVE  floor=${floor:.2f}  ({(price - floor) / price * 100:.1f}% gap)"
        elif profit_target_pct > 0:
            needed = profit_target_pct * 100 - gain_pct
            stop_status = f"waiting  need +{needed:.1f}% more to activate"
        else:
            stop_status = "disabled"

        rows.append([
            sym,
            f"{float(p.qty):.0f}",
            f"${entry:.2f}",
            f"${price:.2f}",
            f"${float(p.unrealized_pl):>+.2f}",
            f"{gain_pct:>+.1f}%",
            stop_status,
        ])

    print(tabulate(
        rows,
        headers=["Symbol", "Qty", "Entry", "Price", "P&L $", "Gain%", "Stop Status"],
        tablefmt="simple",
    ))
    print()


if __name__ == "__main__":
    main()
