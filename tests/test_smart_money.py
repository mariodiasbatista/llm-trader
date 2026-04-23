"""Tests for smart_money.py — size filtering and disclosure fetching."""
import pytest
from unittest.mock import patch, MagicMock
from strategies.smart_money import _estimate_size, fetch_large_trades, fetch_trades, SIZE_MIDPOINTS


class TestEstimateSize:
    def test_known_ranges(self):
        assert _estimate_size("$50,001 - $100,000") == 75_000
        assert _estimate_size("$100,001 - $250,000") == 175_000
        assert _estimate_size("$1,001 - $15,000") == 8_000
        assert _estimate_size("Over $5,000,000") == 7_500_000

    def test_all_ranges_covered(self):
        for label, midpoint in SIZE_MIDPOINTS.items():
            assert _estimate_size(label) == midpoint

    def test_unknown_returns_zero(self):
        assert _estimate_size("Unknown amount") == 0

    def test_case_insensitive(self):
        assert _estimate_size("$50,001 - $100,000".upper()) == 75_000


MOCK_TRADES = [
    {
        "txDate": "2026-04-22",
        "txType": "Buy",
        "size": "$100,001 - $250,000",
        "politician": {"name": "Michael McCaul", "id": "P001"},
        "asset": {"ticker": "NVDA", "assetType": "stock"},
    },
    {
        "txDate": "2026-04-21",
        "txType": "Buy",
        "size": "$1,001 - $15,000",          # below $50K threshold
        "politician": {"name": "Nancy Pelosi", "id": "P002"},
        "asset": {"ticker": "AAPL", "assetType": "stock"},
    },
    {
        "txDate": "2026-04-20",
        "txType": "Sell",                     # sell — excluded by default
        "size": "$500,001 - $1,000,000",
        "politician": {"name": "Josh Gottheimer", "id": "P003"},
        "asset": {"ticker": "MSFT", "assetType": "stock"},
    },
    {
        "txDate": "2026-04-19",
        "txType": "Buy",
        "size": "$250,001 - $500,000",
        "politician": {"name": "Tom Reed", "id": "P004"},
        "asset": {"ticker": "AMD", "assetType": "stock"},
    },
]


class TestFetchLargeTrades:
    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_filters_by_min_size(self, mock_fetch):
        results = fetch_large_trades(min_size=50_000, days_back=30)
        tickers = [t["asset"]["ticker"] for t in results]
        assert "NVDA" in tickers       # $175K — above threshold
        assert "AMD" in tickers        # $375K — above threshold
        assert "AAPL" not in tickers   # $8K — below threshold

    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_excludes_sells_by_default(self, mock_fetch):
        results = fetch_large_trades(min_size=50_000, days_back=30)
        tickers = [t["asset"]["ticker"] for t in results]
        assert "MSFT" not in tickers   # sell — excluded

    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_sorted_by_size_descending(self, mock_fetch):
        results = fetch_large_trades(min_size=50_000, days_back=30)
        sizes = [t["_estimated_size"] for t in results]
        assert sizes == sorted(sizes, reverse=True)

    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_attaches_estimated_size(self, mock_fetch):
        results = fetch_large_trades(min_size=50_000, days_back=30)
        for t in results:
            assert "_estimated_size" in t
            assert t["_estimated_size"] >= 50_000

    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_hundred_k_threshold(self, mock_fetch):
        results = fetch_large_trades(min_size=100_000, days_back=30)
        tickers = [t["asset"]["ticker"] for t in results]
        assert "NVDA" in tickers   # $175K — above
        assert "AMD" in tickers    # $375K — above


class TestFetchTrades:
    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_filter_by_politician(self, mock_fetch):
        results = fetch_trades(days_back=30, politician_name="McCaul")
        assert len(results) == 1
        assert results[0]["asset"]["ticker"] == "NVDA"

    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_case_insensitive_politician_filter(self, mock_fetch):
        results = fetch_trades(days_back=30, politician_name="mccaul")
        assert len(results) == 1

    @patch("strategies.smart_money._fetch_raw", return_value=MOCK_TRADES)
    def test_no_filter_returns_all_recent(self, mock_fetch):
        results = fetch_trades(days_back=30)
        assert len(results) == len(MOCK_TRADES)

    @patch("strategies.smart_money._fetch_raw", return_value=[])
    def test_empty_api_response(self, mock_fetch):
        results = fetch_trades(days_back=7)
        assert results == []
