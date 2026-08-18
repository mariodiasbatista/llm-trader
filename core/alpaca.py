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


import uuid

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
    GetOptionContractsRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, ContractType
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import (
    StockLatestQuoteRequest,
    StockBarsRequest,
    OptionLatestQuoteRequest,
)
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


def _option_data_client() -> OptionHistoricalDataClient:
    c = _creds()["alpaca"]
    return OptionHistoricalDataClient(api_key=c["api_key"], secret_key=c["secret_key"])


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


def _order_id(label: str) -> str:
    return f"llmTrader-{label}-{uuid.uuid4().hex[:8]}"


def _wait_for_fill(order, timeout: float = 15.0, interval: float = 1.0):
    """Poll until the order fills or the timeout elapses.

    Market orders placed during regular trading hours typically fill within
    a few seconds; outside market hours they sit as "accepted" until the
    next open, so the timeout is expected to be hit in that case — callers
    must check order.filled_avg_price is not None before trusting the fill.
    """
    import time
    client = _trading_client()
    deadline = time.monotonic() + timeout
    while order.filled_avg_price is None and time.monotonic() < deadline:
        time.sleep(interval)
        order = client.get_order_by_id(order.id)
    return order


def market_buy(symbol: str, qty: float):
    _debug(f"[alpaca] market_buy {symbol} x{qty}")
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=_order_id(f"buy-{symbol}"),
    )
    result = _wait_for_fill(_trading_client().submit_order(order))
    _debug(f"[alpaca] order submitted id={result.id} status={result.status} filled_avg_price={result.filled_avg_price}")
    return result


def market_sell(symbol: str, qty: float):
    _debug(f"[alpaca] market_sell {symbol} x{qty}")
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        client_order_id=_order_id(f"sell-{symbol}"),
    )
    result = _wait_for_fill(_trading_client().submit_order(order))
    _debug(f"[alpaca] order submitted id={result.id} status={result.status} filled_avg_price={result.filled_avg_price}")
    return result


def close_position(symbol: str):
    """Sell entire position at market."""
    return _wait_for_fill(_trading_client().close_position(symbol))


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
        client_order_id=_order_id(f"trail-{symbol}"),
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
    side_label = "buy" if side == OrderSide.BUY else "sell"
    order = MarketOrderRequest(
        symbol=option_symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        client_order_id=_order_id(f"opt-{side_label}-{option_symbol[:6]}"),
    )
    result = _wait_for_fill(_trading_client().submit_order(order))
    _debug(f"[alpaca] option order submitted id={result.id} status={result.status} filled_avg_price={result.filled_avg_price}")
    return result


def close_option_position(option_symbol: str, qty: int):
    """
    Buy-to-close a short option position. WHEEL only ever sells to open
    (cash-secured puts / covered calls), so closing always means buying back.
    """
    order = MarketOrderRequest(
        symbol=option_symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=_order_id(f"opt-close-{option_symbol[:6]}"),
    )
    result = _wait_for_fill(_trading_client().submit_order(order))
    _debug(f"[alpaca] option close submitted id={result.id} status={result.status} filled_avg_price={result.filled_avg_price}")
    return result


def find_option_contract(symbol: str, target_expiry, option_type: str, target_strike: float, days_tolerance: int = 21):
    """
    Find the real listed option contract nearest to (target_expiry, target_strike).

    Naively rounding a target strike to the nearest whole dollar and guessing an
    expiry Friday builds an OCC symbol that frequently doesn't correspond to any
    actual listed contract — many underlyings only list strikes in $2.50/$5/$10
    increments, and not every Friday is a valid expiration for every ticker.
    Querying Alpaca's contract reference data and snapping to what's actually
    listed avoids constructing a symbol for a contract that was never listed.

    Returns (occ_symbol, strike, expiration_date) for the nearest real expiration
    on/after target_expiry (within days_tolerance) and the strike closest to
    target_strike within that expiration, or None if nothing is listed at all
    in that window (e.g. the underlying has no options market).
    """
    target_date = target_expiry.date() if hasattr(target_expiry, "date") else target_expiry
    req = GetOptionContractsRequest(
        underlying_symbols=[symbol],
        type=ContractType.PUT if option_type == "put" else ContractType.CALL,
        expiration_date_gte=target_date.isoformat(),
        expiration_date_lte=(target_date + timedelta(days=days_tolerance)).isoformat(),
        limit=1000,
    )
    try:
        resp = _trading_client().get_option_contracts(req)
    except Exception as e:
        _debug(f"[alpaca] option contract lookup failed for {symbol}: {e}")
        return None

    contracts = resp.option_contracts or []
    if not contracts:
        return None

    nearest_expiry = min(c.expiration_date for c in contracts)
    same_expiry = [c for c in contracts if c.expiration_date == nearest_expiry]
    best = min(same_expiry, key=lambda c: abs(float(c.strike_price) - target_strike))
    return best.symbol, float(best.strike_price), nearest_expiry


def get_option_mid_price(option_symbol: str) -> float:
    """Return bid/ask midpoint for an option contract. Returns 0.0 if unavailable."""
    try:
        req = OptionLatestQuoteRequest(symbol_or_symbols=option_symbol)
        quote = _option_data_client().get_option_latest_quote(req)
        q = quote[option_symbol]
        ask = float(q.ask_price or 0)
        bid = float(q.bid_price or 0)
        if ask and bid:
            return (ask + bid) / 2
        return ask or bid
    except Exception:
        return 0.0


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


def get_bars_range(symbol: str, start, end):
    """Daily bars for an explicit historical [start, end] window — used by backtest/replay.py."""
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    bars = _data_client().get_stock_bars(req)
    return bars[symbol] if symbol in bars.data else []


def get_sma(symbol: str, days: int = 20) -> float | None:
    """Trailing simple moving average of daily closes, for the live trend filter."""
    bars = get_bars(symbol, days=days * 3)  # buffer for weekends/holidays
    closes = [float(b.close) for b in bars]
    if len(closes) < days:
        return None
    return sum(closes[-days:]) / days
