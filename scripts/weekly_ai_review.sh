#!/usr/bin/env bash
# Weekly autonomous strategy review — invoked from cron.
#
# Runs `claude -p` in a git worktree NESTED inside this repo (not a sibling —
# nesting is what lets Claude Code resolve it back to this project's
# MEMORY.md/auto-memory, and keeps it inside the write-permission root).
# Never runs in the repo root itself, so it can't disturb the files the live
# scheduler process (main.py scheduler) is reading from.
#
# A Telegram notification always fires at the end, whether or not anything
# changed, success or failure.
set -uo pipefail

REPO="/var/projects/llmTrader"
WORKTREE="$REPO/.weekly-review-worktree"   # nested, NOT a sibling — see above
PY="$REPO/.venv/bin/python3"
TS="$(date +%F_%H%M%S)"
BRANCH="weekly-review-$(date +%F)"
LOGFILE="$REPO/logs/claude-logs-weekly-$TS.log"
SUMMARY_REL="weekly_review_summary.md"                    # relative — see prompt notes
SUMMARY_ABS="$WORKTREE/$SUMMARY_REL"

mkdir -p "$REPO/logs"

# cron runs with a minimal PATH; pytest only exists inside the venv
export PATH="$REPO/.venv/bin:$PATH"

# --- set up (or refresh) the nested worktree, always starting from main ---
cd "$REPO"
if [ ! -d "$WORKTREE" ]; then
    git worktree add "$WORKTREE" main >> "$LOGFILE" 2>&1
fi
cd "$WORKTREE"
# defense-in-depth: a prior run that hit max-turns mid-edit can leave dirty
# state behind (seen in testing) — always start from a clean slate
git checkout -- . >> "$LOGFILE" 2>&1 || true
git clean -fd >> "$LOGFILE" 2>&1 || true
rm -f "$SUMMARY_REL"
git checkout main >> "$LOGFILE" 2>&1
git pull --ff-only origin main >> "$LOGFILE" 2>&1
git branch -D "$BRANCH" >> "$LOGFILE" 2>&1 || true
git checkout -b "$BRANCH" >> "$LOGFILE" 2>&1

# Claude's tool sandbox blocks access to anything outside the worktree,
# even via relative "../" traversal — confirmed empirically (a "wc ../logs/
# state.json" call was blocked mid-run). Rather than granting the agent
# --add-dir access to the REAL logs/ directory (which would also grant write
# access next to files the live scheduler depends on), the plain bash
# wrapper — which isn't sandboxed — copies read-only snapshots in instead.
rm -rf logs-snapshot
mkdir -p logs-snapshot
cp "$REPO/logs/trades.log" logs-snapshot/trades.log 2>/dev/null || true
cp "$REPO/logs/bot.log" logs-snapshot/bot.log 2>/dev/null || true
cp "$REPO/logs/state.json" logs-snapshot/state.json 2>/dev/null || true

# NOTE on paths: Claude's Write/Edit tool hangs waiting for an approval that
# never arrives (no TTY) when given an ABSOLUTE path outside a narrow set it
# trusts implicitly. RELATIVE paths (resolved against cwd, which is this
# worktree) go through cleanly. Verified empirically before wiring this up —
# every Read/Write/Edit instruction below is deliberately relative.
PROMPT="Re-analyze this codebase against the objective: create the most profitable strategy that ensures a buy generates profit on sell.

You are running unattended, on branch $BRANCH (created from latest main), in your current working directory. IMPORTANT: use RELATIVE paths only for every Read/Write/Edit tool call (e.g. 'strategies/wheel.py', '../logs/trades.log') — never absolute paths starting with /. Absolute paths will hang waiting on a permission prompt nobody can answer.

Read-only snapshots of the real historical logs have been copied in for you at these relative paths — read them, but they are throwaway copies so there is no need to avoid writing near them, just don't bother:
  - logs-snapshot/trades.log
  - logs-snapshot/bot.log
  - logs-snapshot/state.json

You have a limited number of turns for this run. Budget them: don't dump large command output straight into the conversation. When you run backtest/analysis scripts, redirect their output to a relative file (e.g. 'python scripts/backtest.py > backtest_output.txt 2>&1') and then grep/read only the parts you need, rather than letting the full output stream into your own context. If you notice you are running low on turns partway through, stop investigating and go straight to step 6 (write the summary, noting the review was cut short and what you'd check next week) rather than leaving an uncommitted half-finished edit behind.

Steps:
1. Analyze the last 7 days of those logs plus recent git history (git log on main) for context on recent strategy changes and their outcomes.
2. Always run a backtest/simulation against ALL historical data (scripts/backtest.py, scripts/strategy_backtest.py, or equivalent in this worktree) to double-check any hypothesis before proposing a change. Do not propose changes based on log-reading alone.
3. Do NOT modify code you can show is generating profit. Only modify code that is in a clear, backtest-confirmed loss logic.
4. If a change is warranted: make it on this branch ($BRANCH), run the test suite (pytest), and only if tests pass, commit, push the branch to origin, then open a PR against main using the GitHub MCP tools (mcp__github__create_pull_request, owner=mariodiasbatista, repo=llm-trader, head=$BRANCH, base=main). Include your backtest evidence in the PR description.
5. If nothing needs changing, make no commits and open no PR — that is a valid and expected outcome most weeks.
6. Regardless of outcome, write a Telegram-ready Markdown summary to exactly this RELATIVE path: $SUMMARY_REL
   The summary must be short (readable in a few seconds on a phone) and include:
   - One-line verdict at the top (e.g. \"Good week, no changes needed\" or \"Found a clear-loss bug, opened a PR\")
   - The key finding(s) and your reasoning in 2-4 bullet points
   - If you intervened: the PR URL as a Markdown link, e.g. [PR #12](https://github.com/mariodiasbatista/llm-trader/pull/12)
   - If you did NOT intervene: one sentence explicitly saying why (e.g. \"trailing-stop config is outperforming its backtest baseline, no clear-loss pattern found\")
7. Explain your full reasoning verbosely as you go (this is captured in the run log for future self-review of past decisions) — but keep step 6's summary file itself short.
8. You have access to this project's MEMORY.md and auto-memory files — use them for context on past decisions, and save new ones (feedback/project type) if this run surfaces something worth remembering for next week."

# --dangerously-skip-permissions / --permission-mode bypassPermissions are both
# hard-refused by Claude Code when running as root (confirmed: this whole
# machine runs cron as root) — so this MUST be a fully-enumerated allowlist,
# not a bypass. `timeout` below is a hard safety net in case any tool call
# still isn't covered and the process hangs waiting on a prompt that can't
# be answered headlessly.
timeout 3600 claude -p "$PROMPT" \
    --permission-mode acceptEdits \
    --allowedTools "Read,Write,Edit,Glob,Grep,TodoWrite,Bash(git *),Bash(pytest *),Bash($PY *),mcp__github__create_pull_request,mcp__github__get_pull_request" \
    --max-turns 150 \
    --output-format stream-json --verbose \
    >> "$LOGFILE" 2>&1

CLAUDE_EXIT=$?

# --- notify: always, rich summary if we have one, minimal fallback if not ---
cd "$REPO"
if [ -s "$SUMMARY_ABS" ]; then
    "$PY" "$REPO/scripts/notify_weekly.py" "$SUMMARY_ABS"
else
    "$PY" "$REPO/scripts/notify_weekly.py" --fallback "$LOGFILE" "$CLAUDE_EXIT"
fi

# --- hygiene: if nothing was pushed this week, drop back to main so the
#     worktree starts clean next Sunday ---
cd "$WORKTREE"
rm -f "$SUMMARY_REL"
rm -rf logs-snapshot
if ! git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git checkout main >> "$LOGFILE" 2>&1
    git branch -D "$BRANCH" >> "$LOGFILE" 2>&1 || true
fi

exit "$CLAUDE_EXIT"
