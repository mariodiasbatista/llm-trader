# llm-trader

An AI-powered trading bot connecting **Claude Opus 4.7** to **Alpaca Markets** for automated paper trading.

## How It Works

1. **Signal Source** — Fetches [SEC EDGAR Form 4](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany) filings: open-market stock purchases by corporate insiders (CEOs, CFOs, directors, and other officers). Insiders must file within 2 business days of the trade, so signals are near-real-time — a big upgrade over the 31–45 day publication lag of politician disclosure trackers. Filters by transaction value (≥ $100K default) and high-conviction roles.

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
# AI full pipeline: SEC EDGAR Form 4 → Claude → execute
python main.py analyze

# Preview Claude's decisions without trading
python main.py analyze --dry-run

# Widen the window and lower the conviction bar (optional — default is 1 day / $100K)
python main.py analyze --days 14 --min-value 50000

# Compare strategy performance over time
python main.py performance

# Portfolio snapshot with trailing stop floors
python main.py check

# Manual trailing stop check cycle
python main.py trailing

# Browse raw Form 4 insider buy signals without AI
python scripts/insider_report.py --days 1

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
  sec_insiders.py          ← SEC EDGAR Form 4 fetcher (primary signal source)
  smart_money.py           ← Capitol Trades API (legacy, kept for `smart-money` command)
core/
  alpaca.py                ← All Alpaca API calls
  logger.py                ← State + trade journal
scheduler/
  market_scheduler.py      ← NYSE-hours-only automated scheduler
scripts/
  analyze_and_trade.py     ← Main AI pipeline
  insider_report.py        ← Raw SEC Form 4 signal preview (no AI)
  strategy_performance.py  ← P&L comparison report
tests/                     ← 326 unit tests (pytest)
config/settings.json       ← All tunable parameters
```

## Signal Strategy: Conviction Over Volume

The default mode (`python main.py analyze`) watches for **any** corporate insider making an open-market purchase ("P" transaction code — excludes option exercises, RSU vesting, and stock plan grants) of ≥ $100K. It's restricted to high-conviction roles (CEO, CFO, COO, CTO, President, Director, Chairman, EVP/SVP, General Counsel) by default, since a $250K buy from a rank-and-file officer is noisier than the same buy from a CEO.

Use `--all-roles` to include every insider title, and `--min-value` to adjust the conviction bar.

## Performance Tracking

Every AI-executed trade is logged to `logs/trades.log` with a strategy tag. Run:

```bash
python main.py performance
```

Output: realized P&L, unrealized P&L, ROI %, and a head-to-head comparison between TRAILING_STOP and WHEEL — so you can identify which strategy Claude picks most profitably over time.

## Strategies

### Trailing Stop (Phase 2)
- Buys shares, sets a stop floor 10% below entry
- Floor trails 8% below each new price high — locks in profits
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
.venv/bin/pytest tests/test_sec_insiders.py tests/test_trailing_stop.py tests/test_claude_advisor.py -v

# Live Alpaca integration tests (requires credentials.json)
.venv/bin/pytest tests/test_alpaca_connection.py -v
```

326 unit tests, all mocked — no API calls in CI.

## Configuration

Edit `config/settings.json`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trailing_stop.initial_stop_pct` | 0.10 | First floor: 10% below entry |
| `trailing_stop.trailing_pct` | 0.08 | Trail: 8% below running high |
| `sec_insiders.min_transaction_value` | 100000 | Minimum $ value of an insider's open-market buy |
| `sec_insiders.require_high_conviction` | true | Restrict to CEO/CFO/Director-tier roles |
| `analyze.max_txdate_age_days` | 45 | Skip signals whose transaction date is older than this (legal filing deadline) |
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
