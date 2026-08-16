"""
Broader entry-side edge search — replays SEC EDGAR insider-buy signals over a
much longer window than the ~4 months of live trades gives us, and buckets
alpha-vs-SPY by entry-side attributes (role, transaction size, conviction
flag, cluster buying, price tier) instead of just sweeping exit parameters.

Motivated by the 2026-08-16 finding that TRAILING_STOP trades showed -3.43%
average alpha vs SPY with no profitable subset visible in the live 40-trade
sample — too small to tell "no edge exists" apart from "edge exists but the
sample is too thin to see it." This module exists to get a bigger sample.
"""
from collections import defaultdict
from datetime import date, timedelta

from core.alpaca import get_bars_range
from backtest.signals import fetch_historical_insider_signals
from backtest.replay import simulate_trailing_stop
from backtest.benchmark import fetch_benchmark_closes, alpha_pct, summarize_alpha

POSITION_SIZE_USD = 6000

# Current live TRAILING_STOP config (config/settings.json as of 2026-08-16) —
# use the actual live exit rules so this measures entry-side selection, not a
# confound from also varying the exit.
LIVE_TS_CFG = {
    "initial_stop_pct": 0.08,
    "trailing_pct": 0.08,
    "take_profit_pct": 0.12,
    "profit_target_pct": 0.03,
    "trailing_pct_from_profit": 0.05,
    "ladder_buys": [],
}


def _entry_price(bars) -> float | None:
    return float(bars[0].close) if bars else None


def tag_clusters(signals: list[dict], window_days: int = 14) -> None:
    """Mutate each signal in place with _cluster_size = number of DISTINCT
    insiders who bought the same ticker within +/- window_days of this filing.
    Cluster buying (multiple insiders independently buying) is a classically
    stronger conviction signal than any single purchase."""
    by_ticker = defaultdict(list)
    for s in signals:
        by_ticker[s["asset"]["ticker"]].append(s)

    for ticker, group in by_ticker.items():
        dated = [(date.fromisoformat(s["publishedDate"]), s) for s in group]
        for d, s in dated:
            names = {
                s2["politician"]["name"]
                for d2, s2 in dated
                if abs((d2 - d).days) <= window_days
            }
            s["_cluster_size"] = len(names)


def replay_signals(
    signals: list[dict],
    ts_cfg: dict = LIVE_TS_CFG,
    position_size_usd: float = POSITION_SIZE_USD,
    min_entry_price: float = 50,  # matches live analyze.min_entry_price
    days_forward: int = 180,
    progress_cb=None,
) -> list[dict]:
    """Replay every signal as a TRAILING_STOP entry under ts_cfg, using real
    daily bars, and compute alpha vs SPY. Returns one record per signal with
    both the raw result and the entry-side metadata needed to bucket by."""
    if not signals:
        return []

    window_start = min(date.fromisoformat(s["publishedDate"]) for s in signals)
    window_end = date.today()
    spy_closes = fetch_benchmark_closes(window_start, window_end)

    records = []
    for i, sig in enumerate(signals):
        try:
            entry_date = date.fromisoformat(sig["publishedDate"])
        except (ValueError, KeyError):
            continue
        symbol = sig["asset"]["ticker"]
        end = min(date.today(), entry_date + timedelta(days=days_forward))
        bars = get_bars_range(symbol, entry_date, end)
        entry_price = _entry_price(bars)
        if entry_price is None or entry_price < min_entry_price:
            if progress_cb:
                progress_cb(i + 1, len(signals))
            continue

        result = simulate_trailing_stop(symbol, entry_date, entry_price, ts_cfg, position_size_usd, bars=bars)
        if result is None:
            if progress_cb:
                progress_cb(i + 1, len(signals))
            continue

        alpha = alpha_pct(entry_price, result["exit_price"], spy_closes, entry_date, result["exit_date"])

        records.append({
            "symbol": symbol,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "pnl_usd": result["pnl_usd"],
            "alpha_pct": alpha,
            "is_open": result["is_open"],
            "exit_reason": result["exit_reason"],
            "role": sig.get("_insider_role"),
            "transaction_value": sig.get("_transaction_value"),
            "high_conviction": sig.get("_high_conviction"),
            "cluster_size": sig.get("_cluster_size", 1),
        })
        if progress_cb:
            progress_cb(i + 1, len(signals))

    return records


def _role_bucket(role: str | None) -> str:
    if not role:
        return "Unknown"
    r = role.lower()
    if "chief executive" in r or "ceo" in r or "president" in r and "vice" not in r:
        return "CEO/President"
    if "chairman" in r:
        return "Chairman"
    if "chief financial" in r or "cfo" in r:
        return "CFO"
    if "director" in r:
        return "Director"
    return "Other/" + role


def bucket_report(records: list[dict]) -> dict:
    """Group alpha by role / transaction-value tier / high-conviction flag /
    cluster size / price tier, returning avg_alpha_pct + n per group so a
    small, noisy group can be told apart from a real, sizeable edge."""
    report = {}

    def _group(key_fn, label):
        groups = defaultdict(list)
        for r in records:
            if r["alpha_pct"] is None:
                continue
            groups[key_fn(r)].append(r["alpha_pct"])
        report[label] = {
            k: summarize_alpha(v) for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))
        }

    _group(lambda r: _role_bucket(r["role"]), "role")
    _group(lambda r: r["high_conviction"], "high_conviction")
    _group(lambda r: r["cluster_size"] if r["cluster_size"] < 4 else "4+", "cluster_size")

    def value_tier(r):
        v = r["transaction_value"] or 0
        if v < 150_000:
            return "<$150K"
        if v < 500_000:
            return "$150K-500K"
        if v < 2_000_000:
            return "$500K-2M"
        return "$2M+"
    _group(value_tier, "transaction_value")

    def price_tier(r):
        p = r["entry_price"]
        if p < 20:
            return "<$20"
        if p < 100:
            return "$20-100"
        if p < 300:
            return "$100-300"
        return "$300+"
    _group(price_tier, "entry_price_tier")

    overall = summarize_alpha([r["alpha_pct"] for r in records if r["alpha_pct"] is not None])
    report["overall"] = overall
    return report
