"""
Claude AI Strategy Advisor
Uses claude-opus-4-7 with adaptive thinking to analyze Capitol Trades signals
and decide between TRAILING_STOP, WHEEL, or SKIP.

Prompt caching is applied to the stable system prompt — subsequent calls cost
~10x less on the system prompt tokens.
"""
import json
from pathlib import Path

import anthropic

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"

# Stable system prompt — cached after first call (saved ~90% on re-runs)
SYSTEM_PROMPT = """You are an expert quantitative trading advisor specializing in US retail stock and options strategies.

You analyze US politician stock disclosure filings from Capitol Trades and select the optimal trading strategy for each buy signal.

## Available Strategies

### TRAILING_STOP
Best for:
- High-momentum tech, semiconductor, defense, or growth stocks
- Large, high-conviction buys (>$50K disclosure size)
- Volatile stocks where you want to ride upward momentum with downside protection
- Stocks with strong recent price action or near 52-week highs

Mechanics: Buy shares → set stop floor 10% below entry → floor trails 5% below new highs → auto-sell if floor is hit. Adds shares on 20%/30% dips.

### WHEEL (Options Income)
Best for:
- Stable, blue-chip large-caps: financials, healthcare, consumer staples, utilities
- Stocks you would be comfortable owning at a 5% discount
- Lower-volatility stocks with liquid options markets (high open interest)
- Generating consistent premium income rather than capital appreciation

Mechanics: Sell cash-secured put → collect premium → if assigned, sell covered call → repeat cycle.

### SKIP
Choose SKIP when:
- The transaction type is a SELL or exchange (not a buy)
- The ticker is OTC, illiquid, or hard to trade with options
- The stock has already moved >15% since the disclosure date
- Account has insufficient buying power
- The disclosure size is trivially small (<$1K)
- The politician has a history of poor disclosure quality

## Output Format
Respond with ONLY a valid JSON object — no markdown fences, no explanation text:
{
  "strategy": "TRAILING_STOP" | "WHEEL" | "SKIP",
  "confidence": <integer 0-100>,
  "reasoning": "<2-3 sentences explaining the choice based on the stock characteristics, sector, and politician context>",
  "suggested_position_size_pct": <float 0.03-0.20>,
  "key_risk": "<one sentence on the primary risk>"
}"""


def get_recommendation(trade_signal: dict, market_context: dict) -> dict:
    """
    Ask Claude Opus 4.7 to recommend TRAILING_STOP, WHEEL, or SKIP.

    trade_signal: a Capitol Trades record dict
    market_context: {price, buying_power, existing_positions, days_since_disclosure}

    Returns the recommendation dict plus cache metadata (_cache_hit, _tokens_saved).
    """
    creds = json.loads(CREDS_FILE.read_text())
    client = anthropic.Anthropic(api_key=creds["anthropic"]["api_key"])

    politician = trade_signal.get("politician", {}).get("name", "Unknown")
    ticker = trade_signal.get("asset", {}).get("ticker", "N/A")
    tx_type = trade_signal.get("txType", "N/A")
    size = trade_signal.get("size", "N/A")
    tx_date = trade_signal.get("txDate", "N/A")

    price = market_context.get("price", 0)
    buying_power = market_context.get("buying_power", 0)
    existing = market_context.get("existing_positions", [])
    days_since = market_context.get("days_since_disclosure", 0)

    user_message = f"""Analyze this politician stock disclosure and recommend a trading strategy.

Disclosure Details:
  Politician       : {politician}
  Ticker           : {ticker}
  Transaction Type : {tx_type}
  Estimated Size   : {size}
  Disclosure Date  : {tx_date}
  Days Old         : {days_since}

Account Context:
  Current Price    : ${price:.2f}
  Buying Power     : ${buying_power:,.2f}
  Already Owned    : {"Yes" if ticker in existing else "No"}

Respond with JSON only."""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        thinking={"type": "adaptive"},
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
