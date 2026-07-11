# Joiner Risk Scoring + Server Health Detection

**Date:** 2026-07-11  
**Status:** Approved for implementation planning  
**Project:** discordd (Discord self-bot → Telegram notifier)

## Summary

Enhance the existing multi-account join notifier with:

1. **Joiner authenticity scoring** (top priority) — risk score + flags on every join
2. **Server health scoring** — authenticity score for servers the watcher is in
3. **Telegram notifications** — every join, with louder HIGH-risk formatting
4. **On-demand** — `/health` and `/health <name|id>` via Telegram
5. **Scheduled digest** — every 12 hours

Detection is heuristic (signals + weighted scores), not ground truth.

## Goals

| Priority | Goal |
|----------|------|
| P0 | Flag likely-fake / bot joiners with a clear risk band and reasons |
| P1 | Score servers as LIKELY REAL / MIXED / SUSPICIOUS |
| P1 | Query health on demand via Telegram |
| P1 | Auto digest every 12 hours |

## Non-goals (v1)

- Machine learning / external bot databases
- Auto-kick, ban, or Discord-side moderation actions
- Perfect detection of sophisticated bots
- Dashboard UI (Telegram only)

## Constraints

- Runs as a Discord **user-token self-bot** (`discord.py-self`) — ToS risk unchanged
- Only data visible to the logged-in account (channels, recent messages)
- Must stay light on Discord API usage (no aggressive history scraping)
- Secrets stay in env vars / Railway variables, never committed
- Telegram commands accepted only from configured `TELEGRAM_CHAT_ID` (per account)

## Architecture

```
main.py
  ├─ Discord clients (existing multi-account)
  │    └─ on_member_join
  │         → join_store.record_join()
  │         → risk_scorer.score_member()
  │         → build_join_message() [with risk band]
  │         → send_telegram()
  ├─ Telegram listener (asyncio loop per account)
  │    └─ /health, /health <query>
  │         → health_scorer.score_guild() / score_all()
  │         → send_telegram()
  └─ Digest scheduler (every 12 hours)
       → health_scorer + join_store summary
       → send_telegram()

New modules:
  risk_scorer.py   # joiner risk 0–100 + flags
  health_scorer.py # server health 0–100 + label
  join_store.py    # join history for bursts + digests
  telegram_commands.py  # getUpdates + command handling
```

Existing modules keep their roles: `config.py`, `notifier.py`, `main.py` (orchestration).

## Part A — Joiner risk scoring

### Inputs

From `discord.Member` / `User` plus recent joins from `join_store`:

| Signal | Condition | Points | Flag |
|--------|-----------|--------|------|
| Very new account | age &lt; 1 day | +35 | `very_new_account` |
| New account | age &lt; 7 days | +20 | `new_account` |
| Young account | age &lt; 30 days | +10 | `young_account` |
| Default avatar | no custom avatar | +15 | `default_avatar` |
| Suspicious username | digit-heavy or random-looking | +15 | `suspicious_username` |
| Join burst | ≥5 joins in same guild in 5 minutes | +25 | `join_burst` |
| Discord bot | `member.bot` is true | +40 | `is_bot` |

Account-age points are **not stacked** — use the highest matching age tier only.

Score is clamped to **0–100**.

### Username heuristic (v1)

Flag `suspicious_username` if any:

- Username matches `^[a-zA-Z]+\d{4,}$` (letters + long digit run)
- Length ≥ 15 and ≥ 40% digits
- Looks like random alphanumerics (low vowel ratio + high entropy-ish pattern)

Conservative: prefer false negatives over noisy false positives on this signal alone.

### Bands

| Score | Band | Telegram presentation |
|-------|------|------------------------|
| 0–29 | LOW | Normal join alert + score line |
| 30–59 | MEDIUM | Prefix `⚠️ MEDIUM RISK` + flags |
| 60–100 | HIGH | Prefix `🚨 HIGH RISK JOIN` + flags listed first |

### Notification policy

- **Notify on every join** (all bands)
- HIGH is visually louder; no silent filtering in v1

### Example HIGH alert (shape)

```
🚨 HIGH RISK JOIN
Risk: 72/100
Flags: very_new_account, default_avatar, join_burst

Watcher: Account 1
Server: ...
User: ...
Account created: ...
Joined at: ...
```

## Part B — Server health scoring

### Inputs (per guild)

Sample lightly from readable text channels (cap channels and messages, e.g. up to 5 channels × last ~50 messages when available):

| Signal | Healthy direction |
|--------|-------------------|
| Unique message authors | Higher → better |
| Author concentration | If top 1–3 authors send most traffic → worse |
| Message timing variance | Natural variance → better; flat spam → worse |
| Average recent joiner risk | Lower → better |
| Default-avatar join rate (window) | Lower → better |
| Joins with little/no chat activity | High churn, low chat → worse |

If message history is unavailable (permissions / empty), score from join stats only and mark confidence as `low`.

### Output

- Score **0–100**
- Label:
  - **70–100** → `LIKELY REAL`
  - **40–69** → `MIXED`
  - **0–39** → `SUSPICIOUS`
- Short signal breakdown for Telegram

### API budget (v1)

- Prefer cached scores for a short TTL (e.g. 15–30 minutes) so `/health` spam does not re-scrape Discord every time
- Digest uses the same scorer with cache warming once per run

## Part C — Telegram on-demand commands

### Commands

| Command | Behavior |
|---------|----------|
| `/health` | Ranked list of all guilds for that Discord account |
| `/health <name or id>` | Detailed report for best name match or exact ID |

### Auth

- Only process messages where `chat.id` matches that account’s `TELEGRAM_CHAT_ID`
- Ignore all other chats

### Mechanism

- Background asyncio task polling Telegram `getUpdates` with offset
- Long-poll timeout ~20–30s
- Same bot token already used for outbound alerts

### Multi-account

- Each Discord watcher account keeps its own Telegram bot/chat
- Commands on bot 1 score servers visible to Discord account 1 only

## Part D — 12-hour digest

### Schedule

- Interval: **every 12 hours** from process start (or last digest time persisted in store)
- Persist last digest timestamp in `join_store` so restarts do not immediately re-fire unless overdue

### Format (short — approved)

```
📊 Server Health Digest (12h)

Top authentic:
1. ... — score LABEL
2. ...

Watchlist:
1. ... — score LABEL
2. ...

Joins since last digest: N
  HIGH: x  |  MEDIUM: y  |  LOW: z
```

- Top authentic: up to 5 highest scores labeled LIKELY REAL (or highest overall if few)
- Watchlist: up to 5 lowest scores / SUSPICIOUS+MIXED preference
- Join counts from `join_store` since last digest

## Part E — Persistence (`join_store`)

Lightweight JSON file (e.g. `data/join_history.json`), gitignored:

- Recent joins: guild_id, user_id, timestamp, risk_score, band, flags
- Retention: e.g. last 7 days (enough for bursts + digests)
- Last digest timestamp per account (optional keying by account name)

In-memory primary; flush to disk periodically and on shutdown best-effort.

## Configuration

Env additions (optional with defaults):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DIGEST_INTERVAL_HOURS` | `12` | Digest cadence |
| `JOIN_BURST_WINDOW_SECONDS` | `300` | Burst window |
| `JOIN_BURST_THRESHOLD` | `5` | Joins in window to flag |
| `HEALTH_CACHE_TTL_SECONDS` | `900` | Cache TTL for health scores |

Existing Discord/Telegram account env vars unchanged.

## Error handling

- Risk scoring failure → still send join alert without score, log error
- Health scrape failure → reply with partial/join-only score or clear error message
- Telegram command poll errors → log, backoff, continue
- Digest failures → log, retry next interval

## Testing (manual v1)

1. Local join with fresh alt → expect elevated risk flags
2. Join burst simulation → `join_burst` flag
3. `/health` from authorized chat → ranked list
4. `/health` from wrong chat → ignored
5. Wait / force digest → short digest format
6. Confirm Railway still runs with new modules + `data/` volume or ephemeral store

## Implementation order

1. `risk_scorer.py` + wire into join Telegram messages (bands + flags)
2. `join_store.py` + join burst signal
3. `health_scorer.py` (join-based first, then light message sampling)
4. `telegram_commands.py` + `/health`
5. 12-hour digest scheduler
6. README update for commands + new env vars

## Risks / honesty

- Heuristics will false-positive real new users and false-negative good bots
- Self-bot message sampling increases detection risk vs join-only listening
- Large guilds may yield incomplete or delayed join/message data
