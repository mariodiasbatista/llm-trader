"""
Replay TRAILING_STOP against historical daily bars.

Reuses strategies.trailing_stop.evaluate_position — the exact pure state
machine the live strategy runs — so a parameter sweep here can never silently
diverge from what the bot would actually do with the same config.
"""
from datetime import date, datetime, timedelta

from core.alpaca import get_bars_range
from strategies.trailing_stop import evaluate_position


def simulate_trailing_stop(
    symbol: str,
    entry_date,
    entry_price: float,
    cfg: dict,
    position_size_usd: float,
    end_date=None,
    bars=None,
    max_days: int = 180,
) -> dict | None:
    """
    Replay one TRAILING_STOP position forward from entry_date using daily
    closes, under the given cfg (initial_stop_pct/trailing_pct/take_profit_pct/
    profit_target_pct/ladder_buys). position_size_usd normalizes the starting
    notional so results are comparable across position-sizing candidates
    independent of what was actually invested historically.

    Returns:
      {"exit_date": date|None, "exit_reason": "TAKE_PROFIT"|"STOP_SELL"|None,
       "pnl_usd": float, "is_open": bool, "days_held": int}
    None if no price data is available for the requested window.
    """
    end_date = end_date or min(date.today(), entry_date + timedelta(days=max_days))
    if bars is None:
        bars = get_bars_range(symbol, entry_date, end_date)
    if not bars:
        return None

    ps: dict = {}
    initial_qty = position_size_usd / entry_price
    qty = initial_qty
    avg_entry = entry_price
    total_cost = entry_price * qty

    for i, bar in enumerate(bars):
        bar_date = bar.timestamp.date() if hasattr(bar.timestamp, "date") else bar.timestamp
        price = float(bar.close)
        if price <= 0:
            continue

        events = evaluate_position(cfg, ps, price, avg_entry)

        terminal = next((e for e in events if e["type"] in ("TAKE_PROFIT", "STOP_SELL")), None)
        if terminal:
            pnl_usd = (price - avg_entry) * qty
            return {
                "exit_date": bar_date,
                "exit_reason": terminal["type"],
                "exit_price": price,
                "pnl_usd": pnl_usd,
                "is_open": False,
                "days_held": i + 1,
            }

        for ev in events:
            if ev["type"] == "LADDER_BUY":
                new_shares = ev["shares"]
                total_cost += price * new_shares
                qty += new_shares
                avg_entry = total_cost / qty

    # Never triggered an exit within the window — mark as still open,
    # valued at the last available close.
    last_price = float(bars[-1].close)
    pnl_usd = (last_price - avg_entry) * qty
    last_date = bars[-1].timestamp.date() if hasattr(bars[-1].timestamp, "date") else bars[-1].timestamp
    return {
        "exit_date": last_date,
        "exit_reason": None,
        "exit_price": last_price,
        "pnl_usd": pnl_usd,
        "is_open": True,
        "days_held": len(bars),
    }
