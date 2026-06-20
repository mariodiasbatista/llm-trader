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


class TestTrailingStopInputGuards:
    """Positions with zero or negative entry/price are skipped without crashing."""

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state", side_effect=_base_state)
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_zero_entry_price_skips_position(self, mock_settings, mock_positions, mock_load, mock_save):
        """A position with avg_entry_price=0 must not cause division by zero."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 100.0, 0.0)]

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        assert result["checked"] == []
        assert result["stopped_out"] == []
        assert result["laddered"] == []

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state", side_effect=_base_state)
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_zero_current_price_skips_position(self, mock_settings, mock_positions, mock_load, mock_save):
        """A position with current_price=0 must not cause division by zero."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 0.0, 100.0)]

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        assert result["checked"] == []
        assert result["stopped_out"] == []

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state", side_effect=_base_state)
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_valid_position_processed_alongside_bad_entry(self, mock_settings, mock_positions, mock_load, mock_save):
        """A zero-entry position is skipped but valid positions in the same batch are still processed."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [
            _make_position("BAD", 100.0, 0.0),
            _make_position("GOOD", 100.0, 90.0),
        ]

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        assert len(result["checked"]) == 1
        assert result["checked"][0]["symbol"] == "GOOD"


class TestTrailingStopExceptionHandlers:
    """Stop-sell failures and ladder-buy insufficient-funds paths."""

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.close_position", side_effect=RuntimeError("order rejected"))
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_stop_sell_exception_does_not_crash(
        self, mock_settings, mock_positions, mock_log, mock_close, mock_load, mock_save
    ):
        """If close_position raises, the scheduler loop must not crash."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("AAPL", 88.0, 100.0)]
        mock_load.return_value = _state_with("AAPL", 90.0, 100.0, 100.0, profit_stop_active=True)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()  # must not raise

        # Position was not removed from stopped_out because close failed
        # but the loop completed
        assert isinstance(result, dict)

    @patch("strategies.trailing_stop.telegram_configured", return_value=False)
    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.market_buy")
    @patch("strategies.trailing_stop.log_trade")
    @patch("strategies.trailing_stop.get_account")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_ladder_buy_skipped_on_insufficient_funds(
        self, mock_settings, mock_positions, mock_acct, mock_log, mock_buy, mock_load, mock_save, mock_tg
    ):
        """Ladder buy does not execute when buying_power < cost."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("TSLA", 79.0, 100.0)]
        mock_acct.return_value.buying_power = "50.0"  # far too little
        mock_load.return_value = _state_with("TSLA", 0.0, 100.0, 100.0, profit_stop_active=False)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()

        mock_buy.assert_not_called()
        assert result["laddered"] == []

    @patch("strategies.trailing_stop.send_insufficient_funds_alert")
    @patch("strategies.trailing_stop.telegram_configured", return_value=True)
    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.market_buy")
    @patch("strategies.trailing_stop.get_account")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_insufficient_funds_alert_sent(
        self, mock_settings, mock_positions, mock_acct, mock_buy,
        mock_load, mock_save, mock_cfg, mock_alert
    ):
        """send_insufficient_funds_alert is called when ladder buy can't afford shares."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("TSLA", 79.0, 100.0)]
        mock_acct.return_value.buying_power = "50.0"
        mock_load.return_value = _state_with("TSLA", 0.0, 100.0, 100.0, profit_stop_active=False)

        from strategies.trailing_stop import check_and_update
        check_and_update()

        mock_alert.assert_called_once()
        assert mock_alert.call_args[0][0] == "TSLA"

    @patch("strategies.trailing_stop.save_state")
    @patch("strategies.trailing_stop.load_state")
    @patch("strategies.trailing_stop.market_buy", side_effect=RuntimeError("order failed"))
    @patch("strategies.trailing_stop.get_account")
    @patch("strategies.trailing_stop.get_positions")
    @patch("strategies.trailing_stop._settings")
    def test_ladder_buy_exception_does_not_crash(
        self, mock_settings, mock_positions, mock_acct, mock_buy, mock_load, mock_save
    ):
        """If market_buy raises during a ladder buy, the loop continues without crashing."""
        mock_settings.return_value = SETTINGS["trailing_stop"]
        mock_positions.return_value = [_make_position("TSLA", 79.0, 100.0)]
        mock_acct.return_value.buying_power = "10000.0"
        mock_load.return_value = _state_with("TSLA", 0.0, 100.0, 100.0, profit_stop_active=False)

        from strategies.trailing_stop import check_and_update
        result = check_and_update()  # must not raise
        assert isinstance(result, dict)


# ── Stop-out cooldown recording ───────────────────────────────────────────────

class TestStopOutCooldownRecording:
    """After a STOP_SELL fires, trailing_stop records the date in state['stopped_out']."""

    def _patched_run(self, initial_state):
        from strategies.trailing_stop import check_and_update
        with patch("strategies.trailing_stop._settings", return_value=SETTINGS["trailing_stop"]), \
             patch("strategies.trailing_stop.get_positions",
                   return_value=[_make_position("MSFT", 88.0, 100.0)]), \
             patch("strategies.trailing_stop.log_trade"), \
             patch("strategies.trailing_stop.close_position"), \
             patch("strategies.trailing_stop.load_state", return_value=initial_state), \
             patch("strategies.trailing_stop.save_state") as mock_save:
            check_and_update()
        return mock_save.call_args[0][0]

    def test_stop_out_date_recorded_in_state(self):
        """When a stop fires, today's date is saved under state['stopped_out'][symbol]."""
        from datetime import datetime
        state = _state_with("MSFT", 90.0, 100.0, 100.0, profit_stop_active=True)
        saved = self._patched_run(state)
        assert "stopped_out" in saved
        assert "MSFT" in saved["stopped_out"]
        assert saved["stopped_out"]["MSFT"] == datetime.now().strftime("%Y-%m-%d")

    def test_stop_out_does_not_overwrite_other_tickers(self):
        """Recording a stop-out for one ticker leaves other stopped_out entries intact."""
        from datetime import datetime
        state = _state_with("MSFT", 90.0, 100.0, 100.0, profit_stop_active=True)
        state["stopped_out"] = {"AAPL": "2026-06-08"}
        saved = self._patched_run(state)
        assert saved["stopped_out"]["AAPL"] == "2026-06-08"
        assert "MSFT" in saved["stopped_out"]

    def test_no_stop_out_recorded_when_floor_not_breached(self):
        """When the price is above the floor, no stopped_out entry is written."""
        state = _state_with("MSFT", 85.0, 100.0, 100.0, profit_stop_active=True)
        with patch("strategies.trailing_stop._settings", return_value=SETTINGS["trailing_stop"]), \
             patch("strategies.trailing_stop.get_positions",
                   return_value=[_make_position("MSFT", 90.0, 100.0)]), \
             patch("strategies.trailing_stop.load_state", return_value=state), \
             patch("strategies.trailing_stop.save_state") as mock_save:
            from strategies.trailing_stop import check_and_update
            check_and_update()
        saved = mock_save.call_args[0][0]
        assert saved.get("stopped_out", {}).get("MSFT") is None
