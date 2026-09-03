# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LLM Trader connects Claude Code to Alpaca Markets for automated stock and options trading. The system has two layers:

1. **AI Decision Layer** — `claude-sonnet-4-6` analyzes **SEC EDGAR Form 4 insider-purchase** signals and decides which strategy to apply per signal (Trailing Stop, Wheel, or Skip)
2. **Execution Layer** — Python scripts execute the chosen strategy via Alpaca and log every outcome for performance comparison

WHEEL is currently **disabled** (`wheel.enabled: false`) and gated in code — see "Wheel" below.

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
python main.py status                                    # Account overview
python main.py check                                     # Positions with stop floors and gap %
python main.py analyze                                   # AI pipeline: SEC EDGAR → Claude → trade
python main.py analyze --days 14 --dry-run               # Preview decisions without trading
python main.py analyze --min-value 50000 --all-roles     # Widen the signal filter
python main.py performance                               # Compare TRAILING_STOP vs WHEEL P&L
python main.py trailing                                  # Run one trailing stop cycle manually
python main.py summary                                   # End-of-day portfolio summary
python main.py reconcile-state                           # Fix state.json vs. real Alpaca positions
python main.py scheduler                                 # Start automated scheduler (blocking)
python scripts/insider_report.py --days 1                # Raw Form 4 signals, no AI

python main.py smart-money -p "McCaul"                   # LEGACY Capitol Trades viewer (not the live signal)
python main.py wheel AAPL --contracts 2                  # No-op while wheel.enabled is false
```

## Architecture

```
credentials.json           # Alpaca + Anthropic API keys — gitignored
config/settings.json       # All tunable parameters
agents/
  claude_advisor.py        # claude-sonnet-4-6 AI brain — decides TRAILING_STOP / WHEEL / SKIP
core/
  alpaca.py                # Alpaca API wrapper — all buy/sell/quote calls go here
  logger.py                # Structured logging + JSON state persistence
strategies/
  sec_insiders.py          # SEC EDGAR Form 4 fetcher — THE live signal source
  trailing_stop.py         # Trailing floor + laddered buys logic
  exit_levels.py           # Per-stock take-profit from realized history (pure fns, shared with backtest)
  wheel.py                 # Cash-secured puts → covered calls (disabled)
  smart_money.py           # Capitol Trades API — LEGACY, kept only for `smart-money` command
scripts/
  analyze_and_trade.py     # Main AI pipeline orchestrator
  strategy_performance.py  # P&L comparison report: which strategy wins?
  check_positions.py       # Portfolio snapshot
  run_trailing_stop.py     # Manual trailing stop check
  smart_money_report.py    # Raw disclosure viewer (no AI)
  setup_wheel.py           # Interactive wheel starter
  daily_summary.py         # EOD report
  backtest.py              # 4-scenario comparison vs. actual trade history, with Alpha% vs SPY
  weekly_ai_review.sh       # cron entry point for the autonomous weekly strategy review
  notify_weekly.py          # Telegram summary sender for the weekly review
scheduler/
  market_scheduler.py      # NYSE-hours-only scheduler
backtest/
  benchmark.py              # SPY alpha calc — real edge vs. just riding the market
  real_trades.py            # parses logs/trades.log into per-ticker position records
  replay.py                 # replays TRAILING_STOP against historical bars (shares live evaluate_position())
  sweep.py                  # coordinate-descent parameter sweep, scored on worst-month P&L (+ alpha)
  edge_search.py             # replays SEC EDGAR insider signals over a long window, bucketed by role/value/conviction
  signals.py, trend.py, buckets.py, wheel_replay.py, report.py  # supporting utilities
logs/
  state.json               # Live strategy state (floors, HWMs, wheel stages) — gitignored
  trades.log               # Append-only JSON trade journal — gitignored
  bot.log                  # Operational logs — gitignored
```

## AI Decision Layer (`agents/claude_advisor.py`)

`claude-sonnet-4-6` receives each SEC EDGAR Form 4 insider-buy signal and responds with a JSON recommendation:

```json
{
  "strategy": "TRAILING_STOP",
  "confidence": 72,
  "reasoning": "Pampa Energia is an Argentine energy company with growth exposure; a $1.7M director purchase is a strong conviction signal.",
  "suggested_position_size_pct": 0.08,
  "key_risk": "Argentine macro/currency risk may overwhelm the insider signal"
}
```

**What Claude actually sees per signal** (this is the complete input — `agents/claude_advisor.py`):
insider name, role, company + ticker, shares bought, transaction value, trade date, filing date, signal age, current price, buying power, and whether the ticker is already owned.

It receives **no price history, no volatility, no chart, no fundamentals, no earnings dates, no sector data and no market-regime context.** It cannot see whether the stock is trending, near highs, or falling.

⚠️ **`confidence` is not defined anywhere.** The system prompt specifies only `"confidence": <integer 0-100>` in the output schema — never *confidence in what*. In practice values cluster at 62/68/72/78/82 and mostly restate the prompt's own heuristics ("big buy + senior title → higher number"). Measured against outcomes it correlates **-0.21 with alpha** (higher confidence did slightly *worse*), and the prompt's stated theory is close to inverted vs. the data: $2M+ transactions scored -9.96% alpha and CEO/President buys -9.65%, while Directors — which the prompt treats as *lower* conviction — were the only positive cut at +2.95%.

This matters beyond strategy choice: **`suggested_position_size_pct` sets the position size** (`scripts/analyze_and_trade.py:209` → `shares_budget = buying_power * position_pct`), so an undefined, slightly-negatively-predictive number decides how much capital each trade receives.

⚠️ **The system prompt's stated mechanics are stale**: it tells Claude the trailing stop is *"10% below entry, floor trails 8%"*. Live config is **15%/15% with per-stock adaptive take-profits** (see below). The prompt has not been updated.

**Prompt caching** is applied to the stable system prompt — after the first call, subsequent calls cost ~10x less on the system prompt tokens. The `_cache_hit` flag in the response confirms cache hits. Note the analyze job re-asks about unacted signals every 30 minutes, so the same ticker can generate several calls.

**Decision logic** (encoded in the system prompt):
- `TRAILING_STOP` → momentum stocks (tech, semiconductors, defense, growth); large high-conviction buys; CEO/CFO purchases
- `WHEEL` → stable blue-chips with liquid options (financials, healthcare, consumer staples); Directors at moderate size
- `SKIP` → illiquid/OTC tickers, price already gapped >10% since filing, trivial transaction value, insufficient buying power, sector headwinds

Because WHEEL is disabled and gated in `start_wheel()`, a `WHEEL` verdict currently results in **no trade at all** — it is not silently converted to a TRAILING_STOP.

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
| `trailing_stop.initial_stop_pct` | 0.15 | Floor starts 15% below entry |
| `trailing_stop.trailing_pct` | 0.15 | Floor trails 15% below running highs |
| `trailing_stop.take_profit_pct` | 0.12 | Flat target — kept only for stocks whose history reaches it |
| `trailing_stop.adaptive_take_profit.enabled` | true | Derive take-profit per stock (`strategies/exit_levels.py`); false = flat |
| `trailing_stop.adaptive_take_profit.keep_flat_reach_pct` | 50 | Keep the flat 12% if the stock reached it in ≥ this % of historical 20-day windows |
| `trailing_stop.adaptive_take_profit.target_reach_probability` | 0.7 | Otherwise target the level the stock reaches this often |
| `trailing_stop.adaptive_take_profit.lookback_days` / `horizon_days` | 400 / 20 | History window, and the holding horizon the target is measured over |
| `trailing_stop.ladder_buys` | +10 @-20%, +20 @-30% | Auto-buy more on dips |
| `sec_insiders.min_transaction_value` | 100000 | Minimum $ value of an insider's open-market buy |
| `sec_insiders.require_high_conviction` | true | Restrict to CEO/CFO/Director-tier roles |
| `sec_insiders.days_lookback` / `max_filings` | 1 / 400 | Form 4 scan window and per-run filing cap |
| `analyze.min_entry_price` | 50 | Skip sub-$50 stocks (added 07-27; killed the illiquid-microcap loss pattern) |
| `analyze.max_position_usd` | 3000 | Per-ticker cap on **adding** to an existing position — does *not* cap the initial buy |
| `analyze.max_txdate_age_days` | 45 | Skip signals older than this (insiders may legally file up to 45 days late) |
| `analyze.stop_cooldown_days` | 5 | Days to wait before re-buying a stock that stopped out |
| `analyze.trend_filter_sma_days` | 0 | Per-stock SMA trend filter, **disabled**; `get_sma()` also 403s on this account |
| `wheel.enabled` | false | **Disabled and gated in `start_wheel()`** — see Wheel below |
| `wheel.put_otm_pct` / `call_otm_pct` | 0.05 | Flat 5% OTM strikes for every stock (a known defect — not per-stock) |
| `smart_money.enabled` | false | Legacy Capitol Trades path, superseded by `sec_insiders` |

## Scheduling

The scheduler only fires during NYSE hours (Mon–Fri 09:30–16:00 ET). Use Claude Code's `/schedule` command:

```
/schedule every 5 minutes: python main.py trailing
/schedule every 60 minutes: python main.py analyze --dry-run
/schedule at 16:05: python main.py summary
```

Or run `python main.py scheduler` in a `tmux` session for a persistent process.

## Signal Source — SEC EDGAR Form 4

`strategies/sec_insiders.py` scans SEC EDGAR for Form 4 filings and keeps only **open-market purchases** (transaction code `P` — excludes option exercises, RSU vesting, stock-plan grants) by directors/officers. Insiders must file within 2 business days, so signals are near-real-time. No API key needed, but SEC requires a descriptive `User-Agent` (set in `HEADERS`). Filing fetches run 6-wide via a shared rate limiter to stay under SEC's ~10 req/s cap.

Processed signals are stored in `logs/state.json` under `copied_trades` to prevent re-processing the same disclosure.

`strategies/smart_money.py` (Capitol Trades, politician disclosures) is **legacy** — still reachable via `main.py smart-money` but no longer feeds the live pipeline.

## Wheel — currently disabled

`wheel.enabled` is `false`, and `start_wheel()` refuses to open while it is. Both gates matter: previously only the *management* loop checked the flag, so a wheel could be opened that nothing would ever profit-close, roll, or manage through assignment.

Requires **Level 2 options approval** (this account has level 3). Option symbols use OCC format: `AAPL240315C00150000`. Strikes are resolved against Alpaca's real listed contracts via `core.alpaca.find_option_contract()` — naively rounding a target strike produces symbols that don't exist.

Known gaps before it should be re-enabled: **no stop-loss of any kind** (only exits are profit-close or assignment), flat 5% OTM strikes for every stock, no assignment-risk sizing against available cash, and no cap on concurrent wheels. It also **cannot be backtested** — this account has no OPRA agreement, so `backtest/wheel_replay.py` uses Black-Scholes estimates rather than real option prices.

## Data Flow

```
SEC EDGAR Form 4  (open-market purchases only, ≥$100K, high-conviction roles)
      ↓
strategies/sec_insiders.py   ← fetch + parse filings
      ↓                        filters: min_entry_price $50, max_txdate_age 45d, stop_cooldown 5d
agents/claude_advisor.py     ← claude-sonnet-4-6 picks strategy + position size (cached system prompt)
      ↓
scripts/analyze_and_trade.py ← execute TRAILING_STOP via Alpaca (WHEEL verdicts are gated off)
      ↓
strategies/trailing_stop.py  ← per-stock adaptive take-profit + 15% trailing floor, every 5 min
      ↓
logs/trades.log              ← append trade with strategy tag
      ↓
scripts/backtest.py          ← P&L *and* Alpha% vs SPY — raw P&L alone can't tell edge from market drift
```
