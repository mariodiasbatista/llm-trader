#!/usr/bin/env python3
"""
Live Telegram log-level smoke test.
Sends one message per severity at each level setting so you can verify
what actually arrives in the bot.

Usage:
    python scripts/test_telegram_logs.py
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.notifier import tlog, set_log_level, get_log_level, send_message, LEVEL_LEGEND, is_configured


def section(title: str):
    bar = "─" * 50
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def run():
    if not is_configured():
        print("ERROR: Telegram not configured in credentials.json")
        sys.exit(1)

    print("Telegram log-level smoke test")
    print("Watch your bot for incoming messages.\n")

    # ── Level 0: off ──────────────────────────────────────────────────────────
    section("Level 0 — off (nothing should arrive on Telegram)")
    set_log_level(0)
    tlog("[level=0] debug message — should NOT appear", 1)
    tlog("[level=0] info message  — should NOT appear", 2)
    tlog("[level=0] error message — should NOT appear", 3)
    print("  Sent 3 messages at level=0 (expect NOTHING on Telegram)")
    time.sleep(1)

    # ── Level 3: error only ───────────────────────────────────────────────────
    section("Level 3 — error only")
    set_log_level(3)
    tlog("[level=3] debug message — should NOT appear", 1)
    tlog("[level=3] info message  — should NOT appear", 2)
    tlog("[level=3] ERROR message — should appear ✅", 3)
    print("  Sent 3 messages at level=3 (expect 1 on Telegram: the error)")
    time.sleep(2)

    # ── Level 2: info (default) ───────────────────────────────────────────────
    section("Level 2 — info / default")
    set_log_level(2)
    tlog("[level=2] debug message — should NOT appear", 1)
    tlog("[level=2] INFO message  — should appear ✅", 2)
    tlog("[level=2] ERROR message — should appear ✅", 3)
    print("  Sent 3 messages at level=2 (expect 2 on Telegram: info + error)")
    time.sleep(2)

    # ── Level 1: debug (everything) ───────────────────────────────────────────
    section("Level 1 — debug (all messages)")
    set_log_level(1)
    tlog("[level=1] DEBUG message — should appear ✅", 1)
    tlog("[level=1] INFO message  — should appear ✅", 2)
    tlog("[level=1] ERROR message — should appear ✅", 3)
    print("  Sent 3 messages at level=1 (expect all 3 on Telegram)")
    time.sleep(2)

    # ── Simulate a scheduler flow step ────────────────────────────────────────
    section("Simulated scheduler flow at level=2 (info)")
    set_log_level(2)
    tlog("Scheduler started | trailing=5min | wheel=15min | analyze=30min", 2)
    time.sleep(0.5)
    tlog("Trailing stop check...", 2)
    time.sleep(0.5)
    tlog("Checked 3 positions", 2)
    time.sleep(0.5)
    tlog("AI analyze run (days=2 min_val=$15,000 source=web)...", 2)
    time.sleep(0.5)
    tlog("  [debug] raw API response — should NOT appear at level=2", 1)
    print("  Simulated 4 info steps + 1 debug line (expect 4 on Telegram)")
    time.sleep(2)

    # ── /loglevel command legend ───────────────────────────────────────────────
    section("Sending /loglevel legend to Telegram")
    set_log_level(2)
    lines = ["*Telegram Log Levels*"]
    for lvl, desc in LEVEL_LEGEND.items():
        marker = " <- active" if lvl == get_log_level() else ""
        lines.append(f"`{lvl}` — {desc}{marker}")
    lines.append("\nSend /setlevel N to change the active level.")
    send_message("\n".join(lines))
    print("  Sent legend message")

    # Reset to default
    set_log_level(2)
    print(f"\nDone. Level reset to {get_log_level()} (info/default).")
    print("Check your Telegram bot for the messages above.")


if __name__ == "__main__":
    run()
