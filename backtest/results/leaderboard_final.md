# Backtest Sweep Leaderboard

Generated 2026-07-27T16:12:53 — 300 iterations, 34 real historical positions replayed, 62 historical EDGAR signals fetched.

**Fully-passing candidates found (positive P&L in every sub-period): 0**

---

## #1 — ❌ fails strict bar

**Params changed vs. current config**: (same as current config)

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #2 — ❌ fails strict bar

**Params changed vs. current config**: wheel.put_otm_pct=0.03

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 157 trades, total -$154, worst month -$204, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$5 | 2 (low-N) | ✅ |
  | 2026-05 | +$25 | 30 | ✅ |
  | 2026-06 | +$20 | 66 | ✅ |
  | 2026-07 | -$204 | 59 | ❌ |


---

## #3 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.profit_target_pct=0.02

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #4 — ❌ fails strict bar

**Params changed vs. current config**: wheel.call_otm_pct=0.03

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 145 trades, total -$143, worst month -$175, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$11 | 61 | ✅ |
  | 2026-07 | -$175 | 50 | ❌ |


---

## #5 — ❌ fails strict bar

**Params changed vs. current config**: wheel.put_otm_pct=0.03

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 157 trades, total -$154, worst month -$204, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$5 | 2 (low-N) | ✅ |
  | 2026-05 | +$25 | 30 | ✅ |
  | 2026-06 | +$20 | 66 | ✅ |
  | 2026-07 | -$204 | 59 | ❌ |


---

## #6 — ❌ fails strict bar

**Params changed vs. current config**: sec_insiders.require_high_conviction=False

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #7 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.profit_target_pct=0.0

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #8 — ❌ fails strict bar

**Params changed vs. current config**: sec_insiders.min_transaction_value=150000

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


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

## #9 — ❌ fails strict bar

**Params changed vs. current config**: wheel.call_otm_pct=0.1

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 160 trades, total -$140, worst month -$159, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | -$2 | 66 | ❌ |
  | 2026-07 | -$159 | 60 | ❌ |


---

## #10 — ❌ fails strict bar

**Params changed vs. current config**: trailing_stop.profit_target_pct=0.05

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #11 — ❌ fails strict bar

**Params changed vs. current config**: sec_insiders.require_high_conviction=False

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #12 — ❌ fails strict bar

**Params changed vs. current config**: wheel.profit_close_pct=0.3

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 172 trades, total -$155, worst month -$250, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$4 | 3 | ✅ |
  | 2026-05 | +$29 | 38 | ✅ |
  | 2026-06 | +$62 | 77 | ✅ |
  | 2026-07 | -$250 | 54 | ❌ |


---

## #13 — ❌ fails strict bar

**Params changed vs. current config**: wheel.profit_close_pct=0.3

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 172 trades, total -$155, worst month -$250, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$4 | 3 | ✅ |
  | 2026-05 | +$29 | 38 | ✅ |
  | 2026-06 | +$62 | 77 | ✅ |
  | 2026-07 | -$250 | 54 | ❌ |


---

## #14 — ❌ fails strict bar

**Params changed vs. current config**: wheel.call_otm_pct=0.1

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 160 trades, total -$140, worst month -$159, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | -$2 | 66 | ❌ |
  | 2026-07 | -$159 | 60 | ❌ |


---

## #15 — ❌ fails strict bar

**Params changed vs. current config**: sec_insiders.require_high_conviction=False

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---

## #16 — ❌ fails strict bar

**Params changed vs. current config**: wheel.profit_close_pct=0.3

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 172 trades, total -$155, worst month -$250, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$4 | 3 | ✅ |
  | 2026-05 | +$29 | 38 | ✅ |
  | 2026-06 | +$62 | 77 | ✅ |
  | 2026-07 | -$250 | 54 | ❌ |


---

## #17 — ❌ fails strict bar

**Params changed vs. current config**: wheel.call_otm_pct=0.1

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 160 trades, total -$140, worst month -$159, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | -$2 | 66 | ❌ |
  | 2026-07 | -$159 | 60 | ❌ |


---

## #18 — ❌ fails strict bar

**Params changed vs. current config**: sec_insiders.min_transaction_value=250000

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


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

## #19 — ❌ fails strict bar

**Params changed vs. current config**: wheel.weeks_to_expiry=3

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 108 trades, total +$50, worst month -$114, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$4 | 2 (low-N) | ✅ |
  | 2026-05 | +$33 | 21 | ✅ |
  | 2026-06 | +$126 | 42 | ✅ |
  | 2026-07 | -$114 | 43 | ❌ |


---

## #20 — ❌ fails strict bar

**Params changed vs. current config**: sec_insiders.require_high_conviction=False

**Real trade history (primary score)** — 25 trades, total +$550, worst month -$429, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | -$429 | 1 (low-N) | ❌ |
  | 2026-05 | -$128 | 9 | ❌ |
  | 2026-06 | +$1,490 | 7 | ✅ |
  | 2026-07 | -$383 | 8 | ❌ |


**Synthetic SEC EDGAR replay (secondary evidence)** — 2 trades, total +$416, worst month +$416, PASSES strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-07 | +$416 | 2 (low-N) | ✅ |


**WHEEL estimate (Black-Scholes premiums, no real option data available)** — 149 trades, total -$141, worst month -$167, FAILS strict per-month-positive check.

  | Month | P&L | Trades | Pass |
  |---|---|---|---|
  | 2026-04 | +$3 | 2 (low-N) | ✅ |
  | 2026-05 | +$18 | 32 | ✅ |
  | 2026-06 | +$5 | 61 | ✅ |
  | 2026-07 | -$167 | 54 | ❌ |


---
