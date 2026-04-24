"""Telegram notifications and two-way trade approval."""
import json
from pathlib import Path

import requests

from core.logger import log

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"
_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Tracks the last processed Telegram update ID to avoid replaying callbacks
_LAST_UPDATE_ID = 0


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
    try:
        resp = requests.post(
            _TELEGRAM_API.format(token=_token(), method=method),
            json=payload,
            timeout=10,
        )
        return resp.json()
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
    send_message(f"📊 *Daily Summary*\n\n{text}")


def poll_approvals() -> list[dict]:
    """
    Poll Telegram for pending callback button presses.
    Returns list of dicts: [{"action": "approve"|"skip", "trade_key": "..."}]
    """
    global _LAST_UPDATE_ID
    if not is_configured():
        return []

    resp = _post("getUpdates", {
        "offset": _LAST_UPDATE_ID + 1,
        "timeout": 0,
        "allowed_updates": ["callback_query"],
    })

    results = []
    for update in resp.get("result", []):
        _LAST_UPDATE_ID = max(_LAST_UPDATE_ID, update["update_id"])
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
