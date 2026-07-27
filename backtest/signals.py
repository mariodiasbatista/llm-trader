"""
Fetch a broad historical window of SEC EDGAR Form 4 insider-purchase signals
for backtesting, reusing strategies.sec_insiders' fetch/parse internals so the
backtest can never see a different signal shape than production does.
"""
import json
from pathlib import Path
from datetime import date, timedelta

from strategies.sec_insiders import _fetch_filings_metadata, _fetch_filing, _parse_form4

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(start_date: date, end_date: date) -> Path:
    return CACHE_DIR / f"raw_signals_{start_date}_{end_date}.jsonl"


def fetch_historical_insider_signals(
    start_date: date,
    end_date: date,
    max_filings_per_week: int = 400,
    use_cache: bool = True,
    progress_cb=None,
) -> list[dict]:
    """
    Fetch and parse all Form 4 open-market purchase transactions filed between
    start_date and end_date (inclusive), UNFILTERED by min_transaction_value or
    require_high_conviction — those are applied per sweep candidate in memory
    via filter_signals() so this expensive network fetch only ever runs once
    per date range.

    Pages the window in 7-day chunks (EDGAR full-text search + Form 4 XML
    downloads are unbatched and rate-limited to ~9 req/s, so one giant query
    across a 6-12 month window is impractical).

    Results are cached to backtest/cache/raw_signals_<start>_<end>.jsonl —
    re-running with the same date range and use_cache=True skips the network.
    """
    cache_file = _cache_path(start_date, end_date)
    if use_cache and cache_file.exists():
        with open(cache_file) as f:
            return [json.loads(line) for line in f if line.strip()]

    all_signals = []
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=6), end_date)
        filings_meta = _fetch_filings_metadata(
            start_date=chunk_start, end_date=chunk_end, max_filings=max_filings_per_week,
        )
        for acc_no, doc_name, filing_date, ciks in filings_meta:
            xml_text, fdate = _fetch_filing(acc_no, doc_name, filing_date, ciks)
            if xml_text is None:
                continue
            all_signals.extend(_parse_form4(xml_text, fdate))

        if progress_cb:
            progress_cb(chunk_start, chunk_end, len(filings_meta), len(all_signals))

        chunk_start = chunk_end + timedelta(days=1)

    with open(cache_file, "w") as f:
        for sig in all_signals:
            f.write(json.dumps(sig) + "\n")

    return all_signals


def filter_signals(
    signals: list[dict],
    min_transaction_value: float = 100_000,
    require_high_conviction: bool = True,
) -> list[dict]:
    """Apply the sec_insiders config filters in memory — cheap, run once per sweep candidate."""
    out = []
    for s in signals:
        if s["_transaction_value"] < min_transaction_value:
            continue
        if require_high_conviction and not s["_high_conviction"]:
            continue
        out.append(s)
    return out
