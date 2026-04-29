"""
Phase 4 — The Wheel Strategy (Consistent Options Income)

Stage 1 → Sell a cash-secured put below current price → collect premium
Stage 2 → If assigned (stock drops below strike), sell a covered call above price → collect premium
         → If called away (stock rises above call strike), roll back to Stage 1

Rules:
- Close contracts early at 50% profit
- Check every 15 minutes during market hours
- Requires Level 2 options approval on Alpaca
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from alpaca.trading.enums import OrderSide

from core.alpaca import submit_option_order, get_latest_price, get_option_mid_price, get_position, get_open_orders
from core.logger import load_state, save_state, log_trade, log

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def _settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)["wheel"]


def _occ_symbol(underlying: str, expiry: datetime, option_type: str, strike: float) -> str:
    """Build OCC option symbol e.g. AAPL240315C00150000"""
    exp = expiry.strftime("%y%m%d")
    cp = "C" if option_type == "call" else "P"
    strike_str = f"{int(strike * 1000):08d}"
    return f"{underlying}{exp}{cp}{strike_str}"


def _next_expiry(weeks_out: int = 2) -> datetime:
    today = datetime.now()
    days_to_friday = (4 - today.weekday()) % 7 or 7
    return today + timedelta(days=days_to_friday + (weeks_out - 1) * 7)


def start_wheel(symbol: str, contracts: int = 1) -> dict:
    """Kick off The Wheel by selling the first cash-secured put."""
    cfg = _settings()
    price = get_latest_price(symbol)
    put_strike = round(price * (1 - cfg.get("put_otm_pct", 0.05)))

    expiry = _next_expiry(cfg.get("weeks_to_expiry", 2))
    option_sym = _occ_symbol(symbol, expiry, "put", put_strike)

    premium = get_option_mid_price(option_sym)
    submit_option_order(option_sym, contracts, OrderSide.SELL)
    log_trade("SELL_PUT", symbol, contracts, premium, f"option={option_sym} strike={put_strike}")

    state = load_state()
    state["wheel"][symbol] = {
        "stage": 1,
        "contracts": contracts,
        "put_strike": put_strike,
        "option_symbol": option_sym,
        "expiry": expiry.strftime("%Y-%m-%d"),
        "started": datetime.now().isoformat(),
    }
    save_state(state)
    log.info(f"[{symbol}] Wheel started | Stage 1 | sold put @ ${put_strike} exp {expiry.date()}")
    return state["wheel"][symbol]


def check_and_manage() -> dict:
    """
    Check all wheel positions and advance stages where needed.
    Called every 15 minutes during market hours.
    """
    cfg = _settings()
    if not cfg.get("enabled", False):
        return {"status": "wheel disabled"}

    state = load_state()
    wheel = state.get("wheel", {})
    actions = []

    for symbol, ws in list(wheel.items()):
        price = get_latest_price(symbol)
        stage = ws.get("stage", 1)
        contracts = ws.get("contracts", 1)
        expiry = datetime.strptime(ws["expiry"], "%Y-%m-%d")

        if stage == 1:
            # Check if put was assigned (we now hold ≥100 shares)
            pos = get_position(symbol)
            shares = float(pos.qty) if pos else 0
            if shares >= 100 * contracts:
                log.info(f"[{symbol}] Assigned at put stage — moving to Stage 2 (covered calls)")
                call_strike = round(price * (1 + cfg.get("call_otm_pct", 0.05)))
                new_expiry = _next_expiry(cfg.get("weeks_to_expiry", 2))
                option_sym = _occ_symbol(symbol, new_expiry, "call", call_strike)
                try:
                    call_premium = get_option_mid_price(option_sym)
                    submit_option_order(option_sym, contracts, OrderSide.SELL)
                    log_trade("SELL_CALL", symbol, contracts, call_premium, f"option={option_sym} strike={call_strike}")
                    ws["stage"] = 2
                    ws["call_strike"] = call_strike
                    ws["option_symbol"] = option_sym
                    ws["expiry"] = new_expiry.strftime("%Y-%m-%d")
                    actions.append(f"{symbol}: Stage 1→2 | sold call @ ${call_strike}")
                except Exception as e:
                    log.error(f"[{symbol}] Failed to sell covered call: {e}")

        elif stage == 2:
            # Check if shares were called away
            pos = get_position(symbol)
            shares = float(pos.qty) if pos else 0
            if shares < 100 * contracts:
                log.info(f"[{symbol}] Shares called away — rolling back to Stage 1")
                put_strike = round(price * (1 - cfg.get("put_otm_pct", 0.05)))
                new_expiry = _next_expiry(cfg.get("weeks_to_expiry", 2))
                option_sym = _occ_symbol(symbol, new_expiry, "put", put_strike)
                try:
                    put_premium = get_option_mid_price(option_sym)
                    submit_option_order(option_sym, contracts, OrderSide.SELL)
                    log_trade("SELL_PUT", symbol, contracts, put_premium, f"option={option_sym} strike={put_strike}")
                    ws["stage"] = 1
                    ws["put_strike"] = put_strike
                    ws["option_symbol"] = option_sym
                    ws["expiry"] = new_expiry.strftime("%Y-%m-%d")
                    actions.append(f"{symbol}: Stage 2→1 | sold put @ ${put_strike}")
                except Exception as e:
                    log.error(f"[{symbol}] Failed to sell put: {e}")

    state["wheel"] = wheel
    save_state(state)
    return {"actions": actions}
