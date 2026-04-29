#!/usr/bin/env python3
"""
Strategy Performance Comparison
Reads logs/trades.log and compares TRAILING_STOP vs WHEEL P&L so you can
identify which strategy is most profitable over time.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime
from collections import defaultdict
from tabulate import tabulate
from core.alpaca import get_positions
from core.logger import load_state

TRADES_LOG = Path(__file__).parent.parent / "logs" / "trades.log"


def load_trades() -> list:
    if not TRADES_LOG.exists():
        return []
    trades = []
    with open(TRADES_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except Exception:
                    pass
    return trades


def infer_strategy(action: str, notes: str) -> str:
    """Determine which strategy produced this trade entry."""
    combined = f"{action} {notes}".upper()
    if any(k in combined for k in ("TRAILING_STOP", "TRAILING", "STOP_SELL", "LADDER")):
        return "TRAILING_STOP"
    if any(k in combined for k in ("WHEEL", "SELL_PUT", "SELL_CALL")):
        return "WHEEL"
    return "UNKNOWN"


def main():
    trades = load_trades()

    if not trades:
        print("\nNo trades logged yet.\n")
        print("Run: python main.py analyze")
        print("Then come back here to compare strategy performance.\n")
        return

    positions = {p.symbol: p for p in get_positions()}

    # Annotate and group trades
    by_strategy = defaultdict(list)
    by_ticker_strategy: dict = defaultdict(lambda: defaultdict(list))

    for t in trades:
        strat = infer_strategy(t.get("action", ""), t.get("notes", ""))
        t["_strategy"] = strat
        by_strategy[strat].append(t)
        by_ticker_strategy[t.get("symbol", "")][strat].append(t)

    print(f"\n{'═'*70}")
    print(f"  STRATEGY PERFORMANCE COMPARISON")
    print(f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Trades    : {len(trades)} total | "
          f"{len([t for t in trades if t['_strategy'] != 'UNKNOWN'])} attributed")
    print(f"{'═'*70}")

    summary_rows = []

    for strategy in ["TRAILING_STOP", "WHEEL"]:
        strat_trades = by_strategy.get(strategy, [])
        if not strat_trades:
            print(f"\n  {strategy}: No trades logged yet.")
            continue

        buys = [t for t in strat_trades
                if any(k in t.get("action", "").upper()
                       for k in ("BUY", "START_WHEEL", "SELL_PUT"))]
        exits = [t for t in strat_trades
                 if any(k in t.get("action", "").upper()
                        for k in ("STOP_SELL", "SELL_CALL", "CLOSE"))]

        deployed = sum(t.get("price", 0) * float(t.get("qty", 0)) for t in buys)

        print(f"\n{'─'*70}")
        print(f"  {strategy}")
        print(f"    Entries   : {len(buys)}")
        print(f"    Exits     : {len(exits)}")
        print(f"    Deployed  : ${deployed:>12,.2f}")

        # Per-ticker breakdown — accumulate totals here instead of pre-loop
        ticker_rows = []
        total_realized = 0.0
        total_unrealized = 0.0

        for sym in sorted(by_ticker_strategy.keys()):
            sym_trades = by_ticker_strategy[sym].get(strategy, [])
            if not sym_trades:
                continue

            sym_buys = [t for t in sym_trades
                        if any(k in t.get("action", "").upper()
                               for k in ("BUY", "SELL_PUT", "START_WHEEL"))]
            sym_exits = [t for t in sym_trades
                         if any(k in t.get("action", "").upper()
                                for k in ("STOP_SELL", "SELL_CALL", "CLOSE"))]

            cost = sum(t.get("price", 0) * float(t.get("qty", 0)) for t in sym_buys)
            revenue = sum(t.get("price", 0) * float(t.get("qty", 0)) for t in sym_exits)
            prems = sum(t.get("price", 0) * float(t.get("qty", 0)) * 100
                        for t in sym_trades
                        if "SELL_PUT" in t.get("action", "").upper()
                        or "SELL_CALL" in t.get("action", "").upper())

            unrealized = 0.0
            status = "Closed"
            is_open = sym in positions
            if is_open:
                pos = positions[sym]
                unrealized = float(pos.unrealized_pl)
                total_unrealized += unrealized
                price_now = float(pos.current_price)
                pnl_pct = float(pos.unrealized_plpc) * 100
                status = f"Open ${price_now:.2f} ({pnl_pct:>+.1f}%)"

            if is_open:
                total_pnl = unrealized
                roi = (unrealized / cost * 100) if cost > 0 else 0
            else:
                total_pnl = revenue - cost + prems
                total_realized += total_pnl
                roi = (total_pnl / cost * 100) if cost > 0 else 0

            ticker_rows.append([
                sym, status,
                f"${cost:>10,.0f}",
                f"${total_pnl:>+10,.2f}",
                f"{roi:>+6.1f}%",
            ])

        if ticker_rows:
            print()
            print(tabulate(ticker_rows,
                           headers=["Ticker", "Status", "Deployed", "P&L", "ROI"],
                           tablefmt="simple",
                           colalign=("left", "left", "right", "right", "right")))

        total_pnl_strat = total_realized + total_unrealized
        roi_strat = (total_pnl_strat / deployed * 100) if deployed > 0 else 0
        print(f"\n    Realized   : ${total_realized:>+12,.2f}")
        print(f"\n    Unrealized : ${total_unrealized:>+12,.2f}")
        print(f"    TOTAL P&L  : ${total_pnl_strat:>+12,.2f}  (ROI {roi_strat:>+.1f}%)")

        summary_rows.append([strategy, len(strat_trades), f"${deployed:,.0f}",
                              f"${total_pnl_strat:>+,.2f}", f"{roi_strat:>+.1f}%"])

    # Head-to-head comparison
    if len(summary_rows) >= 2:
        print(f"\n{'═'*70}")
        print(f"  HEAD-TO-HEAD")
        print()
        # Sort by ROI descending
        summary_rows.sort(
            key=lambda r: float(r[4].replace("%", "").replace("+", "")), reverse=True
        )
        print(tabulate(summary_rows,
                       headers=["Strategy", "Trades", "Deployed", "Total P&L", "ROI"],
                       tablefmt="simple"))
        winner = summary_rows[0][0]
        print(f"\n  ★ Leading strategy: {winner}")
        print(f"  Track more trades to build statistical significance.")

    print(f"\n{'═'*70}\n")


if __name__ == "__main__":
    main()
