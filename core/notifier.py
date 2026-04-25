"""Telegram notifications and two-way trade approval."""
import json
from pathlib import Path

import requests

from core.logger import log

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"
_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Tracks the last processed Telegram update ID to avoid replaying callbacks
_LAST_UPDATE_ID = 0

# 0=off  1=debug (all, incl. API calls)  2=info/default  3=error only
_telegram_log_level: int = 2

LEVEL_LEGEND = {
    0: "off — no Telegram messages",
    1: "debug — everything including API calls",
    2: "info — scheduler steps and trades (default)",
    3: "error — warnings and errors only",
}


def set_log_level(level: int) -> None:
    global _telegram_log_level
    _telegram_log_level = max(0, min(3, level))
    log.info(f"Telegram log level → {_telegram_log_level} ({LEVEL_LEGEND[_telegram_log_level]})")


def get_log_level() -> int:
    return _telegram_log_level


def _cfg() -> dict:
    try:
        creds = json.loads(CREDS_FILE.read_text())
        return creds.get("telegram", {})
    except Exception:
        return {}


def _token() -> str:
    return _cfg().get("bot_token", "")


def _chat_id() -> str:
    return str(_cfg().get("chat_id", ""))


def is_configured() -> bool:
    return bool(_token() and _chat_id())


def _post(method: str, payload: dict) -> dict:
    if _telegram_log_level == 1:
        log.debug(f"[telegram] → {method} {payload}")
    try:
        resp = requests.post(
            _TELEGRAM_API.format(token=_token(), method=method),
            json=payload,
            timeout=10,
        )
        result = resp.json()
        if _telegram_log_level == 1:
            log.debug(f"[telegram] ← {result}")
        return result
    except Exception as e:
        log.warning(f"Telegram API error ({method}): {e}")
        return {}


def send_message(text: str) -> None:
    if not is_configured():
        return
    _post("sendMessage", {
        "chat_id": _chat_id(),
        "text": text,
        "parse_mode": "Markdown",
    })


def tlog(message: str, severity: int = 2) -> None:
    """Log locally and forward to Telegram when severity meets the active level.

    severity: 1=debug, 2=info, 3=error
    level setting: 0=off, 1+=debug, 2+=info, 3+=error only
    A message is sent to Telegram when: level != 0 and severity >= level
    """
    if severity == 1:
        log.debug(message)
    elif severity >= 3:
        log.error(message)
    else:
        log.info(message)
    if _telegram_log_level == 0:
        return
    if severity >= _telegram_log_level:
        send_message(message)


def send_trade_approval(trade_key: str, ticker: str, strategy: str,
                         confidence: int, reasoning: str, price: float,
                         politician: str) -> None:
    """Send a Claude recommendation with Approve / Skip inline buttons."""
    if not is_configured():
        return
    text = (
        f"🤖 *Claude recommends {strategy}*\n\n"
        f"*Ticker:* `{ticker}` @ ${price:.2f}\n"
        f"*Politician:* {politician}\n"
        f"*Confidence:* {confidence}%\n"
        f"*Reasoning:* {reasoning[:300]}"
    )
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{trade_key}"},
        {"text": "❌ Skip",    "callback_data": f"skip:{trade_key}"},
    ]]}
    _post("sendMessage", {
        "chat_id": _chat_id(),
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    })


def send_stop_alert(symbol: str, price: float, floor: float) -> None:
    send_message(f"🔴 *STOP TRIGGERED* — `{symbol}`\nPrice ${price:.2f} hit floor ${floor:.2f}")


def send_ladder_alert(symbol: str, qty: int, price: float, drop_pct: float) -> None:
    send_message(f"📉 *LADDER BUY* — `{symbol}`\n{qty} shares @ ${price:.2f} ({drop_pct:.1%} drop from entry)")


def send_summary(text: str) -> None:
    """Send the daily summary — respects log level (info and above)."""
    if _telegram_log_level == 0 or _telegram_log_level > 2:
        return
    send_message(f"📊 *Daily Summary*\n\n{text}")


def _handle_command(text: str) -> None:
    """Dispatch /loglevel and /setlevel N commands received via Telegram."""
    cmd = text.strip().split()
    if cmd[0] == "/loglevel":
        lines = ["*Telegram Log Levels*"]
        for lvl, desc in LEVEL_LEGEND.items():
            marker = " ← active" if lvl == _telegram_log_level else ""
            lines.append(f"`{lvl}` — {desc}{marker}")
        lines.append("\nUse `/setlevel N` to change\\.")
        send_message("\n".join(lines))

    elif cmd[0] == "/setlevel":
        if len(cmd) == 2 and cmd[1].isdigit():
            new_level = int(cmd[1])
            if 0 <= new_level <= 3:
                set_log_level(new_level)
                send_message(
                    f"Log level set to `{new_level}` — {LEVEL_LEGEND[new_level]}"
                )
            else:
                send_message("Invalid level. Use 0–3. Send /loglevel for the legend.")
        else:
            send_message("Usage: `/setlevel N` where N is 0–3. Send /loglevel for legend.")


def poll_approvals() -> list[dict]:
    """Poll Telegram for pending callback button presses and text commands.

    Returns list of approval dicts: [{"action": "approve"|"skip", "trade_key": "..."}]
    Text commands (/loglevel, /setlevel N) are handled as side-effects.
    """
    global _LAST_UPDATE_ID
    if not is_configured():
        return []

    resp = _post("getUpdates", {
        "offset": _LAST_UPDATE_ID + 1,
        "timeout": 0,
        "allowed_updates": ["callback_query", "message"],
    })

    results = []
    for update in resp.get("result", []):
        _LAST_UPDATE_ID = max(_LAST_UPDATE_ID, update["update_id"])

        # Handle text commands
        msg = update.get("message")
        if msg:
            text = msg.get("text", "").strip()
            if text.startswith("/"):
                _handle_command(text)
            continue

        # Handle inline button callbacks (approve/skip)
        cb = update.get("callback_query")
        if not cb:
            continue

        # Acknowledge the button tap so Telegram stops showing the spinner
        _post("answerCallbackQuery", {"callback_query_id": cb["id"]})

        data = cb.get("data", "")
        if ":" not in data:
            continue
        action, trade_key = data.split(":", 1)
        if action in ("approve", "skip"):
            results.append({"action": action, "trade_key": trade_key})
            label = "✅ Approved" if action == "approve" else "❌ Skipped"
            # Edit the original message to show the decision
            _post("editMessageReplyMarkup", {
                "chat_id": _chat_id(),
                "message_id": cb["message"]["message_id"],
                "reply_markup": json.dumps({"inline_keyboard": []}),
            })
            send_message(f"{label} `{trade_key.split('_')[1] if '_' in trade_key else trade_key}`")

    return results
