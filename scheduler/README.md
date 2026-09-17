# Scheduler

Runs automatically during NYSE market hours (Mon–Fri 09:30–16:00 ET).

In production this runs as a systemd service, not by hand — see "Production" below.

```bash
source .venv/bin/activate
python main.py scheduler
```

## Schedule

| Interval | Job | Purpose |
|---|---|---|
| Every 5 min | `_run_trailing_stop` | Trailing stop check — raises floors, sells on floor breach or take-profit, fires ladder buys |
| Every 15 min | `_run_wheel` | Wheel management — **no-op while `wheel.enabled` is `false`** (`check_and_manage()` returns immediately) |
| Every 30 min | `_run_analyze` | SEC EDGAR Form 4 → `claude-sonnet-4-6` → trade execution (5 min timeout per run) |
| Every 60 min | `_check_data_source` | SEC EDGAR connectivity health check |
| Every 15 sec | `_poll_telegram` | Telegram command polling (`/summary`, `/schedule`, `/help`) |
| 16:05 ET daily | `_run_daily_summary` | End of day portfolio report |

The trailing-stop check and the data-source check also run once immediately on startup.

Only the first three jobs are gated on `is_market_open()` — the daily summary, Telegram polling and health check run regardless of market hours.

## Analyze Params (tunable in `config/settings.json` → `schedule`)

| Setting | Default | Meaning |
|---|---|---|
| `analyze_days` | 1 | Days of Form 4 filings to scan each run |
| `analyze_min_disclosure_value` | 100000 | Min $ value of the insider's open-market buy |
| `analyze_source` | `sec_edgar` | Signal source — SEC EDGAR Form 4 filings |
| `analyze_interval_min` | 30 | How often analyze runs (minutes) |

Note that `analyze_source` is descriptive only: the scheduler invokes
`scripts/analyze_and_trade.py`, which always reads SEC EDGAR. The legacy Capitol
Trades path (`strategies/smart_money.py`) is reachable only via
`python main.py smart-money` and no longer feeds the scheduler.

## Production — systemd

The scheduler runs as `llmtrader.service` with `Restart=always`, so it survives
crashes and reboots. Use systemd rather than starting it by hand:

```bash
systemctl status llmtrader
systemctl restart llmtrader
journalctl -u llmtrader -f
```

A single-instance guard (`_enforce_single_instance`) writes `logs/scheduler.pid`
and SIGTERMs any previous instance on startup, so a stray manual run will kill
the service's process rather than run alongside it.

## Running in the background (tmux — development only)

```bash
tmux new -s trader
source .venv/bin/activate
python main.py scheduler
# Ctrl+B then D to detach — keeps running after terminal closes
# tmux attach -t trader  to reattach
```
