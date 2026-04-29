"""Tests for web scraping fallback and source param in smart_money.py."""
import pytest
import requests
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from strategies.smart_money import (
    _scrape_size_to_api_format,
    _parse_scrape_date,
    _fetch_raw,
    fetch_trades,
    fetch_large_trades,
    _SCRAPE_SIZE_MAP,
)


class TestScrapeSizeToApiFormat:
    def test_all_known_sizes(self):
        assert _scrape_size_to_api_format("1K–15K") == "$1,001 - $15,000"
        assert _scrape_size_to_api_format("15K–50K") == "$15,001 - $50,000"
        assert _scrape_size_to_api_format("50K–100K") == "$50,001 - $100,000"
        assert _scrape_size_to_api_format("100K–250K") == "$100,001 - $250,000"
        assert _scrape_size_to_api_format("250K–500K") == "$250,001 - $500,000"
        assert _scrape_size_to_api_format("500K–1M") == "$500,001 - $1,000,000"
        assert _scrape_size_to_api_format("1M–5M") == "$1,000,001 - $5,000,000"
        assert _scrape_size_to_api_format("5M+") == "Over $5,000,000"

    def test_unknown_size_returned_as_is(self):
        assert _scrape_size_to_api_format("unknown") == "unknown"

    def test_all_map_keys_covered(self):
        for key in _SCRAPE_SIZE_MAP:
            result = _scrape_size_to_api_format(key + "–anything")
            assert result != key + "–anything", f"Key '{key}' not matched"


class TestParseScrapDate:
    def test_valid_date(self):
        assert _parse_scrape_date("22 Apr", "2026") == "2026-04-22"
        assert _parse_scrape_date("01 Jan", "2025") == "2025-01-01"
        assert _parse_scrape_date("31 Dec", "2024") == "2024-12-31"

    def test_invalid_date_returns_empty(self):
        assert _parse_scrape_date("bad", "data") == ""
        assert _parse_scrape_date("", "") == ""

    def test_today_format(self):
        """Capitol Trades shows 'Today' + a time string for same-day publications."""
        result = _parse_scrape_date("13:05", "Today")
        assert result == datetime.now().strftime("%Y-%m-%d")

    def test_yesterday_format(self):
        result = _parse_scrape_date("09:30", "Yesterday")
        assert result == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    def test_today_yesterday_case_insensitive(self):
        assert _parse_scrape_date("13:05", "TODAY") == datetime.now().strftime("%Y-%m-%d")
        assert _parse_scrape_date("09:30", "YESTERDAY") == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


SCRAPE_TRADES = [
    {
        "txDate": "2026-03-24",
        "publishedDate": "2026-04-22",
        "txType": "buy",
        "size": "$15,001 - $50,000",
        "price": "348.43",
        "politician": {"name": "Maria Elvira Salazar", "id": "S000168"},
        "asset": {"ticker": "AMGN", "assetName": "Amgen Inc", "assetType": "stock"},
    },
    {
        "txDate": "2026-03-19",
        "publishedDate": "2026-04-22",
        "txType": "buy",
        "size": "$1,001 - $15,000",
        "price": "185.20",
        "politician": {"name": "Maria Elvira Salazar", "id": "S000168"},
        "asset": {"ticker": "BA", "assetName": "Boeing Co", "assetType": "stock"},
    },
]


class TestFetchRawSourceParam:
    @patch("strategies.smart_money._fetch_raw_scrape", side_effect=[SCRAPE_TRADES, []])
    def test_source_web_calls_scraper(self, mock_scrape):
        result = _fetch_raw(source="web")
        assert mock_scrape.call_count == 2  # page 1 had data, page 2 empty → stops
        assert result == SCRAPE_TRADES

    @patch("strategies.smart_money._fetch_raw_scrape")
    @patch("strategies.smart_money.requests.get")
    def test_source_api_does_not_fallback_on_error(self, mock_get, mock_scrape):
        mock_get.side_effect = requests.exceptions.RequestException("503 error")
        result = _fetch_raw(source="api")
        mock_scrape.assert_not_called()
        assert result == []

    @patch("strategies.smart_money._fetch_raw_scrape", side_effect=[SCRAPE_TRADES, []])
    @patch("strategies.smart_money.requests.get")
    def test_source_auto_falls_back_to_scrape_on_api_error(self, mock_get, mock_scrape):
        mock_get.side_effect = requests.exceptions.RequestException("503 error")
        result = _fetch_raw(source="auto")
        assert mock_scrape.call_count == 2  # page 1 had data, page 2 empty → stops
        assert result == SCRAPE_TRADES

    @patch("strategies.smart_money._fetch_raw_scrape")
    @patch("strategies.smart_money.requests.get")
    def test_source_auto_uses_api_when_available(self, mock_get, mock_scrape):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": SCRAPE_TRADES}
        mock_get.return_value = mock_resp
        result = _fetch_raw(source="auto")
        mock_scrape.assert_not_called()
        assert result == SCRAPE_TRADES

    @patch("strategies.smart_money._fetch_raw_scrape")
    @patch("strategies.smart_money.requests.get")
    def test_source_web_skips_api_entirely(self, mock_get, mock_scrape):
        mock_scrape.return_value = SCRAPE_TRADES
        _fetch_raw(source="web")
        mock_get.assert_not_called()


class TestFetchTradesSourceParam:
    @patch("strategies.smart_money._fetch_raw", return_value=SCRAPE_TRADES)
    def test_source_param_passed_through(self, mock_raw):
        fetch_trades(days_back=30, source="web")
        mock_raw.assert_called_once_with(source="web")

    @patch("strategies.smart_money._fetch_raw", return_value=SCRAPE_TRADES)
    def test_default_source_is_auto(self, mock_raw):
        fetch_trades(days_back=30)
        mock_raw.assert_called_once_with(source="auto")


class TestFetchLargeTradesSourceParam:
    @patch("strategies.smart_money._fetch_raw", return_value=SCRAPE_TRADES)
    def test_source_param_passed_through(self, mock_raw):
        fetch_large_trades(min_size=0, days_back=30, source="web")
        mock_raw.assert_called_once_with(page_size=100, source="web")

    @patch("strategies.smart_money._fetch_raw", return_value=SCRAPE_TRADES)
    def test_default_source_is_auto(self, mock_raw):
        fetch_large_trades(min_size=0, days_back=30)
        mock_raw.assert_called_once_with(page_size=100, source="auto")

    @patch("strategies.smart_money._fetch_raw", return_value=SCRAPE_TRADES)
    def test_min_size_zero_returns_all(self, mock_raw):
        results = fetch_large_trades(min_size=0, days_back=60)
        assert len(results) == len(SCRAPE_TRADES)

    @patch("strategies.smart_money._fetch_raw", return_value=SCRAPE_TRADES)
    def test_min_size_above_all_returns_empty(self, mock_raw):
        results = fetch_large_trades(min_size=1_000_000, days_back=30)
        assert results == []
