"""Tests for strategies/wheel.py — zero-premium guards, missing-state-key guards."""
import pytest
from unittest.mock import patch, MagicMock


WHEEL_SETTINGS = {
    "enabled": True,
    "put_otm_pct": 0.05,
    "call_otm_pct": 0.05,
    "weeks_to_expiry": 2,
}


def _base_state():
    return {"positions": {}, "wheel": {}, "copied_trades": []}


def _wheel_state(symbol, stage):
    return {
        "positions": {},
        "wheel": {
            symbol: {
                "stage": stage,
                "contracts": 1,
                "expiry": "2026-06-20",
                "put_strike": 95,
                "call_strike": 105,
            }
        },
        "copied_trades": [],
    }


# ── start_wheel: zero premium ─────────────────────────────────────────────────

class TestStartWheelZeroPremium:
    """start_wheel returns {} and submits no order when the option premium quote is 0."""

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.load_state", side_effect=_base_state)
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=0.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_returns_empty_dict(self, mock_settings, mock_price, mock_premium, mock_submit, mock_load, mock_save):
        from strategies.wheel import start_wheel
        result = start_wheel("AAPL", contracts=1)
        assert result == {}

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.load_state", side_effect=_base_state)
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=0.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_does_not_submit_order(self, mock_settings, mock_price, mock_premium, mock_submit, mock_load, mock_save):
        from strategies.wheel import start_wheel
        start_wheel("AAPL", contracts=1)
        mock_submit.assert_not_called()

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.load_state", side_effect=_base_state)
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.log_trade")
    @patch("strategies.wheel.get_option_mid_price", return_value=0.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_does_not_log_trade(self, mock_settings, mock_price, mock_premium, mock_log, mock_submit, mock_load, mock_save):
        from strategies.wheel import start_wheel
        start_wheel("AAPL", contracts=1)
        mock_log.assert_not_called()

    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.log_trade")
    @patch("strategies.wheel.get_option_mid_price", return_value=1.50)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_normal_premium_submits_order(self, mock_settings, mock_price, mock_premium, mock_log, mock_submit):
        """Positive premium must still submit normally — guard doesn't over-block."""
        state = {"positions": {}, "wheel": {}, "copied_trades": []}
        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.save_state"):
            from strategies.wheel import start_wheel
            start_wheel("AAPL", contracts=1)
        mock_submit.assert_called_once()


# ── start_wheel: missing 'wheel' key in state ─────────────────────────────────

class TestStartWheelMissingWheelKey:
    """start_wheel creates the 'wheel' key if it's absent from state.json."""

    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.log_trade")
    @patch("strategies.wheel.get_option_mid_price", return_value=1.50)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_creates_wheel_key_in_state(self, mock_settings, mock_price, mock_premium, mock_log, mock_submit):
        state_without_wheel = {"positions": {}, "copied_trades": []}
        with patch("strategies.wheel.load_state", return_value=state_without_wheel), \
             patch("strategies.wheel.save_state") as mock_save:
            from strategies.wheel import start_wheel
            start_wheel("AAPL", contracts=1)

        saved = mock_save.call_args[0][0]
        assert "wheel" in saved
        assert "AAPL" in saved["wheel"]
        assert saved["wheel"]["AAPL"]["stage"] == 1


# ── check_and_manage: missing 'expiry' key ────────────────────────────────────

class TestCheckManageMissingExpiry:
    """check_and_manage skips wheel positions that have no 'expiry' key."""

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.get_position")
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_skips_without_raising(self, mock_settings, mock_price, mock_pos, mock_save):
        state = {
            "positions": {},
            "wheel": {"AAPL": {"stage": 1, "contracts": 1}},  # no "expiry"
            "copied_trades": [],
        }
        with patch("strategies.wheel.load_state", return_value=state):
            from strategies.wheel import check_and_manage
            result = check_and_manage()

        assert result["actions"] == []

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.get_position")
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_does_not_call_get_position_for_bad_entry(self, mock_settings, mock_price, mock_pos, mock_save):
        """Position shouldn't even be fetched for an entry with no expiry."""
        state = {
            "positions": {},
            "wheel": {"AAPL": {"stage": 1, "contracts": 1}},
            "copied_trades": [],
        }
        with patch("strategies.wheel.load_state", return_value=state):
            from strategies.wheel import check_and_manage
            check_and_manage()

        mock_pos.assert_not_called()


# ── check_and_manage: zero premium during stage transitions ──────────────────

class TestCheckManageZeroPremium:
    """check_and_manage skips stage transitions when option premium is 0."""

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=0.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage1_zero_call_premium_skips_transition(self, mock_settings, mock_price, mock_premium, mock_submit, mock_save):
        """Stage 1 → 2: if call premium is 0, no order submitted and stage unchanged."""
        # 200 shares = put was assigned, should trigger stage 1 → 2
        mock_pos = MagicMock()
        mock_pos.qty = "200"
        state = _wheel_state("NVDA", stage=1)

        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=mock_pos):
            from strategies.wheel import check_and_manage
            result = check_and_manage()

        mock_submit.assert_not_called()
        assert result["actions"] == []

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=0.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage2_zero_put_premium_skips_transition(self, mock_settings, mock_price, mock_premium, mock_submit, mock_save):
        """Stage 2 → 1: if put premium is 0, no order submitted."""
        # None position = shares called away, should trigger stage 2 → 1
        state = _wheel_state("NVDA", stage=2)

        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=None):
            from strategies.wheel import check_and_manage
            result = check_and_manage()

        mock_submit.assert_not_called()
        assert result["actions"] == []

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.log_trade")
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=2.50)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage1_positive_premium_submits_call(self, mock_settings, mock_price, mock_premium, mock_submit, mock_log, mock_save):
        """Positive premium in stage 1 → 2 still submits the call order."""
        mock_pos = MagicMock()
        mock_pos.qty = "200"
        state = _wheel_state("NVDA", stage=1)

        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=mock_pos):
            from strategies.wheel import check_and_manage
            result = check_and_manage()

        mock_submit.assert_called_once()
        assert len(result["actions"]) == 1
        assert "Stage 1→2" in result["actions"][0]


# ── check_and_manage: wheel disabled ─────────────────────────────────────────

class TestCheckManageDisabled:
    @patch("strategies.wheel._settings", return_value={**WHEEL_SETTINGS, "enabled": False})
    def test_returns_disabled_status_when_wheel_off(self, mock_settings):
        from strategies.wheel import check_and_manage
        result = check_and_manage()
        assert result == {"status": "wheel disabled"}

    @patch("strategies.wheel.get_latest_price")
    @patch("strategies.wheel._settings", return_value={**WHEEL_SETTINGS, "enabled": False})
    def test_no_api_calls_when_disabled(self, mock_settings, mock_price):
        from strategies.wheel import check_and_manage
        check_and_manage()
        mock_price.assert_not_called()


# ── check_and_manage: stage 2→1 success path ─────────────────────────────────

class TestCheckManageStage2Success:
    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.log_trade")
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=1.80)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage2_positive_premium_submits_put(
        self, mock_settings, mock_price, mock_premium, mock_submit, mock_log, mock_save
    ):
        """Stage 2 → 1 with a positive premium submits the put and logs the trade."""
        state = _wheel_state("NVDA", stage=2)
        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=None):  # None = called away
            from strategies.wheel import check_and_manage
            result = check_and_manage()

        mock_submit.assert_called_once()
        mock_log.assert_called_once()
        assert len(result["actions"]) == 1
        assert "Stage 2→1" in result["actions"][0]

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.log_trade")
    @patch("strategies.wheel.submit_option_order")
    @patch("strategies.wheel.get_option_mid_price", return_value=1.80)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage2_updates_wheel_state_to_stage1(
        self, mock_settings, mock_price, mock_premium, mock_submit, mock_log, mock_save
    ):
        """After a successful stage 2 → 1 transition, state records stage=1."""
        state = _wheel_state("NVDA", stage=2)
        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=None):
            from strategies.wheel import check_and_manage
            check_and_manage()

        saved = mock_save.call_args[0][0]
        assert saved["wheel"]["NVDA"]["stage"] == 1


# ── check_and_manage: exception handling ─────────────────────────────────────

class TestCheckManageExceptions:
    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.submit_option_order", side_effect=RuntimeError("API error"))
    @patch("strategies.wheel.get_option_mid_price", return_value=2.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage1_exception_does_not_crash(
        self, mock_settings, mock_price, mock_premium, mock_submit, mock_save
    ):
        """submit_option_order failure in stage 1 is caught; loop continues."""
        mock_pos = MagicMock()
        mock_pos.qty = "200"
        state = _wheel_state("NVDA", stage=1)
        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=mock_pos):
            from strategies.wheel import check_and_manage
            result = check_and_manage()  # must not raise

        assert result["actions"] == []

    @patch("strategies.wheel.save_state")
    @patch("strategies.wheel.submit_option_order", side_effect=RuntimeError("API error"))
    @patch("strategies.wheel.get_option_mid_price", return_value=2.0)
    @patch("strategies.wheel.get_latest_price", return_value=100.0)
    @patch("strategies.wheel._settings", return_value=WHEEL_SETTINGS)
    def test_stage2_exception_does_not_crash(
        self, mock_settings, mock_price, mock_premium, mock_submit, mock_save
    ):
        """submit_option_order failure in stage 2 is caught; loop continues."""
        state = _wheel_state("NVDA", stage=2)
        with patch("strategies.wheel.load_state", return_value=state), \
             patch("strategies.wheel.get_position", return_value=None):
            from strategies.wheel import check_and_manage
            result = check_and_manage()  # must not raise

        assert result["actions"] == []
