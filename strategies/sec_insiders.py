"""
SEC EDGAR Form 4 insider filing fetcher.

Replaces Capitol Trades as the signal source. Corporate insiders (CEO, CFO,
directors) must file Form 4 within 2 business days — giving a near-real-time
signal vs the 45-day politician window.

Signal quality: open-market purchases ("P" transaction code) only — not option
exercises, RSU vesting, or stock plan grants. These cost real money and carry
conviction.

Output format is identical to smart_money.py so the rest of the pipeline
(analyze_and_trade.py, claude_advisor.py) works without changes.
"""

import threading
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

# SEC requires a descriptive User-Agent identifying the app and contact email.
HEADERS = {
    "User-Agent": "llmTrader/1.0 mario.dias.batista@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/xml, */*",
}

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data"

# Per-filing fetches run concurrently (see _fetch_filing_pool below) — this many
# workers, all sharing one rate limiter, so wall-clock time drops roughly
# FETCH_WORKERS-fold vs the old fully-serial loop while the aggregate request
# rate to SEC stays identical to before.
FETCH_WORKERS = 6


class _RateLimiter:
    """Thread-safe: never lets a request START less than `min_interval` after
    the previous one, across *all* threads combined — not per-thread. Multiple
    threads can still have requests in flight simultaneously (that's the whole
    point — overlapping I/O wait is what makes the parallel fetch faster), this
    only throttles how fast new requests are *initiated*.
    """

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self._min_interval
        if sleep_for > 0:
            time.sleep(sleep_for)


# Same ~9 req/s cap the old serial loop used (time.sleep(0.11) between calls),
# just enforced across concurrent workers instead of one thread at a time.
_fetch_rate_limiter = _RateLimiter(min_interval=0.11)

# Only open-market purchases signal conviction — everything else is noise.
PURCHASE_CODE = "P"

# Insider roles worth acting on (open-market buy from anyone lower is usually noise).
HIGH_CONVICTION_TITLES = {
    "ceo", "chief executive",
    "cfo", "chief financial",
    "coo", "chief operating",
    "cto", "chief technology",
    "president",
    "director",
    "chairman",
    "executive vice president", "evp",
    "senior vice president", "svp",
    "general counsel",
}


def _is_high_conviction(title: str) -> bool:
    if not title:
        return False
    t = title.lower()
    for role in HIGH_CONVICTION_TITLES:
        if role not in t:
            continue
        # "president" substring would falsely match "vice president" — skip it for plain VPs
        if role == "president" and "vice president" in t:
            continue
        return True
    return False


def _value_to_size_label(value: float) -> str:
    """Map transaction value to Capitol Trades-style size label (for Claude context)."""
    if value < 15_000:
        return "$1,001 - $15,000"
    elif value < 50_000:
        return "$15,001 - $50,000"
    elif value < 100_000:
        return "$50,001 - $100,000"
    elif value < 250_000:
        return "$100,001 - $250,000"
    elif value < 500_000:
        return "$250,001 - $500,000"
    elif value < 1_000_000:
        return "$500,001 - $1,000,000"
    elif value < 5_000_000:
        return "$1,000,001 - $5,000,000"
    else:
        return "Over $5,000,000"


# ─── EDGAR fetch helpers ──────────────────────────────────────────────────────

def _fetch_filings_metadata(
    days_back: int = 1,
    max_filings: int = 200,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list:
    """
    Return list of (acc_no, doc_name, filing_date, ciks) for Form 4 filings.

    By default scans the last `days_back` days from today. Pass explicit
    `start_date`/`end_date` instead to pull an arbitrary historical window
    (used by backtest/signals.py to replay a larger sample than the live
    1-day lookback ever sees).

    EDGAR search IDs have the format "accno:docname". The _source.ciks field
    lists all CIKs involved — typically [reporter_cik, issuer_cik]. We pass
    both so _fetch_filing can try the correct archive path.
    """
    end_dt = end_date or date.today()
    start_dt = start_date or (end_dt - timedelta(days=days_back))

    filings = []
    from_offset = 0
    page_size = 100

    while len(filings) < max_filings:
        try:
            r = requests.get(
                EDGAR_SEARCH_URL,
                params={
                    "forms": "4",
                    "dateRange": "custom",
                    "startdt": start_dt.strftime("%Y-%m-%d"),
                    "enddt": end_dt.strftime("%Y-%m-%d"),
                    "from": from_offset,
                    "size": page_size,
                },
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                log.warning(f"EDGAR search returned HTTP {r.status_code}")
                break
            data = r.json()
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                raw_id = h["_id"]          # "accno:docname" or just "accno"
                source = h.get("_source", {})
                filing_date = source.get("file_date", "")[:10]
                # All CIKs involved (reporter + issuer) — try each as archive root.
                ciks = [c.lstrip("0") or "0" for c in source.get("ciks", [])]
                if ":" in raw_id:
                    acc_no, doc_name = raw_id.split(":", 1)
                else:
                    acc_no, doc_name = raw_id, None
                # Also add the accno-prefix CIK as a candidate.
                prefix_cik = acc_no.split("-")[0].lstrip("0") or "0"
                if prefix_cik not in ciks:
                    ciks.insert(0, prefix_cik)
                filings.append((acc_no, doc_name, filing_date, ciks))
            if len(hits) < page_size:
                break
            from_offset += page_size
            time.sleep(0.15)  # stay under SEC 10 req/s limit
        except Exception as e:
            log.warning(f"EDGAR search error: {e}")
            break

    log.info(f"EDGAR search: {len(filings)} Form 4 filings for last {days_back}d")
    return filings[:max_filings]


def _fetch_filing(acc_no: str, doc_name: str | None, filing_date: str, ciks: list) -> tuple:
    """
    Download the Form 4 XML. Returns (xml_text, filing_date) or (None, None).

    Tries every CIK in the list as the archive root until one works.
    Fast path: fetch the XML directly using the embedded doc_name.
    Fallback: discover the filename via the filing index JSON.
    """
    today_str = date.today().strftime("%Y-%m-%d")
    acc_clean = acc_no.replace("-", "")

    for cik in ciks:
        base = f"{EDGAR_ARCHIVE_URL}/{cik}/{acc_clean}"

        # Fast path — doc name is embedded in the search result ID.
        if doc_name:
            try:
                r = requests.get(f"{base}/{doc_name}", headers=HEADERS, timeout=8)
                if r.status_code == 200:
                    return r.text, filing_date or today_str
            except Exception:
                pass

        # Fallback — discover filename from the index JSON.
        try:
            r = requests.get(
                f"{base}/{acc_no}-index.json",
                headers={**HEADERS, "Accept": "application/json"},
                timeout=8,
            )
            if r.status_code == 200:
                index = r.json()
                fd = filing_date or (
                    index.get("filingDate") or index.get("file-date")
                    or index.get("dateFiled", today_str)
                )[:10]
                docs = index.get("documents") or index.get("docs") or []
                xml_filename = None
                for doc in docs:
                    fname = doc.get("filename") or doc.get("document") or doc.get("name") or ""
                    if doc.get("type") == "4" and fname.lower().endswith(".xml"):
                        xml_filename = fname
                        break
                if not xml_filename:
                    for doc in docs:
                        fname = doc.get("filename") or doc.get("document") or doc.get("name") or ""
                        if fname.lower().endswith(".xml"):
                            xml_filename = fname
                            break
                if xml_filename:
                    r2 = requests.get(f"{base}/{xml_filename}", headers=HEADERS, timeout=8)
                    if r2.status_code == 200:
                        return r2.text, fd
        except Exception as e:
            log.debug(f"Index fallback failed for {acc_no} cik={cik}: {e}")

    return None, None


# ─── XML parser ───────────────────────────────────────────────────────────────

def _parse_form4(xml_text: str, filing_date: str) -> list:
    """
    Parse Form 4 XML and return a list of standardised buy-signal dicts.

    Only returns open-market purchases (transaction code "P") by directors
    or officers. Each returned dict is compatible with the smart_money.py
    output format so the rest of the pipeline works unchanged.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    def _text(elem, *paths, default=""):
        for path in paths:
            node = elem.find(path)
            if node is not None and node.text:
                return node.text.strip()
        return default

    # ── Issuer ────────────────────────────────────────────────────────────────
    ticker = _text(root, ".//issuerTradingSymbol").upper()
    company_name = _text(root, ".//issuerName")
    if not ticker or not ticker.replace(".", "").replace("-", "").isalpha():
        return []

    # ── Reporter (insider) ────────────────────────────────────────────────────
    reporter_name = _text(root, ".//rptOwnerName")
    reporter_cik  = _text(root, ".//rptOwnerCik")
    officer_title = _text(root, ".//officerTitle")
    _true_vals = {"1", "true", "True"}
    is_director = _text(root, ".//isDirector") in _true_vals
    is_officer  = _text(root, ".//isOfficer") in _true_vals

    # Skip non-director, non-officer insiders (e.g. 10% shareholders only).
    if not (is_director or is_officer):
        return []

    results = []

    for txn in root.findall(".//nonDerivativeTransaction"):
        # Only open-market purchases.
        code = _text(txn, ".//transactionCode")
        if code != PURCHASE_CODE:
            continue

        # Must be an acquisition (A), not a disposition (D).
        # The value is in a <value> child: <transactionAcquiredDisposedCode><value>A</value>
        acq_disp = _text(txn, ".//transactionAcquiredDisposedCode/value",
                         ".//transactionAcquiredDisposedCode")
        if acq_disp.strip().upper() != "A":
            continue

        tx_date_str = _text(
            txn,
            ".//transactionDate/value",
            ".//transactionDate",
            default=filing_date,
        )

        shares_str = _text(txn, ".//transactionShares/value", ".//transactionShares")
        price_str  = _text(txn, ".//transactionPricePerShare/value",
                           ".//transactionPricePerShare")

        try:
            shares = float(shares_str)
            price  = float(price_str) if price_str else 0.0
        except (ValueError, TypeError):
            continue

        if price <= 0 or shares <= 0:
            continue

        tx_value = shares * price
        role = officer_title or ("Director" if is_director else "Officer")

        results.append({
            # ── Core fields (same as smart_money.py) ──────────────────────
            "txDate":        tx_date_str[:10],
            "publishedDate": filing_date,
            "txType":        "buy",
            "size":          _value_to_size_label(tx_value),
            "price":         str(round(price, 2)),
            "politician": {          # field reused for insider info
                "name": reporter_name,
                "id":   f"CIK{reporter_cik}",
            },
            "asset": {
                "ticker":    ticker,
                "assetName": company_name,
                "assetType": "stock",
            },
            # ── Extra context passed to Claude ─────────────────────────────
            "_insider_role":       role,
            "_transaction_value":  tx_value,
            "_shares":             int(shares),
            "_is_director":        is_director,
            "_is_officer":         is_officer,
            "_high_conviction":    _is_high_conviction(role),
        })

    return results


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_insider_buys(
    days_back: int = 1,
    min_transaction_value: float = 100_000,
    max_filings: int = 400,
    require_high_conviction: bool = True,
) -> list:
    """
    Fetch recent Form 4 open-market purchase signals from SEC EDGAR.

    Args:
        days_back:                Days of Form 4 filings to scan (default 1 — bot runs every 30 min)
        min_transaction_value:    Minimum total $ value of the purchase (default $100K)
        max_filings:              Cap on Form 4s parsed per run (rate-limit protection)
        require_high_conviction:  If True, only CEO/CFO/Director/President buys (default True)

    Returns:
        List of buy-signal dicts compatible with smart_money.fetch_large_trades() output.
    """
    filings_meta = _fetch_filings_metadata(days_back=days_back, max_filings=max_filings)

    def _fetch_one(item):
        acc_no, doc_name, filing_date, ciks = item
        _fetch_rate_limiter.wait()
        return _fetch_filing(acc_no, doc_name, filing_date, ciks)

    signals = []
    processed = 0

    # Was a fully serial loop (one filing fetched at a time, ~0.11s apart) —
    # with up to 400 filings that routinely exceeded the 5-minute analyze
    # subprocess timeout, silently dropping the entire cycle's signals.
    # FETCH_WORKERS concurrent requests, throttled by one shared rate limiter
    # to the same aggregate ~9 req/s SEC cap as before, cuts wall-clock time
    # roughly FETCH_WORKERS-fold since the bottleneck is I/O wait, not CPU.
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        future_to_item = {pool.submit(_fetch_one, item): item for item in filings_meta}
        for future in as_completed(future_to_item):
            try:
                xml_text, filing_date = future.result()
            except Exception as e:
                log.warning(f"Filing fetch failed: {e}")
                xml_text, filing_date = None, None

            processed += 1
            if processed % 25 == 0:
                log.info(f"  Parsed {processed}/{len(filings_meta)} filings — {len(signals)} signals so far")

            if xml_text is None:
                continue

            txns = _parse_form4(xml_text, filing_date)
            for t in txns:
                if t["_transaction_value"] < min_transaction_value:
                    continue
                if require_high_conviction and not t["_high_conviction"]:
                    continue
                signals.append(t)

    log.info(
        f"SEC EDGAR: {len(signals)} insider buy signals "
        f"≥ ${min_transaction_value:,.0f} from {processed} filings"
    )
    return signals
