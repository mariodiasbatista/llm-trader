"""Tests for scheduler/market_scheduler.py — portfolio command, daily summary,
market-hours gate, wheel runner, ladder alert forwarding, and poll edge cases."""
import pytest
from datetime import datetime as real_dt
import pytz
from unittest.mock import patch, MagicMock, call

_NY = pytz.timezone("America/New_York")


def _monday(hour, minute=0):
    """Return a tz-aware Monday ET datetime for time-based tests."""
    return real_dt(2026, 5, 11, hour, minute, 0, tzinfo=_NY)


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
        import core.notifier as notifier
        notifier._telegram_log_level = 2
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

    @patch("core.logger.log_trade")
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
        mock_price, mock_wheel, mock_load, mock_save, mock_log
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

    @patch("core.logger.log_trade")
    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.trailing_stop_sell")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_latest_price", return_value=150.0)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_trailing_stop_with_stop_floor_calls_trailing_stop_sell(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_buy, mock_trailing, mock_load, mock_save, mock_log
    ):
        """When a TRAILING_STOP approval includes a stop_floor, trailing_stop_sell is called."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_acct.return_value = _mock_account(buying_power=50000.0)
        state = {
            "pending_trades": {
                "2026-05-08_AAPL_P001": {
                    "ticker": "AAPL",
                    "strategy": "TRAILING_STOP",
                    "confidence": 85,
                    "reasoning": "momentum",
                    "price": 150.0,
                    "politician": "McCaul",
                    "position_pct": 0.05,
                    "stop_floor": 10,
                }
            },
            "positions": {}, "wheel": {}, "copied_trades": [],
        }
        mock_load.return_value = state
        mock_post.side_effect = [{"result": [self._approve_update()]}, {}, {}]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        mock_trailing.assert_called_once()

    @patch("core.logger.log_trade")
    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy", side_effect=RuntimeError("order rejected"))
    @patch("core.alpaca.get_latest_price", return_value=150.0)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_execution_exception_sends_error_message(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_buy, mock_load, mock_save, mock_log
    ):
        """If market_buy raises, an ❌ error message is sent to Telegram."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_acct.return_value = _mock_account(buying_power=50000.0)
        mock_load.return_value = self._make_pending(strategy="TRAILING_STOP")
        mock_post.side_effect = [{"result": [self._approve_update()]}, {}, {}]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()  # must not raise

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("❌" in t for t in sent)


# ── is_market_open — weekday branches ────────────────────────────────────────

class TestIsMarketOpenWeekday:
    def test_returns_true_during_market_hours(self):
        with patch("scheduler.market_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = _monday(10, 0)
            from scheduler.market_scheduler import is_market_open
            assert is_market_open() is True

    def test_returns_false_before_market_open(self):
        with patch("scheduler.market_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = _monday(8, 0)
            from scheduler.market_scheduler import is_market_open
            assert is_market_open() is False

    def test_returns_false_after_market_close(self):
        with patch("scheduler.market_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = _monday(17, 0)
            from scheduler.market_scheduler import is_market_open
            assert is_market_open() is False


# ── _run_analyze ──────────────────────────────────────────────────────────────

class TestRunAnalyze:
    @patch("scheduler.market_scheduler.is_market_open", return_value=False)
    def test_analyze_skipped_when_market_closed(self, _open):
        with patch("subprocess.run") as mock_sub:
            from scheduler.market_scheduler import _run_analyze
            _run_analyze()
            mock_sub.assert_not_called()

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("subprocess.run")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_analyze_logs_stderr_on_nonzero_exit(self, _open, mock_sub, _cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_sub.return_value = MagicMock(stdout="", stderr="failure detail", returncode=1)
        from scheduler.market_scheduler import _run_analyze
        _run_analyze()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("failure detail" in t for t in sent)
        notifier._telegram_log_level = 2


# ── _poll_telegram — not configured / no approvals / insufficient funds ───────

class TestPollTelegramGates:
    @patch("core.notifier.is_configured", return_value=False)
    def test_poll_skips_when_not_configured(self, _cfg):
        with patch("core.alpaca.get_account") as mock_acct:
            from scheduler.market_scheduler import _poll_telegram
            _poll_telegram()
            mock_acct.assert_not_called()

    @patch("core.notifier.poll_approvals", return_value=[])
    @patch("core.notifier.is_configured", return_value=True)
    def test_poll_returns_early_when_no_approvals(self, _cfg, _approvals):
        with patch("core.alpaca.get_account") as mock_acct:
            from scheduler.market_scheduler import _poll_telegram
            _poll_telegram()
            mock_acct.assert_not_called()

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.get_latest_price", return_value=150.0)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_insufficient_buying_power_sends_warning(
        self, _cfg, mock_post, mock_send, mock_acct, _price, mock_load, mock_save
    ):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_acct.return_value = _mock_account(buying_power=1.0)
        mock_load.return_value = {
            "pending_trades": {
                "2026-05-08_AAPL_P001": {
                    "ticker": "AAPL", "strategy": "TRAILING_STOP",
                    "position_pct": 0.05, "stop_floor": None,
                }
            },
            "positions": {}, "wheel": {}, "copied_trades": [],
        }
        mock_post.side_effect = [
            {"result": [{
                "update_id": 99,
                "callback_query": {
                    "id": "cb1",
                    "data": "approve:2026-05-08_AAPL_P001",
                    "message": {"message_id": 1},
                },
            }]},
            {}, {},
        ]
        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("⚠️" in t or "Insufficient" in t for t in sent)
        notifier._telegram_log_level = 2


# ── _build_schedule_message ───────────────────────────────────────────────────

class TestBuildScheduleMessage:
    def _msg(self, hour, minute=0):
        with patch("scheduler.market_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = _monday(hour, minute)
            mock_dt.strptime.side_effect = real_dt.strptime
            from scheduler.market_scheduler import _build_schedule_message
            return _build_schedule_message()

    def test_header_contains_date_and_brand(self):
        msg = self._msg(10)
        assert "2026-05-11" in msg
        assert "LLM Trader" in msg

    def test_pre_market_all_upcoming(self):
        msg = self._msg(8)
        # Market tasks are ⬜ before open; data source check is always 🔄
        assert "⬜" in msg
        assert "Capitol Trades Health Check" in msg

    def test_during_market_recurring_tasks_active(self):
        msg = self._msg(11)
        assert "🔄" in msg
        assert "Trailing Stop" in msg

    def test_after_close_recurring_tasks_completed(self):
        msg = self._msg(17)
        assert "✅" in msg
        assert "⬜" not in msg

    def test_contains_current_time(self):
        msg = self._msg(10, 30)
        assert "10:30 AM ET" in msg


# ── _send_schedule ────────────────────────────────────────────────────────────

class TestSendSchedule:
    @patch("core.notifier.send_message")
    @patch("scheduler.market_scheduler._build_schedule_message", return_value="sched_text")
    def test_delegates_to_send_message(self, _build, mock_send):
        from scheduler.market_scheduler import _send_schedule
        _send_schedule()
        mock_send.assert_called_once_with("sched_text")


# ── start() — command registration ───────────────────────────────────────────

class TestStart:
    @patch("scheduler.market_scheduler._run_trailing_stop")
    @patch("scheduler.market_scheduler.schedule")
    @patch("time.sleep", side_effect=KeyboardInterrupt)
    @patch("core.notifier.is_configured", return_value=False)
    @patch("core.notifier.register_command")
    @patch("core.logger.save_state")
    @patch("core.logger.load_state", return_value={"pending_trades": {"stale": {}}})
    def test_registers_summary_and_schedule_commands(
        self, _load, _save, mock_reg, _cfg, _sleep, _sched, _trailing
    ):
        from scheduler.market_scheduler import start
        with pytest.raises(KeyboardInterrupt):
            start()
        registered = [c[0][0] for c in mock_reg.call_args_list]
        assert "/summary" in registered
        assert "/schedule" in registered

    @patch("scheduler.market_scheduler._run_trailing_stop")
    @patch("scheduler.market_scheduler.schedule")
    @patch("time.sleep", side_effect=KeyboardInterrupt)
    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier.register_command")
    @patch("core.logger.save_state")
    @patch("core.logger.load_state", return_value={"pending_trades": {}})
    def test_sends_startup_message_when_configured(
        self, _load, _save, _reg, _cfg, mock_send, _sleep, _sched, _trailing
    ):
        from scheduler.market_scheduler import start
        with pytest.raises(KeyboardInterrupt):
            start()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("LLM Trader started" in t for t in sent)


# ── _check_data_source ───────────────────────────────────────────────────────

class TestCheckDataSource:
    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.smart_money._fetch_raw")
    @patch("strategies.smart_money._fetch_raw_scrape")
    def test_no_alert_when_both_return_data(self, mock_scrape, mock_api, _cfg, mock_send):
        """No Telegram alert when scrape and API both return rows."""
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_scrape.return_value = [{"ticker": "AAPL"}]
        mock_api.return_value = [{"ticker": "AAPL"}]
        from scheduler.market_scheduler import _check_data_source
        _check_data_source()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert not any("FAILED" in t for t in sent)

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.smart_money._fetch_raw")
    @patch("strategies.smart_money._fetch_raw_scrape")
    def test_alert_when_scrape_returns_empty(self, mock_scrape, mock_api, _cfg, mock_send):
        """Telegram alert sent when web scrape returns 0 rows."""
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_scrape.return_value = []
        mock_api.return_value = [{"ticker": "AAPL"}]
        from scheduler.market_scheduler import _check_data_source
        _check_data_source()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("FAILED" in t and "web scrape" in t for t in sent)

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.smart_money._fetch_raw")
    @patch("strategies.smart_money._fetch_raw_scrape")
    def test_alert_when_scrape_raises(self, mock_scrape, mock_api, _cfg, mock_send):
        """Telegram alert sent when web scrape raises an exception."""
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_scrape.side_effect = Exception("Connection refused")
        mock_api.return_value = [{"ticker": "AAPL"}]
        from scheduler.market_scheduler import _check_data_source
        _check_data_source()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("FAILED" in t for t in sent)

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.smart_money._fetch_raw")
    @patch("strategies.smart_money._fetch_raw_scrape")
    def test_api_only_failure_is_debug_level(self, mock_scrape, mock_api, _cfg, mock_send):
        """API-only failure is severity 1 (debug) — not sent at log level 2 since scraper covers it."""
        import core.notifier as notifier
        notifier._telegram_log_level = 2  # info — debug messages suppressed
        mock_scrape.return_value = [{"ticker": "AAPL"}]
        mock_api.return_value = []
        from scheduler.market_scheduler import _check_data_source
        _check_data_source()
        # At level 2, a severity-1 message is NOT forwarded to Telegram
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert not any("FAILED" in t for t in sent)

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.smart_money._fetch_raw")
    @patch("strategies.smart_money._fetch_raw_scrape")
    def test_api_only_failure_visible_at_debug_level(self, mock_scrape, mock_api, _cfg, mock_send):
        """API-only failure IS visible when log level is 1 (debug)."""
        import core.notifier as notifier
        notifier._telegram_log_level = 1
        mock_scrape.return_value = [{"ticker": "AAPL"}]
        mock_api.return_value = []
        from scheduler.market_scheduler import _check_data_source
        _check_data_source()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("FAILED" in t and "API" in t for t in sent)
        notifier._telegram_log_level = 2


# ── _todays_activity ──────────────────────────────────────────────────────────

class TestTodaysActivity:
    def _write_trades(self, tmp_path, entries):
        import json
        trade_log = tmp_path / "trades.log"
        with open(trade_log, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return trade_log

    def test_counts_todays_buys(self, tmp_path):
        import core.logger as logger_mod
        today = real_dt.now(_NY).strftime("%Y-%m-%d")
        log = self._write_trades(tmp_path, [
            {"ts": f"{today}T10:00:00", "action": "AI_BUY_TRAILING", "symbol": "GE"},
            {"ts": f"{today}T10:30:00", "action": "AI_BUY_TRAILING", "symbol": "MSFT"},
        ])
        original = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = log
        try:
            from scheduler.market_scheduler import _todays_activity
            result = _todays_activity()
            assert result["buys"] == ["GE", "MSFT"]
            assert result["sells"] == []
        finally:
            logger_mod.TRADE_LOG = original

    def test_counts_todays_sells(self, tmp_path):
        import core.logger as logger_mod
        today = real_dt.now(_NY).strftime("%Y-%m-%d")
        log = self._write_trades(tmp_path, [
            {"ts": f"{today}T14:00:00", "action": "STOP_SELL", "symbol": "TDG"},
            {"ts": f"{today}T15:00:00", "action": "TAKE_PROFIT", "symbol": "PEP"},
        ])
        original = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = log
        try:
            from scheduler.market_scheduler import _todays_activity
            result = _todays_activity()
            assert result["sells"] == ["TDG", "PEP"]
            assert result["buys"] == []
        finally:
            logger_mod.TRADE_LOG = original

    def test_excludes_previous_days(self, tmp_path):
        import core.logger as logger_mod
        log = self._write_trades(tmp_path, [
            {"ts": "2026-01-01T10:00:00", "action": "AI_BUY_TRAILING", "symbol": "OLD"},
        ])
        original = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = log
        try:
            from scheduler.market_scheduler import _todays_activity
            result = _todays_activity()
            assert result["buys"] == []
        finally:
            logger_mod.TRADE_LOG = original

    def test_returns_empty_when_no_log_file(self, tmp_path):
        import core.logger as logger_mod
        original = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = tmp_path / "nonexistent.log"
        try:
            from scheduler.market_scheduler import _todays_activity
            result = _todays_activity()
            assert result["buys"] == []
            assert result["sells"] == []
            assert result["realized_pnl"] == 0.0
        finally:
            logger_mod.TRADE_LOG = original

    def test_skips_malformed_lines(self, tmp_path):
        import core.logger as logger_mod
        today = real_dt.now(_NY).strftime("%Y-%m-%d")
        log = self._write_trades(tmp_path, [
            {"ts": f"{today}T10:00:00", "action": "AI_BUY_TRAILING", "symbol": "GE"},
        ])
        log.write_text("not valid json\n" + log.read_text())
        original = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = log
        try:
            from scheduler.market_scheduler import _todays_activity
            result = _todays_activity()
            assert result["buys"] == ["GE"]  # valid line still parsed
        finally:
            logger_mod.TRADE_LOG = original

    def test_summary_includes_activity_indicators(self, tmp_path):
        """_run_daily_summary sends position count, buys, and sells to Telegram."""
        import core.logger as logger_mod
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        today = real_dt.now(_NY).strftime("%Y-%m-%d")
        log = self._write_trades(tmp_path, [
            {"ts": f"{today}T10:00:00", "action": "AI_BUY_TRAILING", "symbol": "GE"},
            {"ts": f"{today}T14:00:00", "action": "STOP_SELL",       "symbol": "TDG"},
        ])
        original_log = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = log
        try:
            with patch("core.alpaca.get_account", return_value=_mock_account()), \
                 patch("core.alpaca.get_positions", return_value=[]), \
                 patch("core.logger.load_state", return_value={"positions": {}, "wheel": {}, "copied_trades": []}), \
                 patch("core.notifier.send_message") as mock_send:
                from scheduler.market_scheduler import _run_daily_summary
                _run_daily_summary()
            text = mock_send.call_args[0][0]
            assert "Positions open" in text
            assert "Buys today" in text
            assert "GE" in text
            assert "Sells today" in text
            assert "TDG" in text
        finally:
            logger_mod.TRADE_LOG = original_log
            notifier._telegram_log_level = 2


    def test_realized_pnl_calculated_from_buy_sell_pairs(self, tmp_path):
        """When entries include qty+price, realized P&L is computed from sell vs avg entry."""
        import core.logger as logger_mod
        today = real_dt.now(_NY).strftime("%Y-%m-%d")
        log = self._write_trades(tmp_path, [
            {"ts": f"{today}T09:30:00", "action": "AI_BUY_TRAILING",
             "symbol": "GE", "qty": 10, "price": 280.0},
            {"ts": f"{today}T15:00:00", "action": "STOP_SELL",
             "symbol": "GE", "qty": 10.0, "price": 300.0},
        ])
        original = logger_mod.TRADE_LOG
        logger_mod.TRADE_LOG = log
        try:
            from scheduler.market_scheduler import _todays_activity, _cumulative_realized_pnl
            activity = _todays_activity()
            assert abs(activity["realized_pnl"] - 200.0) < 0.01  # (300-280)*10

            cum = _cumulative_realized_pnl()
            assert abs(cum["pnl"] - 200.0) < 0.01
            assert cum["deployed"] == 2800.0
            assert abs(cum["roi_pct"] - (200.0 / 2800.0 * 100)) < 0.01
        finally:
            logger_mod.TRADE_LOG = original


# ── _check_data_source — API exception path ──────────────────────────────────

class TestCheckDataSourceApiException:
    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.smart_money._fetch_raw", side_effect=Exception("timeout"))
    @patch("strategies.smart_money._fetch_raw_scrape")
    def test_api_exception_logged_at_debug(self, mock_scrape, mock_api, _cfg, mock_send):
        """API exception is captured and reported at severity 1 when scraper is OK."""
        import core.notifier as notifier
        notifier._telegram_log_level = 1
        mock_scrape.return_value = [{"ticker": "AAPL"}]
        from scheduler.market_scheduler import _check_data_source
        _check_data_source()
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("FAILED" in t and "API" in t for t in sent)
        notifier._telegram_log_level = 2


# ── _enforce_single_instance — stale PID path ────────────────────────────────

class TestEnforceSingleInstanceStalePid:
    def test_stale_pid_does_not_raise(self, tmp_path):
        """If the PID in the file no longer exists, _enforce_single_instance must not raise."""
        import scheduler.market_scheduler as sched
        original = sched._PID_FILE
        pid_file = tmp_path / "scheduler.pid"
        pid_file.write_text("99999999")  # PID that almost certainly doesn't exist
        sched._PID_FILE = pid_file
        try:
            sched._enforce_single_instance()  # must not raise
        finally:
            sched._PID_FILE = original
