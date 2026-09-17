# Scheduler Flow

Full execution flow from start to first trade.

## Startup

```bash
python main.py scheduler      # in production: systemctl start llmtrader
```

- SIGTERMs any previous scheduler instance and writes `logs/scheduler.pid`
- Loads `config/settings.json`
- Clears any `pending_trades` left over from a previous run (stale by definition)
- Registers all jobs with their intervals
- Logs: `Scheduler started | trailing=5min | wheel=15min | analyze=30min | summary=16:05 ET`
- Runs the trailing-stop check and SEC EDGAR health check immediately
- Enters a loop polling every 10 seconds for what is due to run

---

## Every 5 Minutes — Trailing Stop

Fires only during market hours (Mon–Fri 09:30–16:00 ET).

1. Fetches all open positions from Alpaca
2. On a position's first sight, derives and **stamps** its per-stock take-profit
   into `logs/state.json` (`adaptive_tp`) from that stock's own pre-purchase
   price history — see `strategies/exit_levels.py`. The stamp is reused for the
   position's whole life so the target cannot drift underneath an open trade.
3. For each position, compares current price against the trailing stop floor in `logs/state.json`
4. If gain reaches that position's take-profit target → market sell, logged as `TAKE_PROFIT`
5. If price dropped below the floor → market sell, logged as `STOP_SELL`
6. If price hit a new high → raises the floor to 15% below the new high
7. If price dropped 20%/30% below entry → ladder buy (adds 10/20 more shares)

The floor starts 15% below entry and trails 15% below the running high
(`initial_stop_pct` / `trailing_pct`). The `profit_target_pct` and
`trailing_pct_from_profit` keys in `settings.json` belong to an alternate
"profit-target mode" that only activates when `initial_stop_pct` is `0` — they
are **dormant** under the live config.

---

## Every 30 Minutes — AI Analyze

Fires only during market hours (Mon–Fri 09:30–16:00 ET). Runs as a subprocess
with a 5-minute timeout; a timed-out cycle is skipped, not retried.

1. Fetches the last 1 day of **SEC EDGAR Form 4** filings, keeping only
   open-market purchases (transaction code `P`) of ≥ $100K by high-conviction
   roles. Filings are fetched 6-wide behind a shared rate limiter.
2. Applies the pre-filters before any AI call — price ≥ $50, transaction date
   ≤ 45 days old, not within the 5-day post-stop cooldown, per-ticker position
   cap. Every rejection is logged with a `REJECTED_PREFILTER` marker so the
   filters stay measurable (`scripts/rejection_analysis.py`).
3. For each surviving signal not already in `logs/state.json` → sends to
   **`claude-sonnet-4-6`** (`agents/claude_advisor.py`, cached system prompt)
4. Claude responds with one of:
   - `TRAILING_STOP` → market buy on Alpaca, logged to `logs/trades.log`
   - `WHEEL` → **no trade** — `start_wheel()` refuses while `wheel.enabled` is `false`
   - `SKIP` → no action, logged with a `REJECTED_AI` marker, and deliberately
     **not** marked processed so the signal is re-evaluated next cycle while fresh
5. Marks executed signals as processed in `logs/state.json` so they never fire twice

Trades execute immediately. Telegram is notification-only — there is no
approval step in this path.

---

## Every 60 Minutes — Data Source Health Check

Pings SEC EDGAR full-text search and logs a warning if it is unreachable or
returns a non-200. Runs regardless of market hours.

---

## Every 15 Seconds — Telegram Poll

Polls for Telegram commands (`/summary`, `/schedule`, `/help`). Runs regardless
of market hours.

---

## 16:05 ET Daily — Summary

- Pulls account + positions from Alpaca
- Logs portfolio value, cash, day P&L
- Logs per-position unrealized P&L with trailing stop floors and per-stock targets
- Flags the in-profit position closest to its take-profit target as the next likely exit
- Sends the whole report to Telegram

---

## Key Safeguards

- **Market hours check** on the trailing-stop, wheel and analyze jobs — they never fire on weekends or outside 09:30–16:00 ET
- **Single-instance guard** — a new scheduler kills the previous one rather than double-trading
- **`state.json` deduplication** — the same filing never triggers a trade twice
- **Wheel gated at both ends** — `start_wheel()` and `check_and_manage()` both refuse while `wheel.enabled` is `false`
- **Unconfirmed fills never journaled** — a close order without a confirmed fill leaves the position tracked rather than silently dropped
- **Paper trading** — `credentials.json` has `"paper": true`, all orders go to Alpaca paper account
