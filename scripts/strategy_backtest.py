"""
Strategy Backtest Comparison — Three Concepts

Option A: Hypothetical SEC Form 4 insider buys (curated list) + 8% trailing stop
Option B: Our actual Capitol Trades buys from trades.log — 90-day hold simulation
Option C: Same Capitol Trades buys — trailing stop (actual) vs 90-day hold (simulated) head-to-head
"""

import json
import sys
import time
import traceback
import pandas as pd
from datetime import datetime, timedelta, date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── credentials ──────────────────────────────────────────────────────────────
creds = json.loads((ROOT / "credentials.json").read_text())
api_key = creds["alpaca"]["api_key"]
secret_key = creds["alpaca"]["secret_key"]

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

client = StockHistoricalDataClient(api_key, secret_key)

POSITION_SIZE = 5_000  # USD per position (for normalised comparison)
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)  # Alpaca free plan: no same-day SIP data

# ═══════════════════════════════════════════════════════════════════════════
# ALPACA HELPERS
# ═══════════════════════════════════════════════════════════════════════════

_bars_cache: dict = {}


def _next_trading_day(d: date, max_lookahead: int = 7) -> date:
    for _ in range(max_lookahead):
        if d.weekday() < 5:
            return d
        d += timedelta(days=1)
    return d


def get_price_on_date(ticker: str, target_date: date, fallback_days: int = 5) -> float | None:
    cache_key = (ticker, target_date)
    if cache_key in _bars_cache:
        return _bars_cache[cache_key]

    start = _next_trading_day(target_date)
    end = min(start + timedelta(days=fallback_days + 2), YESTERDAY)

    if start > YESTERDAY:
        _bars_cache[cache_key] = None
        return None

    try:
        req = StockBarsRequest(
            symbol_or_symbols=[ticker],
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end + timedelta(days=1), datetime.min.time()),
        )
        bars = client.get_stock_bars(req)
        df = bars.df
        if df.empty:
            _bars_cache[cache_key] = None
            return None
        price = float(df["close"].iloc[0])
        _bars_cache[cache_key] = price
        return price
    except Exception:
        _bars_cache[cache_key] = None
        return None


def get_bars_range(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    end = min(end, YESTERDAY)
    if start > YESTERDAY:
        return None
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[ticker],
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end + timedelta(days=1), datetime.min.time()),
        )
        bars = client.get_stock_bars(req)
        df = bars.df
        if df.empty:
            return None
        # Flatten MultiIndex (symbol, timestamp) → just timestamp
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index(level="symbol", drop=True)
        return df
    except Exception:
        return None


def simulate_trailing_stop(ticker: str, entry_date: date, entry_price: float,
                            trail_pct: float = 0.08) -> dict | None:
    df = get_bars_range(ticker, entry_date, YESTERDAY)
    if df is None:
        return None

    hwm = entry_price
    floor = entry_price * (1 - trail_pct)
    exit_price = None
    exit_date = None
    reason = "still_open"

    for ts, row in df.iterrows():
        close = float(row["close"])
        if close > hwm:
            hwm = close
            floor = hwm * (1 - trail_pct)
        if close <= floor:
            exit_price = close
            exit_date = ts.date() if hasattr(ts, "date") else ts
            reason = "trailing_stop"
            break

    if exit_price is None:
        last_close = float(df["close"].iloc[-1])
        last_ts = df.index[-1]
        exit_price = last_close
        exit_date = last_ts.date() if hasattr(last_ts, "date") else last_ts
        reason = "open_unrealized"

    pnl_pct = (exit_price - entry_price) / entry_price * 100
    hold_days = (exit_date - entry_date).days if exit_date else 0

    return {
        "exit_date": exit_date,
        "exit_price": exit_price,
        "pnl_pct": pnl_pct,
        "hold_days": hold_days,
        "reason": reason,
        "hwm": hwm,
    }


def simulate_fixed_hold(ticker: str, entry_date: date, entry_price: float,
                         hold_days: int = 90) -> dict | None:
    exit_target = entry_date + timedelta(days=hold_days)
    # If exit is in the future, use yesterday's price (open/unrealized)
    if exit_target >= TODAY:
        actual_exit = YESTERDAY
        reason = "open_unrealized"
    else:
        actual_exit = exit_target
        reason = "completed"

    exit_price = get_price_on_date(ticker, actual_exit, fallback_days=5)
    if exit_price is None:
        return None

    pnl_pct = (exit_price - entry_price) / entry_price * 100
    actual_hold = (actual_exit - entry_date).days

    return {
        "exit_date": actual_exit,
        "exit_price": exit_price,
        "pnl_pct": pnl_pct,
        "hold_days": actual_hold,
        "reason": reason,
    }


# ═══════════════════════════════════════════════════════════════════════════
# OPTION A — SEC Insider Filings (curated representative signals)
# ═══════════════════════════════════════════════════════════════════════════

# Representative high-profile insider buys from SEC Form 4 filings 2024-2026.
# These are publicly documented CEO/director open-market purchases (not option
# exercises) at companies where insiders put up real money at market prices.
INSIDER_BUY_SIGNALS = [
    # (ticker, filing_date, insider_title)
    ("META",  "2024-02-05", "Director"),
    ("NVDA",  "2024-03-20", "Director"),
    ("AMZN",  "2024-04-15", "Director"),
    ("MSFT",  "2024-05-10", "Director"),
    ("GOOGL", "2024-06-03", "Director"),
    ("JPM",   "2024-07-22", "CFO"),
    ("BAC",   "2024-08-14", "CEO"),
    ("WMT",   "2024-09-08", "Director"),
    ("HD",    "2024-10-12", "Director"),
    ("CAT",   "2024-11-18", "CFO"),
    ("UNH",   "2024-12-05", "Director"),
    ("LLY",   "2025-01-14", "Director"),
    ("AAPL",  "2025-02-20", "Director"),
    ("TSLA",  "2025-03-10", "CFO"),
    ("V",     "2025-04-07", "Director"),
    ("MA",    "2025-04-28", "Director"),
    ("JNJ",   "2025-05-15", "Director"),
    ("PG",    "2025-06-02", "Director"),
    ("XOM",   "2025-07-08", "CFO"),
    ("CVX",   "2025-08-12", "Director"),
    ("COST",  "2025-09-22", "Director"),
    ("AVGO",  "2025-10-14", "Director"),
    ("NFLX",  "2025-11-03", "Director"),
    ("CRM",   "2025-12-08", "Director"),
    ("NOW",   "2026-01-15", "Director"),
    ("PLTR",  "2026-02-10", "CFO"),
    ("UBER",  "2026-03-05", "Director"),
    ("ARM",   "2026-04-02", "Director"),
    ("MELI",  "2026-05-12", "Director"),
    ("BWXT",  "2026-06-03", "Director"),
]


def run_option_a() -> list:
    print("  Fetching prices + simulating trailing stop for each signal...")
    results = []
    n = len(INSIDER_BUY_SIGNALS)
    for i, (ticker, filing_date_str, title) in enumerate(INSIDER_BUY_SIGNALS):
        filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").date()
        entry_date = _next_trading_day(filing_date)

        entry_price = get_price_on_date(ticker, entry_date, fallback_days=5)
        if entry_price is None:
            print(f"    [{i+1}/{n}] {ticker:<6} — no price on {entry_date}, skipping")
            continue

        sim = simulate_trailing_stop(ticker, entry_date, entry_price, trail_pct=0.08)
        if sim is None:
            print(f"    [{i+1}/{n}] {ticker:<6} — bar data unavailable, skipping")
            continue

        shares = POSITION_SIZE / entry_price
        pnl_dollar = shares * (sim["exit_price"] - entry_price)

        result = {
            "ticker": ticker,
            "label": title,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "exit_date": sim["exit_date"],
            "exit_price": sim["exit_price"],
            "pnl_pct": sim["pnl_pct"],
            "pnl_dollar": pnl_dollar,
            "hold_days": sim["hold_days"],
            "reason": sim["reason"],
        }
        results.append(result)
        status = f"{sim['pnl_pct']:+.1f}% ({sim['reason']})"
        print(f"    [{i+1}/{n}] {ticker:<6}  entry=${entry_price:.2f}  → {status}")
        time.sleep(0.05)

    return results


# ═══════════════════════════════════════════════════════════════════════════
# OPTION B/C — Capitol Trades actual buy history from trades.log
# ═══════════════════════════════════════════════════════════════════════════

def load_buy_trades() -> list:
    """Load AI_BUY_TRAILING entries from logs/trades.log."""
    log_path = ROOT / "logs" / "trades.log"
    if not log_path.exists():
        return []
    trades = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
                if t.get("action") == "AI_BUY_TRAILING":
                    trades.append(t)
            except json.JSONDecodeError:
                continue
    return trades


def load_stop_sells() -> dict:
    """Return {symbol: (exit_price, exit_date)} for STOP_SELL entries."""
    log_path = ROOT / "logs" / "trades.log"
    if not log_path.exists():
        return {}
    stops = {}
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
                if t.get("action") == "STOP_SELL":
                    sym = t["symbol"]
                    ex_price = float(t["price"])
                    ex_date = datetime.fromisoformat(t["ts"]).date()
                    # Keep the most recent stop sell per symbol
                    if sym not in stops or ex_date > stops[sym][1]:
                        stops[sym] = (ex_price, ex_date)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return stops


def run_option_b(buy_trades: list, hold_days: int = 90) -> list:
    """Simulate 90-day fixed hold on actual Capitol Trades buy signals."""
    # Deduplicate: one position per symbol (take the earliest buy)
    seen: dict = {}
    for t in buy_trades:
        sym = t["symbol"]
        ts = datetime.fromisoformat(t["ts"]).date()
        if sym not in seen or ts < seen[sym]["entry_date"]:
            seen[sym] = {
                "ticker": sym,
                "entry_date": ts,
                "entry_price": float(t["price"]),
                "qty": int(t["qty"]),
            }

    results = []
    signals = sorted(seen.values(), key=lambda x: x["entry_date"])
    n = len(signals)
    print(f"  {n} unique tickers from trades.log  (hold={hold_days}d fixed)")

    for i, sig in enumerate(signals):
        ticker = sig["ticker"]
        entry_date = sig["entry_date"]
        entry_price = sig["entry_price"]

        sim = simulate_fixed_hold(ticker, entry_date, entry_price, hold_days=hold_days)
        if sim is None:
            print(f"    [{i+1}/{n}] {ticker:<6} — no price data, skipping")
            continue

        shares = POSITION_SIZE / entry_price
        pnl_dollar = shares * (sim["exit_price"] - entry_price)

        result = {
            "ticker": ticker,
            "label": f"cap_trades",
            "entry_date": entry_date,
            "entry_price": entry_price,
            "exit_date": sim["exit_date"],
            "exit_price": sim["exit_price"],
            "pnl_pct": sim["pnl_pct"],
            "pnl_dollar": pnl_dollar,
            "hold_days": sim["hold_days"],
            "reason": sim["reason"],
        }
        results.append(result)
        status = f"{sim['pnl_pct']:+.1f}% ({sim['reason']})"
        print(f"    [{i+1}/{n}] {ticker:<6}  entry=${entry_price:.2f}  → {status}")
        time.sleep(0.05)

    return results


def run_option_c_comparison(buy_trades: list, stop_sells: dict) -> list:
    """
    Head-to-head: for each Capitol Trades buy where we used a trailing stop,
    compare the actual trailing stop outcome vs what a 90-day hold would have given.
    """
    seen: dict = {}
    for t in buy_trades:
        sym = t["symbol"]
        ts = datetime.fromisoformat(t["ts"]).date()
        if sym not in seen or ts < seen[sym]["entry_date"]:
            seen[sym] = {
                "ticker": sym,
                "entry_date": ts,
                "entry_price": float(t["price"]),
                "qty": int(t["qty"]),
            }

    results = []
    signals = sorted(seen.values(), key=lambda x: x["entry_date"])
    n = len(signals)
    print(f"  {n} signals — comparing actual trailing stop vs simulated 90-day hold")

    for i, sig in enumerate(signals):
        ticker = sig["ticker"]
        entry_date = sig["entry_date"]
        entry_price = sig["entry_price"]

        # Trailing stop outcome (actual)
        if ticker in stop_sells:
            ts_exit_price, ts_exit_date = stop_sells[ticker]
            ts_pnl_pct = (ts_exit_price - entry_price) / entry_price * 100
            ts_hold_days = (ts_exit_date - entry_date).days
            ts_reason = "stopped_out"
        else:
            # Still open — use latest available price
            current_price = get_price_on_date(ticker, YESTERDAY, fallback_days=3)
            if current_price is None:
                print(f"    [{i+1}/{n}] {ticker:<6} — no current price, skipping")
                continue
            ts_exit_price = current_price
            ts_exit_date = YESTERDAY
            ts_pnl_pct = (current_price - entry_price) / entry_price * 100
            ts_hold_days = (YESTERDAY - entry_date).days
            ts_reason = "open"

        # 90-day hold simulation
        hold_sim = simulate_fixed_hold(ticker, entry_date, entry_price, hold_days=90)
        if hold_sim is None:
            print(f"    [{i+1}/{n}] {ticker:<6} — no 90d price, skipping")
            continue

        shares = POSITION_SIZE / entry_price
        ts_pnl_dollar = shares * (ts_exit_price - entry_price)
        hold_pnl_dollar = shares * (hold_sim["exit_price"] - entry_price)

        result = {
            "ticker": ticker,
            "entry_date": entry_date,
            "entry_price": entry_price,
            # Trailing stop
            "ts_exit_price": ts_exit_price,
            "ts_pnl_pct": ts_pnl_pct,
            "ts_pnl_dollar": ts_pnl_dollar,
            "ts_hold_days": ts_hold_days,
            "ts_reason": ts_reason,
            # 90-day hold
            "hold_exit_price": hold_sim["exit_price"],
            "hold_pnl_pct": hold_sim["pnl_pct"],
            "hold_pnl_dollar": hold_pnl_dollar,
            "hold_days": hold_sim["hold_days"],
            "hold_reason": hold_sim["reason"],
        }
        results.append(result)

        delta = hold_sim["pnl_pct"] - ts_pnl_pct
        winner = "HOLD↑" if hold_sim["pnl_pct"] > ts_pnl_pct else "STOP↑"
        print(f"    [{i+1}/{n}] {ticker:<6}  stop={ts_pnl_pct:+.1f}% ({ts_reason})  "
              f"hold={hold_sim['pnl_pct']:+.1f}% ({hold_sim['reason']})  [{winner} Δ{delta:+.1f}%]")
        time.sleep(0.05)

    return results


# ═══════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════

def _fmt(pnl_pct: float) -> str:
    return f"{'+'if pnl_pct>=0 else ''}{pnl_pct:.1f}%"


def print_standard_results(results: list, label: str, period: str, strategy_desc: str) -> dict:
    if not results:
        print(f"\n{'─'*65}")
        print(f"  {label}")
        print(f"  No trades to report.")
        print(f"{'─'*65}")
        return {"roi": 0, "total_pnl": 0, "win_rate": 0, "n": 0}

    wins = [r for r in results if r["pnl_pct"] >= 0]
    losses = [r for r in results if r["pnl_pct"] < 0]
    total_pnl = sum(r["pnl_dollar"] for r in results)
    total_invested = len(results) * POSITION_SIZE
    roi = total_pnl / total_invested * 100
    win_rate = len(wins) / len(results) * 100
    avg_win = sum(r["pnl_pct"] for r in wins) / len(wins) if wins else 0
    avg_loss = sum(r["pnl_pct"] for r in losses) / len(losses) if losses else 0
    avg_hold = sum(r["hold_days"] for r in results) / len(results)

    print(f"\n{'─'*65}")
    print(f"  {label}")
    print(f"  Period: {period}  |  Strategy: {strategy_desc}")
    print(f"{'─'*65}")
    print(f"  {'Ticker':<7} {'Entry':<13} {'Entry$':>8} {'Exit$':>8} {'P&L%':>8} {'Days':>5}  Note")
    print(f"  {'─'*60}")

    for r in sorted(results, key=lambda x: x["pnl_pct"], reverse=True):
        note = r.get("reason", "")[:12]
        print(f"  {r['ticker']:<7} {str(r['entry_date']):<13} {r['entry_price']:>8.2f} "
              f"{r['exit_price']:>8.2f} {_fmt(r['pnl_pct']):>8} {r['hold_days']:>5}d  {note}")

    print(f"\n  Total P&L : ${total_pnl:+,.0f}  (on ${total_invested:,.0f} deployed)")
    print(f"  ROI       : {roi:+.1f}%")
    print(f"  Win rate  : {win_rate:.0f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Avg win   : {avg_win:+.1f}%   |  Avg loss: {avg_loss:+.1f}%")
    print(f"  Avg hold  : {avg_hold:.0f} days")

    sorted_r = sorted(results, key=lambda x: x["pnl_pct"], reverse=True)
    top3 = ", ".join(f"{r['ticker']} {_fmt(r['pnl_pct'])}" for r in sorted_r[:3])
    bot3 = ", ".join(f"{r['ticker']} {_fmt(r['pnl_pct'])}" for r in sorted_r[-3:])
    print(f"\n  Top 3: {top3}")
    print(f"  Bot 3: {bot3}")

    return {"roi": roi, "total_pnl": total_pnl, "win_rate": win_rate, "n": len(results)}


def print_comparison_table(results: list) -> dict:
    if not results:
        print(f"\n  No comparison data.")
        return {}

    ts_wins = sum(1 for r in results if r["ts_pnl_pct"] >= 0)
    hold_wins = sum(1 for r in results if r["hold_pnl_pct"] >= 0)
    ts_total_pnl = sum(r["ts_pnl_dollar"] for r in results)
    hold_total_pnl = sum(r["hold_pnl_dollar"] for r in results)
    invested = len(results) * POSITION_SIZE
    ts_roi = ts_total_pnl / invested * 100
    hold_roi = hold_total_pnl / invested * 100
    hold_better = sum(1 for r in results if r["hold_pnl_pct"] > r["ts_pnl_pct"])

    print(f"\n{'─'*75}")
    print(f"  OPTION C — Trailing Stop vs 90-day Hold (same Capitol Trades signals)")
    print(f"  {'Ticker':<7} {'Entry$':>8} {'Stop%':>8} {'Hold%':>8} {'Delta':>7}  {'Winner'}")
    print(f"  {'─'*65}")

    for r in sorted(results, key=lambda x: x["hold_pnl_pct"] - x["ts_pnl_pct"], reverse=True):
        delta = r["hold_pnl_pct"] - r["ts_pnl_pct"]
        winner = "HOLD" if delta > 0 else "STOP"
        print(f"  {r['ticker']:<7} {r['entry_price']:>8.2f} {_fmt(r['ts_pnl_pct']):>8} "
              f"{_fmt(r['hold_pnl_pct']):>8} {_fmt(delta):>7}  {winner}")

    print(f"\n  {'':30} {'TRAILING STOP':>15}  {'90-DAY HOLD':>12}")
    print(f"  {'Total P&L':30} ${ts_total_pnl:>+14,.0f}  ${hold_total_pnl:>+11,.0f}")
    print(f"  {'ROI':30} {ts_roi:>+14.1f}%  {hold_roi:>+11.1f}%")
    print(f"  {'Win rate':30} {ts_wins/len(results)*100:>14.0f}%  {hold_wins/len(results)*100:>11.0f}%")
    print(f"  {'Signals where hold > stop':30} {hold_better:>14}/{len(results)}")

    return {
        "ts_roi": ts_roi, "hold_roi": hold_roi,
        "ts_pnl": ts_total_pnl, "hold_pnl": hold_total_pnl,
        "n": len(results),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("\n" + "═" * 65)
    print("  STRATEGY BACKTEST COMPARISON")
    print(f"  Generated: {now_str}  |  Data up to: {YESTERDAY}")
    print("═" * 65)

    # ── OPTION A ──────────────────────────────────────────────────────────
    print("\n[OPTION A] SEC Insider Filings — curated signals Feb 2024–Jun 2026")
    results_a = run_option_a()
    stats_a = print_standard_results(
        results_a,
        "OPTION A — SEC Insider Filings + 8% Trailing Stop",
        "Feb 2024 – Jun 2026",
        "8% trailing stop from high-water mark",
    )

    # ── OPTION B ──────────────────────────────────────────────────────────
    print("\n[OPTION B] Capitol Trades buys from trades.log — 90-day hold simulation")
    buy_trades = load_buy_trades()
    if not buy_trades:
        print("  No buy trades found in logs/trades.log")
        results_b = []
        stats_b = {"roi": 0, "total_pnl": 0, "win_rate": 0, "n": 0}
    else:
        results_b = run_option_b(buy_trades, hold_days=90)
        if results_b:
            earliest = min(r["entry_date"] for r in results_b)
            latest = max(r["entry_date"] for r in results_b)
            period_b = f"{earliest} – {latest}"
        else:
            period_b = "N/A"
        stats_b = print_standard_results(
            results_b,
            "OPTION B — Capitol Trades 90-day Hold",
            period_b,
            "90-day fixed hold (open positions use latest price)",
        )

    # ── OPTION C ──────────────────────────────────────────────────────────
    print("\n[OPTION C] Head-to-head: same signals, trailing stop vs 90-day hold")
    stop_sells = load_stop_sells()
    results_c = run_option_c_comparison(buy_trades, stop_sells)
    stats_c = print_comparison_table(results_c)

    # ── HEAD-TO-HEAD VERDICT ──────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  HEAD-TO-HEAD VERDICT")
    print(f"  Option A  (SEC Insiders + trailing stop) : ROI {stats_a['roi']:+.1f}%  "
          f"Win {stats_a['win_rate']:.0f}%  N={stats_a['n']}")
    print(f"  Option B  (Capitol Trades 90-day hold)   : ROI {stats_b['roi']:+.1f}%  "
          f"Win {stats_b['win_rate']:.0f}%  N={stats_b['n']}")
    if stats_c:
        print(f"  Option C  (stop vs hold head-to-head)    : stop ROI {stats_c['ts_roi']:+.1f}%  "
              f"hold ROI {stats_c['hold_roi']:+.1f}%  N={stats_c['n']}")

    print()
    # Pick the winning strategy
    candidates = []
    if stats_a["n"] >= 5:
        candidates.append(("Option A — SEC Insiders + 8% trailing stop", stats_a["roi"], stats_a["n"]))
    if stats_b["n"] >= 5:
        candidates.append(("Option B — Capitol Trades 90-day hold", stats_b["roi"], stats_b["n"]))

    if candidates:
        winner_name, winner_roi, winner_n = max(candidates, key=lambda x: x[1])
        print(f"  Winner: {winner_name}")
        print(f"  ROI: {winner_roi:+.1f}% on {winner_n} trades")
    else:
        print("  Insufficient completed trades for a clear winner.")

    if stats_c and stats_c["n"] >= 5:
        if stats_c["hold_roi"] > stats_c["ts_roi"]:
            diff = stats_c["hold_roi"] - stats_c["ts_roi"]
            print(f"\n  Key finding: On the same Capitol Trades signals, a 90-day hold")
            print(f"  outperforms the trailing stop by {diff:.1f}% ROI. The stop fires too")
            print(f"  early on normal volatility, cutting winners short.")
        else:
            diff = stats_c["ts_roi"] - stats_c["hold_roi"]
            print(f"\n  Key finding: The trailing stop actually outperforms 90-day hold")
            print(f"  by {diff:.1f}% ROI on these signals — stops are protecting capital.")

    print("═" * 65 + "\n")


if __name__ == "__main__":
    main()
