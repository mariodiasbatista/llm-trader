# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LLM Trader connects Claude Code to Alpaca Markets for automated stock and options trading. The system has two layers:

1. **AI Decision Layer** — `claude-opus-4-7` analyzes Capitol Trades politician disclosure data and decides which strategy to apply per signal (Trailing Stop, Wheel, or Skip)
2. **Execution Layer** — Python scripts execute the chosen strategy via Alpaca and log every outcome for performance comparison

Always develop against **Paper Trading** (`"paper": true` in credentials.json).

## First-Time Setup

```bash
bash setup.sh
source .venv/bin/activate
# Edit credentials.json — needs both Alpaca Paper keys AND Anthropic API key
python main.py status
```

`credentials.json` is gitignored. The template is `credentials.json.example`. Both API keys are required.

## Key Commands

```bash
python main.py status                                           # Account overview
python main.py check                                           # Positions with stop floors and gap %
python main.py analyze                                         # AI pipeline: Capitol Trades → Claude → trade
python main.py analyze -p "McCaul" "Pelosi" -d 14 --dry-run   # Preview decisions without trading
python main.py performance                                      # Compare TRAILING_STOP vs WHEEL P&L
python main.py trailing                                        # Run one trailing stop cycle manually
python main.py smart-money -p "McCaul" --buy-only              # Fetch disclosures without AI
python main.py wheel AAPL --contracts 2                        # Start Wheel manually on AAPL
python main.py summary                                         # End-of-day portfolio summary
python main.py scheduler                                       # Start automated scheduler (blocking)
```

## Architecture

```
credentials.json           # Alpaca + Anthropic API keys — gitignored
config/settings.json       # All tunable parameters
agents/
  claude_advisor.py        # Claude Opus 4.7 AI brain — decides TRAILING_STOP / WHEEL / SKIP
core/
  alpaca.py                # Alpaca API wrapper — all buy/sell/quote calls go here
  logger.py                # Structured logging + JSON state persistence
strategies/
  trailing_stop.py         # Trailing floor + laddered buys logic
  wheel.py                 # Cash-secured puts → covered calls → repeat
  smart_money.py           # Capitol Trades API — fetch politician disclosures
scripts/
  analyze_and_trade.py     # Main AI pipeline orchestrator
  strategy_performance.py  # P&L comparison report: which strategy wins?
  check_positions.py       # Portfolio snapshot
  run_trailing_stop.py     # Manual trailing stop check
  smart_money_report.py    # Raw disclosure viewer (no AI)
  setup_wheel.py           # Interactive wheel starter
  daily_summary.py         # EOD report
scheduler/
  market_scheduler.py      # NYSE-hours-only scheduler
logs/
  state.json               # Live strategy state (floors, HWMs, wheel stages) — gitignored
  trades.log               # Append-only JSON trade journal — gitignored
  bot.log                  # Operational logs — gitignored
```

## AI Decision Layer (`agents/claude_advisor.py`)

Claude Opus 4.7 receives each Capitol Trades buy signal and responds with a JSON recommendation:

```json
{
  "strategy": "TRAILING_STOP",
  "confidence": 82,
  "reasoning": "NVDA is a high-momentum semiconductor stock with a large $50K-$100K institutional buy — ideal for trailing stop. Defense/tech sector typical of McCaul holdings.",
  "suggested_position_size_pct": 0.08,
  "key_risk": "Semiconductor sector volatility may trigger stop prematurely"
}
```

**Prompt caching** is applied to the stable system prompt — after the first call, subsequent calls cost ~10x less on the system prompt tokens. The `_cache_hit` flag in the response confirms cache hits.

**Decision logic** (encoded in the system prompt):
- `TRAILING_STOP` → momentum stocks (tech, semiconductors, defense, growth)
- `WHEEL` → stable blue-chips with liquid options (financials, healthcare, consumer staples)
- `SKIP` → sells, illiquid tickers, stale disclosures (>15 days old), insufficient capital

## Performance Tracking

Every AI-executed trade is logged to `logs/trades.log` with the strategy tag embedded in the `notes` field (`strategy=TRAILING_STOP` or `strategy=WHEEL`). Run `python main.py performance` to see:

- Total P&L per strategy (realized + unrealized)
- ROI % per strategy
- Per-ticker breakdown
- Head-to-head winner

The goal is to accumulate enough trades to see which strategy Claude selects most profitably.

## Strategy Configuration (`config/settings.json`)

| Key | Default | Meaning |
|-----|---------|---------|
| `trailing_stop.initial_stop_pct` | 0.10 | Floor starts 10% below entry |
| `trailing_stop.trailing_pct` | 0.05 | Floor trails 5% below running highs |
| `trailing_stop.ladder_buys` | +10 @-20%, +20 @-30% | Auto-buy more on dips |
| `wheel.enabled` | false | Requires options approval on Alpaca |
| `wheel.put_otm_pct` | 0.05 | Sell put 5% below current price |
| `wheel.call_otm_pct` | 0.05 | Sell call 5% above current price |
| `smart_money.politicians` | ["Michael McCaul"] | Politicians to track |
| `smart_money.auto_copy` | false | Rule-based copy (no AI) — prefer `analyze` instead |

## Scheduling

The scheduler only fires during NYSE hours (Mon–Fri 09:30–16:00 ET). Use Claude Code's `/schedule` command:

```
/schedule every 5 minutes: python main.py trailing
/schedule every 60 minutes: python main.py analyze --dry-run
/schedule at 16:05: python main.py summary
```

Or run `python main.py scheduler` in a `tmux` session for a persistent process.

## Capitol Trades Data

`strategies/smart_money.py` uses the free public Capitol Trades API (`https://bff.capitoltrades.com/trades`) — no API key needed. `analyze_and_trade.py` uses this as the input to Claude. Processed trade signals are stored in `logs/state.json` under `copied_trades` to prevent re-processing the same disclosure.

## Wheel — Options Requirements

Requires **Level 2 options approval** on your Alpaca account. Option symbols use OCC format: `AAPL240315C00150000`. Before running in production: roleplay test — *"What would you do if [TICKER] drops to $X?"*

## Data Flow

```
Capitol Trades API
      ↓
strategies/smart_money.py    ← fetch disclosure data
      ↓
agents/claude_advisor.py     ← Claude Opus 4.7 decides strategy (cached system prompt)
      ↓
scripts/analyze_and_trade.py ← execute TRAILING_STOP or WHEEL via Alpaca
      ↓
logs/trades.log              ← append trade with strategy tag
      ↓
scripts/strategy_performance.py ← compare P&L: which strategy wins?
```
