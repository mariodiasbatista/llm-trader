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
| Claude recommends a trade | 🤖 strategy + ✅ Approve / ❌ Skip buttons |
| You tap Approve | Trade executes at live price |
| Stop loss triggers | 🔴 STOP TRIGGERED |
| Ladder buy fires | 📉 LADDER BUY |
| 16:05 daily | 📊 Daily Summary |

## Behaviour

- If Telegram is **configured** — trades are held for your approval before executing
- If Telegram is **not configured** — trades execute automatically (existing behaviour)
- Approve/Skip buttons disappear after you tap to prevent double execution
- Trade price is re-fetched at execution time, not at recommendation time
