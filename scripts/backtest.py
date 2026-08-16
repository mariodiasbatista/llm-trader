#!/usr/bin/env python3
"""
Backtest: 4 Scenario Comparison vs Actual Trade History
Compares actual results against counterfactual filter/sizing rules.

Scenarios:
  0 - Actual (baseline): what really happened
  1 - 7-day txDate filter: exclude trades where politician's txDate > 7 days before buy
  2 - Reduced position size (3% cap instead of 5-8%)
  3 - Trend filter: only buy if entry price > 20-day SMA at buy date
  4 - All filters combined (Scenarios 1 + 2 + 3)
"""

import sys
import json
import re
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Credentials ──────────────────────────────────────────────────────────────
CREDS_FILE = Path(__file__).parent.parent / "credentials.json"
TRADES_LOG  = Path(__file__).parent.parent / "logs" / "trades.log"

creds = json.loads(CREDS_FILE.read_text())
alpaca_cfg = creds["alpaca"]
ALPACA_KEY    = alpaca_cfg["api_key"]
ALPACA_SECRET = alpaca_cfg["secret_key"]

# ── Alpaca data client ────────────────────────────────────────────────────────
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

data_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Parse trades.log — only TRAILING_STOP entries
# (parsing logic lives in backtest/real_trades.py, shared with the sweep tooling)
# ─────────────────────────────────────────────────────────────────────────────

from backtest.real_trades import parse_trades_log
from backtest.benchmark import fetch_benchmark_closes, benchmark_return_pct, alpha_pct, summarize_alpha


def extract_position_pct(notes: str) -> float:
    """
    Try to extract the suggested_position_size_pct from the notes field.
    If not present, default to 0.06 (midpoint of 5-8% range).
    """
    # The notes field from AI_BUY_TRAILING has confidence but not position_pct
    # Position pct was passed to market_buy at runtime; we can infer from qty and account.
    # We don't have account equity at exact time, so use default.
    # For tickers with confidence info we can use known defaults.
    # Default: claude usually suggests 0.05-0.08. Use 0.06 as midpoint default.
    return 0.06


def extract_confidence(notes: str) -> int:
    """Extract confidence % from notes."""
    m = re.search(r"confidence=(\d+)%", notes or "")
    return int(m.group(1)) if m else 68


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Build per-ticker position history
# (moved to backtest/real_trades.py, shared with the sweep tooling)
# ─────────────────────────────────────────────────────────────────────────────

from backtest.real_trades import build_positions


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: txDate knowledge (reconstructed from bot.log + state.json)
# ─────────────────────────────────────────────────────────────────────────────

# Reconstructed from bot.log analysis:
# - "Signal too old (YYYY-MM-DD)" messages confirm publishedDate/txDate used at scan time
# - copied_trades keys {txDate}_{ticker}_{polId} give exact txDate for those tickers
# - For tickers in 60-day scan at inception (BA/GLW/GE), txDate unknown → assume within window
#
# Summary of txDate ages at time of buy:
TX_DATE_KNOWLEDGE = {
    # From bot.log line 12233 (2026-05-13) confirms txDate for these:
    # After first buys on 2026-05-11, a later run found *new* signals with old txDates.
    # The initial buys on 2026-05-11 passed because max_txdate_age_days=45 was the filter.
    # So we know AESI txDate=2026-03-30, MRVL=2026-04-06, CRM=2026-04-06, EQT=2026-04-09
    "AESI": "2026-03-30",   # buy 2026-05-11, 42 days old
    "MRVL": "2026-04-06",   # buy 2026-05-11, 35 days old
    "CRM":  "2026-04-06",   # buy 2026-05-11, 35 days old
    "EQT":  "2026-04-09",   # buy 2026-05-11, 32 days old

    # From copied_trades keys in state.json:
    "MSFT": "2026-05-19",   # bought 2026-06-04, 16 days old (2026-05-19_MSFT_G000583)
    "PH":   "2026-05-15",   # bought 2026-06-01, 17 days old (2026-05-15_PH_T000490)
    "BWXT": "2026-05-15",   # bought 2026-06-08, 24 days old (2026-05-15_BWXT_M001232)
    "DDOG": "2026-05-19",   # bought 2026-06-09, 21 days old (2026-05-19_DDOG_S000168)
    "AGX":  "2026-06-30",   # bought 2026-07-03,  3 days old (2026-06-30_AGX_C001123)
    "COHR": "2026-06-25",   # bought 2026-07-09, 14 days old (2026-06-25_COHR_W000802)
    "AVGO": "2026-06-05",   # bought 2026-07-09, 34 days old (2026-06-05_AVGO_K000389)
    "TSM":  "2026-06-18",   # bought 2026-07-14, 26 days old (2026-06-18_TSM_M001157)

    # For these, no txDate found but buys were in 7-day publishedDate scans.
    # With max_txdate_age_days=45 the politician could have traded up to 45 days before.
    # ASSUMPTION: if no txDate in log/state, treat as fresh (within 7 days) = conservative.
    # BA, GLW, GE: 60-day lookback scan, Salazar - disclosure was April 24 publish, likely traded ~April 15-24
    #   → assume txDate ~April 15-24. Buy was April 24. Max 9 days → within 7-day window? Borderline.
    #   → Without explicit date, assume FRESH (no filter).
    # ULTA, RH: Telegram-approved; signal was from the 2026-04-29 scan (days=32 scan context seen).
    #   Actually RH/ULTA were in a 32-signal run on 2026-04-29. No txDate info. Assume fresh.
    # TDG: 2026-05-07, 7-day scan → likely txDate >=2026-04-30. Buy 2026-05-07 → <=7 days → FRESH
    # CARR: 2026-05-11, 7-day scan, Salazar → txDate from prior week, assume fresh
    # NSIT, TER, HURN, KEYS: 2026-05-11, McCaul disclosure - McCaul files frequently, likely recent
    #   → Assume fresh (no explicit evidence of staleness)
    # AAPL: 2026-06-03, 7-day scan, Ed Case → no txDate found, assume fresh
}

# Default: if not in TX_DATE_KNOWLEDGE, assume txDate = same as buy date (fresh)
ASSUME_FRESH_IF_UNKNOWN = True


def get_tx_age_days(symbol: str, buy_date) -> int:
    """Return how many days old the txDate was at time of buy. -1 = unknown (assume fresh)."""
    tx_date_str = TX_DATE_KNOWLEDGE.get(symbol)
    if tx_date_str is None:
        return 0 if ASSUME_FRESH_IF_UNKNOWN else -1
    tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d").date()
    return (buy_date - tx_date).days


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Fetch current price for open positions
# ─────────────────────────────────────────────────────────────────────────────

_price_cache = {}

def get_current_price(symbol: str) -> float:
    """Fetch latest trade price from Alpaca."""
    if symbol in _price_cache:
        return _price_cache[symbol]
    try:
        from alpaca.data.requests import StockLatestTradeRequest
        req = StockLatestTradeRequest(symbol_or_symbols=[symbol])
        resp = data_client.get_stock_latest_trade(req)
        price = float(resp[symbol].price)
        _price_cache[symbol] = price
        return price
    except Exception:
        # Fallback to latest bar
        try:
            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Day,
                limit=1,
            )
            bars = data_client.get_stock_bars(req)
            bar_list = bars[symbol]
            price = float(bar_list[-1].close)
            _price_cache[symbol] = price
            return price
        except Exception as e:
            print(f"  WARNING: cannot get price for {symbol}: {e}")
            return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Fetch 20-day SMA at buy date (Scenario 3)
# ─────────────────────────────────────────────────────────────────────────────

_sma_cache = {}

def get_20day_sma(symbol: str, buy_date) -> float | None:
    """
    Fetch 30 daily bars ending on buy_date and compute 20-day SMA.
    Returns None if data unavailable.
    BarSet subscript returns a list directly (bars[symbol] → list of Bar).
    """
    cache_key = (symbol, buy_date)
    if cache_key in _sma_cache:
        return _sma_cache[cache_key]

    try:
        end_dt   = datetime.combine(buy_date, datetime.min.time())
        start_dt = end_dt - timedelta(days=45)  # Fetch ~45 days to get 30 trading days

        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt + timedelta(days=1),
        )
        barset = data_client.get_stock_bars(req)
        # BarSet supports direct subscript → list of Bar objects
        bar_list = barset[symbol] if symbol in barset.data else []

        if not bar_list or len(bar_list) < 20:
            _sma_cache[cache_key] = None
            return None

        # Use up to 20 bars ending on or before buy_date
        closes = [float(b.close) for b in bar_list]
        last_20 = closes[-20:]
        sma = sum(last_20) / len(last_20)
        _sma_cache[cache_key] = sma
        return sma

    except Exception as e:
        print(f"  WARNING: SMA fetch failed for {symbol} on {buy_date}: {e}")
        _sma_cache[cache_key] = None
        return None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Compute realized PnL per position
# ─────────────────────────────────────────────────────────────────────────────

def compute_pnl(pos: dict, current_prices: dict) -> dict:
    """
    Compute actual realized + unrealized PnL for a position.
    Returns dict with pnl, deployed_capital, exit_price.
    """
    sym         = pos["symbol"]
    total_cost  = pos["total_cost"]
    total_qty   = pos["total_qty"]
    avg_entry   = pos["avg_entry"]

    if pos["is_open"]:
        current = current_prices.get(sym, get_current_price(sym))
        exit_p  = current
        pnl     = (exit_p - avg_entry) * total_qty
    else:
        exits   = pos["exits"]
        # If partial exits exist (ladder buys may lead to partial sells), compute:
        sold_qty  = sum(e["qty"] for e in exits)
        sold_cost = sum(e["qty"] * e["price"] for e in exits)
        entry_cost_for_sold = avg_entry * sold_qty
        pnl = sold_cost - entry_cost_for_sold
        exit_p = pos["exit_price"]

    return {
        "pnl": pnl,
        "deployed": total_cost,
        "exit_price": exit_p,
    }


def compute_trade_alpha(pos: dict, exit_price: float, spy_closes: dict) -> float | None:
    """Alpha vs. SPY over the position's actual [entry_date, exit_date] window —
    None if benchmark data is unavailable for that window."""
    entry_date = pos["first_buy_date"]
    exit_date = date.fromisoformat(pos["exit_ts"][:10]) if (not pos["is_open"] and pos["exit_ts"]) else date.today()
    return alpha_pct(pos["avg_entry"], exit_price, spy_closes, entry_date, exit_date)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Scenario evaluation
# ─────────────────────────────────────────────────────────────────────────────

SCENARIO_NAMES = {
    0: "Actual (Baseline)",
    1: "7-day txDate Filter",
    2: "3% Position Size Cap",
    3: "Trend Filter (>20-day SMA)",
    4: "All Filters Combined",
}

DEFAULT_POSITION_PCT  = 0.06   # used when actual pct unknown
REDUCED_POSITION_PCT  = 0.03   # Scenario 2 cap


def is_filtered_staleness(pos: dict) -> bool:
    """Scenario 1: True if txDate was > 7 days before buy."""
    tx_age = get_tx_age_days(pos["symbol"], pos["first_buy_date"])
    return tx_age > 7


def is_filtered_trend(pos: dict, sma_map: dict) -> bool:
    """Scenario 3: True if entry price was BELOW 20-day SMA → trend filter removes it."""
    sym   = pos["symbol"]
    entry = pos["avg_entry"]
    sma   = sma_map.get(sym)
    if sma is None:
        return False  # Can't compute → keep trade
    return entry < sma  # Entry below SMA → downtrend → skip


def scale_pnl_to_reduced_size(pos: dict, actual_pnl: float) -> float:
    """
    Scenario 2: Scale PnL down to 3% position size from actual size.
    actual_pct is estimated as DEFAULT_POSITION_PCT (0.06) since
    the exact account equity per trade is not logged.
    """
    actual_pct = DEFAULT_POSITION_PCT
    if actual_pct <= REDUCED_POSITION_PCT:
        return actual_pnl  # Already at or below cap, no scaling
    scale = REDUCED_POSITION_PCT / actual_pct
    return actual_pnl * scale


def scale_deployed_to_reduced_size(deployed: float) -> float:
    """Scale deployed capital to 3% equivalent."""
    scale = REDUCED_POSITION_PCT / DEFAULT_POSITION_PCT
    return deployed * scale


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Run all scenarios
# ─────────────────────────────────────────────────────────────────────────────

def run_scenarios(positions: list, current_prices: dict, sma_map: dict, spy_closes: dict):
    """
    For each scenario, compute aggregate metrics.
    Returns dict: scenario_id → metrics dict.
    """
    results = {}

    for scen_id in range(5):
        trades_included  = []
        trades_excluded  = []
        total_pnl        = 0.0
        total_deployed   = 0.0
        wins             = 0
        losses           = 0
        win_amounts      = []
        loss_amounts     = []

        for pos in positions:
            sym = pos["symbol"]

            # Evaluate filters for this scenario
            stale_filtered  = is_filtered_staleness(pos)
            trend_filtered  = is_filtered_trend(pos, sma_map)

            # Scenario logic
            if scen_id == 0:
                excluded = False
                size_scaled = False
            elif scen_id == 1:
                excluded   = stale_filtered
                size_scaled = False
            elif scen_id == 2:
                excluded   = False
                size_scaled = True
            elif scen_id == 3:
                excluded   = trend_filtered
                size_scaled = False
            elif scen_id == 4:
                excluded   = stale_filtered or trend_filtered
                size_scaled = True  # also apply 3% cap

            if excluded:
                trades_excluded.append({
                    "symbol": sym,
                    "reason": ("stale txDate" if stale_filtered else "") +
                              (" + below SMA" if trend_filtered else ""),
                })
                continue

            # Compute PnL
            pnl_data  = compute_pnl(pos, current_prices)
            raw_pnl   = pnl_data["pnl"]
            raw_deployed = pnl_data["deployed"]
            alpha     = compute_trade_alpha(pos, pnl_data["exit_price"], spy_closes)

            if size_scaled:
                pnl      = scale_pnl_to_reduced_size(pos, raw_pnl)
                deployed = scale_deployed_to_reduced_size(raw_deployed)
            else:
                pnl      = raw_pnl
                deployed = raw_deployed

            total_pnl      += pnl
            total_deployed += deployed

            if pnl >= 0:
                wins += 1
                win_amounts.append(pnl)
            else:
                losses += 1
                loss_amounts.append(pnl)

            trades_included.append({
                "symbol":   sym,
                "pnl":      pnl,
                "deployed": deployed,
                "is_open":  pos["is_open"],
                "stale":    stale_filtered,
                "below_sma": trend_filtered,
                "exit_price": pnl_data["exit_price"],
                "avg_entry":  pos["avg_entry"],
                "sma":       sma_map.get(sym),
                "tx_age":    get_tx_age_days(sym, pos["first_buy_date"]),
                "alpha_pct": alpha,
            })

        n_trades  = len(trades_included)
        roi       = (total_pnl / total_deployed * 100) if total_deployed > 0 else 0
        win_rate  = (wins / n_trades * 100) if n_trades > 0 else 0
        avg_win   = sum(win_amounts) / len(win_amounts) if win_amounts else 0
        avg_loss  = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0
        alpha_summary = summarize_alpha([t["alpha_pct"] for t in trades_included if t["alpha_pct"] is not None])

        results[scen_id] = {
            "n_trades":         n_trades,
            "total_deployed":   total_deployed,
            "total_pnl":        total_pnl,
            "roi":              roi,
            "win_rate":         win_rate,
            "avg_win":          avg_win,
            "avg_loss":         avg_loss,
            "trades_included":  trades_included,
            "trades_excluded":  trades_excluded,
            "avg_alpha_pct":    alpha_summary["avg_alpha_pct"],
            "pct_positive_alpha": alpha_summary["pct_positive_alpha"],
        }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: Print results
# ─────────────────────────────────────────────────────────────────────────────

def print_header(title: str):
    print(f"\n{'═' * 90}")
    print(f"  {title}")
    print(f"{'═' * 90}")


def print_scenario_table(scenario_results: dict, spy_window_return: float | None):
    print_header("SCENARIO COMPARISON TABLE")
    if spy_window_return is not None:
        print(f"\n  SPY over the same window: {spy_window_return:+.1f}% — Alpha% below is return net of this, not raw stock return.")
        print(f"  A strategy can show positive PnL/ROI here purely from market beta while still having negative alpha (no real edge).")
    print(f"\n{'Scenario':<35} {'Trades':>7} {'Deployed':>12} {'PnL $':>10} {'ROI %':>7} {'Win%':>7} {'Avg Win':>9} {'Avg Loss':>10} {'Alpha%':>8}")
    print(f"{'─' * 35} {'─'*7} {'─'*12} {'─'*10} {'─'*7} {'─'*7} {'─'*9} {'─'*10} {'─'*8}")

    for scen_id in range(5):
        r    = scenario_results[scen_id]
        name = SCENARIO_NAMES[scen_id]
        avg_win_str  = f"${r['avg_win']:>8,.0f}" if r['avg_win'] != 0 else "      N/A"
        avg_loss_str = f"${r['avg_loss']:>8,.0f}" if r['avg_loss'] != 0 else "      N/A"
        alpha_str = f"{r['avg_alpha_pct']:>+6.1f}%" if r['avg_alpha_pct'] is not None else "    N/A"
        print(
            f"{name:<35} "
            f"{r['n_trades']:>7} "
            f"${r['total_deployed']:>11,.0f} "
            f"${r['total_pnl']:>+9,.0f} "
            f"{r['roi']:>+6.1f}% "
            f"{r['win_rate']:>6.0f}% "
            f"  {avg_win_str} "
            f"  {avg_loss_str} "
            f"  {alpha_str}"
        )


def print_ticker_breakdown(positions: list, scenario_results: dict, sma_map: dict):
    print_header("PER-TICKER BREAKDOWN")

    # Build a quick lookup for scenario 0 PnL per ticker
    base = {t["symbol"]: t for t in scenario_results[0]["trades_included"]}

    print(f"\n{'Ticker':<6} {'Entry':>8} {'Exit':>8} {'Qty':>6} {'PnL $':>9} {'ROI%':>6} {'Alpha%':>7} {'txAge':>6} {'SMA':>8} {'S1':>4} {'S3':>4} {'Status'}")
    print(f"{'─'*6} {'─'*8} {'─'*8} {'─'*6} {'─'*9} {'─'*6} {'─'*7} {'─'*6} {'─'*8} {'─'*4} {'─'*4} {'─'*12}")

    # Sort by PnL descending
    sorted_pos = sorted(positions, key=lambda p: base.get(p["symbol"], {}).get("pnl", 0), reverse=True)

    for pos in sorted_pos:
        sym      = pos["symbol"]
        entry    = pos["avg_entry"]
        qty      = pos["total_qty"]
        is_open  = pos["is_open"]
        tx_age   = get_tx_age_days(sym, pos["first_buy_date"])
        sma      = sma_map.get(sym)

        # S1 filter: stale?
        s1_filtered = is_filtered_staleness(pos)
        s3_filtered = is_filtered_trend(pos, sma_map)

        # PnL from scenario 0 (actual)
        if sym in base:
            t_info = base[sym]
            pnl    = t_info["pnl"]
            exit_p = t_info["exit_price"]
            roi    = (pnl / (entry * qty) * 100) if (entry * qty) > 0 else 0
            alpha  = t_info["alpha_pct"]
        else:
            pnl    = 0
            exit_p = 0
            roi    = 0
            alpha  = None

        status   = "OPEN" if is_open else "CLOSED"
        s1_str   = "FILT" if s1_filtered else "KEEP"
        s3_str   = "FILT" if s3_filtered else "KEEP"
        sma_str  = f"${sma:>7.2f}" if sma else "   N/A  "
        exit_str = f"${exit_p:>7.2f}" if exit_p else "   N/A  "
        alpha_str = f"{alpha:>+6.1f}%" if alpha is not None else "    N/A"

        print(
            f"{sym:<6} "
            f"${entry:>7.2f} "
            f"{exit_str} "
            f"{qty:>6.0f} "
            f"${pnl:>+8,.0f} "
            f"{roi:>+5.1f}% "
            f"{alpha_str} "
            f"{tx_age:>6}d "
            f"{sma_str} "
            f"{s1_str:>4} "
            f"{s3_str:>4} "
            f"{status}"
        )

    print(f"\n  S1 = Scenario 1 (7-day txDate filter)")
    print(f"  S3 = Scenario 3 (trend filter: entry > 20-day SMA)")
    print(f"  txAge = days between politician's trade date and bot's buy date")


def print_filtered_trades(scenario_results: dict):
    print_header("TRADES FILTERED OUT PER SCENARIO")

    for scen_id in [1, 3, 4]:
        excluded = scenario_results[scen_id]["trades_excluded"]
        if excluded:
            print(f"\n  Scenario {scen_id} — {SCENARIO_NAMES[scen_id]}:")
            for e in excluded:
                # Get PnL from baseline
                pnl_info = next((t for t in scenario_results[0]["trades_included"]
                                 if t["symbol"] == e["symbol"]), None)
                pnl_str = f"${pnl_info['pnl']:>+8,.0f}" if pnl_info else "       N/A"
                print(f"    {e['symbol']:<6} → would-be PnL {pnl_str}  [{e['reason']}]")
        else:
            print(f"\n  Scenario {scen_id}: no trades filtered")


def print_summary_insight(scenario_results: dict):
    print_header("INSIGHTS")

    base_pnl = scenario_results[0]["total_pnl"]
    for scen_id in range(1, 5):
        r      = scenario_results[scen_id]
        delta  = r["total_pnl"] - base_pnl
        better = "better" if delta > 0 else "worse"
        print(f"\n  Scenario {scen_id} ({SCENARIO_NAMES[scen_id]}):")
        print(f"    PnL vs Actual: ${delta:>+,.0f} ({better})")
        print(f"    Trades taken: {r['n_trades']} vs {scenario_results[0]['n_trades']} actual")
        if r["trades_excluded"]:
            avoided_losers = [e for e in r["trades_excluded"]
                              if any(t["symbol"] == e["symbol"] and t["pnl"] < 0
                                     for t in scenario_results[0]["trades_included"])]
            avoided_winners = [e for e in r["trades_excluded"]
                               if any(t["symbol"] == e["symbol"] and t["pnl"] >= 0
                                      for t in scenario_results[0]["trades_included"])]
            if avoided_losers:
                total_avoided_loss = sum(t["pnl"] for t in scenario_results[0]["trades_included"]
                                         if any(e["symbol"] == t["symbol"] for e in r["trades_excluded"])
                                         and t["pnl"] < 0)
                print(f"    Would have avoided {len(avoided_losers)} losing trade(s) (${-total_avoided_loss:,.0f} in losses)")
            if avoided_winners:
                total_avoided_win = sum(t["pnl"] for t in scenario_results[0]["trades_included"]
                                        if any(e["symbol"] == t["symbol"] for e in r["trades_excluded"])
                                        and t["pnl"] >= 0)
                print(f"    Would have missed {len(avoided_winners)} winning trade(s) (${total_avoided_win:,.0f} in gains)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 90)
    print("  LLM TRADER — BACKTEST: 4-SCENARIO COMPARISON")
    print("═" * 90)
    print("\n  Loading trade history...")

    trades    = parse_trades_log()
    positions = build_positions(trades)

    print(f"  Found {len(positions)} distinct TRAILING_STOP ticker positions")
    print(f"  Open positions: {sum(1 for p in positions if p['is_open'])}")
    print(f"  Closed positions: {sum(1 for p in positions if not p['is_open'])}")

    # Fetch current prices for open positions
    print("\n  Fetching current prices for open positions...")
    current_prices = {}
    for pos in positions:
        if pos["is_open"]:
            sym = pos["symbol"]
            print(f"    → {sym}...", end=" ", flush=True)
            current_prices[sym] = get_current_price(sym)
            print(f"${current_prices[sym]:.2f}")

    # Fetch 20-day SMA for all positions (Scenario 3)
    print("\n  Fetching 20-day SMA at entry date for trend filter (Scenario 3)...")
    sma_map = {}
    for pos in positions:
        sym       = pos["symbol"]
        buy_date  = pos["first_buy_date"]
        print(f"    → {sym} @ {buy_date}...", end=" ", flush=True)
        sma = get_20day_sma(sym, buy_date)
        sma_map[sym] = sma
        entry = pos["avg_entry"]
        if sma:
            relation = "ABOVE SMA (KEEP)" if entry >= sma else "BELOW SMA (FILTER)"
            print(f"SMA=${sma:.2f}, Entry=${entry:.2f} → {relation}")
        else:
            print("SMA=N/A (keep)")

    # Fetch SPY benchmark once for the whole window — alpha needs this to tell
    # real stock-picking edge apart from just riding the market's own drift.
    print("\n  Fetching SPY benchmark for alpha calculation...")
    window_start = min(pos["first_buy_date"] for pos in positions)
    spy_closes = fetch_benchmark_closes(window_start, date.today())
    spy_window_return = benchmark_return_pct(spy_closes, window_start, date.today())

    # Run all scenarios
    print("\n  Running scenario analysis...")
    scenario_results = run_scenarios(positions, current_prices, sma_map, spy_closes)

    # Print results
    print_scenario_table(scenario_results, spy_window_return)
    print_ticker_breakdown(positions, scenario_results, sma_map)
    print_filtered_trades(scenario_results)
    print_summary_insight(scenario_results)

    print(f"\n{'═' * 90}")
    print(f"  NOTE: Open positions (marked OPEN) use current market price for unrealized PnL.")
    print(f"  NOTE: txAge = 0 means txDate unknown, assumed fresh (conservative).")
    print(f"  NOTE: Scenario 2 scales PnL by 0.03/0.06 (3%/6% default pos size).")
    print(f"  NOTE: Alpha% = stock return minus SPY return over the same holding window.")
    print(f"        Positive PnL with negative/near-zero alpha means market beta, not stock-picking edge —")
    print(f"        don't conclude a filter/config is 'working' from PnL/win-rate alone, check alpha too.")
    print(f"{'═' * 90}\n")


if __name__ == "__main__":
    main()
