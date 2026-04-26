# llm-trader

An AI-powered trading bot connecting **Claude Opus 4.7** to **Alpaca Markets** for automated paper trading.

## How It Works

1. **Signal Source** — Fetches US politician stock disclosure filings from [Capitol Trades](https://capitoltrades.com) (free public API, no key needed). Filters by trade size ≥ $50K to capture significant, high-conviction moves — independent of which politician made them.

2. **AI Decision** — Claude Opus 4.7 analyzes each signal and decides:
   - `TRAILING_STOP` — buy shares + protect with a trailing stop floor (for momentum stocks: tech, semiconductors, defense)
   - `WHEEL` — sell cash-secured puts for premium income (for stable blue-chips with liquid options)
   - `SKIP` — pass on the signal (stale, illiquid, or low conviction)

3. **Execution** — Alpaca Paper Trading API executes the trade.

4. **Performance Tracking** — Every trade is logged with its strategy tag. Run `python main.py performance` to see which strategy wins over time.

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/llm-trader
cd llm-trader
bash setup.sh
source .venv/bin/activate

# Fill in your API keys
cp credentials.json.example credentials.json
# Edit credentials.json with:
#   - Alpaca Paper Trading keys (https://app.alpaca.markets/paper/dashboard/overview)
#   - Anthropic API key (https://console.anthropic.com)

python main.py status
```

## Usage

```bash
# AI full pipeline: Capitol Trades → Claude → execute
python main.py analyze

# Preview Claude's decisions without trading
python main.py analyze --dry-run

# Filter by politician (optional — default watches ALL $50K+ moves)
python main.py analyze --politicians "McCaul" "Pelosi" --days 14

# Compare strategy performance over time
python main.py performance

# Portfolio snapshot with trailing stop floors
python main.py check

# Manual trailing stop check cycle
python main.py trailing

# Browse raw disclosures without AI
python main.py smart-money --buy-only

# Start The Wheel manually on a specific stock
python main.py wheel AAPL --contracts 1

# Start automated background scheduler (NYSE hours only)
python main.py scheduler
```

## Architecture

```
agents/
  claude_advisor.py        ← Claude Opus 4.7 strategy selector (TRAILING_STOP / WHEEL / SKIP)
strategies/
  trailing_stop.py         ← Trailing floor + laddered buys
  wheel.py                 ← Cash-secured puts → covered calls cycle
  smart_money.py           ← Capitol Trades API (by size or by politician)
core/
  alpaca.py                ← All Alpaca API calls
  logger.py                ← State + trade journal
scheduler/
  market_scheduler.py      ← NYSE-hours-only automated scheduler
scripts/
  analyze_and_trade.py     ← Main AI pipeline
  strategy_performance.py  ← P&L comparison report
tests/                     ← 23 unit tests (pytest)
config/settings.json       ← All tunable parameters
```

## Signal Strategy: Size Over Identity

The default mode (`python main.py analyze`) watches for **any** politician buying ≥ $50K — not just a pre-selected list. A $250K buy by an unknown congressman in a defense stock carries the same signal weight as a $250K buy by a famous name. Filtering by identity misses moves. Filtering by conviction size captures them.

Use `--politicians` to narrow to specific names when needed.

## Performance Tracking

Every AI-executed trade is logged to `logs/trades.log` with a strategy tag. Run:

```bash
python main.py performance
```

Output: realized P&L, unrealized P&L, ROI %, and a head-to-head comparison between TRAILING_STOP and WHEEL — so you can identify which strategy Claude picks most profitably over time.

## Strategies

### Trailing Stop (Phase 2)
- Buys shares, sets a stop floor 10% below entry
- Floor trails 5% below each new price high — locks in profits
- Laddered buys: adds 10 shares at -20% drop, 20 shares at -30%
- Auto-sells entire position if price hits the floor

### Wheel (Phase 4 — options approval required)
- Stage 1: Sell cash-secured put 5% below current price → collect premium
- Stage 2: If assigned, sell covered call 5% above current price → collect premium
- Close contracts at 50% profit target
- Repeats indefinitely (Stage 1 → 2 → 1 → ...)

## Tests

```bash
# Unit tests (no credentials needed)
.venv/bin/pytest tests/test_smart_money.py tests/test_trailing_stop.py tests/test_claude_advisor.py -v

# Live Alpaca integration tests (requires credentials.json)
.venv/bin/pytest tests/test_alpaca_connection.py -v
```

23 unit tests, all mocked — no API calls in CI.

## Configuration

Edit `config/settings.json`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trailing_stop.initial_stop_pct` | 0.10 | First floor: 10% below entry |
| `trailing_stop.trailing_pct` | 0.05 | Trail: 5% below running high |
| `smart_money.politicians` | ["Michael McCaul"] | Politicians for named-filter mode |
| `wheel.put_otm_pct` | 0.05 | Sell put 5% below market |
| `wheel.call_otm_pct` | 0.05 | Sell call 5% above market |

## Production Deployment (Server)

### Scheduler as a systemd Service

The scheduler runs as a systemd service so it starts automatically on boot and restarts itself on crash — no manual intervention needed.

```bash
# Check status
systemctl status llmtrader

# Restart manually
systemctl restart llmtrader

# Stop
systemctl stop llmtrader

# Tail logs via journalctl
journalctl -u llmtrader -f
```

The service file is at `/etc/systemd/system/llmtrader.service`. Logs continue to write to `logs/bot.log` as normal.

To set it up on a fresh server:

```bash
# Copy service file and enable
cp deploy/llmtrader.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable llmtrader
systemctl start llmtrader
```

### Memory — Add Swap (1 GB VPS)

On a 1 GB server, running Claude Code + scheduler + MCP servers simultaneously can exhaust RAM and trigger the OOM killer. Add a 2 GB swap file as a safety net:

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

This persists across reboots. Verify with `free -h`.

## Important Notes

- Always use `"paper": true` in `credentials.json` during development
- `credentials.json` is gitignored — never commit it
- The Wheel strategy requires Level 2 options approval on Alpaca
- Use `--dry-run` to preview Claude's decisions before any money moves

## Requirements

- Python 3.10+
- Alpaca Paper Trading account (free)
- Anthropic API key (Claude Opus 4.7)
