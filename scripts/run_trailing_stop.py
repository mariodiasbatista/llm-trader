#!/usr/bin/env python3
"""Manually trigger a single trailing stop check cycle."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.trailing_stop import check_and_update

if __name__ == "__main__":
    result = check_and_update()

    print(f"\nChecked {len(result['checked'])} positions")

    for pos in result["checked"]:
        print(
            f"  {pos['symbol']:6s}  price=${pos['price']:.2f}  "
            f"floor=${pos['floor']:.2f}  gap={pos['gap_pct']:.1f}%  "
            f"hwm=${pos['hwm']:.2f}"
        )

    if result["stopped_out"]:
        print(f"\nSTOPPED OUT: {', '.join(result['stopped_out'])}")

    for l in result["laddered"]:
        print(f"\nLADDER BUY: {l['qty']} {l['symbol']} @ ${l['price']:.2f}")
