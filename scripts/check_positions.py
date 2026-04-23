#!/usr/bin/env python3
"""Show all open positions with trailing stop state."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tabulate import tabulate
from core.alpaca import get_account, get_positions
from core.logger import load_state


def main():
    acct = get_account()
    positions = get_positions()
    state = load_state()

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
        floor = ps.get("stop_floor")
        hwm = ps.get("high_water_mark")
        price = float(p.current_price)
        gap = f"{(price - floor) / price * 100:.1f}%" if floor else "—"

        rows.append([
            sym,
            f"{float(p.qty):.0f}",
            f"${float(p.avg_entry_price):.2f}",
            f"${price:.2f}",
            f"${float(p.unrealized_pl):>+.2f}",
            f"{float(p.unrealized_plpc)*100:>+.1f}%",
            f"${floor:.2f}" if floor else "—",
            f"${hwm:.2f}" if hwm else "—",
            gap,
        ])

    print(tabulate(
        rows,
        headers=["Symbol", "Qty", "Entry", "Price", "P&L", "P&L%", "Stop Floor", "HWM", "Gap"],
        tablefmt="simple",
    ))
    print()


if __name__ == "__main__":
    main()
