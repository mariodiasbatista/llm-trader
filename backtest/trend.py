"""
SMA-based trend filter for backtest replay — mirrors core.alpaca.get_sma's logic
but works off pre-fetched historical bar windows so the sweep can score the
"only buy above the N-day SMA" lever without re-fetching per candidate.
"""
from datetime import date, timedelta

from core.alpaca import get_bars_range

MAX_SMA_DAYS = 50
SMA_LOOKBACK_DAYS = 110  # calendar days back, enough for a 50-trading-day SMA + buffer


def prefetch_sma_bars(keys: list[tuple[str, date]]) -> dict:
    """Fetch [as_of - SMA_LOOKBACK_DAYS, as_of] bars once per (symbol, as_of) key."""
    cache = {}
    for symbol, as_of in keys:
        if (symbol, as_of) in cache:
            continue
        start = as_of - timedelta(days=SMA_LOOKBACK_DAYS)
        try:
            cache[(symbol, as_of)] = get_bars_range(symbol, start, as_of)
        except Exception:
            cache[(symbol, as_of)] = []
    return cache


def sma_as_of(bars, as_of_date, days: int) -> float | None:
    """SMA of the `days` closes strictly before as_of_date. None if data is insufficient."""
    if days <= 0 or not bars:
        return None
    closes = [
        float(b.close) for b in bars
        if (b.timestamp.date() if hasattr(b.timestamp, "date") else b.timestamp) < as_of_date
    ]
    if len(closes) < days:
        return None
    return sum(closes[-days:]) / days
