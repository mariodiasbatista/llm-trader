"""
Estimate WHEEL (cash-secured put / covered call) premiums for backtesting.

Alpaca's OPRA market-data agreement is not signed on this account — confirmed
directly: `OptionBarsRequest` returns "OPRA agreement is not signed" even for
a live, currently-listed contract. Real historical option quotes are not
available at any horizon here, so premiums are instead estimated via
Black-Scholes using historical stock closes plus a rolling realized-volatility
proxy. This is clearly an approximation, not real market data — results from
this module must always be labeled "estimated" and reported separately from
real-trade P&L, never blended into one number.
"""
import math
from datetime import date, timedelta
from statistics import stdev

from core.alpaca import get_bars_range

RISK_FREE_RATE = 0.05  # rough T-bill proxy; negligible effect on short-dated OTM premiums


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes_put(spot: float, strike: float, days_to_expiry: float, vol: float, r: float = RISK_FREE_RATE) -> float:
    if days_to_expiry <= 0 or vol <= 0 or spot <= 0:
        return max(strike - spot, 0.0)
    t = days_to_expiry / 365.0
    d1 = (math.log(spot / strike) + (r + 0.5 * vol ** 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def black_scholes_call(spot: float, strike: float, days_to_expiry: float, vol: float, r: float = RISK_FREE_RATE) -> float:
    if days_to_expiry <= 0 or vol <= 0 or spot <= 0:
        return max(spot - strike, 0.0)
    t = days_to_expiry / 365.0
    d1 = (math.log(spot / strike) + (r + 0.5 * vol ** 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return spot * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)


def realized_vol(closes: list[float], window: int = 20) -> float:
    """Annualized realized volatility from daily closes (last `window` days)."""
    window = min(window, len(closes) - 1)
    if window < 2:
        return 0.30  # fallback: typical single-stock vol when history is too short
    returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(len(closes) - window, len(closes))
        if closes[i - 1] > 0
    ]
    if len(returns) < 2:
        return 0.30
    return stdev(returns) * math.sqrt(252)


def simulate_wheel_cycle(symbol: str, start_date: date, cfg: dict, max_cycles: int = 12, bars=None) -> dict:
    """
    Simulate repeated put-sell (rolling to covered-call on assignment) cycles
    for one ticker starting at start_date, using Black-Scholes-estimated
    premiums and profit_close_pct-triggered early closes — mirroring
    strategies/wheel.py's stage machine at a simplified, estimate-only level.

    Pass `bars` (pre-fetched via core.alpaca.get_bars_range) to avoid a network
    round-trip per candidate when sweeping — only the cfg changes between
    sweep iterations, not the underlying price series.

    Returns {"total_pnl": float, "cycles": [...], "months_covered": int}.
    """
    weeks_to_expiry = cfg.get("weeks_to_expiry", 2)
    put_otm_pct = cfg.get("put_otm_pct", 0.05)
    call_otm_pct = cfg.get("call_otm_pct", 0.05)
    profit_close_pct = cfg.get("profit_close_pct", 0.5)
    expiry_days = weeks_to_expiry * 7

    if bars is None:
        end_date = min(date.today(), start_date + timedelta(weeks=weeks_to_expiry * max_cycles + 4))
        bars = get_bars_range(symbol, start_date - timedelta(days=30), end_date)
    if len(bars) < 25:
        return {"total_pnl": 0.0, "cycles": [], "months_covered": 0}

    closes = [float(b.close) for b in bars]
    dates = [b.timestamp.date() if hasattr(b.timestamp, "date") else b.timestamp for b in bars]

    def price_and_vol_at(idx):
        window_closes = closes[max(0, idx - 25): idx + 1]
        return closes[idx], realized_vol(window_closes)

    idx = next((i for i, d in enumerate(dates) if d >= start_date), 0)
    stage = 1
    total_pnl = 0.0
    cycles = []

    for _ in range(max_cycles):
        if idx >= len(closes) - 1:
            break
        spot, vol = price_and_vol_at(idx)
        strike = round(spot * (1 - put_otm_pct)) if stage == 1 else round(spot * (1 + call_otm_pct))
        premium = (
            black_scholes_put(spot, strike, expiry_days, vol)
            if stage == 1 else black_scholes_call(spot, strike, expiry_days, vol)
        )
        if premium <= 0:
            break

        exit_idx = min(idx + expiry_days, len(closes) - 1)
        cycle_pnl, exit_reason, assigned = None, "expired_worthless", False

        for j in range(idx + 1, exit_idx + 1):
            cur_spot, cur_vol = price_and_vol_at(j)
            days_left = expiry_days - (j - idx)
            cur_premium = (
                black_scholes_put(cur_spot, strike, days_left, cur_vol)
                if stage == 1 else black_scholes_call(cur_spot, strike, days_left, cur_vol)
            )
            if premium > 0 and (premium - cur_premium) / premium >= profit_close_pct:
                cycle_pnl, exit_reason, idx = premium - cur_premium, "early_profit_close", j
                break

        if cycle_pnl is None:
            final_spot = closes[exit_idx]
            intrinsic = max(strike - final_spot, 0) if stage == 1 else max(final_spot - strike, 0)
            cycle_pnl = premium - intrinsic
            assigned = intrinsic > 0
            idx = exit_idx

        total_pnl += cycle_pnl
        cycles.append({
            "date": dates[min(idx, len(dates) - 1)], "stage": stage, "strike": strike,
            "premium": premium, "pnl": cycle_pnl, "exit_reason": exit_reason,
        })
        if assigned:
            stage = 2 if stage == 1 else 1

    months_covered = len({f"{c['date'].year}-{c['date'].month:02d}" for c in cycles}) if cycles else 0
    return {"total_pnl": total_pnl, "cycles": cycles, "months_covered": months_covered}
