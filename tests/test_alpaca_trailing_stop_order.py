"""Tests for trailing_stop_sell() in core/alpaca.py."""
import pytest
from unittest.mock import patch, MagicMock, call
from alpaca.trading.enums import OrderSide, TimeInForce


class TestTrailingStopSell:
    @patch("core.alpaca._trading_client")
    def test_submits_trailing_stop_order(self, mock_client):
        from core.alpaca import trailing_stop_sell
        mock_tc = MagicMock()
        mock_client.return_value = mock_tc

        trailing_stop_sell("AAPL", 10, 5.0)

        mock_tc.submit_order.assert_called_once()
        order = mock_tc.submit_order.call_args[0][0]
        assert order.symbol == "AAPL"
        assert order.qty == 10
        assert order.side == OrderSide.SELL
        assert order.time_in_force == TimeInForce.GTC
        assert order.trail_percent == 5.0

    @patch("core.alpaca._trading_client")
    def test_uses_gtc_time_in_force(self, mock_client):
        from core.alpaca import trailing_stop_sell
        mock_tc = MagicMock()
        mock_client.return_value = mock_tc

        trailing_stop_sell("NVDA", 5, 10.0)

        order = mock_tc.submit_order.call_args[0][0]
        assert order.time_in_force == TimeInForce.GTC

    @patch("core.alpaca._trading_client")
    def test_trail_percent_passed_correctly(self, mock_client):
        from core.alpaca import trailing_stop_sell
        mock_tc = MagicMock()
        mock_client.return_value = mock_tc

        trailing_stop_sell("TSLA", 1, 7.5)

        order = mock_tc.submit_order.call_args[0][0]
        assert order.trail_percent == 7.5

    @patch("core.alpaca._trading_client")
    def test_returns_order_response(self, mock_client):
        from core.alpaca import trailing_stop_sell
        mock_tc = MagicMock()
        mock_order = MagicMock()
        mock_tc.submit_order.return_value = mock_order
        mock_client.return_value = mock_tc

        result = trailing_stop_sell("AAPL", 10, 5.0)

        assert result == mock_order
