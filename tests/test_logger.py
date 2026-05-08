"""Tests for core/logger.py — state_lock mutex and log_trade file writes."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


# ── state_lock ────────────────────────────────────────────────────────────────

class TestStateLock:
    """state_lock is a working exclusive file lock context manager."""

    def test_is_context_manager(self, tmp_path):
        import core.logger as logger
        real_lock = logger._STATE_LOCK_FILE
        logger._STATE_LOCK_FILE = tmp_path / "state.lock"
        try:
            from core.logger import state_lock
            with state_lock():
                pass  # must not raise
        finally:
            logger._STATE_LOCK_FILE = real_lock

    def test_creates_lock_file(self, tmp_path):
        import core.logger as logger
        real_lock = logger._STATE_LOCK_FILE
        lock_path = tmp_path / "state.lock"
        logger._STATE_LOCK_FILE = lock_path
        try:
            from core.logger import state_lock
            with state_lock():
                assert lock_path.exists()
        finally:
            logger._STATE_LOCK_FILE = real_lock

    def test_releases_lock_after_normal_exit(self, tmp_path):
        """After the with block, a second acquisition must succeed immediately."""
        import core.logger as logger
        real_lock = logger._STATE_LOCK_FILE
        logger._STATE_LOCK_FILE = tmp_path / "state.lock"
        try:
            from core.logger import state_lock
            with state_lock():
                pass
            with state_lock():  # would deadlock if lock wasn't released
                pass
        finally:
            logger._STATE_LOCK_FILE = real_lock

    def test_releases_lock_on_exception(self, tmp_path):
        """Lock is released even when an exception is raised inside the block."""
        import core.logger as logger
        real_lock = logger._STATE_LOCK_FILE
        logger._STATE_LOCK_FILE = tmp_path / "state.lock"
        try:
            from core.logger import state_lock
            try:
                with state_lock():
                    raise ValueError("intentional error")
            except ValueError:
                pass
            with state_lock():  # would deadlock if lock wasn't released on exception
                pass
        finally:
            logger._STATE_LOCK_FILE = real_lock


# ── log_trade ─────────────────────────────────────────────────────────────────

class TestLogTrade:
    """log_trade appends valid JSON entries to trades.log."""

    def test_writes_single_entry(self, tmp_path):
        import core.logger as logger
        real_log = logger.TRADE_LOG
        logger.TRADE_LOG = tmp_path / "trades.log"
        try:
            from core.logger import log_trade
            log_trade("TEST_BUY", "AAPL", 10, 150.0, "notes=test")

            lines = (tmp_path / "trades.log").read_text().strip().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["action"] == "TEST_BUY"
            assert entry["symbol"] == "AAPL"
            assert entry["qty"] == 10
            assert entry["price"] == 150.0
            assert entry["notes"] == "notes=test"
            assert "ts" in entry
        finally:
            logger.TRADE_LOG = real_log

    def test_appends_multiple_entries(self, tmp_path):
        import core.logger as logger
        real_log = logger.TRADE_LOG
        logger.TRADE_LOG = tmp_path / "trades.log"
        try:
            from core.logger import log_trade
            log_trade("BUY", "AAPL", 10, 150.0)
            log_trade("SELL", "AAPL", 10, 160.0)
            log_trade("LADDER_BUY", "AAPL", 5, 145.0)

            lines = (tmp_path / "trades.log").read_text().strip().splitlines()
            assert len(lines) == 3
            assert json.loads(lines[0])["action"] == "BUY"
            assert json.loads(lines[1])["action"] == "SELL"
            assert json.loads(lines[2])["action"] == "LADDER_BUY"
        finally:
            logger.TRADE_LOG = real_log

    def test_each_line_is_valid_json(self, tmp_path):
        import core.logger as logger
        real_log = logger.TRADE_LOG
        logger.TRADE_LOG = tmp_path / "trades.log"
        try:
            from core.logger import log_trade
            log_trade("AI_BUY_TRAILING", "NVDA", 5, 875.50, "strategy=TRAILING_STOP")

            raw = (tmp_path / "trades.log").read_text().strip()
            entry = json.loads(raw)  # must not raise
            assert isinstance(entry, dict)
        finally:
            logger.TRADE_LOG = real_log


# ── load_state / save_state ───────────────────────────────────────────────────

class TestLoadSaveState:
    def test_load_returns_defaults_when_file_missing(self, tmp_path):
        import core.logger as logger
        real_state = logger.STATE_FILE
        logger.STATE_FILE = tmp_path / "nonexistent.json"
        try:
            from core.logger import load_state
            state = load_state()
            assert state == {"positions": {}, "wheel": {}, "copied_trades": []}
        finally:
            logger.STATE_FILE = real_state

    def test_save_then_load_roundtrips(self, tmp_path):
        import core.logger as logger
        real_state = logger.STATE_FILE
        logger.STATE_FILE = tmp_path / "state.json"
        try:
            from core.logger import load_state, save_state
            data = {"positions": {"AAPL": {"stop_floor": 90.0}}, "wheel": {}, "copied_trades": ["key1"]}
            save_state(data)
            loaded = load_state()
            assert loaded["positions"]["AAPL"]["stop_floor"] == 90.0
            assert "key1" in loaded["copied_trades"]
        finally:
            logger.STATE_FILE = real_state

    def test_save_adds_last_updated(self, tmp_path):
        import core.logger as logger
        real_state = logger.STATE_FILE
        logger.STATE_FILE = tmp_path / "state.json"
        try:
            from core.logger import save_state, load_state
            save_state({"positions": {}, "wheel": {}, "copied_trades": []})
            loaded = load_state()
            assert "last_updated" in loaded
        finally:
            logger.STATE_FILE = real_state
