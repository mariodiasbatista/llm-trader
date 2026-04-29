"""
Phase 2 — Trailing Stop Strategy
- Holds freely until the position reaches profit_target_pct gain from entry
- Once the profit target is hit, activates a trailing stop floor
- Raises the floor as price climbs (trails trailing_pct_from_profit below the new high)
- Sells the full position if price hits the active floor
- Laddered buys: auto-purchases more shares on steep dips
"""
import json
from pathlib import Path

from core.alpaca import get_positions, get_latest_price, close_position, market_buy, get_account
from core.logger import load_state, save_state, log_trade, log
from core.notifier import is_configured as telegram_configured, send_insufficient_funds_alert

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def _settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)["trailing_stop"]


def check_and_update() -> dict:
    """
    Evaluate all open positions against trailing stop rules.
    Meant to be called every 5 minutes during market hours.
    Returns a summary of every position and any actions taken.
    """
    cfg = _settings()
    state = load_state()
    positions = get_positions()
    summary = {"checked": [], "stopped_out": [], "laddered": []}

    for pos in positions:
        symbol = pos.symbol
        price = float(pos.current_price)
        entry = float(pos.avg_entry_price)
        qty = float(pos.qty)

        # Bootstrap state for newly tracked positions
        if symbol not in state["positions"]:
            state["positions"][symbol] = {
                "high_water_mark": price,
                "stop_floor": 0.0,
                "entry_price": entry,
                "ladder_triggered": [],
                "profit_stop_active": False,
            }
            log.info(f"[{symbol}] New position tracked | entry=${entry:.2f} | waiting for profit target")

        ps = state["positions"][symbol]
        profit_target_pct = cfg.get("profit_target_pct", 0)
        trail_from_profit = cfg.get("trailing_pct_from_profit", cfg.get("trailing_pct", 0.05))
        gain_pct = (price - entry) / entry

        if not ps.get("profit_stop_active", False):
            # Activate trailing stop once profit target is reached
            if profit_target_pct > 0 and gain_pct >= profit_target_pct:
                ps["profit_stop_active"] = True
                ps["high_water_mark"] = price
                ps["stop_floor"] = price * (1 - trail_from_profit)
                log.info(
                    f"[{symbol}] Profit target +{profit_target_pct:.0%} reached @ ${price:.2f} "
                    f"→ trailing stop activated, floor=${ps['stop_floor']:.2f}"
                )
        else:
            # Trail the floor upward as price sets new highs
            if price > ps["high_water_mark"]:
                ps["high_water_mark"] = price
                new_floor = price * (1 - trail_from_profit)
                if new_floor > ps["stop_floor"]:
                    ps["stop_floor"] = new_floor
                    log.info(f"[{symbol}] New high ${price:.2f} → floor raised to ${new_floor:.2f}")

        gap_pct = (price - ps["stop_floor"]) / price * 100 if ps["stop_floor"] > 0 else None
        summary["checked"].append({
            "symbol": symbol,
            "price": price,
            "floor": ps["stop_floor"],
            "hwm": ps["high_water_mark"],
            "gap_pct": gap_pct,
            "entry": entry,
            "qty": qty,
            "gain_pct": gain_pct,
            "profit_stop_active": ps.get("profit_stop_active", False),
        })

        # Stop triggered (only fires once profit_stop_active=True and floor is set)
        if ps.get("profit_stop_active") and price <= ps["stop_floor"]:
            log.warning(f"[{symbol}] STOP TRIGGERED @ ${price:.2f} (floor ${ps['stop_floor']:.2f})")
            try:
                close_position(symbol)
                log_trade("STOP_SELL", symbol, qty, price, f"floor={ps['stop_floor']:.2f}")
                summary["stopped_out"].append(symbol)
                del state["positions"][symbol]
                continue
            except Exception as e:
                log.error(f"[{symbol}] Stop-sell failed: {e}")

        # Laddered buys on deep dips below entry
        drop_from_entry = (entry - price) / entry
        for rung in cfg.get("ladder_buys", []):
            key = f"ladder_{rung['drop_pct']}"
            if drop_from_entry >= rung["drop_pct"] and key not in ps["ladder_triggered"]:
                try:
                    acct = get_account()
                    buying_power = float(acct.buying_power)
                    cost = price * rung["shares"]
                    if buying_power >= cost:
                        market_buy(symbol, rung["shares"])
                        log_trade(
                            "LADDER_BUY", symbol, rung["shares"], price,
                            f"drop={drop_from_entry:.1%} rung={rung['drop_pct']:.0%}"
                        )
                        ps["ladder_triggered"].append(key)
                        summary["laddered"].append({"symbol": symbol, "qty": rung["shares"], "price": price})
                    else:
                        log.warning(f"[{symbol}] Ladder buy skipped — insufficient buying power (${buying_power:.0f} < ${cost:.0f})")
                        if telegram_configured():
                            send_insufficient_funds_alert(symbol, cost, buying_power)
                except Exception as e:
                    log.error(f"[{symbol}] Ladder buy failed: {e}")

    save_state(state)
    return summary
