"""
Phase 3 — Smart Money & Information Edge

Connects to Capitol Trades (capitoltrades.com) — a free public API tracking
US politician stock disclosures.

Two fetch modes:
  - fetch_trades()       : filter by politician name (original mode)
  - fetch_large_trades() : filter by minimum trade SIZE regardless of politician
                           This catches significant institutional-level moves
                           from anyone, not just pre-selected politicians.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

from core.alpaca import market_buy, get_latest_price, get_account
from core.logger import load_state, save_state, log_trade, log

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"
CAPITOL_TRADES_URL = "https://bff.capitoltrades.com/trades"
CAPITOL_TRADES_WEB = "https://www.capitoltrades.com/trades"

# Capitol Trades reports size as a dollar range string.
# We map each range to its midpoint for comparison.
SIZE_MIDPOINTS = {
    "$1,001 - $15,000": 8_000,
    "$15,001 - $50,000": 32_500,
    "$50,001 - $100,000": 75_000,
    "$100,001 - $250,000": 175_000,
    "$250,001 - $500,000": 375_000,
    "$500,001 - $1,000,000": 750_000,
    "$1,000,001 - $5,000,000": 3_000_000,
    "Over $5,000,000": 7_500_000,
}

# Maps scraped short-form sizes (e.g. "15K–50K") to API-format strings.
_SCRAPE_SIZE_MAP = {
    "1K":   "$1,001 - $15,000",
    "15K":  "$15,001 - $50,000",
    "50K":  "$50,001 - $100,000",
    "100K": "$100,001 - $250,000",
    "250K": "$250,001 - $500,000",
    "500K": "$500,001 - $1,000,000",
    "1M":   "$1,000,001 - $5,000,000",
    "5M":   "Over $5,000,000",
}

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def _settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return json.load(f)["smart_money"]


def _estimate_size(size_str: str) -> int:
    """Convert Capitol Trades size range string to an estimated dollar value."""
    for label, midpoint in SIZE_MIDPOINTS.items():
        if label.lower() in size_str.lower():
            return midpoint
    nums = re.findall(r"[\d,]+", size_str.replace(",", ""))
    if nums:
        return int(nums[-1])
    return 0


def _scrape_size_to_api_format(scrape_size: str) -> str:
    """Convert scraped short size (e.g. '15K–50K') to API-format string."""
    for key, val in _SCRAPE_SIZE_MAP.items():
        if scrape_size.startswith(key):
            return val
    return scrape_size


def _parse_scrape_date(day: str, month_year: str) -> str:
    """Convert '22 Apr' + '2026' to '2026-04-22'."""
    try:
        return datetime.strptime(f"{day} {month_year}", "%d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _fetch_raw_scrape(page: int = 1) -> list:
    """Scrape the Capitol Trades website as a fallback when the API is down."""
    from bs4 import BeautifulSoup

    try:
        params = {"page": page} if page > 1 else {}
        resp = requests.get(
            CAPITOL_TRADES_WEB,
            params=params,
            headers=_SCRAPE_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Capitol Trades web scrape failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("tbody tr")
    trades = []

    for row in rows:
        try:
            # Politician
            pol_link = row.select_one("h2.politician-name a")
            if not pol_link:
                continue
            pol_name = pol_link.get_text(strip=True)
            pol_href = pol_link.get("href", "")
            pol_id = pol_href.strip("/").split("/")[-1]

            # Ticker
            ticker_el = row.select_one("span.issuer-ticker")
            raw_ticker = ticker_el.get_text(strip=True) if ticker_el else ""
            ticker = raw_ticker.split(":")[0] if raw_ticker else ""

            # Company
            issuer_el = row.select_one("h3.q-fieldset.issuer-name a")
            company = issuer_el.get_text(strip=True) if issuer_el else ""

            # Dates — first two date cells each have a day div and a year div
            date_cells = row.select("td div.text-center")
            pub_date = tx_date = ""
            if len(date_cells) >= 1:
                parts = [d.get_text(strip=True) for d in date_cells[0].find_all("div")]
                if len(parts) == 2:
                    pub_date = _parse_scrape_date(parts[0], parts[1])
            if len(date_cells) >= 2:
                parts = [d.get_text(strip=True) for d in date_cells[1].find_all("div")]
                if len(parts) == 2:
                    tx_date = _parse_scrape_date(parts[0], parts[1])

            # Transaction type
            tx_el = row.select_one("span.tx-type")
            tx_type = tx_el.get_text(strip=True) if tx_el else ""

            # Size (short form like "15K–50K")
            size_el = row.select_one("span.trade-size span.text-txt-dimmer")
            size_raw = size_el.get_text(strip=True) if size_el else ""
            size = _scrape_size_to_api_format(size_raw)

            # Price
            price_el = row.find(lambda tag: tag.name == "td" and tag.get_text(strip=True).startswith("$"))
            price_str = price_el.get_text(strip=True).lstrip("$") if price_el else ""

            trades.append({
                "txDate": tx_date,
                "publishedDate": pub_date,
                "txType": tx_type,
                "size": size,
                "price": price_str,
                "politician": {"name": pol_name, "id": pol_id},
                "asset": {"ticker": ticker, "assetName": company, "assetType": "stock"},
            })
        except Exception as e:
            log.warning(f"Skipping malformed scrape row: {e}")
            continue

    return trades


def _fetch_raw(page_size: int = 100, page: int = 1, source: str = "auto") -> list:
    """Fetch one page of disclosures.

    source: "auto" (API with web fallback) | "api" (API only) | "web" (scrape only)
    """
    if source == "web":
        return _fetch_raw_scrape(page=page)

    params = {
        "pageSize": page_size,
        "page": page,
        "sortBy": "txDate",
        "sortDir": "desc",
    }
    try:
        resp = requests.get(CAPITOL_TRADES_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException as e:
        if source == "api":
            log.error(f"Capitol Trades API unavailable: {e}")
            return []
        log.warning(f"Capitol Trades API unavailable ({e}), falling back to web scrape")
        return _fetch_raw_scrape(page=page)


def fetch_trades(days_back: int = 7, politician_name: str = None,
                 source: str = "auto") -> list:
    """Pull recent politician stock disclosures, optionally filtered by name."""
    trades = _fetch_raw(source=source)
    cutoff = datetime.now() - timedelta(days=days_back)

    recent = []
    for t in trades:
        try:
            if datetime.strptime(t.get("txDate", ""), "%Y-%m-%d") >= cutoff:
                recent.append(t)
        except ValueError:
            pass

    if politician_name:
        name_lower = politician_name.lower()
        recent = [
            t for t in recent
            if name_lower in t.get("politician", {}).get("name", "").lower()
        ]

    return recent


def fetch_large_trades(min_size: int = 50_000, days_back: int = 7,
                       tx_types: tuple = ("buy",),
                       source: str = "auto") -> list:
    """
    Fetch ALL significant buy disclosures above a dollar threshold,
    regardless of which politician made them.

    This is the primary signal source for the AI pipeline — it catches
    important market moves based on conviction size, not identity.

    Args:
        min_size: Minimum estimated trade value in dollars (default $50K)
        days_back: How many calendar days to look back
        tx_types: Transaction types to include (default: buys only)
        source: "auto" | "api" | "web"
    """
    trades = _fetch_raw(page_size=100, source=source)
    cutoff = datetime.now() - timedelta(days=days_back)

    results = []
    for t in trades:
        # Date filter
        try:
            tx_date = datetime.strptime(t.get("txDate", ""), "%Y-%m-%d")
            if tx_date < cutoff:
                continue
        except ValueError:
            continue

        # Type filter (buys only by default)
        tx_type = t.get("txType", "").lower()
        if not any(typ in tx_type for typ in tx_types):
            continue

        # Size filter
        size_str = t.get("size", "")
        estimated = _estimate_size(size_str)
        t["_estimated_size"] = estimated
        if estimated < min_size:
            continue

        # Skip non-stock assets (options, crypto, etc.)
        asset_type = t.get("asset", {}).get("assetType", "").lower()
        if asset_type and "stock" not in asset_type and "equity" not in asset_type:
            continue

        results.append(t)

    # Sort by estimated size descending — biggest moves first
    results.sort(key=lambda x: x.get("_estimated_size", 0), reverse=True)
    return results


def format_summary(trades: list) -> str:
    if not trades:
        return "No trades found."
    lines = ["Date       | Politician                      | Ticker | Type       | Size"]
    lines.append("-" * 78)
    for t in trades[:25]:
        name = t.get("politician", {}).get("name", "Unknown")[:30]
        ticker = t.get("asset", {}).get("ticker", "N/A")[:6]
        tx_type = t.get("txType", "N/A")[:10]
        size = t.get("size", "N/A")
        date = t.get("txDate", "N/A")
        est = t.get("_estimated_size", 0)
        est_str = f"~${est:>10,.0f}" if est else ""
        lines.append(f"{date} | {name:<30} | {ticker:<6} | {tx_type:<10} | {size:<25} {est_str}")
    return "\n".join(lines)


def check_and_copy() -> dict:
    """
    Rule-based copy (no AI). Prefer python main.py analyze for AI-driven execution.
    """
    cfg = _settings()
    if not cfg.get("enabled", False):
        return {"status": "smart_money disabled"}

    politicians = cfg.get("politicians", [])
    auto_copy = cfg.get("auto_copy", False)
    min_value = cfg.get("min_trade_value", 15000)
    days_back = cfg.get("days_lookback", 7)

    all_trades = []
    for pol in politicians:
        all_trades.extend(fetch_trades(days_back=days_back, politician_name=pol))

    buy_signals = [t for t in all_trades if "buy" in t.get("txType", "").lower()]
    actions = []

    if auto_copy and buy_signals:
        state = load_state()
        acct = get_account()
        buying_power = float(acct.buying_power)

        for trade in buy_signals:
            ticker = trade.get("asset", {}).get("ticker", "")
            if not ticker or not ticker.replace(".", "").isalpha():
                continue

            trade_key = f"{trade.get('txDate')}_{ticker}_{trade.get('politician', {}).get('id', '')}"
            if trade_key in state.get("copied_trades", []):
                continue

            try:
                price = get_latest_price(ticker)
                shares = max(1, int(min_value / price))
                cost = shares * price
                if buying_power < cost:
                    continue
                market_buy(ticker, shares)
                log_trade(
                    "SMART_BUY", ticker, shares, price,
                    f"copying {trade.get('politician', {}).get('name', 'unknown')}"
                )
                state.setdefault("copied_trades", []).append(trade_key)
                buying_power -= cost
                actions.append(f"Copied: {shares} {ticker} @ ${price:.2f}")
            except Exception as e:
                log.error(f"Failed to copy {ticker}: {e}")

        save_state(state)

    return {
        "trades_found": len(all_trades),
        "buy_signals": len(buy_signals),
        "actions": actions,
        "summary": format_summary(all_trades),
    }
