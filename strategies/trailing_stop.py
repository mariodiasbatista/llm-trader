"""
Phase 2 — Trailing Stop Strategy
- Holds freely until the position reaches profit_target_pct gain from entry
- Once the profit target is hit, activates a trailing stop floor
- Raises the floor as price climbs (trails trailing_pct_from_profit below the new high)
- Sells the full position if price hits the active floor
- Laddered buys: auto-purchases more shares on steep dips
"""
import json
from datetime import datetime
from pathlib import Path

from alpaca.trading.enums import AssetClass

from core.alpaca import get_positions, get_latest_price, close_position, market_buy, get_account
from core.logger import load_state, save_state, log_trade, log, state_lock
from core.notifier import is_configured as telegram_configured, send_insufficient_funds_alert

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def _settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)["trailing_stop"]


def evaluate_position(cfg: dict, ps: dict, price: float, entry: float) -> list[dict]:
    """
    Pure state-transition step for a single tracked position — no I/O, no
    logging, no Alpaca calls. Mutates `ps` in place and returns the list of
    events that occurred this step, e.g.:

      {"type": "bootstrap", "floor": ..., "classic_mode": ...}
      {"type": "profit_target_activated", "floor": ...}
      {"type": "floor_raised", "floor": ...}
      {"type": "TAKE_PROFIT", "gain_pct": ...}
      {"type": "STOP_SELL", "floor": ...}
      {"type": "LADDER_BUY", "drop_pct": ..., "shares": ..., "drop_from_entry": ...}

    A TAKE_PROFIT or STOP_SELL event means the position is fully closed — the
    caller should stop evaluating it further. Shared verbatim between the live
    check_and_update() loop and backtest/replay.py so the two can never drift.
    """
    events = []
    initial_stop_pct = cfg.get("initial_stop_pct", 0)
    profit_target_pct = cfg.get("profit_target_pct", 0)
    take_profit_pct = cfg.get("take_profit_pct", 0)
    trailing_pct = cfg.get("trailing_pct", 0.05)
    trail_from_profit = cfg.get("trailing_pct_from_profit", trailing_pct)
    gain_pct = (price - entry) / entry

    # Two modes driven by initial_stop_pct:
    #   > 0  →  classic mode: floor set immediately on entry, trails from day 1
    #   = 0  →  profit-target mode: floor stays 0 until gain_pct hits profit_target_pct
    classic_mode = initial_stop_pct > 0

    if "high_water_mark" not in ps:
        floor = price * (1 - initial_stop_pct) if classic_mode else 0.0
        ps["high_water_mark"] = price
        ps["stop_floor"] = floor
        ps["ladder_triggered"] = []
        ps["profit_stop_active"] = classic_mode
        events.append({"type": "bootstrap", "floor": floor, "classic_mode": classic_mode})

    # Backfill flag for positions bootstrapped before this field existed
    if "profit_stop_active" not in ps:
        ps["profit_stop_active"] = ps.get("stop_floor", 0) > 0

    if not ps.get("profit_stop_active", False):
        # Profit-target mode: activate once target is reached
        if profit_target_pct > 0 and gain_pct >= profit_target_pct:
            ps["profit_stop_active"] = True
            ps["high_water_mark"] = price
            ps["stop_floor"] = price * (1 - trail_from_profit)
            events.append({"type": "profit_target_activated", "floor": ps["stop_floor"]})
    else:
        # Classic or activated profit-target: trail floor upward on new highs
        if price > ps["high_water_mark"]:
            ps["high_water_mark"] = price
            pct = trailing_pct if classic_mode else trail_from_profit
            new_floor = price * (1 - pct)
            if new_floor > ps["stop_floor"]:
                ps["stop_floor"] = new_floor
                events.append({"type": "floor_raised", "floor": new_floor})

    # Take-profit: sell immediately when gain hits the target
    if take_profit_pct > 0 and gain_pct >= take_profit_pct:
        events.append({"type": "TAKE_PROFIT", "gain_pct": gain_pct})
        return events

    # Stop triggered when floor is active and price breaches it
    if ps.get("profit_stop_active") and price <= ps["stop_floor"]:
        events.append({"type": "STOP_SELL", "floor": ps["stop_floor"]})
        return events

    # Laddered buys on deep dips below entry
    drop_from_entry = (entry - price) / entry
    for rung in cfg.get("ladder_buys", []):
        key = f"ladder_{rung['drop_pct']}"
        if drop_from_entry >= rung["drop_pct"] and key not in ps["ladder_triggered"]:
            ps["ladder_triggered"].append(key)
            events.append({
                "type": "LADDER_BUY",
                "drop_pct": rung["drop_pct"],
                "shares": rung["shares"],
                "drop_from_entry": drop_from_entry,
            })

    return events


def check_and_update() -> dict:
    """
    Evaluate all open positions against trailing stop rules.
    Meant to be called every 5 minutes during market hours.
    Returns a summary of every position and any actions taken.
    """
    cfg = _settings()
    positions = get_positions()
    summary = {"checked": [], "stopped_out": [], "laddered": []}

    with state_lock():
        state = load_state()

        for pos in positions:
            if pos.asset_class != AssetClass.US_EQUITY:
                # Options legs (WHEEL's short puts/calls) are managed by wheel.py —
                # long-stock trailing/take-profit math is meaningless for them.
                continue

            symbol = pos.symbol
            price = float(pos.current_price)
            entry = float(pos.avg_entry_price)
            qty = float(pos.qty)

            if entry <= 0 or price <= 0:
                log.warning(f"[{symbol}] Skipping — invalid price={price} or entry={entry}")
                continue

            if symbol not in state["positions"]:
                state["positions"][symbol] = {"entry_price": entry}
            ps = state["positions"][symbol]

            events = evaluate_position(cfg, ps, price, entry)

            for ev in events:
                if ev["type"] == "bootstrap":
                    log.info(
                        f"[{symbol}] New position tracked | entry=${entry:.2f} | "
                        + (f"floor=${ev['floor']:.2f}" if ev["classic_mode"] else "waiting for profit target")
                    )
                elif ev["type"] == "profit_target_activated":
                    log.info(
                        f"[{symbol}] Profit target +{cfg.get('profit_target_pct', 0):.0%} reached @ ${price:.2f} "
                        f"→ trailing stop activated, floor=${ev['floor']:.2f}"
                    )
                elif ev["type"] == "floor_raised":
                    log.info(f"[{symbol}] New high ${price:.2f} → floor raised to ${ev['floor']:.2f}")

            gap_pct = (price - ps["stop_floor"]) / price * 100 if (ps["stop_floor"] > 0 and price > 0) else None
            summary["checked"].append({
                "symbol": symbol,
                "price": price,
                "floor": ps["stop_floor"],
                "hwm": ps["high_water_mark"],
                "gap_pct": gap_pct,
                "entry": entry,
                "qty": qty,
                "gain_pct": (price - entry) / entry,
                "profit_stop_active": ps.get("profit_stop_active", False),
            })

            closed = False
            for ev in events:
                if ev["type"] not in ("TAKE_PROFIT", "STOP_SELL"):
                    continue
                action = ev["type"]
                if action == "TAKE_PROFIT":
                    log.info(f"[{symbol}] TAKE PROFIT @ ${price:.2f} (+{ev['gain_pct']:.1%} from entry ${entry:.2f})")
                else:
                    log.warning(f"[{symbol}] STOP TRIGGERED @ ${price:.2f} (floor ${ev['floor']:.2f})")
                try:
                    close_order = close_position(symbol)
                    fill_price = float(close_order.filled_avg_price) if close_order.filled_avg_price is not None else price
                    notes = (
                        f"gain={ev['gain_pct']:.1%} target={cfg.get('take_profit_pct', 0):.0%}"
                        if action == "TAKE_PROFIT"
                        else f"floor={ev['floor']:.2f}"
                    )
                    log_trade(
                        action, symbol, qty, fill_price,
                        notes + ("" if close_order.filled_avg_price is not None else " unconfirmed_fill=true")
                    )
                    summary["stopped_out"].append(symbol)
                    del state["positions"][symbol]
                    if action == "STOP_SELL":
                        state.setdefault("stopped_out", {})[symbol] = datetime.now().strftime("%Y-%m-%d")
                    closed = True
                except Exception as e:
                    log.error(f"[{symbol}] {'Take-profit' if action == 'TAKE_PROFIT' else 'Stop-sell'} sell failed: {e}")
                break  # at most one terminal event per evaluation

            if closed:
                continue

            for ev in events:
                if ev["type"] != "LADDER_BUY":
                    continue
                try:
                    acct = get_account()
                    buying_power = float(acct.buying_power)
                    cost = price * ev["shares"]
                    if buying_power >= cost:
                        order = market_buy(symbol, ev["shares"])
                        fill_price = float(order.filled_avg_price) if order.filled_avg_price is not None else price
                        log_trade(
                            "LADDER_BUY", symbol, ev["shares"], fill_price,
                            f"drop={ev['drop_from_entry']:.1%} rung={ev['drop_pct']:.0%}"
                            + ("" if order.filled_avg_price is not None else " unconfirmed_fill=true")
                        )
                        summary["laddered"].append({"symbol": symbol, "qty": ev["shares"], "price": fill_price})
                    else:
                        log.warning(f"[{symbol}] Ladder buy skipped — insufficient buying power (${buying_power:.0f} < ${cost:.0f})")
                        if telegram_configured():
                            send_insufficient_funds_alert(symbol, cost, buying_power)
                except Exception as e:
                    log.error(f"[{symbol}] Ladder buy failed: {e}")

        save_state(state)
    return summary
