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

# External command handlers registered at startup: {"/cmd": (description, callable)}
_command_registry: dict = {}


def register_command(command: str, description: str, handler) -> None:
    """Register a callable for a /command so _handle_command can dispatch it."""
    _command_registry[command] = (description, handler)

LEVEL_LEGEND = {
    0: "off — no Telegram messages",
    1: "debug — everything including API calls",
    2: "info — scheduler steps and trades (default)",
    3: "error — warnings and errors only",
}


_SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def set_log_level(level: int) -> None:
    global _telegram_log_level
    _telegram_log_level = max(0, min(3, level))
    log.info(f"Telegram log level → {_telegram_log_level} ({LEVEL_LEGEND[_telegram_log_level]})")
    try:
        settings = json.loads(_SETTINGS_FILE.read_text())
        settings["telegram_log_level"] = _telegram_log_level
        _SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except Exception as e:
        log.warning(f"Could not persist log level to settings.json: {e}")


def get_log_level() -> int:
    return _telegram_log_level


def load_log_level() -> None:
    """Read telegram_log_level from settings.json and apply it. Called on startup."""
    global _telegram_log_level
    try:
        settings = json.loads(_SETTINGS_FILE.read_text())
        level = int(settings.get("telegram_log_level", 2))
        _telegram_log_level = max(0, min(3, level))
        log.info(f"Telegram log level loaded: {_telegram_log_level} ({LEVEL_LEGEND[_telegram_log_level]})")
    except Exception as e:
        log.warning(f"Could not load log level from settings.json: {e}")


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


def _level_allows(severity: int) -> bool:
    """Return True if the current log level allows sending this severity."""
    return _telegram_log_level != 0 and severity >= _telegram_log_level


def _trading_fees(price: float, qty: float) -> float:
    """Alpaca regulatory fees on a stock sell: SEC fee + FINRA TAF. Zero commission."""
    import math
    proceeds = price * qty
    sec_fee = math.ceil(proceeds * 0.0000278 * 100) / 100
    finra_taf = min(math.ceil(qty * 0.000145 * 100) / 100, 7.27)
    return sec_fee + finra_taf


def send_stop_alert(symbol: str, price: float, floor: float, entry: float = 0, qty: float = 0) -> None:
    if not _level_allows(3):
        return
    pnl = (price - entry) * qty if entry and qty else None
    pnl_pct = ((price - entry) / entry * 100) if entry else None
    total_gain_line = ""
    pnl_line = ""
    if pnl is not None:
        fees = _trading_fees(price, qty)
        total_gain = pnl - fees
        gain_icon = "💰" if total_gain >= 0 else "🔻"
        total_gain_line = f" | {gain_icon} *Total Gain* ${total_gain:+,.2f}"
        pnl_icon = "💰" if pnl >= 0 else "🔻"
        pnl_line = f"\n{pnl_icon} *P&L:* ${pnl:+,.2f} ({pnl_pct:+.1f}%) on {qty:.0f} shares | Fees ${fees:.2f}"
    send_message(
        f"🔴💸 *POSITION CLOSED* — `{symbol}`\n"
        f"Sold @ ${price:.2f} | Floor ${floor:.2f}{total_gain_line}"
        f"{pnl_line}"
    )


def send_ladder_alert(symbol: str, qty: int, price: float, drop_pct: float) -> None:
    if not _level_allows(2):
        return
    send_message(f"📉 *LADDER BUY* — `{symbol}`\n{qty} shares @ ${price:.2f} ({drop_pct:.1%} drop from entry)")


def send_insufficient_funds_alert(symbol: str, needed: float, available: float) -> None:
    if not _level_allows(2):
        return
    send_message(f"⚠️ *SKIPPED — Insufficient Funds* — `{symbol}`\nNeed ${needed:,.0f} | Have ${available:,.0f}")


def send_summary(text: str) -> None:
    """Send the daily summary — respects log level (info and above)."""
    if _telegram_log_level == 0 or _telegram_log_level > 2:
        return
    send_message(f"📊 *Daily Summary*\n\n{text}")


def _handle_command(text: str) -> None:
    """Dispatch Telegram commands."""
    cmd = text.strip().split()

    if cmd[0] == "/help":
        lines = ["*LLM Trader — Available Commands*\n"]
        lines.append("`/help` — show this message")
        lines.append("`/summary` — portfolio snapshot with today & total P&L per position")
        lines.append("`/loglevel` — show current Telegram log level")
        lines.append("`/setlevel N` — set log level (0=off 1=debug 2=info 3=errors only)")
        for cmd_name, (desc, _) in sorted(_command_registry.items()):
            lines.append(f"`{cmd_name}` — {desc}")
        send_message("\n".join(lines))

    elif cmd[0] == "/loglevel":
        lines = ["*Telegram Log Levels*"]
        for lvl, desc in LEVEL_LEGEND.items():
            marker = " ← active" if lvl == _telegram_log_level else ""
            lines.append(f"`{lvl}` — {desc}{marker}")
        lines.append("\nUse `/setlevel N` to change.")
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

    elif cmd[0] in _command_registry:
        _, handler = _command_registry[cmd[0]]
        try:
            handler()
        except Exception as e:
            send_message(f"Error running `{cmd[0]}`: {e}")

    else:
        send_message(f"Unknown command: `{cmd[0]}`\nSend `/help` for available commands.")


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
