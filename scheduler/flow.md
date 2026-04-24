# Scheduler Flow

Full execution flow from start to first trade.

## Startup

```bash
python main.py scheduler
```

- Loads `config/settings.json`
- Registers all jobs with their intervals
- Logs: `Scheduler started | trailing=5min | wheel=15min | analyze=30min | summary=16:05 ET`
- Enters infinite loop checking every 30 seconds what is due to run

---

## Every 5 Minutes — Trailing Stop

Fires only during market hours (Mon–Fri 09:30–16:00 ET).

1. Fetches all open positions from Alpaca
2. For each position, compares current price against the trailing stop floor in `logs/state.json`
3. If price dropped below floor → market sell, logged to `logs/trades.log`
4. If price hit a new high → raises the floor
5. If price dropped 20%+ below entry → ladder buy (adds more shares)

---

## Every 30 Minutes — AI Analyze

Fires only during market hours (Mon–Fri 09:30–16:00 ET).

1. Scrapes `www.capitoltrades.com` for last 2 days of disclosures
2. Filters buys ≥ $15K disclosed value
3. For each new signal not already in `logs/state.json` → sends to **Claude Opus 4.7**
4. Claude responds with one of:
   - `TRAILING_STOP` → market buy on Alpaca, logged to `logs/trades.log`
   - `WHEEL` → sells a cash-secured put, logged to `logs/trades.log`
   - `SKIP` → no action, signal discarded
5. Marks signal as processed in `logs/state.json` so it never fires twice

---

## 16:05 ET Daily — Summary

- Pulls account + positions from Alpaca
- Logs portfolio value, cash, day P&L
- Logs per-position unrealized P&L with trailing stop floors

---

## Key Safeguards

- **Market hours check** on every job — nothing fires on weekends or outside 09:30–16:00 ET
- **`state.json` deduplication** — same disclosure never triggers a trade twice
- **Paper trading** — `credentials.json` has `"paper": true`, all orders go to Alpaca paper account
