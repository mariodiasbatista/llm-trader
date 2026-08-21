"""
Phase 4 — The Wheel Strategy (Consistent Options Income)

Stage 1 → Sell a cash-secured put below current price → collect premium
Stage 2 → If assigned (stock drops below strike), sell a covered call above price → collect premium
         → If called away (stock rises above call strike), roll back to Stage 1

Rules:
- Close contracts early at profit_close_pct (buy-to-close, then roll to a fresh contract)
- Check every 15 minutes during market hours
- Requires Level 2 options approval on Alpaca
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from alpaca.trading.enums import OrderSide

from core.alpaca import (
    submit_option_order, close_option_position, get_latest_price,
    get_option_mid_price, get_position, get_open_orders, find_option_contract,
)
from core.logger import load_state, save_state, log_trade, log, state_lock

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def _settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)["wheel"]


def _next_expiry(weeks_out: int = 2) -> datetime:
    today = datetime.now()
    days_to_friday = (4 - today.weekday()) % 7 or 7
    return today + timedelta(days=days_to_friday + (weeks_out - 1) * 7)


def _sell_put(symbol: str, cfg: dict, contracts: int) -> dict | None:
    """Sell a cash-secured put and return the resulting wheel-state dict, or None if no listed contract/quote."""
    price = get_latest_price(symbol)
    target_strike = price * (1 - cfg.get("put_otm_pct", 0.05))
    target_expiry = _next_expiry(cfg.get("weeks_to_expiry", 2))

    found = find_option_contract(symbol, target_expiry, "put", target_strike)
    if found is None:
        log.warning(f"[{symbol}] No listed put contract found near strike ${target_strike:.2f} / expiry ~{target_expiry.date()}, skipping")
        return None
    option_sym, put_strike, expiry_date = found

    premium = get_option_mid_price(option_sym)
    if premium <= 0:
        log.warning(f"[{symbol}] Put premium is zero — quote unavailable for {option_sym}, skipping")
        return None

    try:
        order = submit_option_order(option_sym, contracts, OrderSide.SELL)
    except Exception as e:
        log.error(f"[{symbol}] Failed to sell put: {e}")
        return None
    fill_price = float(order.filled_avg_price) if order.filled_avg_price is not None else premium
    log_trade(
        "SELL_PUT", symbol, contracts, fill_price,
        f"option={option_sym} strike={put_strike}"
        + ("" if order.filled_avg_price is not None else " unconfirmed_fill=true")
    )
    return {
        "stage": 1,
        "contracts": contracts,
        "put_strike": put_strike,
        "option_symbol": option_sym,
        "premium_collected": fill_price,
        "expiry": expiry_date.strftime("%Y-%m-%d") if hasattr(expiry_date, "strftime") else str(expiry_date),
        "started": datetime.now().isoformat(),
    }


def _sell_call(symbol: str, cfg: dict, contracts: int, price: float) -> dict | None:
    """Sell a covered call and return the resulting wheel-state dict, or None if no listed contract/quote."""
    target_strike = price * (1 + cfg.get("call_otm_pct", 0.05))
    target_expiry = _next_expiry(cfg.get("weeks_to_expiry", 2))

    found = find_option_contract(symbol, target_expiry, "call", target_strike)
    if found is None:
        log.warning(f"[{symbol}] No listed call contract found near strike ${target_strike:.2f} / expiry ~{target_expiry.date()}, skipping")
        return None
    option_sym, call_strike, expiry_date = found

    premium = get_option_mid_price(option_sym)
    if premium <= 0:
        log.warning(f"[{symbol}] Call premium is zero — quote unavailable for {option_sym}, skipping")
        return None

    try:
        order = submit_option_order(option_sym, contracts, OrderSide.SELL)
    except Exception as e:
        log.error(f"[{symbol}] Failed to sell covered call: {e}")
        return None
    fill_price = float(order.filled_avg_price) if order.filled_avg_price is not None else premium
    log_trade(
        "SELL_CALL", symbol, contracts, fill_price,
        f"option={option_sym} strike={call_strike}"
        + ("" if order.filled_avg_price is not None else " unconfirmed_fill=true")
    )
    return {
        "stage": 2,
        "contracts": contracts,
        "call_strike": call_strike,
        "option_symbol": option_sym,
        "premium_collected": fill_price,
        "expiry": expiry_date.strftime("%Y-%m-%d") if hasattr(expiry_date, "strftime") else str(expiry_date),
        "started": datetime.now().isoformat(),
    }


def start_wheel(symbol: str, contracts: int = 1) -> dict:
    """Kick off The Wheel by selling the first cash-secured put."""
    cfg = _settings()
    # The enabled flag must gate OPENING too, not just check_and_manage(). Without
    # this the AI decision layer could still open wheels while the management loop
    # was switched off, leaving a short option with nothing to profit-close, roll,
    # or handle assignment for it — and wheel has no stop-loss to fall back on.
    # Happened for real: BWA 2026-08-21, opened with enabled=false and immediately
    # orphaned. Any caller wanting a manual wheel must flip wheel.enabled first.
    if not cfg.get("enabled", False):
        log.warning(f"[{symbol}] Wheel is disabled in settings — refusing to open a position that nothing would manage")
        return {}

    ws = _sell_put(symbol, cfg, contracts)
    if ws is None:
        return {}

    with state_lock():
        state = load_state()
        state.setdefault("wheel", {})[symbol] = ws
        save_state(state)
    log.info(f"[{symbol}] Wheel started | Stage 1 | sold put @ ${ws['put_strike']} exp {ws['expiry']}")
    return ws


def _try_early_profit_close(symbol: str, ws: dict, cfg: dict, price: float) -> tuple[bool, dict | None]:
    """
    Buy-to-close the current option leg if profit_close_pct has been captured, then
    roll into a fresh contract of the same stage (new put if stage 1, new call if stage 2).

    Returns (closed, new_ws). new_ws is None if closed but no roll was possible
    (quote unavailable) — caller should drop the symbol from state in that case.
    """
    option_sym = ws.get("option_symbol")
    premium_collected = ws.get("premium_collected")
    if not option_sym or not premium_collected:
        return False, None

    current_mid = get_option_mid_price(option_sym)
    if current_mid <= 0:
        return False, None

    # Short-option P&L is inverted vs. long stock: the premium seller profits
    # as the option's price falls (it becomes cheaper to buy back), not as it rises.
    pct_captured = (premium_collected - current_mid) / premium_collected
    profit_close_pct = cfg.get("profit_close_pct", 0.5)
    if pct_captured < profit_close_pct:
        return False, None

    stage = ws.get("stage", 1)
    contracts = ws.get("contracts", 1)
    try:
        close_order = close_option_position(option_sym, contracts)
        close_fill = float(close_order.filled_avg_price) if close_order.filled_avg_price is not None else current_mid
        log_trade(
            "TAKE_PROFIT", symbol, contracts, close_fill,
            f"option={option_sym} pct_captured={pct_captured:.1%}"
            + ("" if close_order.filled_avg_price is not None else " unconfirmed_fill=true")
        )
    except Exception as e:
        log.error(f"[{symbol}] Early profit-close failed: {e}")
        return False, None

    new_ws = _sell_put(symbol, cfg, contracts) if stage == 1 else _sell_call(symbol, cfg, contracts, price)
    return True, new_ws


def check_and_manage() -> dict:
    """
    Check all wheel positions and advance stages where needed.
    Called every 15 minutes during market hours.
    """
    cfg = _settings()
    if not cfg.get("enabled", False):
        return {"status": "wheel disabled"}

    with state_lock():
        state = load_state()
        wheel = state.setdefault("wheel", {})
        actions = []

        for symbol, ws in list(wheel.items()):
            expiry_str = ws.get("expiry")
            if not expiry_str:
                log.warning(f"[{symbol}] Wheel state missing expiry — skipping")
                continue
            price = get_latest_price(symbol)
            stage = ws.get("stage", 1)
            contracts = ws.get("contracts", 1)

            closed, new_ws = _try_early_profit_close(symbol, ws, cfg, price)
            if closed:
                if new_ws:
                    wheel[symbol] = new_ws
                    actions.append(f"{symbol}: closed stage {stage} early for profit, rolled to new contract")
                else:
                    del wheel[symbol]
                    actions.append(f"{symbol}: closed stage {stage} early for profit, no roll (quote unavailable)")
                continue

            expiry = datetime.strptime(expiry_str, "%Y-%m-%d")

            if stage == 1:
                # Check if put was assigned (we now hold ≥100 shares)
                pos = get_position(symbol)
                shares = float(pos.qty) if pos else 0
                if shares >= 100 * contracts:
                    log.info(f"[{symbol}] Assigned at put stage — moving to Stage 2 (covered calls)")
                    new_ws = _sell_call(symbol, cfg, contracts, price)
                    if new_ws:
                        wheel[symbol] = new_ws
                        actions.append(f"{symbol}: Stage 1→2 | sold call @ ${new_ws['call_strike']}")

            elif stage == 2:
                # Check if shares were called away
                pos = get_position(symbol)
                shares = float(pos.qty) if pos else 0
                if shares < 100 * contracts:
                    log.info(f"[{symbol}] Shares called away — rolling back to Stage 1")
                    new_ws = _sell_put(symbol, cfg, contracts)
                    if new_ws:
                        wheel[symbol] = new_ws
                        actions.append(f"{symbol}: Stage 2→1 | sold put @ ${new_ws['put_strike']}")

        state["wheel"] = wheel
        save_state(state)
    return {"actions": actions}
