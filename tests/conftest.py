"""Global test isolation — prevents tests from contaminating live config and log files."""
import json
import logging
import pytest


@pytest.fixture(autouse=True)
def _isolate_settings_file(tmp_path):
    """Every test uses a private temp settings.json — real config/settings.json is never touched."""
    import core.notifier as notifier
    fake = tmp_path / "settings.json"
    fake.write_text(json.dumps({"telegram_log_level": 2}))
    original = notifier._SETTINGS_FILE
    notifier._SETTINGS_FILE = fake
    yield fake
    notifier._SETTINGS_FILE = original
    notifier._telegram_log_level = 2


@pytest.fixture(autouse=True)
def _isolate_trade_log(tmp_path):
    """Every test writes trades to a private temp file — real logs/trades.log is never touched."""
    import core.logger as logger_mod
    original = logger_mod.TRADE_LOG
    logger_mod.TRADE_LOG = tmp_path / "trades.log"
    yield
    logger_mod.TRADE_LOG = original


@pytest.fixture(autouse=True)
def _silence_bot_log():
    """Replace the bot.log FileHandler with NullHandler — real logs/bot.log is never touched."""
    import core.logger as logger_mod
    file_handlers = [h for h in logger_mod.log.handlers if isinstance(h, logging.FileHandler)]
    null = logging.NullHandler()
    for h in file_handlers:
        logger_mod.log.removeHandler(h)
    logger_mod.log.addHandler(null)
    yield
    logger_mod.log.removeHandler(null)
    for h in file_handlers:
        logger_mod.log.addHandler(h)
