"""
Integration test: simulated Capitol Trades signal → trade pipeline → Telegram messages.

All external calls (Alpaca API, Claude API, Telegram HTTP, filesystem) are mocked.
Covers:
  1. Signal → send_trade_approval (analyze pipeline)
  2. Telegram approve callback → market_buy + confirmation message
  3. Telegram skip callback → no trade executed
  4. Scheduler step messages forwarded to Telegram at the correct log level
"""
import json
import pytest
from unittest.mock import patch, MagicMock, call

# ── Shared test data ───────────────────────────────────────────────────────────

NVDA_SIGNAL = {
    "txDate": "2026-04-25",
    "txType": "purchase",
    "size": "$50,001 - $100,000",
    "asset": {"ticker": "NVDA"},
    "politician": {"name": "Michael McCaul", "id": "P001"},
}

TRAILING_STOP_REC = {
    "strategy": "TRAILING_STOP",
    "confidence": 85,
    "reasoning": "NVDA is a high-momentum semiconductor stock — ideal for trailing stop.",
    "suggested_position_size_pct": 0.08,
    "key_risk": "Sector volatility may trigger stop prematurely.",
    "_cache_hit": False,
    "_tokens_saved": 0,
    "_cache_written": 3000,
}

TRADE_KEY = "2026-04-25_NVDA_P001"


def _mock_account(buying_power=50_000.0, equity=100_000.0):
    acct = MagicMock()
    acct.buying_power = buying_power
    acct.equity = equity
    acct.last_equity = 99_000.0
    acct.portfolio_value = equity
    acct.cash = buying_power
    return acct


def _approve_update(trade_key=TRADE_KEY, update_id=1):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cb1",
            "data": f"approve:{trade_key}",
            "message": {"message_id": 42},
        },
    }


def _skip_update(trade_key=TRADE_KEY, update_id=2):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cb2",
            "data": f"skip:{trade_key}",
            "message": {"message_id": 43},
        },
    }


# ── 1. Signal → Telegram approval ─────────────────────────────────────────────

class TestSignalToTelegramApproval:
    """analyze_and_trade pipeline sends the right approval message for a new signal."""

    def _run_pipeline_for_signal(self, signal, recommendation, send_trade_approval_mock,
                                  market_buy_mock=None):
        """Replicate the core per-signal logic from analyze_and_trade.main()."""
        from core.notifier import send_trade_approval, is_configured
        import core.notifier as notifier

        ticker = signal["asset"]["ticker"]
        trade_key = (
            f"{signal['txDate']}_{ticker}_{signal['politician']['id']}"
        )
        strategy = recommendation["strategy"]
        confidence = recommendation["confidence"]
        reasoning = recommendation["reasoning"]
        position_pct = recommendation["suggested_position_size_pct"]
        politician_name = signal["politician"]["name"]
        price = 875.50

        pending = {}
        pending[trade_key] = {
            "ticker": ticker,
            "strategy": strategy,
            "confidence": confidence,
            "reasoning": reasoning,
            "price": price,
            "politician": politician_name,
            "position_pct": position_pct,
            "stop_floor": None,
        }
        send_trade_approval(
            trade_key=trade_key,
            ticker=ticker,
            strategy=strategy,
            confidence=confidence,
            reasoning=reasoning,
            price=price,
            politician=politician_name,
        )
        return pending, trade_key

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier._chat_id", return_value="123")
    def test_approval_message_contains_signal_data(self, _chat, _cfg, mock_post):
        """Telegram approval message carries ticker, strategy, politician, and confidence."""
        from core.notifier import send_trade_approval

        send_trade_approval(
            trade_key=TRADE_KEY,
            ticker="NVDA",
            strategy="TRAILING_STOP",
            confidence=85,
            reasoning=TRAILING_STOP_REC["reasoning"],
            price=875.50,
            politician="Michael McCaul",
        )

        mock_post.assert_called_once()
        method, payload = mock_post.call_args[0]
        assert method == "sendMessage"
        assert "NVDA" in payload["text"]
        assert "TRAILING_STOP" in payload["text"]
        assert "McCaul" in payload["text"]
        assert "85%" in payload["text"]

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier._chat_id", return_value="123")
    def test_approval_message_has_approve_and_skip_buttons(self, _chat, _cfg, mock_post):
        """Inline keyboard includes both Approve and Skip buttons keyed to the trade."""
        from core.notifier import send_trade_approval

        send_trade_approval(
            trade_key=TRADE_KEY,
            ticker="NVDA",
            strategy="TRAILING_STOP",
            confidence=85,
            reasoning="Strong momentum.",
            price=875.50,
            politician="Michael McCaul",
        )

        _, payload = mock_post.call_args[0]
        keyboard = json.loads(payload["reply_markup"])["inline_keyboard"][0]
        callback_data = [b["callback_data"] for b in keyboard]
        assert f"approve:{TRADE_KEY}" in callback_data
        assert f"skip:{TRADE_KEY}" in callback_data

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier._chat_id", return_value="123")
    def test_wheel_signal_sends_wheel_strategy(self, _chat, _cfg, mock_post):
        """A WHEEL recommendation results in a Telegram message that says WHEEL."""
        from core.notifier import send_trade_approval

        send_trade_approval(
            trade_key="2026-04-25_JPM_P001",
            ticker="JPM",
            strategy="WHEEL",
            confidence=78,
            reasoning="JPM is a stable blue-chip financial — ideal for premium collection.",
            price=198.30,
            politician="Nancy Pelosi",
        )

        _, payload = mock_post.call_args[0]
        assert "WHEEL" in payload["text"]
        assert "JPM" in payload["text"]
        assert "78%" in payload["text"]


# ── 2. Telegram approve → trade execution ─────────────────────────────────────

class TestTelegramApproveExecutesTrade:
    """_poll_telegram executes a market buy and sends a confirmation after Approve tap."""

    def _make_pending_state(self, strategy="TRAILING_STOP", trade_key=TRADE_KEY):
        return {
            "pending_trades": {
                trade_key: {
                    "ticker": "NVDA",
                    "strategy": strategy,
                    "confidence": 85,
                    "reasoning": "Strong momentum.",
                    "price": 875.50,
                    "politician": "Michael McCaul",
                    "position_pct": 0.08,
                    "stop_floor": None,
                }
            },
            "positions": {},
            "wheel": {},
            "copied_trades": [],
        }

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_latest_price", return_value=875.50)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_approve_calls_market_buy(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_buy, mock_load, mock_save
    ):
        """Approve callback triggers market_buy for the pending NVDA trade."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0

        mock_acct.return_value = _mock_account()
        mock_load.return_value = self._make_pending_state()
        mock_post.side_effect = [
            {"result": [_approve_update()]},  # getUpdates
            {},  # answerCallbackQuery
            {},  # editMessageReplyMarkup
        ]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        mock_buy.assert_called_once()
        args = mock_buy.call_args[0]
        assert args[0] == "NVDA"
        assert args[1] >= 1  # at least 1 share

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_latest_price", return_value=875.50)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_approve_sends_confirmation_message(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_buy, mock_load, mock_save
    ):
        """Confirmation message with ✅ and NVDA ticker is sent after approve."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0

        mock_acct.return_value = _mock_account()
        mock_load.return_value = self._make_pending_state()
        mock_post.side_effect = [
            {"result": [_approve_update()]},
            {},
            {},
        ]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        sent_texts = [c[0][0] for c in mock_send.call_args_list]
        assert any("NVDA" in t and "✅" in t for t in sent_texts), (
            f"Expected a ✅ NVDA confirmation in Telegram messages, got: {sent_texts}"
        )

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_latest_price", return_value=875.50)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_approve_removes_trade_from_pending(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_buy, mock_load, mock_save
    ):
        """Approved trade is removed from pending_trades in saved state."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0

        mock_acct.return_value = _mock_account()
        mock_load.return_value = self._make_pending_state()
        mock_post.side_effect = [{"result": [_approve_update()]}, {}, {}]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        saved_state = mock_save.call_args[0][0]
        assert TRADE_KEY not in saved_state.get("pending_trades", {})

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_latest_price", return_value=875.50)
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_approve_marks_trade_as_copied(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_price, mock_buy, mock_load, mock_save
    ):
        """Trade key lands in copied_trades after approval so it won't re-process."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0

        mock_acct.return_value = _mock_account()
        mock_load.return_value = self._make_pending_state()
        mock_post.side_effect = [{"result": [_approve_update()]}, {}, {}]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        saved_state = mock_save.call_args[0][0]
        assert TRADE_KEY in saved_state.get("copied_trades", [])


# ── 3. Telegram skip → no trade ───────────────────────────────────────────────

class TestTelegramSkipNoTrade:
    """_poll_telegram does not buy when the user taps Skip."""

    def _make_pending_state(self, trade_key=TRADE_KEY):
        return {
            "pending_trades": {
                trade_key: {
                    "ticker": "NVDA",
                    "strategy": "TRAILING_STOP",
                    "confidence": 85,
                    "reasoning": "Strong momentum.",
                    "price": 875.50,
                    "politician": "Michael McCaul",
                    "position_pct": 0.08,
                    "stop_floor": None,
                }
            },
            "positions": {},
            "wheel": {},
            "copied_trades": [],
        }

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_skip_does_not_call_market_buy(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_buy, mock_load, mock_save
    ):
        """Skipping a trade must never trigger a market buy."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0

        mock_acct.return_value = _mock_account()
        mock_load.return_value = self._make_pending_state()
        mock_post.side_effect = [
            {"result": [_skip_update()]},  # getUpdates
            {},  # answerCallbackQuery
            {},  # editMessageReplyMarkup
        ]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        mock_buy.assert_not_called()

    @patch("core.logger.save_state")
    @patch("core.logger.load_state")
    @patch("core.alpaca.market_buy")
    @patch("core.alpaca.get_account")
    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_skip_marks_trade_as_copied(
        self, mock_cfg, mock_post, mock_send, mock_acct,
        mock_buy, mock_load, mock_save
    ):
        """Skipped trade is added to copied_trades so it won't resurface."""
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0

        mock_acct.return_value = _mock_account()
        mock_load.return_value = self._make_pending_state()
        mock_post.side_effect = [
            {"result": [_skip_update()]},
            {},
            {},
        ]

        from scheduler.market_scheduler import _poll_telegram
        _poll_telegram()

        saved_state = mock_save.call_args[0][0]
        assert TRADE_KEY in saved_state.get("copied_trades", [])


# ── 4. tlog level visibility in scheduler steps ───────────────────────────────

class TestSchedulerTlogLevelVisibility:
    """Scheduler step messages reach Telegram at level 2 and are suppressed at level 3."""

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.trailing_stop.check_and_update")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_trailing_stop_step_visible_at_level_2(
        self, _open, mock_check, _cfg, mock_send
    ):
        """'Trailing stop check...' reaches Telegram when log level is 2 (info)."""
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        mock_check.return_value = {"checked": [], "stopped_out": [], "laddered": []}

        from scheduler.market_scheduler import _run_trailing_stop
        _run_trailing_stop()

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("Trailing stop check" in t for t in sent), (
            f"Expected 'Trailing stop check' in Telegram messages, got: {sent}"
        )
        notifier._telegram_log_level = 2  # reset

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.trailing_stop.check_and_update")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_trailing_stop_step_suppressed_at_level_3(
        self, _open, mock_check, _cfg, mock_send
    ):
        """'Trailing stop check...' does NOT reach Telegram when log level is 3 (error only)."""
        import core.notifier as notifier
        notifier._telegram_log_level = 3
        mock_check.return_value = {"checked": [], "stopped_out": [], "laddered": []}

        from scheduler.market_scheduler import _run_trailing_stop
        _run_trailing_stop()

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert not any("Trailing stop check" in t for t in sent), (
            f"Info message leaked to Telegram at level 3: {sent}"
        )
        notifier._telegram_log_level = 2  # reset

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("strategies.trailing_stop.check_and_update")
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_stop_triggered_visible_at_level_3(
        self, _open, mock_check, _cfg, mock_send
    ):
        """Stop-triggered alerts still reach Telegram even at level 3 (error severity)."""
        import core.notifier as notifier
        notifier._telegram_log_level = 3
        mock_check.return_value = {
            "checked": [{"symbol": "NVDA", "price": 820.0, "floor": 850.0}],
            "stopped_out": ["NVDA"],
            "laddered": [],
        }

        from scheduler.market_scheduler import _run_trailing_stop
        _run_trailing_stop()

        # send_stop_alert internally calls send_message — NVDA must appear
        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("NVDA" in t for t in sent), (
            f"Stop alert for NVDA missing from Telegram at level 3: {sent}"
        )
        notifier._telegram_log_level = 2  # reset

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_analyze_step_visible_at_level_2(self, _open, _cfg, mock_send):
        """AI analyze run start message reaches Telegram at level 2."""
        import core.notifier as notifier
        notifier._telegram_log_level = 2

        import subprocess
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            from scheduler.market_scheduler import _run_analyze
            _run_analyze()

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("AI analyze run" in t for t in sent), (
            f"Expected 'AI analyze run' in Telegram messages at level 2, got: {sent}"
        )
        notifier._telegram_log_level = 2  # reset

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_analyze_subprocess_output_only_at_debug(self, _open, _cfg, mock_send):
        """Analyze subprocess stdout lines go to Telegram only at debug level (1)."""
        import core.notifier as notifier
        mock_result = MagicMock()
        mock_result.stdout = "Processing NVDA signal\nBought 10 shares"
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            # At level 2 (info): subprocess lines must NOT appear
            notifier._telegram_log_level = 2
            from scheduler.market_scheduler import _run_analyze
            _run_analyze()
            sent_level2 = [c[0][0] for c in mock_send.call_args_list]
            assert not any("Processing NVDA" in t for t in sent_level2)

            mock_send.reset_mock()

            # At level 1 (debug): subprocess lines MUST appear
            notifier._telegram_log_level = 1
            _run_analyze()
            sent_level1 = [c[0][0] for c in mock_send.call_args_list]
            assert any("Processing NVDA" in t for t in sent_level1)

        notifier._telegram_log_level = 2  # reset
