"""Tests for trailing_stop.py — stop floor logic and ladder buys."""
import pytest
from unittest.mock import patch, MagicMock


def _make_position(symbol, current_price, avg_entry, qty=10):
    pos = MagicMock()
    pos.symbol = symbol
    pos.current_price = str(current_price)
    pos.avg_entry_price = str(avg_entry)
    pos.qty = str(qty)
    return pos


SETTINGS = {
    "trailing_stop": {
        "enabled": True,
        "initial_stop_pct": 0.10,
        "trailing_pct": 0.05,
        "ladder_buys": [
            {"drop_pct": 0.20, "shares": 10},
            {"drop_pct": 0.30, "shares": 20},
        ],
    }
}


class TestTrailingStopLogic:
    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state", return_value={"positions": {}, "wheel": {}, "copied_trades": []})
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_new_position_initializes_floor(self, mock_settings, mock_positions, mock_load, mock_save):
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 100.0, 95.0)]

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        assert len(result["checked"]) == 1
        pos = result["checked"][0]
        assert pos["symbol"] == "AAPL"
        # Initial floor = 100 * (1 - 0.10) = 90.0
        assert abs(pos["floor"] - 90.0) < 0.01

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.close_position")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_stop_triggered_when_price_below_floor(
        self, mock_settings, mock_positions, mock_log, mock_close, mock_load, mock_save
    ):
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 88.0, 100.0)]
        mock_load.return_value = {
            "positions": {
                "AAPL": {
                    "high_water_mark": 100.0,
                    "stop_floor": 90.0,   # price 88 < floor 90 → stop triggered
                    "entry_price": 100.0,
                    "ladder_triggered": [],
                }
            },
            "wheel": {},
            "copied_trades": [],
        }

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_close.assert_called_once_with("AAPL")
        assert "AAPL" in result["stopped_out"]

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_floor_rises_with_new_high(
        self, mock_settings, mock_positions, mock_load, mock_save
    ):
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("NVDA", 120.0, 100.0)]
        mock_load.return_value = {
            "positions": {
                "NVDA": {
                    "high_water_mark": 110.0,   # new high is 120
                    "stop_floor": 104.5,         # 110 * 0.95
                    "entry_price": 100.0,
                    "ladder_triggered": [],
                }
            },
            "wheel": {},
            "copied_trades": [],
        }

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        saved_state = mock_save.call_args[0][0]
        new_floor = saved_state["positions"]["NVDA"]["stop_floor"]
        # New floor should be 120 * 0.95 = 114.0
        assert abs(new_floor - 114.0) < 0.01
        new_hwm = saved_state["positions"]["NVDA"]["high_water_mark"]
        assert new_hwm == 120.0

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.market_buy")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_account")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_ladder_buy_triggered_at_20pct_drop(
        self, mock_settings, mock_positions, mock_acct, mock_log, mock_buy, mock_load, mock_save
    ):
        mock_settings.return_value = SETTINGS["trailing_stop"]
        # entry=100, current=79 → 21% drop → triggers 20% ladder
        mock_positions.return_value = [_make_position("TSLA", 79.0, 100.0)]
        mock_acct.return_value.buying_power = "10000.0"
        mock_load.return_value = {
            "positions": {
                "TSLA": {
                    "high_water_mark": 100.0,
                    "stop_floor": 70.0,          # price 79 > floor 70 — not stopped
                    "entry_price": 100.0,
                    "ladder_triggered": [],
                }
            },
            "wheel": {},
            "copied_trades": [],
        }

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_buy.assert_called_once_with("TSLA", 10)   # first ladder: 10 shares
        assert len(result["laddered"]) == 1
        assert result["laddered"][0]["symbol"] == "TSLA"

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.close_position")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_floor_does_not_drop(
        self, mock_settings, mock_positions, mock_log, mock_close, mock_load, mock_save
    ):
        """When price drops below the existing floor, stop fires — floor never lowers."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 95.0, 100.0)]
        mock_load.return_value = {
            "positions": {
                "AAPL": {
                    "high_water_mark": 110.0,
                    "stop_floor": 104.5,   # 95 < 104.5 → stop fires
                    "entry_price": 100.0,
                    "ladder_triggered": [],
                }
            },
            "wheel": {},
            "copied_trades": [],
        }

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_close.assert_called_once_with("AAPL")
        assert "AAPL" in result["stopped_out"]
