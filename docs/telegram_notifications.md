# Telegram Notifications

## Setup (2 minutes)

1. Open Telegram, search `@BotFather`, send `/newbot` — get your `bot_token`
2. Message your bot once, then get your `chat_id`:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Add to `credentials.json`:
   ```json
   "telegram": {
     "bot_token": "123456789:ABC...",
     "chat_id": "YOUR_CHAT_ID"
   }
   ```

## Notifications

| Event | Message |
|---|---|
| Scheduler starts | 🚀 LLM Trader started |
| Claude buys a stock | ✅ Bought `TICKER` — shares @ price, strategy + confidence |
| Insufficient buying power | ⚠️ needed vs. available |
| Execution fails | ❌ Execution failed for `TICKER` |
| Stop loss triggers | 🔴 STOP TRIGGERED |
| Ladder buy fires | 📉 LADDER BUY |
| 16:05 daily | 📊 Daily Summary |

## Commands

| Command | Effect |
|---|---|
| `/summary` | Full portfolio snapshot with entry prices, stops and per-stock targets |
| `/schedule` | Today's trading schedule with live status |
| `/help` | List available commands |

## Behaviour

- **Telegram is notification-only. It never gates a trade.** Trades execute
  immediately when Claude recommends them, whether or not Telegram is
  configured — see `scripts/analyze_and_trade.py` ("Execute immediately").
- If Telegram is not configured, execution is identical; you just get no messages.

> **Deprecated:** earlier versions held each recommendation for an ✅ Approve /
> ❌ Skip tap before executing. That gate was removed in favour of autonomous
> execution. The machinery still exists in `core/notifier.py`
> (`send_trade_approval`, `poll_approvals`) and in the scheduler's
> `_poll_telegram` handler, but **no production code path calls it any more** —
> nothing writes `pending_trades`, so no approval prompt is ever sent. It is
> reachable only from tests. Treat the approve/skip flow as dead code, not as
> current behaviour.
