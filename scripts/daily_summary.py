#!/usr/bin/env python3
"""Print end-of-day portfolio summary."""
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

    print(f"\n{'═'*55}")
    print(f"  END OF DAY SUMMARY")
    print(f"{'═'*55}")
    print(f"  Portfolio Value : ${float(acct.portfolio_value):>12,.2f}")
    print(f"  Cash            : ${float(acct.cash):>12,.2f}")
    print(f"  Day P&L         : ${day_pnl:>+12,.2f}")
    print(f"  Open Positions  : {len(positions)}")

    if positions:
        rows = []
        for p in positions:
            ps = state["positions"].get(p.symbol, {})
            rows.append([
                p.symbol,
                f"{float(p.qty):.0f}",
                f"${float(p.current_price):.2f}",
                f"${float(p.unrealized_pl):>+.2f}",
                f"{float(p.unrealized_plpc)*100:>+.1f}%",
                f"${ps['stop_floor']:.2f}" if ps.get("stop_floor") else "—",
            ])
        print()
        print(tabulate(rows, headers=["Symbol", "Qty", "Price", "Unreal. P&L", "P&L%", "Stop"], tablefmt="simple"))

    wheel = state.get("wheel", {})
    if wheel:
        print(f"\n  Wheel Positions: {len(wheel)}")
        for sym, ws in wheel.items():
            print(f"    {sym}: Stage {ws['stage']} | exp {ws['expiry']}")

    print(f"\n{'═'*55}\n")


if __name__ == "__main__":
    main()
