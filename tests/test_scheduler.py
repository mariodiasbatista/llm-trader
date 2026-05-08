"""Tests for scheduler/market_scheduler.py — portfolio command, daily summary,
market-hours gate, wheel runner, ladder alert forwarding, and poll edge cases."""
import pytest
from unittest.mock import patch, MagicMock, call


# ── Shared helpers ────────────────────────────────────────────────────────────

def _mock_account(portfolio=98000.0, cash=57000.0, buying_power=155000.0,
                  equity=98000.0, last_equity=98200.0):
    acct = MagicMock()
    acct.portfolio_value = str(portfolio)
    acct.cash = str(cash)
    acct.buying_power = str(buying_power)
    acct.equity = str(equity)
    acct.last_equity = str(last_equity)
    return acct


def _mock_position(symbol, qty, avg_entry, current, total_pl, total_plpc,
                   intraday_pl, intraday_plpc):
    pos = MagicMock()
    pos.symbol = symbol
    pos.qty = str(qty)
    pos.avg_entry_price = str(avg_entry)
    pos.current_price = str(current)
    pos.unrealized_pl = str(total_pl)
    pos.unrealized_plpc = str(total_plpc)
    pos.unrealized_intraday_pl = str(intraday_pl)
    pos.unrealized_intraday_plpc = str(intraday_plpc)
    return pos


def _base_state():
    return {"positions": {}, "wheel": {}, "copied_trades": []}


# ── is_market_open ────────────────────────────────────────────────────────────

class TestIsMarketOpen:
    def test_returns_false_on_saturday(self):
        from datetime import datetime
        import pytz
        ny = pytz.timezone("America/New_York")
        saturday = datetime(2026, 5, 9, 12, 0, 0, tzinfo=ny)
        with patch("scheduler.market_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(weekday=lambda: 5)
            from scheduler.market_scheduler import is_market_open
            assert is_market_open() is False

    def test_returns_false_on_sunday(self):
        with patch("scheduler.market_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(weekday=lambda: 6)
            from scheduler.market_scheduler import is_market_open
            assert is_market_open() is False


# ── _run_trailing_stop / _run_wheel — market-closed gate ─────────────────────

class TestMarketClosedGate:
    @patch("strategies.trailing_stop.check_and_update")
    @patch("scheduler.market_scheduler.is_market_open", return_value=False)
    def test_trailing_stop_skipped_when_market_closed(self, _open, mock_check):
        from scheduler.market_scheduler import _run_trailing_stop
        _run_trailing_stop()
        mock_check.assert_not_called()

    @patch("strategies.wheel.check_and_manage")
    @patch("scheduler.market_scheduler.is_market_open", return_value=False)
    def test_wheel_skipped_when_market_closed(self, _open, mock_manage):
        from scheduler.market_scheduler import _run_wheel
        _run_wheel()
        mock_manage.assert_not_called()


# ── _run_trailing_stop — ladder alert forwarding ──────────────────────────────

class TestRunTrailingStopLadderAlert:
    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.trailing_stop.check_and_update")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_ladder_alert_sent_when_laddered(self, _open, mock_check, _cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_check.return_value = {
            "checked": [],
            "stopped_out": [],
            "laddered": [{"symbol": "TSLA", "qty": 10, "price": 200.0}],
        }
        from scheduler.market_scheduler import _run_trailing_stop
        _run_trailing_stop()

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("TSLA" in t for t in sent)
        notifier._telegram_log_level = 2


# ── _run_wheel ────────────────────────────────────────────────────────────────

class TestRunWheel:
    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.wheel.check_and_manage")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_wheel_actions_forwarded_to_telegram(self, _open, mock_manage, _cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_manage.return_value = {"actions": ["AAPL: Stage 1→2 | sold call @ $155"]}

        from scheduler.market_scheduler import _run_wheel
        _run_wheel()

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("Stage 1→2" in t for t in sent)
        notifier._telegram_log_level = 2

    @patch("strategies.wheel.check_and_manage")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_wheel_no_error_on_empty_actions(self, _open, mock_manage):
        mock_manage.return_value = {"actions": []}
        from scheduler.market_scheduler import _run_wheel
        _run_wheel()  # must not raise


# ── _run_portfolio ────────────────────────────────────────────────────────────

class TestRunPortfolio:
    def _run(self, positions, state=None, acct=None):
        if acct is None:
            acct = _mock_account()
        if state is None:
            state = _base_state()
        with patch("core.alpaca.get_account", return_value=acct), \
             patch("core.alpaca.get_positions", return_value=positions), \
             patch("core.logger.load_state", return_value=state), \
             patch("core.notifier.send_message") as mock_send:
            from scheduler.market_scheduler import _run_portfolio
            _run_portfolio()
            return mock_send.call_args[0][0]

    def test_sends_portfolio_value(self):
        text = self._run([], acct=_mock_account(portfolio=98174.34))
        assert "98,174.34" in text

    def test_sends_cash(self):
        text = self._run([], acct=_mock_account(cash=57366.61))
        assert "57,366.61" in text

    def test_sends_buying_power(self):
        text = self._run([], acct=_mock_account(buying_power=155540.95))
        assert "155,540.95" in text

    def test_positive_day_pnl_shows_green_icon(self):
        acct = _mock_account(equity=99000.0, last_equity=98000.0)
        text = self._run([], acct=acct)
        assert "🟢" in text

    def test_negative_day_pnl_shows_red_icon(self):
        acct = _mock_account(equity=97000.0, last_equity=98000.0)
        text = self._run([], acct=acct)
        assert "🔴" in text

    def test_no_positions_shows_placeholder(self):
        text = self._run([])
        assert "No open positions" in text

    def test_position_symbol_shown(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006)
        text = self._run([pos])
        assert "GE" in text

    def test_position_entry_and_current_price_shown(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006)
        text = self._run([pos])
        assert "283.98" in text
        assert "300.73" in text

    def test_position_total_pnl_shown(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006)
        text = self._run([pos])
        assert "+519.00" in text or "+$519" in text

    def test_stop_floor_shown_when_present(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006)
        state = {"positions": {"GE": {"stop_floor": 274.90}}, "wheel": {}, "copied_trades": []}
        text = self._run([pos], state=state)
        assert "274.90" in text

    def test_stop_floor_omitted_when_absent(self):
        pos = _mock_position("RH", 65, 133.41, 134.05, 41.6, 0.0048, 26.0, 0.003)
        text = self._run([pos])
        assert "Stop" not in text

    def test_multiple_positions_all_shown(self):
        positions = [
            _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006),
            _mock_position("ULTA", 20, 528.13, 526.68, -29.0, -0.003, 3.0, 0.0003),
        ]
        text = self._run(positions)
        assert "GE" in text
        assert "ULTA" in text

    def test_losing_position_shows_red_icon(self):
        pos = _mock_position("TDG", 10, 1252.86, 1223.83, -290.0, -0.023, -182.0, -0.015)
        text = self._run([pos])
        assert "🔴" in text

    def test_winning_position_shows_green_icon(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, 10.0, 0.001)
        text = self._run([pos])
        assert "🟢" in text


# ── _run_daily_summary ────────────────────────────────────────────────────────

class TestRunDailySummary:
    def _run(self, positions, state=None, acct=None, log_level=2):
        import core.notifier as notifier
        notifier._telegram_log_level = log_level
        if acct is None:
            acct = _mock_account()
        if state is None:
            state = _base_state()
        with patch("core.alpaca.get_account", return_value=acct), \
             patch("core.alpaca.get_positions", return_value=positions), \
             patch("core.logger.load_state", return_value=state), \
             patch("core.notifier.send_message") as mock_send:
            from scheduler.market_scheduler import _run_daily_summary
            _run_daily_summary()
            notifier._telegram_log_level = 2
            return mock_send

    def test_sends_summary_message(self):
        mock_send = self._run([])
        assert mock_send.called

    def test_contains_portfolio_value(self):
        acct = _mock_account(portfolio=98174.34)
        mock_send = self._run([], acct=acct)
        text = mock_send.call_args[0][0]
        assert "98,174.34" in text

    def test_position_lines_included(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006)
        mock_send = self._run([pos])
        text = mock_send.call_args[0][0]
        assert "GE" in text

    def test_floor_shown_in_summary(self):
        pos = _mock_position("GE", 31, 283.98, 300.73, 519.0, 0.059, -59.0, -0.006)
        state = {"positions": {"GE": {"stop_floor": 274.90}}, "wheel": {}, "copied_trades": []}
        mock_send = self._run([pos], state=state)
        text = mock_send.call_args[0][0]
        assert "274.90" in text

    def test_suppressed_at_level_3(self):
        """send_summary respects log level — nothing sent at level 3."""
        mock_send = self._run([], log_level=3)
        assert not mock_send.called

    def test_suppressed_at_level_0(self):
        mock_send = self._run([], log_level=0)
        assert not mock_send.called


# ── _poll_telegram — WHEEL strategy and unknown key ──────────────────────────

class TestPollTelegramEdgeCases:
    def _make_pending(self, strategy="TRAILING_STOP"):
        return {
            "pending_trades": {
                "2026-05-08_AAPL_P001": {
                    "ticker": "AAPL",
                    "strategy": strategy,
                    "confidence": 80,
                    "reasoning": "stable",
                    "price": 150.0,
                    "politician": "Pelosi",
                    "position_pct": 0.05,
                    "stop_floor": None,
                }
            },
            "positions": {},
            "wheel": {},
            "copied_trades": [],
        }

    def _approve_update(self, trade_key="2026-05-08_AAPL_P001"):
        return {
            "update_id": 1,
            "callback_query": {
                "id": "cb1",
                "data": f"approve:{trade_key}",
                "message": {"message_id": 1},
            },
        }

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_unknown_trade_key_logs_without_crashing(
        self, mock_cfg, mock_post, mock_send, mock_acct, mock_load, mock_save
    ):
        """Callback for a trade_key not in pending_trades must not raise."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_acct.return_value = _mock_account()
        mock_load.return_value = {"pending_trades": {}, "positions": {}, "wheel": {}, "copied_trades": []}
        mock_post.side_effect = [
            {"result": [self._approve_update("nonexistent_key")]},
            {},
            {},
        ]
        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()  # must not raise

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("strategies.wheel.start_wheel")
    @patch("core.alpaca.get_latest_price", return_value=150.0)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_wheel_strategy_calls_start_wheel(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_wheel, mock_load, mock_save
    ):
        """Approving a WHEEL trade calls start_wheel."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_acct.return_value = _mock_account(buying_power=50000.0)
        mock_load.return_value = self._make_pending(strategy="WHEEL")
        mock_wheel.return_value = {"put_strike": 142.0}
        mock_post.side_effect = [
            {"result": [self._approve_update()]},
            {},
            {},
        ]
        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()
        mock_wheel.assert_called_once_with("AAPL", contracts=1)
