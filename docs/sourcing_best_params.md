# Sourcing the Best Params

Analysis based on scraping 1,200 trades (100 pages) from Capitol Trades on 2026-04-24.

---

## Recommended Command

```bash
python main.py analyze --days 60 --min-disclosure-value 15000 \
  --politicians "Khanna" "McCaul" "McCormick" "Gottheimer" "Cisneros" "Cohen" \
  --source web --dry-run
```

---

## Parameter Recommendations

### `--days` → 60

65% of disclosures have a **31–45 day filing delay** between when the trade happened
and when it is published on Capitol Trades. A window of 7 days (old default) misses
almost everything. 60 days gives a safe buffer.

| Filing delay | % of trades |
|---|---|
| 0–15 days | 14% |
| 16–30 days | 21% |
| 31–45 days | 65% |

### `--min-disclosure-value` → 15000

98% of buys are under $50,000. The old default of 50,000 filtered out nearly all signals.
Setting to 15,000 cuts the $1K–$15K noise (likely routine rebalancing) while keeping
all meaningful conviction buys.

| Disclosure size | % of buys |
|---|---|
| $1K–$15K | 49% |
| $15K–$50K | 49% |
| $100K+ | 2% |

### `--source` → `web`

The `bff.capitoltrades.com` API returns 503 intermittently. Use `--source web` to scrape
`www.capitoltrades.com` directly as a reliable fallback. Default is `auto` which tries
the API first and falls back automatically.

---

## Politicians to Follow

Ranked by conviction score (large buys weighted 3x + total buys + estimated total value).
Data from 1,200 most recent trades as of 2026-04-24.

### Tier 1 — Must Follow

| Politician | Party | Buys | 50K+ | Est. Total | Notes |
|---|---|---|---|---|---|
| **Ro Khanna** | D-CA | 246 | 9 | $6,188,500 | Most active buyer, tech-heavy (ABNB, AMZN, GOOGL) |
| **Dave McCormick** | R-PA | 14 | 14 | $5,350,000 | 100% conviction rate — every single buy is $50K+, focused on GS |
| **Michael McCaul** | R-TX | 71 | 12 | $3,288,000 | Consistent, diversified across tech/defense/healthcare |

Dave McCormick is the hidden gem — 14 buys, all 14 above $50K. Pure conviction, no noise.

### Tier 2 — Strong Signals

| Politician | Party | Buys | 50K+ | Est. Total | Notes |
|---|---|---|---|---|---|
| **Steve Cohen** | D-CT | 1 | 1 | $750,000 | Single $750K bet — extreme conviction when he moves |
| **Josh Gottheimer** | D-NJ | 12 | 2 | $905,000 | High average size per trade |
| **Richard Blumenthal** | D-CT | 44 | 4 | $1,515,500 | High volume but many unresolved tickers (ETFs/options) |
| **Gil Cisneros** | D-CA | 90 | 2 | $1,327,500 | High volume, tech focused |
| **Rich McCormick** | R-GA | 12 | 1 | $263,000 | Balanced diversified portfolio |

### Tier 3 — Worth Including for Breadth

| Politician | Party | Buys | 50K+ | Est. Total |
|---|---|---|---|---|
| Sheri Biggs | R | 9 | 1 | $263,500 |
| Scott Peters | D-CA | 3 | 2 | $258,000 |
| Thomas Kean Jr | R-NJ | 6 | 2 | $182,000 |
| Tim Moore | R-NC | 8 | 1 | $253,500 |
| John Fetterman | D-PA | 7 | 0 | $56,000 |
| August Pfluger | R-TX | 6 | 0 | $195,000 |
| Rob Bresnahan | R-PA | 2 | 2 | $150,000 |

---

## Key Observations

- **Dave McCormick** is the strongest signal source — 100% of his buys are above $50K,
  meaning zero noise. Every disclosure is a conviction trade.
- **Ro Khanna** generates the most raw signals (246 buys) but many are small. Best used
  with `--min-disclosure-value 15000` to filter out the lowest tier.
- **Steve Cohen** trades rarely but when he does it is a very large position — worth
  monitoring even with low frequency.
- **Richard Blumenthal** has many `N/A` tickers (likely ETFs or options that Capitol
  Trades doesn't map to a ticker), which reduces signal quality.
- The dataset only goes back 3 years and is sorted by publication date. Trading patterns
  may shift over time as politicians' committee assignments change.

---

## Full Dataset Summary (100 pages, 1,200 trades)

- **Total politicians with buys**: 36
- **Date range of tx_dates**: 15–52 days ago (avg 33 days)
- **Buy/Sell split**: ~72% buys / 28% sells
- **Source**: `www.capitoltrades.com` (web scrape, API was unavailable)
