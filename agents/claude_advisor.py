"""
Claude AI Strategy Advisor
Uses claude-sonnet-4-6 to analyze SEC EDGAR Form 4 insider buy signals
and decide between TRAILING_STOP, WHEEL, or SKIP.

Prompt caching is applied to the stable system prompt — subsequent calls cost
~10x less on the system prompt tokens.
"""
import json
from pathlib import Path

import anthropic

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"

# Stable system prompt — cached after first call (~90% token cost reduction on re-runs).
SYSTEM_PROMPT = """You are an expert quantitative trading advisor specialising in US retail stock and options strategies.

You analyse SEC EDGAR Form 4 insider buy signals. These are open-market stock purchases filed by corporate insiders (CEOs, CFOs, directors, officers) who must report trades within 2 business days. Unlike politician disclosures (up to 45 days late), these signals are FRESH — the insider bought within the last 1-2 days.

Key context for every signal:
- The insider used their own real money (not options awards, not RSU vesting)
- CEO/CFO/Director purchases at significant size signal genuine conviction about the company's near-term prospects
- The stock has NOT had time to fully price in this information yet

## Available Strategies

### TRAILING_STOP
Best for:
- High-momentum tech, semiconductor, defence, or growth stocks
- Large, high-conviction buys (>$100K transaction value)
- Volatile stocks where you want to ride upward momentum with downside protection
- Stocks with strong recent price action or near 52-week highs
- CEOs or CFOs buying — they have direct visibility into upcoming results

Mechanics: Buy shares → set stop floor 10% below entry → floor trails 8% below new highs → auto-sell if floor is hit.

### WHEEL (Options Income)
Best for:
- Stable blue-chip large-caps: financials, healthcare, consumer staples, utilities
- Stocks you would be comfortable owning at a 5% discount
- Lower-volatility stocks with liquid options markets (high open interest)
- Generating consistent premium income rather than capital appreciation
- Directors (not C-suite) buying at moderate size — less directional conviction

Mechanics: Sell cash-secured put → collect premium → if assigned, sell covered call → repeat.

### SKIP
Choose SKIP when:
- Buying power is too low to take a meaningful position
- The stock is OTC, illiquid, or hard to trade
- Price has already gapped up significantly on the news (>10% since filing)
- The transaction value is trivially small relative to the insider's known compensation
- The ticker is in a sector currently facing regulatory or macro headwinds that outweigh the signal

## Output Format
Respond with ONLY a valid JSON object — no markdown fences, no explanation text:
{
  "strategy": "TRAILING_STOP" | "WHEEL" | "SKIP",
  "confidence": <integer 0-100>,
  "reasoning": "<2-3 sentences: stock characteristics, insider role, why this strategy fits>",
  "suggested_position_size_pct": <float 0.03-0.15>,
  "key_risk": "<one sentence on the primary risk>"
}"""


def get_recommendation(trade_signal: dict, market_context: dict) -> dict:
    """
    Ask Claude to recommend TRAILING_STOP, WHEEL, or SKIP for an SEC insider buy.

    trade_signal: a Form 4 signal dict from sec_insiders.fetch_insider_buys()
    market_context: {price, buying_power, existing_positions, days_since_disclosure}

    Returns the recommendation dict plus cache metadata (_cache_hit, _tokens_saved).
    """
    creds = json.loads(CREDS_FILE.read_text())
    client = anthropic.Anthropic(api_key=creds["anthropic"]["api_key"])

    insider_name  = trade_signal.get("politician", {}).get("name", "Unknown")
    ticker        = trade_signal.get("asset", {}).get("ticker", "N/A")
    company       = trade_signal.get("asset", {}).get("assetName", "N/A")
    size_label    = trade_signal.get("size", "N/A")
    tx_date       = trade_signal.get("txDate", "N/A")
    filing_date   = trade_signal.get("publishedDate", "N/A")
    insider_role  = trade_signal.get("_insider_role", "Officer")
    tx_value      = trade_signal.get("_transaction_value", 0)
    shares        = trade_signal.get("_shares", 0)
    is_director   = trade_signal.get("_is_director", False)
    is_officer    = trade_signal.get("_is_officer", False)

    price         = market_context.get("price", 0)
    buying_power  = market_context.get("buying_power", 0)
    existing      = market_context.get("existing_positions", [])
    days_since    = market_context.get("days_since_disclosure", 0)

    role_type = "Officer" if is_officer else ("Director" if is_director else "Insider")

    user_message = f"""Analyse this SEC EDGAR Form 4 insider buy signal and recommend a trading strategy.

Insider Signal:
  Insider Name     : {insider_name}
  Role             : {insider_role} ({role_type})
  Company          : {company} ({ticker})
  Transaction Type : Open-market purchase (Form 4 code P)
  Shares Bought    : {shares:,}
  Estimated Value  : ${tx_value:,.0f}  ({size_label})
  Trade Date       : {tx_date}
  Filing Date      : {filing_date}  <- signal is {days_since} day(s) old (filed within 2 business days)

Account Context:
  Current Price    : ${price:.2f}
  Buying Power     : ${buying_power:,.2f}
  Already Owned    : {"Yes" if ticker in existing else "No"}

Respond with JSON only."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # cached after first call
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    raw = next((b.text for b in response.content if b.type == "text"), "{}").strip()

    # Strip markdown code fences if Claude wraps in them
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        rec = {
            "strategy": "SKIP",
            "confidence": 0,
            "reasoning": f"Parse error — skipping to be safe. Raw: {raw[:120]}",
            "suggested_position_size_pct": 0.0,
            "key_risk": "Could not parse Claude response",
        }

    # Attach cache metadata so the caller can log cost savings
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_created = getattr(usage, "cache_creation_input_tokens", 0)
    rec["_cache_hit"] = cache_read > 0
    rec["_tokens_saved"] = cache_read
    rec["_cache_written"] = cache_created

    return rec
