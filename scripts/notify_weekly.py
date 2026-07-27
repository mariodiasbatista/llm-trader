#!/usr/bin/env python3
"""Send the weekly AI strategy-review summary to Telegram.

Usage:
    notify_weekly.py <summary_markdown_file>
    notify_weekly.py --fallback <log_file> <exit_code>

Called by scripts/weekly_ai_review.sh after each weekly cron run. The
"--fallback" form fires when the review agent didn't produce a summary
file (crash, timeout, hit --max-turns) so the run is never silent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.notifier import send_message  # noqa: E402


def main() -> None:
    if sys.argv[1:2] == ["--fallback"]:
        log_file, exit_code = sys.argv[2], sys.argv[3]
        text = (
            "⚠️ *Weekly AI Review — no summary produced*\n\n"
            f"The review agent exited (code `{exit_code}`) without writing a "
            "summary. It may have crashed or hit its turn limit.\n\n"
            f"Raw log: `{log_file}`"
        )
    else:
        summary_path = Path(sys.argv[1])
        body = summary_path.read_text().strip()
        text = f"\U0001f4c5 *Weekly AI Strategy Review*\n\n{body}"

    send_message(text, parse_mode="Markdown")


if __name__ == "__main__":
    main()
