# Backtest Sweep Leaderboard

Generated 2026-07-27T01:05:03 — 300 iterations, 34 real historical positions replayed, 62 historical EDGAR signals fetched.

**Fully-passing candidates found (positive P&L in every sub-period): 0**

---

## #1 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #2 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, trailing_stop.profit_target_pct=0.02, position_size_usd=3000, min_entry_price=50

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #3 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, sec_insiders.min_transaction_value=250000

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 0 trades, total +$0, worst month +$0, FAILS strict per-month-positive check.

  _(no trades)_


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #4 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, trailing_stop.profit_target_pct=0.0, position_size_usd=3000, min_entry_price=50

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #5 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.call_otm_pct=0.07

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 153 trades, total -$151, worst month -$174, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$2 | 63 | ✅ |
  | 2026-07 | -$174 | 56 | ❌ |


---

## #6 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.put_otm_pct=0.07

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 147 trades, total -$93, worst month -$126, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$1 | 2 (low-N) | ✅ |
  | 2026-05 | +$27 | 34 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$126 | 50 | ❌ |


---

## #7 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.put_otm_pct=0.1

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 148 trades, total +$1, worst month -$84, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$1 | 3 | ✅ |
  | 2026-05 | +$15 | 35 | ✅ |
  | 2026-06 | +$70 | 65 | ✅ |
  | 2026-07 | -$84 | 45 | ❌ |


---

## #8 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.put_otm_pct=0.07

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 147 trades, total -$93, worst month -$126, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$1 | 2 (low-N) | ✅ |
  | 2026-05 | +$27 | 34 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$126 | 50 | ❌ |


---

## #9 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.call_otm_pct=0.03

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 145 trades, total -$143, worst month -$175, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$11 | 61 | ✅ |
  | 2026-07 | -$175 | 50 | ❌ |


---

## #10 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, sec_insiders.require_high_conviction=False

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #11 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.call_otm_pct=0.1

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 160 trades, total -$140, worst month -$159, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | -$2 | 66 | ❌ |
  | 2026-07 | -$159 | 60 | ❌ |


---

## #12 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, trailing_stop.profit_target_pct=0.05, position_size_usd=3000, min_entry_price=50

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #13 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.call_otm_pct=0.1

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 160 trades, total -$140, worst month -$159, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | -$2 | 66 | ❌ |
  | 2026-07 | -$159 | 60 | ❌ |


---

## #14 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.put_otm_pct=0.07

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 147 trades, total -$93, worst month -$126, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$1 | 2 (low-N) | ✅ |
  | 2026-05 | +$27 | 34 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$126 | 50 | ❌ |


---

## #15 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.put_otm_pct=0.07

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 147 trades, total -$93, worst month -$126, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$1 | 2 (low-N) | ✅ |
  | 2026-05 | +$27 | 34 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$126 | 50 | ❌ |


---

## #16 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, sec_insiders.min_transaction_value=500000

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 0 trades, total +$0, worst month +$0, FAILS strict per-month-positive check.

  _(no trades)_


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #17 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, sec_insiders.min_transaction_value=150000

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 0 trades, total +$0, worst month +$0, FAILS strict per-month-positive check.

  _(no trades)_


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #18 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, sec_insiders.require_high_conviction=False

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #19 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, position_size_usd=3000, min_entry_price=50, wheel.weeks_to_expiry=3

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 108 trades, total +$50, worst month -$114, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$4 | 2 (low-N) | ✅ |
  | 2026-05 | +$33 | 21 | ✅ |
  | 2026-06 | +$126 | 42 | ✅ |
  | 2026-07 | -$114 | 43 | ❌ |


---

## #20 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.initial_stop_pct=0.08, trailing_stop.take_profit_pct=0.06, trailing_stop.ladder_buys_enabled=False, position_size_usd=3000, min_entry_price=50

**Real trade history (primary score)** — 25 trades, total -$178, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | +$455 | 11 | ✅ |
  | 2026-06 | +$174 | 6 | ✅ |
  | 2026-07 | -$378 | 7 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$249, worst month +$0, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-06 | +$249 | 1 (low-N) | ✅ |
  | 2026-07 | +$0 | 1 (low-N) | ❌ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---
