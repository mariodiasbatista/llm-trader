"""
Integration test: simulated Capitol Trades signal → trade pipeline → Telegram messages.

All external calls (Alpaca API, Claude API, Telegram HTTP, filesystem) are mocked.
Covers:
  1. Signal → send_trade_approval (analyze pipeline)
  2. Telegram approve callback → market_buy + confirmation message
  3. Telegram skip callback → no trade executed
  4. Scheduler step messages forwarded to Telegram at the correct log level
"""
import importlib.util
import json
import pytest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch, MagicMock, call


def _load_analyze_module():
    """Load scripts/analyze_and_trade.py as a module so we can call main() in tests."""
    spec = importlib.util.spec_from_file_location(
        "_analyze_and_trade",
        Path(__file__).parent.parent / "scripts" / "analyze_and_trade.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _noop_lock():
    yield

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

    @patch("core.logger.log_trade")
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
        mock_price, mock_buy, mock_load, mock_save, mock_log
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

    @patch("core.logger.log_trade")
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
        mock_price, mock_buy, mock_load, mock_save, mock_log
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

    @patch("core.logger.log_trade")
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
        mock_price, mock_buy, mock_load, mock_save, mock_log
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

    @patch("core.logger.log_trade")
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
        mock_price, mock_buy, mock_load, mock_save, mock_log
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


# ── 5. Analyze subprocess timeout ─────────────────────────────────────────────

class TestAnalyzeSubprocessTimeout:
    """_run_analyze handles subprocess.TimeoutExpired without crashing the scheduler."""

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_timeout_does_not_raise(self, _open, _cfg, mock_send):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="python", timeout=300)):
            from scheduler.market_scheduler import _run_analyze
            _run_analyze()  # must not propagate the exception

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("scheduler.market_scheduler.is_market_open", return_value=True)
    def test_timeout_sends_error_to_telegram(self, _open, _cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="python", timeout=300)):
            from scheduler.market_scheduler import _run_analyze
            _run_analyze()

        sent = [c[0][0] for c in mock_send.call_args_list]
        assert any("timed out" in t.lower() for t in sent), (
            f"Expected timeout error in Telegram messages, got: {sent}"
        )
        notifier._telegram_log_level = 2  # reset


# ── 6. SKIP signals marked as processed ───────────────────────────────────────

class TestSkipSignalMarkedAsProcessed:
    """SKIP recommendations must land in copied_trades — prevents Claude re-analyzing same ticker."""

    def _signal(self, ticker="ALH", date="2026-05-11", pol_id="P001"):
        return {
            "txDate": date, "txType": "purchase",
            "size": "$15,001 - $50,000",
            "asset": {"ticker": ticker},
            "politician": {"name": "Michael McCaul", "id": pol_id},
        }

    def _skip_rec(self, reason="Not a liquid ticker."):
        return {
            "strategy": "SKIP", "confidence": 0, "reasoning": reason,
            "suggested_position_size_pct": 0.0, "key_risk": "",
            "_cache_hit": False, "_tokens_saved": 0,
        }

    def _run_main(self, signals, rec, initial_copied=None):
        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        state = {
            "positions": {}, "wheel": {},
            "copied_trades": initial_copied or [],
            "pending_trades": {},
        }
        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=[]), \
             patch.object(mod, "get_latest_price", return_value=19.0), \
             patch.object(mod, "fetch_large_trades", return_value=signals), \
             patch.object(mod, "get_recommendation", return_value=rec) as mock_rec, \
             patch.object(mod, "load_state", return_value=state), \
             patch.object(mod, "save_state") as mock_save, \
             patch.object(mod, "state_lock", _noop_lock), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()
        return mock_save, mock_rec

    def test_skip_trade_key_saved_to_copied_trades(self):
        """After SKIP, the trade_key must appear in saved copied_trades."""
        mock_save, _ = self._run_main([self._signal()], self._skip_rec())
        saved = mock_save.call_args[0][0]
        assert "2026-05-11_ALH_P001" in saved["copied_trades"]

    def test_already_processed_skip_does_not_call_claude(self):
        """If a SKIP trade_key is already in copied_trades, Claude is never called again."""
        _, mock_rec = self._run_main(
            [self._signal()], self._skip_rec(),
            initial_copied=["2026-05-11_ALH_P001"],
        )
        mock_rec.assert_not_called()


# ── 7. size_up flag — diversification guard ───────────────────────────────────

class TestSizeUpFlag:
    """When size_up=false, the bot must not buy more of a ticker already in the portfolio."""

    def _signal(self, ticker="EQT", date="2026-05-12", pol_id="M001"):
        return {
            "txDate": date, "txType": "purchase",
            "size": "$15,001 - $50,000",
            "asset": {"ticker": ticker},
            "politician": {"name": "Michael McCaul", "id": pol_id},
        }

    def _existing_position(self, symbol="EQT"):
        pos = MagicMock()
        pos.symbol = symbol
        return pos

    def _run(self, existing_positions, size_up, signal=None):
        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        state = {"positions": {}, "wheel": {}, "copied_trades": [], "pending_trades": {}}

        # Write a temp settings.json with the desired size_up value
        import json, tempfile
        from pathlib import Path
        settings = {"analyze": {"size_up": size_up}, "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {}}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(settings, tmp)
        tmp.flush()

        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=existing_positions), \
             patch.object(mod, "get_latest_price", return_value=56.0), \
             patch.object(mod, "fetch_large_trades", return_value=[signal or self._signal()]), \
             patch.object(mod, "get_recommendation") as mock_rec, \
             patch.object(mod, "load_state", return_value=state), \
             patch.object(mod, "save_state"), \
             patch.object(mod, "state_lock", _noop_lock), \
             patch.object(mod, "_cfg_path" if hasattr(mod, "_cfg_path") else "_json",
                          new=MagicMock()) if False else patch(
                 "builtins.open", MagicMock()) if False else \
             patch("pathlib.Path.read_text", return_value=json.dumps(settings)), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()
        return mock_rec

    def test_size_up_false_skips_existing_ticker(self):
        """With size_up=false, a signal for an already-owned ticker never reaches Claude."""
        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        state = {"positions": {}, "wheel": {}, "copied_trades": [], "pending_trades": {}}

        import json
        settings = {
            "analyze": {"size_up": False},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }

        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=[self._existing_position("EQT")]), \
             patch.object(mod, "fetch_large_trades", return_value=[self._signal("EQT")]), \
             patch.object(mod, "get_recommendation") as mock_rec, \
             patch.object(mod, "load_state", return_value=state), \
             patch.object(mod, "save_state"), \
             patch.object(mod, "state_lock", _noop_lock), \
             patch("pathlib.Path.read_text", return_value=json.dumps(settings)), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()

        mock_rec.assert_not_called()

    def test_size_up_true_allows_adding_to_existing_position(self):
        """With size_up=true, a signal for an already-owned ticker IS sent to Claude."""
        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        state = {"positions": {}, "wheel": {}, "copied_trades": [], "pending_trades": {}}

        import json
        settings = {
            "analyze": {"size_up": True},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }
        skip_rec = {
            "strategy": "SKIP", "confidence": 0, "reasoning": "test",
            "suggested_position_size_pct": 0.0, "key_risk": "",
            "_cache_hit": False, "_tokens_saved": 0,
        }

        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=[self._existing_position("EQT")]), \
             patch.object(mod, "get_latest_price", return_value=56.0), \
             patch.object(mod, "fetch_large_trades", return_value=[self._signal("EQT")]), \
             patch.object(mod, "get_recommendation", return_value=skip_rec) as mock_rec, \
             patch.object(mod, "load_state", return_value=state), \
             patch.object(mod, "save_state"), \
             patch.object(mod, "state_lock", _noop_lock), \
             patch("pathlib.Path.read_text", return_value=json.dumps(settings)), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()

        mock_rec.assert_called_once()

    def test_size_up_false_does_not_affect_new_tickers(self):
        """With size_up=false, signals for tickers NOT in the portfolio reach Claude normally."""
        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        state = {"positions": {}, "wheel": {}, "copied_trades": [], "pending_trades": {}}

        import json
        settings = {
            "analyze": {"size_up": False},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }
        skip_rec = {
            "strategy": "SKIP", "confidence": 0, "reasoning": "test",
            "suggested_position_size_pct": 0.0, "key_risk": "",
            "_cache_hit": False, "_tokens_saved": 0,
        }

        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=[self._existing_position("GE")]), \
             patch.object(mod, "get_latest_price", return_value=56.0), \
             patch.object(mod, "fetch_large_trades", return_value=[self._signal("EQT")]), \
             patch.object(mod, "get_recommendation", return_value=skip_rec) as mock_rec, \
             patch.object(mod, "load_state", return_value=state), \
             patch.object(mod, "save_state"), \
             patch.object(mod, "state_lock", _noop_lock), \
             patch("pathlib.Path.read_text", return_value=json.dumps(settings)), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()

        mock_rec.assert_called_once()


# ── 8. max_position_usd cap ───────────────────────────────────────────────────

class TestMaxPositionCap:
    """With size_up=true, max_position_usd prevents compounding beyond a dollar cap."""

    def _signal(self, ticker="EQT"):
        return {
            "txDate": "2026-05-12", "txType": "purchase",
            "size": "$15,001 - $50,000",
            "asset": {"ticker": ticker},
            "politician": {"name": "Michael McCaul", "id": "M001"},
        }

    def _position(self, symbol, qty, price):
        pos = MagicMock()
        pos.symbol = symbol
        pos.qty = str(qty)
        pos.current_price = str(price)
        return pos

    def _run(self, positions, settings):
        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        state = {"positions": {}, "wheel": {}, "copied_trades": [], "pending_trades": {}}
        skip_rec = {
            "strategy": "SKIP", "confidence": 0, "reasoning": "test",
            "suggested_position_size_pct": 0.0, "key_risk": "",
            "_cache_hit": False, "_tokens_saved": 0,
        }
        import json
        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=positions), \
             patch.object(mod, "get_latest_price", return_value=56.0), \
             patch.object(mod, "fetch_large_trades", return_value=[self._signal()]), \
             patch.object(mod, "get_recommendation", return_value=skip_rec) as mock_rec, \
             patch.object(mod, "load_state", return_value=state), \
             patch.object(mod, "save_state"), \
             patch.object(mod, "state_lock", _noop_lock), \
             patch("pathlib.Path.read_text", return_value=json.dumps(settings)), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()
        return mock_rec

    def test_cap_blocks_claude_when_position_exceeds_limit(self):
        """If position value >= max_position_usd, Claude is never called."""
        settings = {
            "analyze": {"size_up": True, "max_position_usd": 10000},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }
        mock_rec = self._run([self._position("EQT", 200, 56.0)], settings)  # 200×56=$11,200 > $10K
        mock_rec.assert_not_called()

    def test_cap_allows_claude_when_position_below_limit(self):
        """If position value < max_position_usd, signal reaches Claude normally."""
        settings = {
            "analyze": {"size_up": True, "max_position_usd": 10000},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }
        mock_rec = self._run([self._position("EQT", 100, 56.0)], settings)  # 100×56=$5,600 < $10K
        mock_rec.assert_called_once()

    def test_no_cap_allows_unlimited_size_up(self):
        """When max_position_usd is absent, size_up has no ceiling."""
        settings = {
            "analyze": {"size_up": True},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }
        mock_rec = self._run([self._position("EQT", 500, 56.0)], settings)  # no cap
        mock_rec.assert_called_once()


# ── 9. _mark_processed saves immediately ─────────────────────────────────────

class TestMarkProcessedPersistsImmediately:
    """Each signal is saved to copied_trades immediately — survives mid-run crashes."""

    def _signal(self, ticker="OMF", date="2026-05-12", pol_id="M001"):
        return {
            "txDate": date, "txType": "purchase",
            "size": "$15,001 - $50,000",
            "asset": {"ticker": ticker},
            "politician": {"name": "Michael McCaul", "id": pol_id},
        }

    def test_skip_signal_saved_before_next_signal_processed(self):
        """SKIP trade_key is in copied_trades after the first signal — not deferred to end."""
        saved_states = []

        def capture_save(state):
            saved_states.append([k for k in state.get("copied_trades", [])])

        mod = _load_analyze_module()
        acct = MagicMock()
        acct.buying_power = 50_000.0
        initial_state = {"positions": {}, "wheel": {}, "copied_trades": [], "pending_trades": {}}

        import json
        settings = {
            "analyze": {"size_up": False},
            "trailing_stop": {}, "wheel": {}, "smart_money": {}, "schedule": {},
        }
        skip_rec = {
            "strategy": "SKIP", "confidence": 0, "reasoning": "illiquid",
            "suggested_position_size_pct": 0.0, "key_risk": "",
            "_cache_hit": False, "_tokens_saved": 0,
        }

        with patch.object(mod, "get_account", return_value=acct), \
             patch.object(mod, "get_positions", return_value=[]), \
             patch.object(mod, "get_latest_price", return_value=51.0), \
             patch.object(mod, "fetch_large_trades", return_value=[self._signal()]), \
             patch.object(mod, "get_recommendation", return_value=skip_rec), \
             patch.object(mod, "load_state", return_value=initial_state), \
             patch.object(mod, "save_state", side_effect=capture_save), \
             patch.object(mod, "state_lock", _noop_lock), \
             patch("pathlib.Path.read_text", return_value=json.dumps(settings)), \
             patch("sys.argv", ["analyze_and_trade.py"]):
            mod.main()

        # save_state was called and OMF key was persisted
        assert any("2026-05-12_OMF_M001" in k for saved in saved_states for k in saved)
