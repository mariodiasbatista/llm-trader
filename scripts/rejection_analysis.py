#!/usr/bin/env python3
"""
Did we reject profitable trades?

Replays every signal the system REJECTED — at any stage of the funnel — through
the exact same trailing-stop rules the live book runs, and compares the result
against the trades we actually took.

The question this answers: are the pre-check filters and the AI gate protecting
us from losses, or are they cutting off profit? Measured in alpha vs SPY, not
raw P&L — a rejected signal that "made money" in a rising market proves nothing
(see backtest/benchmark.py).

Why this exists: filters that discard signals silently can never be evaluated —
they always look justified on the signals they let through. The $50 price floor
demonstrated this concretely: all 31 sub-$50 signals predate it and none exist
after, so there was no counterfactual to replay. Rejections are now logged with
a REJECTED_PREFILTER / REJECTED_AI marker precisely so this script can exist.

Usage:
    python scripts/rejection_analysis.py                  # everything in bot.log
    python scripts/rejection_analysis.py --since 2026-09-03
    python scripts/rejection_analysis.py --min-sample 10  # hide thin cohorts
"""
import sys
import re
import json
import argparse
import statistics
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.alpaca import get_bars_range
from backtest.benchmark import fetch_benchmark_closes, alpha_pct, summarize_alpha
from backtest.replay import simulate_trailing_stop
from strategies.exit_levels import mfe_distribution, reach_rate, level_at_reach_probability

BOT_LOG = Path(__file__).parent.parent / "logs" / "bot.log"
TRADES_LOG = Path(__file__).parent.parent / "logs" / "trades.log"
SETTINGS = Path(__file__).parent.parent / "config" / "settings.json"

POSITION_SIZE_USD = 6000   # normalised so cohorts are comparable regardless of real sizing
FORWARD_DAYS = 180

REJECT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) [\d:,]+ \[INFO\] \[([A-Z.]{1,6})\] "
    r"REJECTED_(PREFILTER|AI) reason=([a-z_]+)(.*)$"
)

# Structured rejection logging began 2026-09-03. Before that the AI's SKIPs were
# written as a bare "[TICK] SKIP — reason", and the pre-filters logged prose or
# nothing at all. Parse the legacy SKIP form too so the historical sample isn't
# thrown away — it is the only pre-09-03 rejection data that exists.
LEGACY_SKIP_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) [\d:,]+ \[INFO\] \[([A-Z.]{1,6})\] SKIP — (.*)$"
)
# Minimum forward bars needed before a signal can be judged at all.
MIN_FORWARD_BARS = 2


def classify_skip_condition(text: str) -> str:
    """Map the AI's free-text skip reason onto a condition.

    Worth separating from the filter *name*: a `claude_skip` tells you the AI
    rejected it, not why. Measured 2026-09-03, the two most common reasons —
    staleness and small-cap/price aversion — are conditions its prompt never
    lists, i.e. rules it invented, and both rejected profitable signals.
    """
    s = (text or "").lower()
    if "days old" in s or "stale" in s:
        return "stale [self-invented]"
    if "gapped" in s or "already run" in s or "already up" in s or "since the filing" in s:
        return "already gapped >10%"
    if any(w in s for w in ("illiquid", "otc", "thin", "low volume", "liquidity")):
        return "illiquid / OTC"
    if "buying power" in s or "insufficient capital" in s:
        return "buying power too low"
    if "relative to" in s and ("compensation" in s or "salary" in s):
        return "trivial vs compensation"
    if any(w in s for w in ("headwind", "regulatory", "macro", "tariff", "sector", "cyclical")):
        return "sector headwinds"
    if any(w in s for w in ("micro-cap", "small-cap", "penny", "speculative", "volatile",
                            "trades at $", "per share", "biotech", "clinical")):
        return "small-cap / price [self-invented]"
    return "other"


def parse_rejections(since: date | None) -> dict:
    """{(ticker, date): reason} — deduped, because the scanner re-logs the same
    signal every run (~13x/day)."""
    out = {}
    if not BOT_LOG.exists():
        return out
    with open(BOT_LOG, errors="ignore") as f:
        for line in f:
            line = line.rstrip()
            m = REJECT_RE.match(line)
            if m:
                d = date.fromisoformat(m.group(1))
                if since and d < since:
                    continue
                out.setdefault((m.group(2), d), (m.group(4), m.group(5) or ""))
                continue
            m = LEGACY_SKIP_RE.match(line)
            if m:
                d = date.fromisoformat(m.group(1))
                if since and d < since:
                    continue
                out.setdefault((m.group(2), d), ("claude_skip", m.group(3)))
    return out


def parse_buys(since: date | None) -> set:
    out = set()
    if not TRADES_LOG.exists():
        return out
    with open(TRADES_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except json.JSONDecodeError:
                continue
            if t.get("action") != "AI_BUY_TRAILING":
                continue
            d = date.fromisoformat(t["ts"][:10])
            if since and d < since:
                continue
            out.add((t["symbol"], d))
    return out


def _live_cfg() -> dict:
    return json.loads(SETTINGS.read_text())["trailing_stop"]


def replay(items, cfg, spy, bars_cache, pre_cache, skipped_recent=None):
    """Run each (ticker, date) through the live exit rules. Returns records.

    Signals with too little forward data are collected into `skipped_recent`
    rather than silently dropped — otherwise a run full of fresh rejections
    reports an empty table with no explanation.
    """
    acfg = cfg.get("adaptive_take_profit", {})
    skipped_recent = skipped_recent if skipped_recent is not None else []
    recs = []
    for tk, dt in sorted(items):
        key = (tk, dt)
        if key not in bars_cache:
            try:
                bars_cache[key] = get_bars_range(tk, dt, min(date.today(), dt + timedelta(days=FORWARD_DAYS)))
            except Exception:
                bars_cache[key] = []
        bars = bars_cache[key]
        if not bars or len(bars) < MIN_FORWARD_BARS:
            # Signal too recent (or no data): nothing has happened yet to judge.
            skipped_recent.append((tk, dt))
            continue

        # per-stock adaptive take-profit, from pre-entry history only
        tp = None
        if acfg.get("enabled"):
            if key not in pre_cache:
                try:
                    pre_cache[key] = get_bars_range(tk, dt - timedelta(days=acfg.get("lookback_days", 400)), dt)
                except Exception:
                    pre_cache[key] = []
            dist = mfe_distribution(pre_cache[key], acfg.get("horizon_days", 20))
            if len(dist) >= acfg.get("min_windows", 40):
                flat = cfg.get("take_profit_pct", 0.12)
                if reach_rate(dist, flat * 100) >= acfg.get("keep_flat_reach_pct", 50):
                    tp = flat
                else:
                    lvl = level_at_reach_probability(dist, acfg.get("target_reach_probability", 0.7))
                    tp = max(acfg.get("tp_min", 0.03), min(acfg.get("tp_max", 0.60), lvl / 100))

        run_cfg = {**cfg, **({"take_profit_pct": tp} if tp else {})}
        entry = float(bars[0].close)
        r = simulate_trailing_stop(tk, dt, entry, run_cfg, POSITION_SIZE_USD, bars=bars)
        if r is None:
            continue
        recs.append({
            "ticker": tk, "date": dt, "entry": entry,
            "pnl": r["pnl_usd"], "open": r["is_open"], "reason": r["exit_reason"],
            "alpha": alpha_pct(entry, r["exit_price"], spy, dt, r["exit_date"]),
        })
    return recs


def summarize(label, recs, min_sample=1):
    if len(recs) < min_sample:
        print(f"{label:38}{len(recs):>5}   (below --min-sample, not shown)")
        return
    closed = [r for r in recs if not r["open"]]
    wins = sum(1 for r in closed if r["pnl"] > 0)
    al = summarize_alpha([r["alpha"] for r in recs if r["alpha"] is not None])
    aa, pp = al["avg_alpha_pct"], al["pct_positive_alpha"]
    print(
        f"{label:38}{len(recs):>5}{len(closed):>7} ${sum(r['pnl'] for r in recs):>10,.0f}"
        f"{(wins / len(closed) * 100 if closed else 0):>7.1f}%"
        f"{(f'{aa:+.2f}%' if aa is not None else 'n/a'):>9}"
        f"{(f'{pp:.0f}%' if pp is not None else 'n/a'):>7}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", type=str, default=None, help="only signals on/after YYYY-MM-DD")
    ap.add_argument("--min-sample", type=int, default=1, help="hide cohorts smaller than this")
    args = ap.parse_args()
    since = date.fromisoformat(args.since) if args.since else None

    rejections = parse_rejections(since)
    buys = parse_buys(since)
    rejections = {k: v for k, v in rejections.items() if k not in buys}

    print(f"Rejected signals found : {len(rejections)}")
    print(f"Trades actually taken  : {len(buys)}")
    if not rejections:
        print("\nNo rejections logged yet in this window. Rejection logging began 2026-09-03;")
        print("allow a few weeks of market days before the comparison is meaningful.")
        return

    all_dates = [d for _, d in rejections] + [d for _, d in buys]
    spy = fetch_benchmark_closes(min(all_dates), date.today())
    cfg = _live_cfg()
    bars_cache, pre_cache = {}, {}

    print("\nReplaying under the LIVE exit rules "
          f"(stop {cfg['initial_stop_pct']:.0%}, adaptive TP "
          f"{'on' if cfg.get('adaptive_take_profit', {}).get('enabled') else 'off'}), "
          f"${POSITION_SIZE_USD:,} per position, alpha vs SPY.\n")

    header = f"{'Cohort':38}{'n':>5}{'closed':>7}{'total_P&L':>11}{'win%':>7}{'alpha':>9}{'beat':>7}"
    print(header)
    print("-" * len(header))

    unripe_took, unripe_rej = [], []
    took = replay(buys, cfg, spy, bars_cache, pre_cache, unripe_took)
    passed = replay(set(rejections), cfg, spy, bars_cache, pre_cache, unripe_rej)
    if unripe_rej or unripe_took:
        print(f"  ({len(unripe_rej) + len(unripe_took)} signals too recent to judge yet — excluded)\n")
    summarize("TOOK (what we actually bought)", took, 1)
    summarize("REJECTED (all reasons)", passed, 1)
    summarize("BOTH (no filtering at all)", took + passed, 1)

    by_reason = defaultdict(list)
    reason_of = {k: v[0] for k, v in rejections.items()}
    text_of   = {k: v[1] for k, v in rejections.items()}
    for r in passed:
        by_reason[reason_of.get((r["ticker"], r["date"]), "?")].append(r)

    if by_reason:
        print("\nRejected, broken down by which filter stopped it:")
        for reason, recs in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            summarize(f"  {reason}", recs, args.min_sample)

    # Break the AI's skips down by the condition it cited, not just "claude_skip"
    ai = [r for r in passed if reason_of.get((r["ticker"], r["date"]), "").startswith("claude_skip")]
    if ai:
        by_cond = defaultdict(list)
        for r in ai:
            by_cond[classify_skip_condition(text_of.get((r["ticker"], r["date"]), ""))].append(r)
        print("\nAI skips, by the condition Claude actually cited:")
        for cond, recs in sorted(by_cond.items(), key=lambda x: -len(x[1])):
            summarize(f"  {cond}", recs, args.min_sample)

    # Per-filter verdict: a filter earns its place only if what it REJECTS has
    # lower alpha than what we KEPT. Anything else is discarding profit.
    took_alpha = summarize_alpha([r["alpha"] for r in took if r["alpha"] is not None])["avg_alpha_pct"]
    if took_alpha is not None and by_reason:
        print(f"\nVERDICT — kept trades average {took_alpha:+.2f}% alpha. A filter is worth keeping")
        print("only if the signals it rejected did WORSE than that:")
        for reason, recs in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            if len(recs) < args.min_sample:
                continue
            a = summarize_alpha([r["alpha"] for r in recs if r["alpha"] is not None])["avg_alpha_pct"]
            if a is None:
                continue
            gap = a - took_alpha
            verdict = "JUSTIFIED" if gap < 0 else "COSTING ALPHA"
            print(f"  {reason:34} rejected alpha {a:+6.2f}%  vs kept {took_alpha:+6.2f}%  "
                  f"→ {gap:+6.2f}pp  {verdict}")

    good = [r for r in passed if (r["alpha"] or 0) > 0]
    if good:
        print(f"\n{len(good)}/{len(passed)} rejected signals had POSITIVE alpha. Best missed:")
        for r in sorted(good, key=lambda x: -(x["alpha"] or 0))[:10]:
            print(f"  {r['ticker']:6} {str(r['date']):12} ${r['pnl']:>+8,.0f}  alpha {r['alpha']:+6.2f}%"
                  f"   [{reason_of.get((r['ticker'], r['date']), '?')}]")

    print("\nRead the alpha column, not P&L: more trades mechanically means more dollars.")
    print("A filter is only justified if what it rejects has LOWER alpha than what it keeps.")


if __name__ == "__main__":
    main()
