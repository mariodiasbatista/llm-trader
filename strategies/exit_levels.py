"""
Adaptive per-stock take-profit levels.

A single flat take_profit_pct assumes every stock can plausibly reach it in a
typical holding period. Measured against real history that's false: only ~42%
of bought positions ever touched +12% within 60 days, and the same 12% is
simultaneously a ~2-sigma stretch for a stable name (TM, AAPL) and less than
half a sigma for a volatile one (BYRN, BOT). For the stocks that can't reach
it, the take-profit is dead code — those positions can only ever exit at the
stop, which is the losing half of the distribution.

This module derives the target from what a stock *actually does*: the
distribution of "best gain reached within `horizon` trading days" over its own
pre-purchase history (max favorable excursion, MFE). Two knobs:

  - if the stock reaches the flat target often enough, keep the flat target
  - otherwise fall back to the level it reaches `target_reach_probability`
    of the time

Deliberately non-parametric. An earlier volatility-scaled (sigma-based)
version of this idea swung 8x in measured alpha purely from changing the
sigma lookback window — a fitted artifact, not an effect. Quantiles of
realized moves make no distributional assumption and proved far stabler:
across 250-600d lookbacks the win rate moved 0.7 percentage points.

Pure functions only — no I/O — so the live strategy and backtest replay share
one implementation and can't diverge.
"""


def mfe_distribution(bars, horizon_days: int = 20) -> list[float]:
    """
    Distribution of max-favorable-excursion (%) over `horizon_days` trading
    days, computed across every window in `bars`.

    `bars` must be strictly pre-purchase for live/backtest use — including any
    bar at or after the entry date leaks future information into the target.
    """
    closes = [float(b.close) for b in bars]
    highs = [float(b.high) for b in bars]
    out = []
    for i in range(len(closes) - horizon_days):
        base = closes[i]
        if base <= 0:
            continue
        out.append((max(highs[i + 1:i + 1 + horizon_days]) / base - 1) * 100)
    return sorted(out)


def reach_rate(dist: list[float], level_pct: float) -> float | None:
    """What share of historical windows reached `level_pct` (a percentage, e.g. 12)."""
    if not dist:
        return None
    return sum(1 for x in dist if x >= level_pct) / len(dist) * 100


def level_at_reach_probability(dist: list[float], probability: float) -> float | None:
    """
    The gain level (%) this stock reached in `probability` of historical windows.
    probability=0.7 → the level it hits 70% of the time (a modest, frequently
    achieved target); probability=0.3 → a rarer, more ambitious one.
    """
    if not dist:
        return None
    idx = int(round((1.0 - probability) * (len(dist) - 1)))
    return dist[min(len(dist) - 1, max(0, idx))]


def resolve_take_profit(dist: list[float], flat_tp: float, cfg: dict) -> float | None:
    """
    Resolve the take-profit fraction for one position.

    Returns the flat target when the stock reaches it often enough, otherwise
    the level it reaches `target_reach_probability` of the time, clamped.
    None when there isn't enough history to judge — caller should fall back to
    the flat value rather than guess.
    """
    min_windows = cfg.get("min_windows", 40)
    if not dist or len(dist) < min_windows:
        return None

    keep_flat_above = cfg.get("keep_flat_reach_pct", 50)
    rr = reach_rate(dist, flat_tp * 100)
    if rr is not None and rr >= keep_flat_above:
        return flat_tp

    level = level_at_reach_probability(dist, cfg.get("target_reach_probability", 0.7))
    if level is None:
        return None
    tp = level / 100.0
    return max(cfg.get("tp_min", 0.03), min(cfg.get("tp_max", 0.60), tp))
