"""Tests for core/notifier.py — Telegram notifications and approval flow."""
import json
import pytest
from unittest.mock import patch, MagicMock, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_creds(token="test-token", chat_id="123456"):
    return {"telegram": {"bot_token": token, "chat_id": chat_id}}


def _cb_update(update_id, action, trade_key, message_id=1):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cb123",
            "data": f"{action}:{trade_key}",
            "message": {"message_id": message_id},
        },
    }


# ── is_configured ─────────────────────────────────────────────────────────────

class TestIsConfigured:
    @patch("core.notifier._cfg", return_value={"bot_token": "tok", "chat_id": "123"})
    def test_true_when_both_set(self, _):
        from core.notifier import is_configured
        assert is_configured() is True

    @patch("core.notifier._cfg", return_value={"bot_token": "", "chat_id": "123"})
    def test_false_when_token_missing(self, _):
        from core.notifier import is_configured
        assert is_configured() is False

    @patch("core.notifier._cfg", return_value={"bot_token": "tok", "chat_id": ""})
    def test_false_when_chat_id_missing(self, _):
        from core.notifier import is_configured
        assert is_configured() is False

    @patch("core.notifier._cfg", return_value={})
    def test_false_when_empty(self, _):
        from core.notifier import is_configured
        assert is_configured() is False


# ── send_message ──────────────────────────────────────────────────────────────

class TestSendMessage:
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier._chat_id", return_value="123")
    def test_sends_message(self, mock_chat, mock_cfg, mock_post):
        from core.notifier import send_message
        send_message("hello")
        mock_post.assert_called_once_with("sendMessage", {
            "chat_id": "123",
            "text": "hello",
            "parse_mode": "Markdown",
        })

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=False)
    def test_skips_when_not_configured(self, mock_cfg, mock_post):
        from core.notifier import send_message
        send_message("hello")
        mock_post.assert_not_called()


# ── send_trade_approval ───────────────────────────────────────────────────────

class TestSendTradeApproval:
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier._chat_id", return_value="123")
    def test_sends_with_inline_keyboard(self, mock_chat, mock_cfg, mock_post):
        from core.notifier import send_trade_approval
        send_trade_approval(
            trade_key="2026-04-24_NVDA_P001",
            ticker="NVDA", strategy="TRAILING_STOP",
            confidence=85, reasoning="Strong momentum",
            price=875.50, politician="Michael McCaul",
        )
        mock_post.assert_called_once()
        method, payload = mock_post.call_args[0]
        assert method == "sendMessage"
        assert "NVDA" in payload["text"]
        assert "TRAILING_STOP" in payload["text"]
        assert "85%" in payload["text"]
        keyboard = json.loads(payload["reply_markup"])
        buttons = keyboard["inline_keyboard"][0]
        assert any("approve:2026-04-24_NVDA_P001" in b["callback_data"] for b in buttons)
        assert any("skip:2026-04-24_NVDA_P001" in b["callback_data"] for b in buttons)

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=False)
    def test_skips_when_not_configured(self, mock_cfg, mock_post):
        from core.notifier import send_trade_approval
        send_trade_approval("key", "NVDA", "TRAILING_STOP", 80, "reason", 100.0, "McCaul")
        mock_post.assert_not_called()

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    @patch("core.notifier._chat_id", return_value="123")
    def test_truncates_long_reasoning(self, mock_chat, mock_cfg, mock_post):
        from core.notifier import send_trade_approval
        long_reason = "x" * 500
        send_trade_approval("key", "AAPL", "TRAILING_STOP", 90, long_reason, 150.0, "Pelosi")
        _, payload = mock_post.call_args[0]
        assert len(payload["text"]) < 800


# ── send_stop_alert / send_ladder_alert ───────────────────────────────────────

class TestAlertHelpers:
    @patch("core.notifier.send_message")
    def test_stop_alert_content(self, mock_send):
        from core.notifier import send_stop_alert
        send_stop_alert("AAPL", 140.0, 150.0, entry=100.0, qty=10)
        text = mock_send.call_args[0][0]
        assert "AAPL" in text
        assert "140.00" in text
        assert "150.00" in text
        assert "Total Gain" in text
        assert "P&L" in text
        assert "$+400.00" in text  # gross (140-100)*10
        assert "Fees" in text

    @patch("core.notifier.send_message")
    def test_stop_alert_loss(self, mock_send):
        from core.notifier import send_stop_alert
        send_stop_alert("AAPL", 90.0, 85.0, entry=100.0, qty=10)
        text = mock_send.call_args[0][0]
        assert "🔻" in text
        assert "$-100.00" in text  # gross (90-100)*10
        assert "Total Gain" in text
        assert "Fees" in text

    @patch("core.notifier.send_message")
    def test_ladder_alert_content(self, mock_send):
        from core.notifier import send_ladder_alert
        send_ladder_alert("TSLA", 10, 200.0, 0.2)
        text = mock_send.call_args[0][0]
        assert "TSLA" in text
        assert "10" in text
        assert "200.00" in text


# ── poll_approvals ────────────────────────────────────────────────────────────

class TestPollApprovals:
    @patch("core.notifier.is_configured", return_value=False)
    def test_returns_empty_when_not_configured(self, _):
        from core.notifier import poll_approvals
        assert poll_approvals() == []

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_returns_approve_action(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.side_effect = [
            {"result": [_cb_update(1, "approve", "2026-04-24_NVDA_P001")]},
            {},  # answerCallbackQuery
            {},  # editMessageReplyMarkup
        ]
        from core.notifier import poll_approvals
        results = poll_approvals()
        assert len(results) == 1
        assert results[0]["action"] == "approve"
        assert results[0]["trade_key"] == "2026-04-24_NVDA_P001"

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_returns_skip_action(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.side_effect = [
            {"result": [_cb_update(2, "skip", "2026-04-24_AAPL_P002")]},
            {}, {},
        ]
        from core.notifier import poll_approvals
        results = poll_approvals()
        assert results[0]["action"] == "skip"
        assert results[0]["trade_key"] == "2026-04-24_AAPL_P002"

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_advances_last_update_id(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.side_effect = [
            {"result": [_cb_update(42, "approve", "key")]},
            {}, {},
        ]
        from core.notifier import poll_approvals
        poll_approvals()
        assert notifier._LAST_UPDATE_ID == 42

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_ignores_unknown_actions(self, mock_cfg, mock_post):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": [{
            "update_id": 10,
            "callback_query": {
                "id": "cb1", "data": "unknown:key",
                "message": {"message_id": 1},
            },
        }]}
        from core.notifier import poll_approvals
        results = poll_approvals()
        assert results == []

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_ignores_updates_without_callback(self, mock_cfg, mock_post):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": [{"update_id": 5, "message": {"text": "hi"}}]}
        from core.notifier import poll_approvals
        results = poll_approvals()
        assert results == []

    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_empty_result_returns_empty_list(self, mock_cfg, mock_post):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": []}
        from core.notifier import poll_approvals
        assert poll_approvals() == []

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_loglevel_command_sends_legend(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": [{
            "update_id": 10,
            "message": {"text": "/loglevel"},
        }]}
        from core.notifier import poll_approvals
        results = poll_approvals()
        assert results == []
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "0" in text and "1" in text and "2" in text and "3" in text

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_setlevel_command_changes_level(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        notifier._telegram_log_level = 2
        mock_post.return_value = {"result": [{
            "update_id": 11,
            "message": {"text": "/setlevel 1"},
        }]}
        from core.notifier import poll_approvals, get_log_level
        results = poll_approvals()
        assert results == []
        assert get_log_level() == 1
        notifier._telegram_log_level = 2  # reset

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_setlevel_invalid_sends_error(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": [{
            "update_id": 12,
            "message": {"text": "/setlevel 9"},
        }]}
        from core.notifier import poll_approvals
        poll_approvals()
        mock_send.assert_called_once()
        assert "Invalid" in mock_send.call_args[0][0]


# ── tlog ──────────────────────────────────────────────────────────────────────

class TestTlog:
    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_info_sent_at_level_2(self, mock_cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        from core.notifier import tlog
        tlog("flow step", 2)
        mock_send.assert_called_once_with("flow step")

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_debug_not_sent_at_level_2(self, mock_cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        from core.notifier import tlog
        tlog("debug detail", 1)
        mock_send.assert_not_called()

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_debug_sent_at_level_1(self, mock_cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 1
        from core.notifier import tlog
        tlog("api call", 1)
        mock_send.assert_called_once_with("api call")
        notifier._telegram_log_level = 2

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_nothing_sent_at_level_0(self, mock_cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 0
        from core.notifier import tlog
        tlog("anything", 2)
        mock_send.assert_not_called()
        notifier._telegram_log_level = 2

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_error_sent_at_level_3(self, mock_cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 3
        from core.notifier import tlog
        tlog("boom", 3)
        mock_send.assert_called_once_with("boom")
        notifier._telegram_log_level = 2

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_info_not_sent_at_level_3(self, mock_cfg, mock_send):
        import core.notifier as notifier
        notifier._telegram_log_level = 3
        from core.notifier import tlog
        tlog("flow step", 2)
        mock_send.assert_not_called()
        notifier._telegram_log_level = 2


# ── set_log_level / get_log_level ─────────────────────────────────────────────

class TestLogLevel:
    @pytest.fixture(autouse=True)
    def _isolate_settings(self, tmp_path):
        """Redirect _SETTINGS_FILE to a temp file so tests never touch the real config."""
        import json
        import core.notifier as notifier
        real_path = notifier._SETTINGS_FILE
        fake = tmp_path / "settings.json"
        fake.write_text(json.dumps({"telegram_log_level": 2}))
        notifier._SETTINGS_FILE = fake
        yield
        notifier._SETTINGS_FILE = real_path
        notifier._telegram_log_level = 2

    def test_default_is_2(self):
        import core.notifier as notifier
        notifier._telegram_log_level = 2
        from core.notifier import get_log_level
        assert get_log_level() == 2

    def test_set_clamps_below_0(self):
        from core.notifier import set_log_level, get_log_level
        import core.notifier as notifier
        set_log_level(-5)
        assert get_log_level() == 0
        notifier._telegram_log_level = 2

    def test_set_clamps_above_3(self):
        from core.notifier import set_log_level, get_log_level
        import core.notifier as notifier
        set_log_level(99)
        assert get_log_level() == 3
        notifier._telegram_log_level = 2

    def test_set_valid_level(self):
        from core.notifier import set_log_level, get_log_level
        import core.notifier as notifier
        set_log_level(1)
        assert get_log_level() == 1
        notifier._telegram_log_level = 2

    def test_set_persists_to_settings_file(self, tmp_path):
        import json
        import core.notifier as notifier
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"telegram_log_level": 2, "schedule": {}}))
        notifier._SETTINGS_FILE = settings_file  # autouse fixture restores this on teardown

        from core.notifier import set_log_level
        set_log_level(3)

        assert json.loads(settings_file.read_text())["telegram_log_level"] == 3

    def test_set_survives_missing_settings_file(self, tmp_path):
        import core.notifier as notifier
        notifier._SETTINGS_FILE = tmp_path / "nonexistent.json"

        from core.notifier import set_log_level, get_log_level
        set_log_level(1)  # must not raise even though file is missing
        assert get_log_level() == 1


# ── register_command / /help / /summary ───────────────────────────────────────

class TestRegisterCommand:
    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        """Isolate _command_registry between tests."""
        import core.notifier as notifier
        original = dict(notifier._command_registry)
        yield
        notifier._command_registry = original

    def test_register_adds_to_registry(self):
        import core.notifier as notifier
        from core.notifier import register_command
        handler = lambda: None
        register_command("/mycommand", "does something", handler)
        assert "/mycommand" in notifier._command_registry
        desc, fn = notifier._command_registry["/mycommand"]
        assert desc == "does something"
        assert fn is handler

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_registered_command_is_dispatched(self, mock_cfg, mock_send):
        from core.notifier import register_command, _handle_command
        called = []
        register_command("/mycommand", "test", lambda: called.append(True))
        _handle_command("/mycommand")
        assert called == [True]

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_handler_exception_sends_error_message(self, mock_cfg, mock_send):
        from core.notifier import register_command, _handle_command
        register_command("/boom", "explodes", lambda: (_ for _ in ()).throw(RuntimeError("oops")))
        _handle_command("/boom")
        mock_send.assert_called_once()
        assert "Error" in mock_send.call_args[0][0]
        assert "oops" in mock_send.call_args[0][0]

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_unknown_command_sends_hint(self, mock_cfg, mock_send):
        from core.notifier import _handle_command
        _handle_command("/doesnotexist")
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "Unknown" in text
        assert "/help" in text


class TestHelpCommand:
    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        import core.notifier as notifier
        original = dict(notifier._command_registry)
        yield
        notifier._command_registry = original

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_help_lists_builtin_commands(self, mock_cfg, mock_send):
        from core.notifier import _handle_command
        _handle_command("/help")
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "/help" in text
        assert "/summary" in text
        assert "/loglevel" in text
        assert "/setlevel" in text

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_help_includes_registered_commands(self, mock_cfg, mock_send):
        from core.notifier import register_command, _handle_command
        register_command("/status", "show bot status", lambda: None)
        _handle_command("/help")
        text = mock_send.call_args[0][0]
        assert "/status" in text
        assert "show bot status" in text

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_help_via_poll_approvals(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": [{
            "update_id": 20,
            "message": {"text": "/help"},
        }]}
        from core.notifier import poll_approvals
        poll_approvals()
        mock_send.assert_called_once()
        assert "/help" in mock_send.call_args[0][0]


class TestSummaryCommand:
    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        import core.notifier as notifier
        original = dict(notifier._command_registry)
        yield
        notifier._command_registry = original

    @patch("core.notifier.send_message")
    @patch("core.notifier.is_configured", return_value=True)
    def test_summary_command_calls_handler(self, mock_cfg, mock_send):
        from core.notifier import register_command, _handle_command
        calls = []
        register_command("/summary", "portfolio snapshot", lambda: calls.append(True))
        _handle_command("/summary")
        assert calls == [True]

    @patch("core.notifier.send_message")
    @patch("core.notifier._post")
    @patch("core.notifier.is_configured", return_value=True)
    def test_summary_triggered_via_telegram_message(self, mock_cfg, mock_post, mock_send):
        import core.notifier as notifier
        notifier._LAST_UPDATE_ID = 0
        mock_post.return_value = {"result": [{
            "update_id": 21,
            "message": {"text": "/summary"},
        }]}
        calls = []
        from core.notifier import register_command, poll_approvals
        register_command("/summary", "portfolio snapshot", lambda: calls.append(True))
        poll_approvals()
        assert calls == [True]

    def test_load_reads_persisted_level(self, tmp_path):
        import json
        import core.notifier as notifier
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"telegram_log_level": 3}))
        notifier._SETTINGS_FILE = settings_file

        from core.notifier import load_log_level, get_log_level
        load_log_level()
        assert get_log_level() == 3

    def test_load_defaults_to_2_when_key_missing(self, tmp_path):
        import json
        import core.notifier as notifier
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"schedule": {}}))
        notifier._SETTINGS_FILE = settings_file
        notifier._telegram_log_level = 0

        from core.notifier import load_log_level, get_log_level
        load_log_level()
        assert get_log_level() == 2

    def test_load_survives_corrupt_file(self, tmp_path):
        import core.notifier as notifier
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("not valid json{{")
        notifier._SETTINGS_FILE = settings_file

        from core.notifier import load_log_level, get_log_level
        load_log_level()  # must not raise
        assert get_log_level() == 2  # unchanged
