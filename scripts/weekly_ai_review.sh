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

# --- set up (or refresh) the nested worktree ---
# Uses a dedicated "weekly-base" branch that mirrors origin/main, rather than
# literally checking out "main" — the live directory permanently owns the
# actual "main" branch (git refuses to have the same branch checked out in
# two worktrees at once), so this worktree tracks main's tip under a
# different local name instead.
cd "$REPO"
if [ ! -d "$WORKTREE" ]; then
    git fetch origin main >> "$LOGFILE" 2>&1
    git worktree add -B weekly-base "$WORKTREE" origin/main >> "$LOGFILE" 2>&1
fi
cd "$WORKTREE"
# defense-in-depth: a prior run that hit max-turns mid-edit can leave dirty
# state behind (seen in testing) — always start from a clean slate
git checkout -- . >> "$LOGFILE" 2>&1 || true
git clean -fd >> "$LOGFILE" 2>&1 || true
rm -f "$SUMMARY_REL"
git fetch origin main >> "$LOGFILE" 2>&1
git checkout -B weekly-base origin/main >> "$LOGFILE" 2>&1
git branch -D "$BRANCH" >> "$LOGFILE" 2>&1 || true
git checkout -b "$BRANCH" >> "$LOGFILE" 2>&1

# Claude's tool sandbox blocks access to anything outside the worktree,
# even via relative "../" traversal — confirmed empirically (a "wc ../logs/
# state.json" call was blocked mid-run). Rather than granting the agent
# --add-dir access to the REAL logs/ directory (which would also grant write
# access next to files the live scheduler depends on), the plain bash
# wrapper — which isn't sandboxed — copies fresh read-only snapshots directly
# into the WORKTREE'S OWN logs/ dir (gitignored, so this never gets
# committed). This must be the worktree's real logs/ path, not a
# logs-snapshot/ side directory — scripts/backtest.py and friends
# (strategy_backtest.py, strategy_performance.py, reconcile_state.py,
# backtest/real_trades.py) all hardcode reading a relative "logs/trades.log"
# via cwd, not a configurable path. A prior version copied into
# logs-snapshot/ instead, which none of those scripts ever read, so the
# worktree's logs/ dir silently kept whatever was checked out weeks ago and
# backtests ran against stale data with no error (caught 2026-08-16: 4
# trades missing). git clean -fd (above) does NOT remove these since
# .gitignore'd files are skipped without -x/-X, so without this explicit
# sync they'd never refresh on their own.
mkdir -p logs
cp "$REPO/logs/trades.log" logs/trades.log 2>/dev/null || true
cp "$REPO/logs/bot.log" logs/bot.log 2>/dev/null || true
cp "$REPO/logs/state.json" logs/state.json 2>/dev/null || true

# NOTE on paths: Claude's Write/Edit tool hangs waiting for an approval that
# never arrives (no TTY) when given an ABSOLUTE path outside a narrow set it
# trusts implicitly. RELATIVE paths (resolved against cwd, which is this
# worktree) go through cleanly. Verified empirically before wiring this up —
# every Read/Write/Edit instruction below is deliberately relative.
PROMPT="Re-analyze this codebase against the objective: create the most profitable strategy that ensures a buy generates profit on sell.

You are running unattended, on branch $BRANCH (created from latest main), in your current working directory. IMPORTANT: use RELATIVE paths only for every Read/Write/Edit tool call (e.g. 'strategies/wheel.py', '../logs/trades.log') — never absolute paths starting with /. Absolute paths will hang waiting on a permission prompt nobody can answer.

Fresh read-only snapshots of the real historical logs have been synced into this worktree's own logs/ directory for you — this is also the exact relative path scripts/backtest.py and friends read by default, so no special handling is needed to use them in a backtest:
  - logs/trades.log
  - logs/bot.log
  - logs/state.json
These are throwaway copies (logs/ is gitignored in this repo) — there is no need to avoid writing near them, just don't bother.

You have a limited number of turns for this run. Budget them: don't dump large command output straight into the conversation. When you run backtest/analysis scripts, redirect their output to a relative file (e.g. 'python scripts/backtest.py > backtest_output.txt 2>&1') and then grep/read only the parts you need, rather than letting the full output stream into your own context. If you notice you are running low on turns partway through, stop investigating and go straight to step 6 (write the summary, noting the review was cut short and what you'd check next week) rather than leaving an uncommitted half-finished edit behind.

Steps:
1. Analyze the last 7 days of those logs plus recent git history (git log on weekly-base, which mirrors main) for context on recent strategy changes and their outcomes.
2. Always run a backtest/simulation against ALL historical data (scripts/backtest.py, scripts/strategy_backtest.py, or equivalent in this worktree) to double-check any hypothesis before proposing a change. Do not propose changes based on log-reading alone.
2b. scripts/backtest.py and backtest/sweep.py now report Alpha% (stock return minus SPY return over the same holding window) alongside raw \$ P&L — check it before concluding anything is 'working' or 'broken'. A 2026-08-16 review found trades that looked like they had real upside cut short by a tight stop, but average alpha vs SPY was actually -3.43% (SPY itself rose +8.7% over the window) — the apparent edge was mostly market beta, not stock-picking skill. Positive P&L/win-rate with flat-or-negative alpha means the strategy is riding the market, not beating it; don't recommend exit-parameter changes (wider stops, position sizing, etc.) on P&L/win-rate alone without also checking whether alpha is positive.
2c. THE LIVE EXIT STRATEGY CHANGED ON 2026-08-19 (commit b8d4f62) — do not assume a flat 8%/12% config. Stop and trail are now 15% (the old 8% sat inside the noise band: median max adverse excursion is -10.7%), and take_profit_pct is derived PER STOCK in strategies/exit_levels.py: keep 12% if that stock's own pre-purchase history reached 12% in at least 50% of 20-day windows, otherwise use the level it reached 70% of the time, clamped to [3%, 60%]. The derived value is stamped into state.json per position and reused for that position's life. Positions opened BEFORE 2026-08-19 deliberately stay on the flat 12% and are unstamped — that is intentional (re-deriving mid-trade would have force-closed open winners), so do NOT 'fix' it. When judging exit performance, compare against this as the baseline, and note that trades entered before 2026-08-19 ran under the OLD exit rules — mixing the two eras in one aggregate will mislead you. Its backtested numbers (win rate 36->77%, beat-SPY 39->68%) are IN-SAMPLE on 41 trades; the first genuine out-of-sample read is trades entered after 2026-08-19. Full detail in auto-memory.
2d. OPEN HYPOTHESIS pending out-of-sample validation from ~2026-09-08 onward — if enough NEW trades have accumulated since 2026-08-19, re-test on the fresh slice rather than re-mining the old sample: on the ENTRY side, excluding CFO-titled insider signals / tilting toward Director-titled ones showed an alpha lift across three cuts of a 9-month EDGAR replay. Not implemented. It was discovered by mining a 41-trade sample, and a sensitivity check on a related exit-side idea showed a volatility-scaled variant swinging 8x on an arbitrary lookback choice — so require robustness (insensitivity to arbitrary window/parameter choices) before recommending it, and say so explicitly if the fresh sample is still too small to conclude.
3. Do NOT modify code you can show is generating profit (profit net of alpha vs SPY, not just raw \$). Only modify code that is in a clear, backtest-confirmed loss logic.
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

# --- hygiene: if nothing was pushed this week, drop back to weekly-base so
#     the worktree starts clean next Sunday ---
cd "$WORKTREE"
rm -f "$SUMMARY_REL"
# logs/{trades.log,bot.log,state.json} deliberately left in place — gitignored,
# and get overwritten with a fresh copy at the top of next week's run anyway.
if ! git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git checkout weekly-base >> "$LOGFILE" 2>&1
    git branch -D "$BRANCH" >> "$LOGFILE" 2>&1 || true
fi

exit "$CLAUDE_EXIT"
