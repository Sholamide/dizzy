# Joiner Risk Scoring + One-Shot Server Health Report

**Date:** 2026-07-11  
**Status:** Approved for implementation planning (revised)  
**Project:** discordd (Discord self-bot → Telegram notifier)

## Summary

Enhance the existing multi-account join notifier with:

1. **Joiner authenticity scoring** (top priority) — risk score + flags on every user join to any watched server
2. **One-shot server health report** — when *you* join a new Discord server, monitor it quietly for **48 hours**, then send **one** detailed authenticity report with flags; **never re-report** that server again

Detection is heuristic (signals + weighted scores), not ground truth.

## What you get in Telegram

| Event | What happens |
|-------|----------------|
| Someone joins a server you’re in | Immediate report: user details + risk score + flags (LOW / MEDIUM / HIGH) |
| *You* join a new server | Silent monitoring starts; after **48 hours**, one detailed server health report with flags |
| Same server later | **No** further health digests or re-reports for that server |

## Goals

| Priority | Goal |
|----------|------|
| P0 | Flag likely-fake / bot joiners with a clear risk band and reasons |
| P1 | After 48h in a newly joined server, send one authenticity report with flags |
| P1 | Persist “already reported” so the same server is not reported again |

## Non-goals (v1)

- `/health` or other Telegram commands (not needed)
- Recurring 12-hour digests for all servers
- Re-scoring / re-notifying servers already reported
- Machine learning / external bot databases
- Auto-kick, ban, or Discord-side moderation actions
- Perfect detection of sophisticated bots
- Dashboard UI (Telegram only)

## Constraints

- Runs as a Discord **user-token self-bot** (`discord.py-self`) — ToS risk unchanged
- Only data visible to the logged-in account (channels, recent messages)
- Must stay light on Discord API usage (no aggressive history scraping)
- Secrets stay in env vars / Railway variables, never committed

## Architecture

```
main.py
  ├─ Discord clients (existing multi-account)
  │    ├─ on_member_join (other users)
  │    │    → join_store.record_join()
  │    │    → risk_scorer.score_member()
  │    │    → Telegram join alert (always)
  │    ├─ on_guild_join (you joined a server)
  │    │    → server_store.schedule_report(guild, due_at = now + 48h)
  │    └─ background ticker
  │         → for each due, unreported guild
  │              → health_scorer.score_guild()
  │              → Telegram one-shot report
  │              → server_store.mark_reported(guild)

Modules:
  risk_scorer.py    # joiner risk 0–100 + flags
  health_scorer.py  # server health 0–100 + flags/label
  join_store.py     # join history for bursts + health inputs
  server_store.py   # guild watch schedule + reported flags
```

Existing: `config.py`, `notifier.py`, `main.py` (orchestration).

## Part A — Joiner risk scoring (unchanged priority)

### When

Every `on_member_join` for members that are **not** the watcher account itself (optional: still log self-joins but do not alert).

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
Score clamped to **0–100**.

### Username heuristic (v1)

Flag `suspicious_username` if any:

- Username matches `^[a-zA-Z]+\d{4,}$`
- Length ≥ 15 and ≥ 40% digits
- Random-looking alphanumerics (low vowel ratio)

### Bands

| Score | Band | Telegram presentation |
|-------|------|------------------------|
| 0–29 | LOW | Normal join alert + score line |
| 30–59 | MEDIUM | Prefix `⚠️ MEDIUM RISK` + flags |
| 60–100 | HIGH | Prefix `🚨 HIGH RISK JOIN` + flags listed first |

### Notification policy

- **Notify on every join** (all bands)
- HIGH is visually louder; no silent filtering in v1
- Language: risk + flags — never absolute “this is a bot”

### Example HIGH alert

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

## Part B — One-shot server health report (48 hours)

### Lifecycle

```
You join guild X
  → server_store: status=watching, joined_at=now, report_due_at=now+48h, reported=false

Every few minutes (background)
  → if report_due_at <= now AND reported=false
       → run health_scorer
       → send Telegram report
       → mark reported=true (never send again for this guild+account)

Restart / redeploy
  → load server_store from disk
  → already-reported guilds stay skipped
  → watching guilds still due (or overdue) get reported once
```

### Trigger

- Discord event: `on_guild_join` (your account was added to a guild)
- Also on startup: discover guilds in `client.guilds` that are **not** yet in the store → treat as newly seen and schedule 48h from first-seen time (or from now if unknown)

**Important:** Existing servers already in the store as `reported=true` are never re-queued.

### What “monitor for 48 hours” means

During the wait window, the bot already records normal join events into `join_store`. At report time it uses:

- Joins observed in that guild since `joined_at` (risk averages, default-avatar rate, burstiness, churn)
- Optional light message sampling **only at report time** (if `HEALTH_MESSAGE_SAMPLING=true`)

No continuous scrape during the 48h wait.

### Report contents (detailed, once)

```
📊 NEW SERVER REPORT (48h)
Server: Name (ID)
Watcher: Account 1
Watched since: ...
Report window: 48h

Health: 71/100 — LIKELY REAL
Confidence: medium
Data: joins only   (or joins + messages)

Flags:
- low_joiner_risk_avg
- diverse_join_ages
...

Join stats (window):
- Joins: N
- HIGH / MEDIUM / LOW: x / y / z
- Default avatar joins: p%

(Optional message signals if sampling on)
```

### Health score / labels

Same bands as before when enough data:

| Score | Label |
|-------|-------|
| 70–100 | `LIKELY REAL` |
| 40–69 | `MIXED` |
| 0–39 | `SUSPICIOUS` |

If too little evidence → `INSUFFICIENT DATA` (still send once, with explanation — counts as reported so we don’t spam retries forever). Optionally allow one retry after +24h only if `INSUFFICIENT DATA` and `reported` was deferred — **v1 default: mark reported even on insufficient data** to honor “no re-report”.

### Confidence

| Situation | Confidence |
|-----------|------------|
| Message sample + ≥10 recorded joins in window | `high` |
| Joins only, ≥10 joins | `medium` |
| Joins only, &lt;10 joins | `low` / lean `INSUFFICIENT DATA` |

### Deduping / “don’t report again”

Key: `(watcher_account_name, guild_id)`

- `reported=true` → skip forever (v1)
- Leaving and rejoining the same guild: **still skip** if already reported (avoids re-spam). Optional later: reset only if `RESET_SERVER_REPORTS=true` env wipe.

## Part C — Persistence

### `join_store` (`data/join_history.json`)

- Recent joins: guild_id, user_id, timestamp, risk_score, band, flags
- Retention: last 7 days (covers 48h windows + bursts)

### `server_store` (`data/server_watch.json`)

Per watcher account + guild:

```json
{
  "account": "Account 1",
  "guild_id": "123",
  "guild_name": "Example",
  "joined_at": "ISO",
  "report_due_at": "ISO",
  "reported": true,
  "reported_at": "ISO",
  "last_score": 71,
  "last_label": "LIKELY REAL"
}
```

Gitignore `data/`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVER_REPORT_DELAY_HOURS` | `48` | Wait after joining a server before one-shot report |
| `JOIN_BURST_WINDOW_SECONDS` | `300` | Burst window for joiner scoring |
| `JOIN_BURST_THRESHOLD` | `5` | Joins in window to flag |
| `HEALTH_MESSAGE_SAMPLING` | `false` | Optional message sampling at report time only |
| `HEALTH_CACHE_TTL_SECONDS` | `900` | Unused for recurring digests; optional if report retry ever added |

## Error handling

- Risk scoring failure → still send join alert without score, log error
- Server report failure → log; retry on next ticker until success, then mark reported (so a transient Telegram outage doesn’t permanently lose the one report)
- After successful send → `reported=true` permanently

## Testing (manual v1)

1. Fresh alt joins a watched server → elevated joiner risk flags in Telegram  
2. Join burst → `join_burst`  
3. Watcher joins a new test server → no immediate health report  
4. Force delay short in test (`SERVER_REPORT_DELAY_HOURS=0.01`) → one detailed report  
5. Restart process → same guild not reported again  
6. Another user join still alerts as usual  

## Implementation order

1. `risk_scorer.py` + wire into join Telegram messages  
2. `join_store.py` + join burst  
3. `server_store.py` + `on_guild_join` scheduling  
4. `health_scorer.py` (join-based; optional message sampling at report time)  
5. Background due-report ticker + one-shot Telegram report  
6. README: joiner alerts + 48h server report behavior  

## Risks / honesty + mitigations

### False positives / negatives on joiners

- Multi-signal scores; show flags not absolute verdicts  
- Tunable burst/age knobs  
- Accept MEDIUM on brand-new real users as caution  

### Self-bot message sampling risk

- Message sampling **off by default**  
- Only runs **once** at the 48h report (if enabled), not continuously  
- Join-based report always available  

### Large / quiet servers

- Confidence + `INSUFFICIENT DATA` wording  
- Still one report max so quiet servers don’t get endless follow-ups  

## Revision notes (vs earlier draft)

**Removed:** `/health` commands, recurring 12h digests, re-reporting servers.  
**Added:** 48h watch after *you* join a server → single detailed report → permanent skip.
