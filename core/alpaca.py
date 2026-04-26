"""Alpaca API wrapper — all market data and order execution flows through here."""
import json
from pathlib import Path
from datetime import datetime, timedelta

from core.logger import log


def _debug(msg: str) -> None:
    """Log at debug severity to Telegram when level=1."""
    try:
        from core.notifier import tlog
        tlog(msg, 1)
    except Exception:
        log.debug(msg)


from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"


def _creds():
    if not CREDS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json not found. Copy credentials.json.example and fill in your keys."
        )
    with open(CREDS_FILE) as f:
        return json.load(f)


def _trading_client() -> TradingClient:
    c = _creds()["alpaca"]
    return TradingClient(
        api_key=c["api_key"],
        secret_key=c["secret_key"],
        paper=c.get("paper", True),
    )


def _data_client() -> StockHistoricalDataClient:
    c = _creds()["alpaca"]
    return StockHistoricalDataClient(api_key=c["api_key"], secret_key=c["secret_key"])


# ── Account ────────────────────────────────────────────────────────────────


def get_account():
    acct = _trading_client().get_account()
    _debug(
        f"[alpaca] account: equity=${float(acct.equity):,.2f} "
        f"cash=${float(acct.cash):,.2f} bp=${float(acct.buying_power):,.2f}"
    )
    return acct


def get_positions():
    positions = _trading_client().get_all_positions()
    _debug(f"[alpaca] positions: {[p.symbol for p in positions]}")
    return positions


def get_position(symbol: str):
    try:
        return _trading_client().get_open_position(symbol)
    except Exception:
        return None


# ── Orders ─────────────────────────────────────────────────────────────────


def market_buy(symbol: str, qty: float):
    _debug(f"[alpaca] market_buy {symbol} x{qty}")
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    result = _trading_client().submit_order(order)
    _debug(f"[alpaca] order submitted id={result.id} status={result.status}")
    return result


def market_sell(symbol: str, qty: float):
    _debug(f"[alpaca] market_sell {symbol} x{qty}")
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    result = _trading_client().submit_order(order)
    _debug(f"[alpaca] order submitted id={result.id} status={result.status}")
    return result


def close_position(symbol: str):
    """Sell entire position at market."""
    return _trading_client().close_position(symbol)


def trailing_stop_sell(symbol: str, qty: float, trail_percent: float):
    """Place a native Alpaca trailing stop sell order (GTC).

    Executes at the broker level instantly when price drops trail_percent%
    from its peak — no polling needed.
    trail_percent: e.g. 5.0 for a 5% trailing stop
    """
    order = TrailingStopOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
        trail_percent=trail_percent,
    )
    return _trading_client().submit_order(order)


def get_open_orders():
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
    return _trading_client().get_orders(req)


# ── Options (Wheel strategy) ───────────────────────────────────────────────


def submit_option_order(option_symbol: str, qty: int, side: OrderSide):
    """
    Submit a market option order.
    option_symbol must be in OCC format: AAPL240315C00150000
    Requires options trading approval on your Alpaca account.
    """
    order = MarketOrderRequest(
        symbol=option_symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    return _trading_client().submit_order(order)


# ── Market data ────────────────────────────────────────────────────────────


def get_latest_price(symbol: str) -> float:
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    quote = _data_client().get_stock_latest_quote(req)
    ask = quote[symbol].ask_price
    bid = quote[symbol].bid_price
    price = float((ask + bid) / 2) if ask and bid else float(ask or bid)
    _debug(f"[alpaca] {symbol} price=${price:.2f} (ask={ask} bid={bid})")
    return price


def get_bars(symbol: str, days: int = 30):
    end = datetime.now()
    start = end - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    return _data_client().get_stock_bars(req)[symbol]
