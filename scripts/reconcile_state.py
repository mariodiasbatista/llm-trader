#!/usr/bin/env python3
"""
Reconcile logs/state.json against live Alpaca positions.

Finds tracked positions and wheel entries in state.json that no longer exist
in the live account (e.g. closed positions whose state cleanup never fired)
and removes them. Defaults to a dry-run report; pass --apply to actually save.

Usage:
  python scripts/reconcile_state.py            # report only
  python scripts/reconcile_state.py --apply     # report and remove stale entries
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alpaca.trading.enums import AssetClass

from core.alpaca import get_positions
from core.logger import load_state, save_state, log, state_lock


def find_stale_entries(state: dict, live_positions: list) -> tuple[list, list]:
    live_equity_symbols = {p.symbol for p in live_positions if p.asset_class == AssetClass.US_EQUITY}
    live_option_symbols = {p.symbol for p in live_positions if p.asset_class == AssetClass.US_OPTION}

    stale_positions = [
        sym for sym in state.get("positions", {})
        if sym not in live_equity_symbols
    ]
    stale_wheel = [
        sym for sym, ws in state.get("wheel", {}).items()
        if ws.get("option_symbol") not in live_option_symbols
    ]
    return stale_positions, stale_wheel


def main():
    apply = "--apply" in sys.argv[1:]

    with state_lock():
        state = load_state()
        live_positions = get_positions()
        stale_positions, stale_wheel = find_stale_entries(state, live_positions)

        print(f"\n{'═' * 60}")
        print(f"  STATE RECONCILIATION {'(APPLYING CHANGES)' if apply else '(DRY RUN)'}")
        print(f"{'═' * 60}\n")

        if not stale_positions and not stale_wheel:
            print("  No stale entries found — state.json matches live account.\n")
            return

        for sym in stale_positions:
            entry = state["positions"][sym]
            print(f"  [positions] {sym}: entry=${entry.get('entry_price', 0):.2f} "
                  f"floor=${entry.get('stop_floor', 0):.2f} — no matching live equity position")
        for sym in stale_wheel:
            entry = state["wheel"][sym]
            print(f"  [wheel]     {sym}: stage={entry.get('stage')} "
                  f"option={entry.get('option_symbol')} expiry={entry.get('expiry')} — no matching live option position")

        if apply:
            for sym in stale_positions:
                del state["positions"][sym]
                log.info(f"[reconcile_state] removed stale tracked position: {sym}")
            for sym in stale_wheel:
                del state["wheel"][sym]
                log.info(f"[reconcile_state] removed stale wheel entry: {sym}")
            save_state(state)
            print(f"\n  Removed {len(stale_positions)} stale position(s), {len(stale_wheel)} stale wheel entr(y/ies).\n")
        else:
            print(f"\n  {len(stale_positions)} stale position(s), {len(stale_wheel)} stale wheel entr(y/ies) found.")
            print("  Re-run with --apply to remove them.\n")


if __name__ == "__main__":
    main()
