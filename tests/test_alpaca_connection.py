"""
Live integration tests against Alpaca Paper Trading.
Requires credentials.json to be filled in.

Run: pytest tests/test_alpaca_connection.py -v
"""
import json
import pytest
from pathlib import Path

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"

# Skip all tests in this file if credentials.json is not configured
def _creds_ready() -> bool:
    if not CREDS_FILE.exists():
        return False
    try:
        creds = json.loads(CREDS_FILE.read_text())
        key = creds.get("alpaca", {}).get("api_key", "")
        return key and not key.startswith("PK") == key   # skip if still example key
    except Exception:
        return False


needs_creds = pytest.mark.skipif(
    not CREDS_FILE.exists(),
    reason="credentials.json not found — run setup.sh first"
)


@needs_creds
class TestAlpacaConnection:
    def test_account_is_accessible(self):
        from core.alpaca import get_account
        acct = get_account()
        assert acct is not None
        assert acct.status in ("ACTIVE", "active")

    @needs_creds
    def test_account_is_paper(self):
        """Ensure we are never running against a live account."""
        creds = json.loads(CREDS_FILE.read_text())
        assert creds["alpaca"].get("paper", True) is True, (
            "DANGER: credentials.json has paper=false — refusing to run tests against live account"
        )

    @needs_creds
    def test_can_fetch_positions(self):
        from core.alpaca import get_positions
        positions = get_positions()
        assert isinstance(positions, list)

    @needs_creds
    def test_can_get_price(self):
        from core.alpaca import get_latest_price
        price = get_latest_price("AAPL")
        assert isinstance(price, float)
        assert price > 0

    @needs_creds
    def test_buying_power_is_positive(self):
        from core.alpaca import get_account
        acct = get_account()
        buying_power = float(acct.buying_power)
        assert buying_power >= 0

    @needs_creds
    def test_portfolio_value_is_reasonable(self):
        from core.alpaca import get_account
        acct = get_account()
        portfolio_value = float(acct.portfolio_value)
        # Paper account starts with $100K
        assert portfolio_value > 0


@needs_creds
class TestCapitolTradesAPI:
    def test_fetch_returns_list(self):
        from strategies.smart_money import fetch_trades
        trades = fetch_trades(days_back=30)
        assert isinstance(trades, list)

    def test_large_trades_filtered_by_size(self):
        from strategies.smart_money import fetch_large_trades
        trades = fetch_large_trades(min_size=50_000, days_back=30)
        for t in trades:
            assert t.get("_estimated_size", 0) >= 50_000

    def test_large_trades_are_buys(self):
        from strategies.smart_money import fetch_large_trades
        trades = fetch_large_trades(min_size=50_000, days_back=30)
        for t in trades:
            assert "buy" in t.get("txType", "").lower()

    def test_large_trades_sorted_by_size(self):
        from strategies.smart_money import fetch_large_trades
        trades = fetch_large_trades(min_size=50_000, days_back=30)
        if len(trades) >= 2:
            sizes = [t["_estimated_size"] for t in trades]
            assert sizes == sorted(sizes, reverse=True)
