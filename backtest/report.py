"""Generate a Markdown leaderboard + JSON dump from a backtest/sweep.py run."""
import json
from datetime import datetime, date
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _fmt_money(x: float) -> str:
    sign = "+" if x >= 0 else "-"
    return f"{sign}${abs(x):,.0f}"


def _month_table(buckets: dict) -> str:
    if not buckets:
        return "  _(no trades)_\n"
    lines = ["  | Month | P&L | Trades | Pass |", "  |---|---|---|---|"]
    for month, b in buckets.items():
        flag = "✅" if b["pnl"] > 0 else "❌"
        conf = " (low-N)" if b["low_confidence"] else ""
        lines.append(f"  | {month} | {_fmt_money(b['pnl'])} | {b['n']}{conf} | {flag} |")
    return "\n".join(lines) + "\n"


def _fmt_alpha(result: dict) -> str:
    avg = result.get("avg_alpha_pct")
    if avg is None:
        return "alpha: N/A"
    pct_pos = result.get("pct_positive_alpha")
    return f"alpha vs SPY: {avg:+.1f}% avg ({pct_pos:.0f}% of trades beat SPY)"


def _evidence_section(title: str, result: dict | None) -> str:
    if result is None:
        return f"**{title}**: not available for this run.\n"
    lines = [
        f"**{title}** — {result['n_trades']} trades, total {_fmt_money(result['total_pnl'])}, "
        f"worst month {_fmt_money(result['worst_month_pnl'])}, "
        f"{'PASSES' if result['all_positive'] else 'FAILS'} strict per-month-positive check, "
        f"{_fmt_alpha(result)}.",
        "",
        _month_table(result["buckets"]),
    ]
    return "\n".join(lines)


def generate_leaderboard(sweep_result: dict, label: str = None) -> tuple[Path, Path]:
    """
    Write backtest/results/leaderboard_<timestamp>.md and sweep_<timestamp>.json
    from a backtest.sweep.run_sweep() result. Returns (md_path, json_path).
    """
    ts = label or datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = RESULTS_DIR / f"leaderboard_{ts}.md"
    json_path = RESULTS_DIR / f"sweep_{ts}.json"

    base = sweep_result["base_candidate"]
    lines = [
        "# Backtest Sweep Leaderboard",
        "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} — "
        f"{sweep_result['iterations']} iterations, {sweep_result['n_real_positions']} real historical "
        f"positions replayed, {sweep_result['n_edgar_signals']} historical EDGAR signals fetched.",
        "",
        f"**Fully-passing candidates found (positive P&L in every sub-period): {len(sweep_result['passing'])}**",
        "",
        "---",
        "",
    ]

    for rank, r in enumerate(sweep_result["leaderboard"], start=1):
        diff = {k: v for k, v in r["candidate"].items() if base.get(k) != v}
        diff_str = ", ".join(f"{k}={v}" for k, v in diff.items()) if diff else "(same as current config)"
        status = "✅ PASSES" if r["passes_strict"] else "❌ fails strict bar"

        lines.append(f"## #{rank} — {status}")
        lines.append("")
        lines.append(f"**Params changed vs. current config**: {diff_str}")
        lines.append("")
        lines.append(_evidence_section("Real trade history (primary score)", r["real_trades"]))
        lines.append("")
        lines.append(_evidence_section("Synthetic SEC EDGAR replay (secondary evidence)", r["edgar_replay"]))
        lines.append("")
        lines.append(_evidence_section("WHEEL estimate (Black-Scholes premiums, no real option data available)", r["wheel_estimate"]))
        lines.append("")
        lines.append("---")
        lines.append("")

    md_path.write_text("\n".join(lines))

    def _json_default(o):
        if isinstance(o, date):
            return o.isoformat()
        return str(o)

    json_path.write_text(json.dumps(sweep_result, default=_json_default, indent=2))

    return md_path, json_path
