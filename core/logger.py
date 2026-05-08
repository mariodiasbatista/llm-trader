"""State persistence and structured logging."""
import fcntl
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

STATE_FILE = LOGS_DIR / "state.json"
TRADE_LOG = LOGS_DIR / "trades.log"
_STATE_LOCK_FILE = LOGS_DIR / "state.lock"


@contextmanager
def state_lock():
    """Exclusive file lock around state.json read-modify-write sequences."""
    with open(_STATE_LOCK_FILE, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

log = logging.getLogger("llm-trader")
if not log.handlers:
    log.setLevel(logging.INFO)
    log.propagate = False
    _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    _fh = logging.FileHandler(LOGS_DIR / "bot.log")
    _fh.setFormatter(_fmt)
    log.addHandler(_fh)
    # StreamHandler omitted: systemd redirects stdout to bot.log, which
    # would duplicate every line when running as a service.


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"positions": {}, "wheel": {}, "copied_trades": []}


def save_state(state: dict):
    state["last_updated"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log_trade(action: str, symbol: str, qty, price: float, notes: str = ""):
    entry = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "notes": notes,
    }
    with open(TRADE_LOG, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(entry) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    log.info(f"TRADE | {action:20s} | {qty:>6} {symbol:6s} @ ${price:.2f} | {notes}")
