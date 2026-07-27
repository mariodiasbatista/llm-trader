"""Sub-period bucketing for the strict "positive in every sub-period" check."""

LOW_CONFIDENCE_TRADE_THRESHOLD = 3


def month_key(date) -> str:
    return f"{date.year:04d}-{date.month:02d}"


def bucket_by_month(records: list[dict], date_field: str = "exit_date") -> dict[str, dict]:
    """
    Group P&L records into calendar-month buckets.

    Each record must have a `pnl` field and a date under `date_field`.
    Returns {month_key: {"pnl": total, "n": count, "low_confidence": bool}}.
    Months with fewer than LOW_CONFIDENCE_TRADE_THRESHOLD trades are flagged
    rather than merged into a neighbor — merging would hide exactly the kind
    of thin-sample noise the strict per-period check is meant to expose.
    """
    buckets: dict[str, dict] = {}
    for r in records:
        key = month_key(r[date_field])
        b = buckets.setdefault(key, {"pnl": 0.0, "n": 0, "trades": []})
        b["pnl"] += r["pnl"]
        b["n"] += 1
        b["trades"].append(r)

    for b in buckets.values():
        b["low_confidence"] = b["n"] < LOW_CONFIDENCE_TRADE_THRESHOLD

    return dict(sorted(buckets.items()))


def worst_bucket_pnl(buckets: dict[str, dict]) -> float:
    """Return the minimum monthly P&L across all buckets (the value the sweep optimizes)."""
    if not buckets:
        return 0.0
    return min(b["pnl"] for b in buckets.values())


def all_buckets_positive(buckets: dict[str, dict]) -> bool:
    return all(b["pnl"] > 0 for b in buckets.values()) if buckets else False
