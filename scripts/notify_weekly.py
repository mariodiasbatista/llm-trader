#!/usr/bin/env python3
"""Send the weekly AI strategy-review summary to Telegram.

Usage:
    notify_weekly.py <summary_markdown_file>
    notify_weekly.py --fallback <log_file> <exit_code>

Called by scripts/weekly_ai_review.sh after each weekly cron run. The
"--fallback" form fires when the review agent didn't produce a summary
file (crash, timeout, hit --max-turns) so the run is never silent.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core.notifier as notifier  # noqa: E402


def _md_to_telegram_html(text: str) -> str:
    """Convert the agent's GitHub-flavored Markdown (**bold**, [text](url), `code`)
    into Telegram-safe HTML. Telegram's legacy parse_mode="Markdown" only supports
    single-asterisk bold and has no tolerance for unmatched/nested entities — a
    2026-08-09 summary broke it with a 400 "can't parse entities" error, which
    silently dropped the entire notification (send failures are logged, not
    raised). HTML only requires escaping &/</>, which auto-generated financial
    text (full of %, $, parens, hyphens) is far less likely to break.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def _send_with_fallback(raw_text: str) -> None:
    """Try Telegram-HTML first; if that ever fails for any reason, fall back to
    unformatted plain text rather than risk losing the notification entirely."""
    html_payload = {
        "chat_id": notifier._chat_id(),
        "text": _md_to_telegram_html(raw_text),
        "parse_mode": "HTML",
    }
    if notifier._post("sendMessage", html_payload).get("ok"):
        return
    notifier._post("sendMessage", {"chat_id": notifier._chat_id(), "text": raw_text})


def main() -> None:
    if not notifier.is_configured():
        print("Telegram not configured — skipping notification", file=sys.stderr)
        return

    if sys.argv[1:2] == ["--fallback"]:
        log_file, exit_code = sys.argv[2], sys.argv[3]
        text = (
            "⚠️ Weekly AI Review — no summary produced\n\n"
            f"The review agent exited (code {exit_code}) without writing a "
            "summary. It may have crashed or hit its turn limit.\n\n"
            f"Raw log: {log_file}"
        )
    else:
        summary_path = Path(sys.argv[1])
        body = summary_path.read_text().strip()
        text = f"\U0001f4c5 Weekly AI Strategy Review\n\n{body}"

    _send_with_fallback(text)


if __name__ == "__main__":
    main()
