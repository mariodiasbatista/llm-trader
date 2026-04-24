# Scheduler

Runs automatically during NYSE market hours (Mon–Fri 09:30–16:00 ET).

```bash
source .venv/bin/activate
python main.py scheduler
```

## Schedule

| Interval | Command | Purpose |
|---|---|---|
| Every 5 min | `trailing` | Price-sensitive trailing stop checks — sells if floor is breached |
| Every 15 min | `wheel` | Options wheel management — monitors puts/calls |
| Every 30 min | `analyze` | Capitol Trades → Claude Opus 4.7 → trade execution |
| 16:05 ET daily | `summary` | End of day portfolio report |

## Analyze Params (tunable in `config/settings.json`)

| Setting | Default | Meaning |
|---|---|---|
| `analyze_days` | 2 | Days of disclosures to scan each run |
| `analyze_min_disclosure_value` | 15000 | Min $ value of politician's disclosed trade |
| `analyze_source` | web | Data source: `auto`, `api`, or `web` |
| `analyze_interval_min` | 30 | How often analyze runs (minutes) |

## Running in the background (tmux)

```bash
tmux new -s trader
source .venv/bin/activate
python main.py scheduler
# Ctrl+B then D to detach — keeps running after terminal closes
# tmux attach -t trader  to reattach
```
