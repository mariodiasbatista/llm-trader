"""Tests for trailing_stop.py — profit-target-activated stop floor and ladder buys."""
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
        "take_profit_pct": 0.20,
        "profit_target_pct": 0.10,
        "trailing_pct_from_profit": 0.05,
        "ladder_buys": [
            {"drop_pct": 0.20, "shares": 10},
            {"drop_pct": 0.30, "shares": 20},
        ],
    }
}

SETTINGS_PROFIT_TARGET = {
    "trailing_stop": {
        **SETTINGS["trailing_stop"],
        "initial_stop_pct": 0,
    }
}

def _base_state():
    return {"positions": {}, "wheel": {}, "copied_trades": []}

def _state_with(symbol, floor, hwm, entry, profit_stop_active=True):
    return {
        "positions": {
            symbol: {
                "high_water_mark": hwm,
                "stop_floor": floor,
                "entry_price": entry,
                "ladder_triggered": [],
                "profit_stop_active": profit_stop_active,
            }
        },
        "wheel": {},
        "copied_trades": [],
    }


class TestTrailingStopLogic:
    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state", side_effect=_base_state)
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_new_position_initializes_floor(self, mock_settings, mock_positions, mock_load, mock_save):
        """Classic mode: new position gets floor set immediately at entry - 10%."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 100.0, 95.0)]

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        assert len(result["checked"]) == 1
        pos = result["checked"][0]
        assert pos["symbol"] == "AAPL"
        # Classic mode: floor = 100 * (1 - 0.10) = 90.0
        assert abs(pos["floor"] - 90.0) < 0.01
        assert pos["profit_stop_active"] is True

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state", side_effect=_base_state)
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_new_position_waits_for_profit_target(self, mock_settings, mock_positions, mock_load, mock_save):
        """Profit-target mode: new position starts with floor=0, waiting."""
        mock_settings.return_value = SETTINGS_PROFIT_TARGET["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 100.0, 95.0)]

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        pos = result["checked"][0]
        assert pos["floor"] == 0.0
        assert pos["profit_stop_active"] is False

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_profit_target_activates_stop(self, mock_settings, mock_positions, mock_load, mock_save):
        """Profit-target mode: when price reaches +10% from entry, stop activates."""
        mock_settings.return_value = SETTINGS_PROFIT_TARGET["trailing_stop"]
        # entry=100, price=111 → +11% gain → crosses 10% target
        mock_positions.return_value = [_make_position("AAPL", 111.0, 100.0)]
        mock_load.return_value = _state_with("AAPL", 0.0, 100.0, 100.0, profit_stop_active=False)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        saved = mock_save.call_args[0][0]
        ps = saved["positions"]["AAPL"]
        assert ps["profit_stop_active"] is True
        # Floor = 111 * (1 - 0.05) = 105.45
        assert abs(ps["stop_floor"] - 105.45) < 0.01

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.close_position")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_stop_triggered_when_price_below_floor(
        self, mock_settings, mock_positions, mock_log, mock_close, mock_load, mock_save
    ):
        """Stop fires when price drops below floor and profit_stop_active=True."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 88.0, 100.0)]
        mock_load.return_value = _state_with("AAPL", 90.0, 100.0, 100.0, profit_stop_active=True)

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
        """Floor trails upward when profit_stop_active=True and price sets a new high."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("NVDA", 120.0, 100.0)]
        mock_load.return_value = _state_with("NVDA", 104.5, 110.0, 100.0, profit_stop_active=True)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        saved_state = mock_save.call_args[0][0]
        new_floor = saved_state["positions"]["NVDA"]["stop_floor"]
        # New floor = 120 * (1 - 0.05) = 114.0
        assert abs(new_floor - 114.0) < 0.01
        assert saved_state["positions"]["NVDA"]["high_water_mark"] == 120.0

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
        """Ladder buy fires at 20% drop from entry regardless of stop state."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        # entry=100, current=79 → 21% drop → triggers 20% ladder
        mock_positions.return_value = [_make_position("TSLA", 79.0, 100.0)]
        mock_acct.return_value.buying_power = "10000.0"
        mock_load.return_value = _state_with("TSLA", 0.0, 100.0, 100.0, profit_stop_active=False)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_buy.assert_called_once_with("TSLA", 10)
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
        """Floor never lowers — if price drops below active floor, stop fires."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 95.0, 100.0)]
        mock_load.return_value = _state_with("AAPL", 104.5, 110.0, 100.0, profit_stop_active=True)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_close.assert_called_once_with("AAPL")
        assert "AAPL" in result["stopped_out"]

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.close_position")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_take_profit_fires_at_target(
        self, mock_settings, mock_positions, mock_log, mock_close, mock_load, mock_save
    ):
        """Take-profit closes position immediately when gain_pct hits take_profit_pct."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        # entry=100, price=122 → +22% → above 20% take_profit_pct
        mock_positions.return_value = [_make_position("AAPL", 122.0, 100.0)]
        mock_load.return_value = _state_with("AAPL", 103.0, 115.0, 100.0, profit_stop_active=True)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_close.assert_called_once_with("AAPL")
        assert "AAPL" in result["stopped_out"]
        log_call = mock_log.call_args[0]
        assert log_call[0] == "TAKE_PROFIT"

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.close_position")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_take_profit_not_triggered_below_target(
        self, mock_settings, mock_positions, mock_log, mock_close, mock_load, mock_save
    ):
        """Take-profit does not fire when gain is below target."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        # entry=100, price=115 → +15% → below 20% take_profit_pct
        mock_positions.return_value = [_make_position("AAPL", 115.0, 100.0)]
        mock_load.return_value = _state_with("AAPL", 103.0, 115.0, 100.0, profit_stop_active=True)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_close.assert_not_called()
        assert "AAPL" not in result["stopped_out"]
