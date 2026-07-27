"""
Coordinate-descent parameter sweep across TRAILING_STOP, sec_insiders filters,
position sizing, and WHEEL settings.

Scoring is grounded in real historical trade data (the ~34 actual TRAILING_STOP
positions in logs/trades.log, replayed against real historical daily bars under
each candidate's parameters) — that's the primary ranking signal. A broader
SEC EDGAR historical-signal replay and a Black-Scholes WHEEL premium estimate
are computed alongside as corroborating evidence and reported separately,
never blended into the primary score (real trades vs. synthetic replay differ
too much in sample composition for one number to be meaningful).
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

from core.alpaca import get_bars_range
from backtest.real_trades import parse_trades_log, build_positions
from backtest.replay import simulate_trailing_stop
from backtest.wheel_replay import simulate_wheel_cycle
from backtest.buckets import bucket_by_month, worst_bucket_pnl, all_buckets_positive
from backtest.signals import filter_signals, fetch_historical_insider_signals

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"

LADDER_BUYS_DEFAULT = [{"drop_pct": 0.2, "shares": 10}, {"drop_pct": 0.3, "shares": 20}]

PARAM_GRID = {
    "trailing_stop.initial_stop_pct":       [0.05, 0.07, 0.08, 0.10, 0.12, 0.15],
    "trailing_stop.trailing_pct":           [0.03, 0.05, 0.06, 0.08, 0.10],
    "trailing_stop.take_profit_pct":        [0.05, 0.06, 0.08, 0.10, 0.12],
    "trailing_stop.profit_target_pct":      [0.0, 0.02, 0.03, 0.05],
    "trailing_stop.ladder_buys_enabled":    [True, False],
    "position_size_usd":                    [3000, 5000, 8000, 10000],
    "min_entry_price":                      [0, 5, 10, 20, 50],
    "sec_insiders.min_transaction_value":    [100_000, 150_000, 250_000, 500_000],
    "sec_insiders.require_high_conviction":  [True, False],
    "wheel.put_otm_pct":                    [0.03, 0.05, 0.07, 0.10],
    "wheel.call_otm_pct":                   [0.03, 0.05, 0.07, 0.10],
    "wheel.profit_close_pct":               [0.3, 0.5, 0.7],
    "wheel.weeks_to_expiry":                [1, 2, 3],
}


def _load_base_config() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def candidate_from_base(base: dict) -> dict:
    return {
        "trailing_stop.initial_stop_pct": base["trailing_stop"]["initial_stop_pct"],
        "trailing_stop.trailing_pct": base["trailing_stop"]["trailing_pct"],
        "trailing_stop.take_profit_pct": base["trailing_stop"]["take_profit_pct"],
        "trailing_stop.profit_target_pct": base["trailing_stop"]["profit_target_pct"],
        "trailing_stop.ladder_buys_enabled": bool(base["trailing_stop"].get("ladder_buys")),
        "position_size_usd": base.get("analyze", {}).get("max_position_usd", 10000),
        # No live equivalent today — the investigation's strongest finding was that
        # post-migration losses cluster in thin, sub-$20 micro-caps, so this is
        # swept from 0 (no filter, matching current behavior) upward.
        "min_entry_price": 0,
        "sec_insiders.min_transaction_value": base["sec_insiders"]["min_transaction_value"],
        "sec_insiders.require_high_conviction": base["sec_insiders"]["require_high_conviction"],
        "wheel.put_otm_pct": base["wheel"]["put_otm_pct"],
        "wheel.call_otm_pct": base["wheel"]["call_otm_pct"],
        "wheel.profit_close_pct": base["wheel"]["profit_close_pct"],
        "wheel.weeks_to_expiry": base["wheel"]["weeks_to_expiry"],
    }


def candidate_to_cfgs(candidate: dict) -> tuple[dict, dict, float]:
    ts_cfg = {
        "initial_stop_pct": candidate["trailing_stop.initial_stop_pct"],
        "trailing_pct": candidate["trailing_stop.trailing_pct"],
        "take_profit_pct": candidate["trailing_stop.take_profit_pct"],
        "profit_target_pct": candidate["trailing_stop.profit_target_pct"],
        "trailing_pct_from_profit": candidate["trailing_stop.trailing_pct"],
        "ladder_buys": LADDER_BUYS_DEFAULT if candidate["trailing_stop.ladder_buys_enabled"] else [],
    }
    wheel_cfg = {
        "put_otm_pct": candidate["wheel.put_otm_pct"],
        "call_otm_pct": candidate["wheel.call_otm_pct"],
        "profit_close_pct": candidate["wheel.profit_close_pct"],
        "weeks_to_expiry": candidate["wheel.weeks_to_expiry"],
    }
    return ts_cfg, wheel_cfg, candidate["position_size_usd"]


def candidate_diff(candidate: dict, base: dict) -> dict:
    return {k: v for k, v in candidate.items() if base.get(k) != v}


# ── Bar prefetch (once per sweep run — reused across every candidate) ────────

def _prefetch_bars(keys: list[tuple[str, date]], days_forward: int = 180) -> dict:
    cache = {}
    for symbol, start in keys:
        if (symbol, start) in cache:
            continue
        end = min(date.today(), start + timedelta(days=days_forward))
        try:
            cache[(symbol, start)] = get_bars_range(symbol, start, end)
        except Exception:
            cache[(symbol, start)] = []
    return cache


# ── Per-evidence-source scoring ───────────────────────────────────────────────

def _score_trailing_stop(positions: list[dict], bars_cache: dict, ts_cfg: dict, position_size_usd: float, min_entry_price: float = 0) -> dict:
    records = []
    for pos in positions:
        symbol, start = pos["symbol"], pos["first_buy_date"]
        entry_price = pos["buys"][0]["price"]
        if entry_price < min_entry_price:
            continue
        bars = bars_cache.get((symbol, start))
        if not bars:
            continue
        result = simulate_trailing_stop(symbol, start, entry_price, ts_cfg, position_size_usd, bars=bars)
        if result is None:
            continue
        records.append({
            "symbol": symbol, "pnl": result["pnl_usd"], "exit_date": result["exit_date"],
            "exit_reason": result["exit_reason"], "is_open": result["is_open"],
        })
    buckets = bucket_by_month(records, "exit_date")
    return {
        "records": records, "buckets": buckets,
        "worst_month_pnl": worst_bucket_pnl(buckets),
        "total_pnl": sum(r["pnl"] for r in records),
        "n_trades": len(records),
        "all_positive": all_buckets_positive(buckets),
    }


def _score_edgar_replay(signals_raw, bars_cache, ts_cfg, position_size_usd, min_transaction_value, require_high_conviction, min_entry_price: float = 0) -> dict | None:
    if not signals_raw:
        return None
    filtered = filter_signals(signals_raw, min_transaction_value, require_high_conviction)
    records = []
    for sig in filtered:
        symbol = sig["asset"]["ticker"]
        try:
            # publishedDate (filing date) is when the bot could actually see this
            # signal — txDate is the insider's own transaction date, which can be
            # up to 2 business days earlier. Entry price also comes from real
            # market bars, never the Form 4-reported per-share price: the bot
            # always buys at the current market price via market_buy(), and an
            # insider's reported price can reflect a negotiated/restricted-stock
            # price wildly different from the market (confirmed empirically —
            # e.g. one filing reported $0.80 for a stock trading at $13.28).
            entry_date = date.fromisoformat(sig["publishedDate"])
        except (ValueError, KeyError):
            continue
        bars = bars_cache.get((symbol, entry_date))
        if not bars:
            continue
        entry_price = float(bars[0].close)
        if entry_price < max(min_entry_price, 0.01):
            continue
        result = simulate_trailing_stop(symbol, entry_date, entry_price, ts_cfg, position_size_usd, bars=bars)
        if result is None:
            continue
        records.append({
            "symbol": symbol, "pnl": result["pnl_usd"], "exit_date": result["exit_date"],
            "exit_reason": result["exit_reason"], "is_open": result["is_open"],
        })
    buckets = bucket_by_month(records, "exit_date")
    return {
        "records": records, "buckets": buckets,
        "worst_month_pnl": worst_bucket_pnl(buckets),
        "total_pnl": sum(r["pnl"] for r in records),
        "n_trades": len(records),
        "all_positive": all_buckets_positive(buckets),
        "n_filtered_from": len(signals_raw),
    }


def _score_wheel(universe: list[tuple[str, date]], bars_cache: dict, wheel_cfg: dict) -> dict:
    records = []
    for symbol, start in universe:
        bars = bars_cache.get((symbol, start))
        result = simulate_wheel_cycle(symbol, start, wheel_cfg, bars=bars)
        for c in result["cycles"]:
            records.append({"symbol": symbol, "pnl": c["pnl"], "exit_date": c["date"]})
    buckets = bucket_by_month(records, "exit_date")
    return {
        "records": records, "buckets": buckets,
        "worst_month_pnl": worst_bucket_pnl(buckets),
        "total_pnl": sum(r["pnl"] for r in records),
        "n_trades": len(records),
        "all_positive": all_buckets_positive(buckets),
    }


# ── Sweep driver ───────────────────────────────────────────────────────────────

def run_sweep(
    max_iterations: int = 200,
    edgar_start: date | None = None,
    edgar_end: date | None = None,
    use_edgar_cache: bool = True,
    seed: int = 42,
    target_passing: int = 3,
    progress_cb=None,
) -> dict:
    rng = random.Random(seed)
    base = _load_base_config()
    current = candidate_from_base(base)

    positions = [p for p in build_positions(parse_trades_log()) if p["buys"]]

    bars_cache = _prefetch_bars([(p["symbol"], p["first_buy_date"]) for p in positions])

    signals_raw = []
    edgar_bars_cache = {}
    if edgar_start and edgar_end:
        signals_raw = fetch_historical_insider_signals(edgar_start, edgar_end, use_cache=use_edgar_cache)
        # Prefetch bars for the loosest possible filter so every candidate's
        # (tighter) filtered subset is already covered by the cache.
        loosest = filter_signals(signals_raw, min_transaction_value=50_000, require_high_conviction=False)
        keys = []
        for sig in loosest:
            try:
                keys.append((sig["asset"]["ticker"], date.fromisoformat(sig["publishedDate"])))
            except (ValueError, KeyError):
                continue
        edgar_bars_cache = _prefetch_bars(keys)

    wheel_universe = list({(p["symbol"], p["first_buy_date"]) for p in positions})
    wheel_bars_cache = _prefetch_bars(wheel_universe, days_forward=120)

    def evaluate(candidate: dict) -> dict:
        ts_cfg, wheel_cfg, pos_size = candidate_to_cfgs(candidate)
        min_entry_price = candidate["min_entry_price"]
        real_result = _score_trailing_stop(positions, bars_cache, ts_cfg, pos_size, min_entry_price)
        edgar_result = _score_edgar_replay(
            signals_raw, edgar_bars_cache, ts_cfg, pos_size,
            candidate["sec_insiders.min_transaction_value"],
            candidate["sec_insiders.require_high_conviction"],
            min_entry_price,
        )
        wheel_result = _score_wheel(wheel_universe, wheel_bars_cache, wheel_cfg)

        passes_strict = real_result["all_positive"] and (edgar_result is None or edgar_result["all_positive"])
        return {
            "candidate": dict(candidate),
            "real_trades": real_result,
            "edgar_replay": edgar_result,
            "wheel_estimate": wheel_result,
            "score": (real_result["worst_month_pnl"], real_result["total_pnl"]),
            "passes_strict": passes_strict,
        }

    best = evaluate(current)
    all_results = [best]
    passing = [best] if best["passes_strict"] else []

    axes = list(PARAM_GRID.keys())
    iterations = 0
    while iterations < max_iterations and len(passing) < target_passing:
        axis = rng.choice(axes)
        trial = dict(current)
        trial[axis] = rng.choice(PARAM_GRID[axis])
        iterations += 1
        if trial == current:
            continue

        result = evaluate(trial)
        all_results.append(result)

        if result["score"] > best["score"]:
            best = result
            current = trial
        if result["passes_strict"]:
            passing.append(result)

        if progress_cb:
            progress_cb(iterations, max_iterations, best, len(passing))

    all_results.sort(key=lambda r: r["score"], reverse=True)
    return {
        "iterations": iterations,
        "best": best,
        "passing": passing,
        "leaderboard": all_results[:20],
        "base_candidate": candidate_from_base(base),
        "n_real_positions": len(positions),
        "n_edgar_signals": len(signals_raw),
    }


if __name__ == "__main__":
    import argparse

    from backtest.report import generate_leaderboard

    parser = argparse.ArgumentParser(description="Run the strategy parameter sweep.")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--edgar-days", type=int, default=0, help="Also replay this many days of historical EDGAR signals (0 = skip)")
    parser.add_argument("--edgar-end", type=str, default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--no-cache", action="store_true", help="Force a fresh EDGAR fetch instead of using backtest/cache/")
    parser.add_argument("--label", type=str, default=None, help="Label for the output leaderboard/json filenames")
    args = parser.parse_args()

    def _progress(i, total, best, n_passing):
        if i % 10 == 0 or i == total:
            print(f"  [{i}/{total}] best worst-month=${best['score'][0]:,.0f} total=${best['score'][1]:,.0f} passing={n_passing}")

    edgar_start = edgar_end = None
    if args.edgar_days > 0:
        edgar_end = date.fromisoformat(args.edgar_end) if args.edgar_end else date.today()
        edgar_start = edgar_end - timedelta(days=args.edgar_days)
        print(f"Will replay historical EDGAR signals {edgar_start} .. {edgar_end}")

    print(f"Running parameter sweep (max {args.iterations} iterations)...")
    result = run_sweep(
        max_iterations=args.iterations,
        edgar_start=edgar_start,
        edgar_end=edgar_end,
        use_edgar_cache=not args.no_cache,
        progress_cb=_progress,
    )
    print(f"\nDone. {result['iterations']} iterations, {len(result['passing'])} fully-passing candidates found.")
    print(f"Best worst-month P&L: ${result['best']['score'][0]:,.0f} | total: ${result['best']['score'][1]:,.0f}")

    md_path, json_path = generate_leaderboard(result, label=args.label)
    print(f"\nLeaderboard: {md_path}")
    print(f"Raw results: {json_path}")
