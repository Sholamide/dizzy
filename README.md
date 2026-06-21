# Discord Join Notifier

A Python self-bot that listens for new member joins across all Discord servers you're in, then sends a Telegram notification with details about the new member.

> **Warning:** This uses your personal Discord user token. Self-bots violate Discord's Terms of Service and can result in account bans. Use at your own risk.

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

   Copy the example env file and fill in your values:

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:

   ```
   DISCORD_TOKEN=your_discord_user_token
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

### Getting your Discord token

1. Open Discord in the browser
2. Open DevTools (F12) → Network tab
3. Filter by `api/` → find any request → copy the `Authorization` header value

### Getting your Telegram chat ID

1. Message your bot on Telegram
2. Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find `"chat":{"id":...}` in the response

## Run

```bash
source .venv/bin/activate
python main.py
```

When running, you should see:

```
Logged in as YourName#1234 — watching N server(s)
```

## What you'll receive on Telegram

```
New member joined!
Server: My Server (ID: 123456789)
User: JohnDoe (JohnDoe#1234) (ID: 987654321)
Account created: Jan 5, 2023 (2 years ago)
Joined at: Jun 21, 2026 15:10 UTC
```

## Project structure

```
discordd/
├── main.py           # Self-bot entry point and event listener
├── notifier.py       # Telegram notification helper
├── .env              # Secrets (never commit this)
├── .env.example      # Env template
├── requirements.txt
└── README.md
```

## Deploy to Railway (recommended)

Railway runs the bot 24/7 with auto-restart. No server admin needed.

### 1. Push code to GitHub

```bash
cd /Users/Olamide.Sholuade/discordd
git init
git add Dockerfile .dockerignore main.py notifier.py requirements.txt .env.example .gitignore README.md
git commit -m "Add Discord join notifier"
```

Create a new repo on [github.com/new](https://github.com/new), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/discordd.git
git branch -M main
git push -u origin main
```

Do **not** commit `.env` — secrets go in Railway's dashboard only.

### 2. Deploy on Railway

1. Go to [railway.app](https://railway.app) and sign up (GitHub login works)
2. **New Project** → **Deploy from GitHub repo** → select `discordd`
3. Railway detects the `Dockerfile` and builds automatically
4. Open the service → **Variables** → add:
   - `DISCORD_TOKEN`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Open **Deployments** → check logs for:
   ```
   Logged in as YourName — watching N server(s)
   ```

The bot stays running. Railway restarts it if it crashes.

**Cost:** about $5/month of usage credit (Hobby plan). You get a small free trial to start.

### Useful Railway commands

- **View logs:** service → **Deployments** → latest deploy → logs
- **Restart:** **Deployments** → **Redeploy**
- **Update token:** change variable → redeploy

## Notes

- The bot listens to **all servers** your account is in
- `on_member_join` requires the server to send member join events; very large servers may have this disabled or delayed
- Keep your `.env` file private and never commit it to version control
