# Discord Join Notifier

A Python self-bot that watches Discord servers you’re in and notifies you on Telegram when:

1. **Someone joins** — immediate alert with a risk score and flags (likely throwaway / farm patterns)
2. **You join a new server** — silent monitoring for **72 hours**, then **one** detailed health report; that server is never reported again

> **Warning:** This uses your personal Discord user token. Self-bots violate Discord’s Terms of Service and can result in account bans. Use at your own risk. Scoring is heuristic, not proof.

## Requirements

- Python 3.10+
- A Discord user token
- A Telegram bot token and chat ID

## Setup

1. **Clone or enter this directory**

2. **Create a virtual environment and install dependencies**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   ```
   # Account 1
   DISCORD_TOKEN=your_discord_user_token
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_chat_id

   # Account 2 (optional)
   DISCORD_TOKEN_2=...
   TELEGRAM_BOT_TOKEN_2=...
   TELEGRAM_CHAT_ID_2=...

   # Scoring / reports (defaults shown)
   SERVER_REPORT_DELAY_HOURS=72
   JOIN_BURST_WINDOW_SECONDS=300
   JOIN_BURST_THRESHOLD=5
   HEALTH_MESSAGE_SAMPLING=false
   DATA_DIR=data
   ```

## Run

```bash
source .venv/bin/activate
python main.py
```

```
[Account 1] Logged in as YourName — watching N server(s)
```

## What you’ll get on Telegram

### Every member join

Risk band + flags, e.g.:

```
🚨 HIGH RISK JOIN ALERT 🚨
Risk score: 72/100
Flags: very_new_account, default_avatar, join_burst
...
```

Bands: **LOW** (0–29), **MEDIUM** (30–59), **HIGH** (60–100).

### After you join a new server (once)

After `SERVER_REPORT_DELAY_HOURS` (default 72):

```
📊 NEW SERVER REPORT (72h)
Health score / label / confidence / flags
Join stats in the watch window
```

Already-reported servers are **never** re-reported (state in `data/server_watch.json`).

## Persistence

| File | Purpose |
|------|---------|
| `data/join_history.json` | Recent joins (bursts + health inputs) |
| `data/server_watch.json` | 72h schedules + `reported` flags |

On Railway, mount a volume at `/app/data` so reports aren’t re-scheduled after every redeploy.

## Deploy to Railway

1. Push code to GitHub (never commit `.env`)
2. Deploy from GitHub; Dockerfile builds the app
3. Set Variables: Discord + Telegram tokens, and optional scoring env vars
4. Attach a volume to `/app/data`
5. Check logs for `Logged in as ... — watching N server(s)`

## Quick local test for server reports

```bash
SERVER_REPORT_DELAY_HOURS=0.01 python main.py
```

Join a test server with the watcher account → expect one health report within about a minute → restart → no second report.

## Project structure

```
discordd/
├── main.py
├── config.py
├── notifier.py
├── risk_scorer.py
├── health_scorer.py
├── join_store.py
├── server_store.py
├── data/                 # created at runtime (gitignored)
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

## Notes

- Heuristics can flag real new users and miss careful bots — treat scores as guidance
- Message sampling for health is **off** by default (`HEALTH_MESSAGE_SAMPLING=false`)
- Large servers may delay join events
- Keep secrets out of git
