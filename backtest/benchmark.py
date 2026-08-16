"""
SPY benchmark utilities — alpha vs. the market, not just raw $ P&L.

Why this exists: a 2026-08-16 analysis found that TRAILING_STOP trades looked
like they had real upside being cut short by a tight stop (most touched a new
high before reverting), but that was mostly SPY's own +8.7% drift over the
same window — average alpha vs. SPY across 33 closed trades was -3.43%, and
no confidence/role/transaction-size/source cut showed a profitable subset.
Raw P&L and win-rate alone can't distinguish "the strategy has edge" from
"the market went up and dragged positions with it" — alpha vs. a benchmark
can. Every backtest scoring path should report it alongside P&L.
"""
from datetime import date

from core.alpaca import get_bars_range

BENCHMARK_SYMBOL = "SPY"


def fetch_benchmark_closes(start: date, end: date) -> dict[date, float]:
    """Daily SPY closes over [start, end], keyed by date."""
    bars = get_bars_range(BENCHMARK_SYMBOL, start, end)
    return {
        (b.timestamp.date() if hasattr(b.timestamp, "date") else b.timestamp): float(b.close)
        for b in bars
    }


def _nearest_close(closes: dict[date, float], d: date) -> float | None:
    on_or_before = [x for x in closes if x <= d]
    if on_or_before:
        return closes[max(on_or_before)]
    on_or_after = [x for x in closes if x >= d]
    return closes[min(on_or_after)] if on_or_after else None


def benchmark_return_pct(closes: dict[date, float], start: date, end: date) -> float | None:
    """% return of the benchmark between two dates (nearest available close on each side)."""
    start_close = _nearest_close(closes, start)
    end_close = _nearest_close(closes, end)
    if start_close is None or end_close is None:
        return None
    return (end_close / start_close - 1) * 100


def alpha_pct(entry_price: float, exit_price: float, closes: dict[date, float], entry_date: date, exit_date: date) -> float | None:
    """Stock return minus benchmark return over the same [entry_date, exit_date] window."""
    if entry_price <= 0:
        return None
    stock_ret = (exit_price / entry_price - 1) * 100
    spy_ret = benchmark_return_pct(closes, entry_date, exit_date)
    if spy_ret is None:
        return None
    return stock_ret - spy_ret


def summarize_alpha(alphas: list[float]) -> dict:
    """Aggregate stats over a list of alpha_pct values (None entries already excluded by caller)."""
    if not alphas:
        return {"avg_alpha_pct": None, "pct_positive_alpha": None, "n": 0}
    n = len(alphas)
    positive = sum(1 for a in alphas if a > 0)
    return {
        "avg_alpha_pct": sum(alphas) / n,
        "pct_positive_alpha": positive / n * 100,
        "n": n,
    }
