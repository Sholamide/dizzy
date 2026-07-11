# Joiner Risk + 72h Server Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score every Discord joiner with risk flags in Telegram, and send one detailed server health report 72 hours after the watcher joins a guild — never re-report that server.

**Architecture:** Pure scoring modules (`risk_scorer`, `health_scorer`) plus JSON persistence (`join_store`, `server_store`). `main.py` wires Discord events: `on_member_join` → score + alert; `on_guild_join` / startup → schedule 72h report; background ticker sends due reports once and marks them reported.

**Tech Stack:** Python 3.10+, discord.py-self, requests, python-dotenv, pytest (dev/test)

**Spec:** `docs/superpowers/specs/2026-07-11-joiner-server-health-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `risk_scorer.py` | Joiner score 0–100, band, flags (no I/O) |
| `join_store.py` | Persist recent joins; burst counts; guild join stats |
| `server_store.py` | Schedule / due / mark-reported guild watches |
| `health_scorer.py` | Server health from join stats (+ optional message sampling later) |
| `main.py` | Wire events, messages, ticker |
| `config.py` | Load scoring/report env defaults |
| `tests/test_risk_scorer.py` | Unit tests for risk scoring |
| `tests/test_join_store.py` | Burst + persistence |
| `tests/test_server_store.py` | Schedule / due / no re-report |
| `tests/test_health_scorer.py` | Health labels + insufficient data |
| `Dockerfile` | Copy new modules + create `data/` |
| `.env.example` / `README.md` | Document new env vars + behavior |
| `requirements.txt` | Add `pytest` for local tests |

---

### Task 1: Test harness + risk_scorer

**Files:**
- Create: `tests/test_risk_scorer.py`
- Create: `risk_scorer.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest to requirements**

Append to `requirements.txt`:

```
pytest
```

- [ ] **Step 2: Write failing risk_scorer tests**

Create `tests/test_risk_scorer.py`:

```python
from datetime import datetime, timedelta, timezone

from risk_scorer import RiskResult, score_member_signals


def _created(days_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def test_very_new_account_scores_high_age_tier():
    result = score_member_signals(
        created_at=_created(0.5),
        avatar_url=None,
        username="alice",
        is_bot=False,
        join_burst=False,
    )
    assert "very_new_account" in result.flags
    assert "new_account" not in result.flags
    assert result.score >= 35
    assert result.band == "MEDIUM" or result.band == "HIGH"


def test_age_tiers_do_not_stack():
    result = score_member_signals(
        created_at=_created(0.5),
        avatar_url="https://cdn.example/a.png",
        username="normaluser",
        is_bot=False,
        join_burst=False,
    )
    age_flags = [f for f in result.flags if f.endswith("_account")]
    assert len(age_flags) == 1
    assert age_flags[0] == "very_new_account"


def test_default_avatar_and_suspicious_username():
    result = score_member_signals(
        created_at=_created(400),
        avatar_url=None,
        username="user12345",
        is_bot=False,
        join_burst=False,
    )
    assert "default_avatar" in result.flags
    assert "suspicious_username" in result.flags
    assert result.score == 30
    assert result.band == "MEDIUM"


def test_bot_and_burst_push_high():
    result = score_member_signals(
        created_at=_created(400),
        avatar_url="https://cdn.example/a.png",
        username="helper",
        is_bot=True,
        join_burst=True,
    )
    assert "is_bot" in result.flags
    assert "join_burst" in result.flags
    assert result.score >= 60
    assert result.band == "HIGH"


def test_old_custom_avatar_user_is_low():
    result = score_member_signals(
        created_at=_created(800),
        avatar_url="https://cdn.example/a.png",
        username="jane",
        is_bot=False,
        join_burst=False,
    )
    assert result.score == 0
    assert result.band == "LOW"
    assert result.flags == []
```

- [ ] **Step 3: Run tests — expect fail**

```bash
cd /Users/Olamide.Sholuade/discordd
source .venv/bin/activate
pip install pytest -q
pytest tests/test_risk_scorer.py -v
```

Expected: `ModuleNotFoundError: No module named 'risk_scorer'`

- [ ] **Step 4: Implement risk_scorer.py**

Create `risk_scorer.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RiskResult:
    score: int
    band: str  # LOW | MEDIUM | HIGH
    flags: list[str]


_LETTER_DIGIT_RUN = re.compile(r"^[A-Za-z]+\d{4,}$")


def _band(score: int) -> str:
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _suspicious_username(username: str) -> bool:
    name = username.split("#", 1)[0]
    if _LETTER_DIGIT_RUN.match(name):
        return True
    if len(name) >= 15:
        digits = sum(ch.isdigit() for ch in name)
        if digits / len(name) >= 0.4:
            return True
    letters = [ch.lower() for ch in name if ch.isalpha()]
    if len(letters) >= 10:
        vowels = sum(ch in "aeiou" for ch in letters)
        if vowels / len(letters) < 0.2:
            return True
    return False


def score_member_signals(
    *,
    created_at: datetime,
    avatar_url: str | None,
    username: str,
    is_bot: bool,
    join_burst: bool,
) -> RiskResult:
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_days = (now - created_at).total_seconds() / 86400.0
    score = 0
    flags: list[str] = []

    if age_days < 1:
        score += 35
        flags.append("very_new_account")
    elif age_days < 7:
        score += 20
        flags.append("new_account")
    elif age_days < 30:
        score += 10
        flags.append("young_account")

    if not avatar_url:
        score += 15
        flags.append("default_avatar")

    if _suspicious_username(username):
        score += 15
        flags.append("suspicious_username")

    if join_burst:
        score += 25
        flags.append("join_burst")

    if is_bot:
        score += 40
        flags.append("is_bot")

    score = max(0, min(100, score))
    return RiskResult(score=score, band=_band(score), flags=flags)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/test_risk_scorer.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add requirements.txt risk_scorer.py tests/test_risk_scorer.py
git commit -m "feat: add joiner risk scorer with unit tests"
```

---

### Task 2: join_store (history + burst)

**Files:**
- Create: `join_store.py`
- Create: `tests/test_join_store.py`

- [ ] **Step 1: Write failing join_store tests**

Create `tests/test_join_store.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from join_store import JoinStore


def test_burst_true_when_threshold_met(tmp_path: Path):
    store = JoinStore(tmp_path / "joins.json", retention_days=7)
    now = datetime.now(timezone.utc)
    guild_id = "111"
    for i in range(4):
        store.record_join(
            guild_id=guild_id,
            user_id=str(1000 + i),
            timestamp=now - timedelta(seconds=30 * i),
            risk_score=10,
            band="LOW",
            flags=[],
            default_avatar=False,
        )
    assert store.is_join_burst(guild_id, now=now, window_seconds=300, threshold=5) is False

    store.record_join(
        guild_id=guild_id,
        user_id="2000",
        timestamp=now,
        risk_score=10,
        band="LOW",
        flags=[],
        default_avatar=False,
    )
    assert store.is_join_burst(guild_id, now=now, window_seconds=300, threshold=5) is True


def test_guild_stats_and_persistence(tmp_path: Path):
    path = tmp_path / "joins.json"
    store = JoinStore(path, retention_days=7)
    now = datetime.now(timezone.utc)
    store.record_join(
        guild_id="222",
        user_id="1",
        timestamp=now,
        risk_score=70,
        band="HIGH",
        flags=["very_new_account"],
        default_avatar=True,
    )
    store.record_join(
        guild_id="222",
        user_id="2",
        timestamp=now,
        risk_score=10,
        band="LOW",
        flags=[],
        default_avatar=False,
    )
    store.flush()

    store2 = JoinStore(path, retention_days=7)
    stats = store2.guild_stats("222", since=now - timedelta(hours=1))
    assert stats["total"] == 2
    assert stats["high"] == 1
    assert stats["medium"] == 0
    assert stats["low"] == 1
    assert stats["default_avatar_pct"] == 50.0
    assert stats["avg_risk"] == 40.0
```

- [ ] **Step 2: Run tests — expect fail**

```bash
pytest tests/test_join_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'join_store'`

- [ ] **Step 3: Implement join_store.py**

Create `join_store.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class JoinStore:
    def __init__(self, path: Path, *, retention_days: int = 7) -> None:
        self.path = path
        self.retention_days = retention_days
        self._joins: list[dict[str, Any]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._joins = data.get("joins", [])
        self._prune()

    def flush(self) -> None:
        self._prune()
        self.path.write_text(
            json.dumps({"joins": self._joins}, indent=2),
            encoding="utf-8",
        )

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        kept: list[dict[str, Any]] = []
        for row in self._joins:
            ts = _parse_ts(row["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                kept.append(row)
        self._joins = kept

    def record_join(
        self,
        *,
        guild_id: str,
        user_id: str,
        timestamp: datetime,
        risk_score: int,
        band: str,
        flags: list[str],
        default_avatar: bool,
    ) -> None:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        self._joins.append(
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "timestamp": timestamp.isoformat(),
                "risk_score": risk_score,
                "band": band,
                "flags": flags,
                "default_avatar": default_avatar,
            }
        )
        self.flush()

    def is_join_burst(
        self,
        guild_id: str,
        *,
        now: datetime,
        window_seconds: int,
        threshold: int,
    ) -> bool:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        start = now - timedelta(seconds=window_seconds)
        count = 0
        for row in self._joins:
            if row["guild_id"] != str(guild_id):
                continue
            ts = _parse_ts(row["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if start <= ts <= now:
                count += 1
        return count >= threshold

    def guild_stats(self, guild_id: str, *, since: datetime) -> dict[str, Any]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        rows = []
        for row in self._joins:
            if row["guild_id"] != str(guild_id):
                continue
            ts = _parse_ts(row["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= since:
                rows.append(row)

        total = len(rows)
        if total == 0:
            return {
                "total": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "default_avatar_pct": 0.0,
                "avg_risk": 0.0,
            }

        high = sum(1 for r in rows if r["band"] == "HIGH")
        medium = sum(1 for r in rows if r["band"] == "MEDIUM")
        low = sum(1 for r in rows if r["band"] == "LOW")
        default_n = sum(1 for r in rows if r.get("default_avatar"))
        avg_risk = sum(r["risk_score"] for r in rows) / total
        return {
            "total": total,
            "high": high,
            "medium": medium,
            "low": low,
            "default_avatar_pct": round(100.0 * default_n / total, 1),
            "avg_risk": round(avg_risk, 1),
        }
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_join_store.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add join_store.py tests/test_join_store.py
git commit -m "feat: add join history store with burst detection"
```

---

### Task 3: server_store (72h schedule, no re-report)

**Files:**
- Create: `server_store.py`
- Create: `tests/test_server_store.py`

- [ ] **Step 1: Write failing server_store tests**

Create `tests/test_server_store.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server_store import ServerStore


def test_schedule_and_due(tmp_path: Path):
    store = ServerStore(tmp_path / "servers.json")
    now = datetime.now(timezone.utc)
    store.schedule_watch(
        account="Account 1",
        guild_id="99",
        guild_name="Test",
        joined_at=now,
        report_due_at=now + timedelta(hours=72),
    )
    assert store.due_reports(now=now) == []
    due = store.due_reports(now=now + timedelta(hours=73))
    assert len(due) == 1
    assert due[0]["guild_id"] == "99"


def test_mark_reported_never_due_again(tmp_path: Path):
    path = tmp_path / "servers.json"
    store = ServerStore(path)
    now = datetime.now(timezone.utc)
    store.schedule_watch(
        account="Account 1",
        guild_id="99",
        guild_name="Test",
        joined_at=now,
        report_due_at=now - timedelta(minutes=1),
    )
    store.mark_reported(
        account="Account 1",
        guild_id="99",
        reported_at=now,
        last_score=71,
        last_label="LIKELY REAL",
    )
    assert store.due_reports(now=now + timedelta(days=30)) == []

    store2 = ServerStore(path)
    store2.schedule_watch(
        account="Account 1",
        guild_id="99",
        guild_name="Test",
        joined_at=now,
        report_due_at=now - timedelta(minutes=1),
    )
    assert store2.due_reports(now=now) == []


def test_unknown_guild_schedules_once(tmp_path: Path):
    store = ServerStore(tmp_path / "servers.json")
    now = datetime.now(timezone.utc)
    created = store.ensure_watch(
        account="Account 1",
        guild_id="55",
        guild_name="New",
        now=now,
        delay_hours=72,
    )
    assert created is True
    created_again = store.ensure_watch(
        account="Account 1",
        guild_id="55",
        guild_name="New",
        now=now,
        delay_hours=72,
    )
    assert created_again is False
```

- [ ] **Step 2: Run tests — expect fail**

```bash
pytest tests/test_server_store.py -v
```

Expected: import error for `server_store`

- [ ] **Step 3: Implement server_store.py**

Create `server_store.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _key(account: str, guild_id: str) -> str:
    return f"{account}:{guild_id}"


class ServerStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._rows: dict[str, dict[str, Any]] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for row in data.get("servers", []):
            self._rows[_key(row["account"], row["guild_id"])] = row

    def flush(self) -> None:
        self.path.write_text(
            json.dumps({"servers": list(self._rows.values())}, indent=2),
            encoding="utf-8",
        )

    def schedule_watch(
        self,
        *,
        account: str,
        guild_id: str,
        guild_name: str,
        joined_at: datetime,
        report_due_at: datetime,
    ) -> None:
        k = _key(account, str(guild_id))
        existing = self._rows.get(k)
        if existing and existing.get("reported"):
            return
        if existing:
            return
        self._rows[k] = {
            "account": account,
            "guild_id": str(guild_id),
            "guild_name": guild_name,
            "joined_at": joined_at.isoformat(),
            "report_due_at": report_due_at.isoformat(),
            "reported": False,
            "reported_at": None,
            "last_score": None,
            "last_label": None,
        }
        self.flush()

    def ensure_watch(
        self,
        *,
        account: str,
        guild_id: str,
        guild_name: str,
        now: datetime,
        delay_hours: float,
    ) -> bool:
        k = _key(account, str(guild_id))
        if k in self._rows:
            return False
        due = now + timedelta(hours=delay_hours)
        self.schedule_watch(
            account=account,
            guild_id=str(guild_id),
            guild_name=guild_name,
            joined_at=now,
            report_due_at=due,
        )
        return True

    def due_reports(self, *, now: datetime) -> list[dict[str, Any]]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        due: list[dict[str, Any]] = []
        for row in self._rows.values():
            if row.get("reported"):
                continue
            due_at = datetime.fromisoformat(row["report_due_at"])
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
            if due_at <= now:
                due.append(row)
        return due

    def mark_reported(
        self,
        *,
        account: str,
        guild_id: str,
        reported_at: datetime,
        last_score: int | None,
        last_label: str | None,
    ) -> None:
        k = _key(account, str(guild_id))
        row = self._rows.get(k)
        if not row:
            return
        row["reported"] = True
        row["reported_at"] = reported_at.isoformat()
        row["last_score"] = last_score
        row["last_label"] = last_label
        self.flush()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_server_store.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add server_store.py tests/test_server_store.py
git commit -m "feat: add server watch store with one-shot report tracking"
```

---

### Task 4: health_scorer (join-based)

**Files:**
- Create: `health_scorer.py`
- Create: `tests/test_health_scorer.py`

- [ ] **Step 1: Write failing health tests**

Create `tests/test_health_scorer.py`:

```python
from health_scorer import score_guild_from_joins


def test_insufficient_data_when_few_joins():
    result = score_guild_from_joins(
        {
            "total": 3,
            "high": 1,
            "medium": 1,
            "low": 1,
            "default_avatar_pct": 33.0,
            "avg_risk": 40.0,
        }
    )
    assert result.insufficient_data is True
    assert result.label == "INSUFFICIENT DATA"
    assert result.confidence == "low"


def test_likely_real_low_risk_joins():
    result = score_guild_from_joins(
        {
            "total": 20,
            "high": 1,
            "medium": 2,
            "low": 17,
            "default_avatar_pct": 10.0,
            "avg_risk": 12.0,
        }
    )
    assert result.insufficient_data is False
    assert result.score >= 70
    assert result.label == "LIKELY REAL"
    assert result.confidence == "medium"
    assert "low_joiner_risk_avg" in result.flags


def test_suspicious_high_risk_joins():
    result = score_guild_from_joins(
        {
            "total": 20,
            "high": 14,
            "medium": 4,
            "low": 2,
            "default_avatar_pct": 80.0,
            "avg_risk": 68.0,
        }
    )
    assert result.score <= 39
    assert result.label == "SUSPICIOUS"
    assert "high_joiner_risk_avg" in result.flags
    assert "high_default_avatar_rate" in result.flags
```

- [ ] **Step 2: Run tests — expect fail**

```bash
pytest tests/test_health_scorer.py -v
```

Expected: import error

- [ ] **Step 3: Implement health_scorer.py**

Create `health_scorer.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HealthResult:
    score: int | None
    label: str
    confidence: str
    flags: list[str]
    insufficient_data: bool
    data_source: str


def score_guild_from_joins(stats: dict[str, Any], *, min_joins: int = 10) -> HealthResult:
    total = int(stats.get("total", 0))
    avg_risk = float(stats.get("avg_risk", 0))
    default_pct = float(stats.get("default_avatar_pct", 0))
    high = int(stats.get("high", 0))

    if total < min_joins:
        return HealthResult(
            score=None,
            label="INSUFFICIENT DATA",
            confidence="low",
            flags=["too_few_joins"],
            insufficient_data=True,
            data_source="joins only",
        )

    score = 100
    flags: list[str] = []

    if avg_risk <= 20:
        flags.append("low_joiner_risk_avg")
    elif avg_risk <= 40:
        score -= 15
        flags.append("moderate_joiner_risk_avg")
    else:
        score -= 35
        flags.append("high_joiner_risk_avg")

    if default_pct <= 25:
        flags.append("low_default_avatar_rate")
    elif default_pct <= 50:
        score -= 10
        flags.append("moderate_default_avatar_rate")
    else:
        score -= 25
        flags.append("high_default_avatar_rate")

    high_ratio = high / total
    if high_ratio >= 0.4:
        score -= 25
        flags.append("many_high_risk_joins")
    elif high_ratio >= 0.2:
        score -= 10
        flags.append("some_high_risk_joins")
    else:
        flags.append("few_high_risk_joins")

    score = max(0, min(100, score))
    if score >= 70:
        label = "LIKELY REAL"
    elif score >= 40:
        label = "MIXED"
    else:
        label = "SUSPICIOUS"

    return HealthResult(
        score=score,
        label=label,
        confidence="medium",
        flags=flags,
        insufficient_data=False,
        data_source="joins only",
    )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_health_scorer.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add health_scorer.py tests/test_health_scorer.py
git commit -m "feat: add join-based server health scorer"
```

---

### Task 5: Wire config + main.py (joins + guild watch + ticker)

**Files:**
- Modify: `config.py`
- Modify: `main.py`
- Modify: `.env.example`
- Modify: `Dockerfile`

- [ ] **Step 1: Extend config.py with scoring settings**

Add after `AccountConfig` in `config.py`:

```python
@dataclass(frozen=True)
class AppSettings:
    server_report_delay_hours: float
    join_burst_window_seconds: int
    join_burst_threshold: int
    health_message_sampling: bool
    data_dir: str


def load_settings() -> AppSettings:
    return AppSettings(
        server_report_delay_hours=float(os.getenv("SERVER_REPORT_DELAY_HOURS", "72")),
        join_burst_window_seconds=int(os.getenv("JOIN_BURST_WINDOW_SECONDS", "300")),
        join_burst_threshold=int(os.getenv("JOIN_BURST_THRESHOLD", "5")),
        health_message_sampling=os.getenv("HEALTH_MESSAGE_SAMPLING", "false").lower()
        in {"1", "true", "yes"},
        data_dir=os.getenv("DATA_DIR", "data"),
    )
```

- [ ] **Step 2: Rewrite main.py wiring**

Replace `main.py` with orchestration that:

1. Creates shared `JoinStore` / `ServerStore` under `DATA_DIR`
2. On `on_member_join`: skip if `member.id == self.user.id`; compute burst from store **before** recording current join for the burst check using threshold including current join (record first then check with threshold, or check count+1 — prefer: check `is_join_burst` after recording so the new join counts)
3. Score with `score_member_signals` using `avatar_url=str(member.avatar.url) if member.avatar else None` (discord.py-self: use `member.display_avatar` fallback — if `member.avatar` is None treat as default)
4. Build Telegram message with band-specific header
5. On `on_guild_join` / `on_ready`: `server_store.ensure_watch(...)`
6. Start `asyncio` task that every 60s calls `due_reports`, scores via `join_store.guild_stats(since=joined_at)`, sends report, `mark_reported` only after successful Telegram send

Full `main.py` target structure:

```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import discord

from config import AccountConfig, load_accounts, load_settings
from health_scorer import HealthResult, score_guild_from_joins
from join_store import JoinStore
from notifier import send_telegram
from risk_scorer import RiskResult, score_member_signals
from server_store import ServerStore


# keep format_account_age from existing main.py


def build_join_message(
    member: discord.Member,
    account: AccountConfig,
    risk: RiskResult,
) -> str:
    joined_at = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    if risk.band == "HIGH":
        header = "🚨 HIGH RISK JOIN"
    elif risk.band == "MEDIUM":
        header = "⚠️ MEDIUM RISK JOIN"
    else:
        header = "🔔 NEW MEMBER ALERT"

    flags = ", ".join(risk.flags) if risk.flags else "none"
    return (
        f"{header}\n"
        f"Risk: {risk.score}/100 ({risk.band})\n"
        f"Flags: {flags}\n\n"
        f"🤖 Watcher: {account.name}\n"
        f"📂 Server: {member.guild.name} (`{member.guild.id}`)\n"
        f"👤 {member.display_name} (`{member}`)\n"
        f"🆔 `{member.id}`\n"
        f"🎂 {format_account_age(member.created_at)}\n"
        f"🚪 {joined_at}\n"
    )


def build_server_report(
    *,
    account: AccountConfig,
    guild_name: str,
    guild_id: str,
    joined_at: str,
    delay_hours: float,
    health: HealthResult,
    stats: dict,
) -> str:
    score_line = (
        f"Health: {health.score}/100 — {health.label}"
        if health.score is not None
        else f"Health: {health.label}"
    )
    flags = "\n".join(f"- {f}" for f in health.flags) or "- none"
    return (
        f"📊 NEW SERVER REPORT ({int(delay_hours)}h)\n"
        f"Server: {guild_name} (`{guild_id}`)\n"
        f"Watcher: {account.name}\n"
        f"Watched since: {joined_at}\n\n"
        f"{score_line}\n"
        f"Confidence: {health.confidence}\n"
        f"Data: {health.data_source}\n\n"
        f"Flags:\n{flags}\n\n"
        f"Join stats (window):\n"
        f"- Joins: {stats['total']}\n"
        f"- HIGH / MEDIUM / LOW: {stats['high']} / {stats['medium']} / {stats['low']}\n"
        f"- Default avatar joins: {stats['default_avatar_pct']}%\n"
        f"- Avg joiner risk: {stats['avg_risk']}\n"
    )


class JoinNotifierClient(discord.Client):
    def __init__(
        self,
        account: AccountConfig,
        *,
        join_store: JoinStore,
        server_store: ServerStore,
        settings,
    ) -> None:
        super().__init__()
        self.account = account
        self.join_store = join_store
        self.server_store = server_store
        self.settings = settings

    async def on_ready(self) -> None:
        print(
            f"[{self.account.name}] Logged in as {self.user} — "
            f"watching {len(self.guilds)} server(s)"
        )
        now = datetime.now(timezone.utc)
        for guild in self.guilds:
            self.server_store.ensure_watch(
                account=self.account.name,
                guild_id=str(guild.id),
                guild_name=guild.name,
                now=now,
                delay_hours=self.settings.server_report_delay_hours,
            )
        self.loop.create_task(self._report_ticker())

    async def on_guild_join(self, guild: discord.Guild) -> None:
        now = datetime.now(timezone.utc)
        created = self.server_store.ensure_watch(
            account=self.account.name,
            guild_id=str(guild.id),
            guild_name=guild.name,
            now=now,
            delay_hours=self.settings.server_report_delay_hours,
        )
        if created:
            print(
                f"[{self.account.name}] Watching new server {guild.name} — "
                f"report due in {self.settings.server_report_delay_hours}h"
            )

    async def on_member_join(self, member: discord.Member) -> None:
        if self.user and member.id == self.user.id:
            return

        now = datetime.now(timezone.utc)
        # provisional record omitted: score burst using current store + 1
        burst = self.join_store.is_join_burst(
            str(member.guild.id),
            now=now,
            window_seconds=self.settings.join_burst_window_seconds,
            threshold=max(1, self.settings.join_burst_threshold - 1),
        )
        # Better approach in implementation: record after score, but for burst
        # include this join by counting existing in window then adding 1.
        # Use helper: treat burst if (count_in_window + 1) >= threshold.

        default_avatar = member.avatar is None
        risk = score_member_signals(
            created_at=member.created_at,
            avatar_url=None if default_avatar else str(member.avatar.url),
            username=str(member),
            is_bot=bool(member.bot),
            join_burst=burst,
        )

        self.join_store.record_join(
            guild_id=str(member.guild.id),
            user_id=str(member.id),
            timestamp=now,
            risk_score=risk.score,
            band=risk.band,
            flags=risk.flags,
            default_avatar=default_avatar,
        )

        message = build_join_message(member, self.account, risk)
        print(
            f"[{self.account.name}] Member joined: {member} in {member.guild.name} "
            f"[{risk.band} {risk.score}]"
        )
        try:
            send_telegram(
                message,
                bot_token=self.account.telegram_bot_token,
                chat_id=self.account.telegram_chat_id,
            )
        except Exception as exc:
            print(f"[{self.account.name}] Failed to send Telegram notification: {exc}")

    async def _report_ticker(self) -> None:
        while not self.is_closed():
            await self._process_due_reports()
            await asyncio.sleep(60)

    async def _process_due_reports(self) -> None:
        now = datetime.now(timezone.utc)
        for row in self.server_store.due_reports(now=now):
            if row["account"] != self.account.name:
                continue
            joined_at = datetime.fromisoformat(row["joined_at"])
            if joined_at.tzinfo is None:
                joined_at = joined_at.replace(tzinfo=timezone.utc)
            stats = self.join_store.guild_stats(row["guild_id"], since=joined_at)
            health = score_guild_from_joins(stats)
            message = build_server_report(
                account=self.account,
                guild_name=row["guild_name"],
                guild_id=row["guild_id"],
                joined_at=row["joined_at"],
                delay_hours=self.settings.server_report_delay_hours,
                health=health,
                stats=stats,
            )
            try:
                send_telegram(
                    message,
                    bot_token=self.account.telegram_bot_token,
                    chat_id=self.account.telegram_chat_id,
                )
            except Exception as exc:
                print(
                    f"[{self.account.name}] Server report failed for "
                    f"{row['guild_name']}: {exc}"
                )
                continue
            self.server_store.mark_reported(
                account=self.account.name,
                guild_id=row["guild_id"],
                reported_at=now,
                last_score=health.score,
                last_label=health.label,
            )
            print(
                f"[{self.account.name}] Sent one-shot server report for "
                f"{row['guild_name']} ({health.label})"
            )


async def run_account(
    account: AccountConfig,
    *,
    join_store: JoinStore,
    server_store: ServerStore,
    settings,
) -> None:
    client = JoinNotifierClient(
        account,
        join_store=join_store,
        server_store=server_store,
        settings=settings,
    )
    try:
        await client.start(account.discord_token)
    except discord.LoginFailure as exc:
        raise discord.LoginFailure(
            f"[{account.name}] Invalid Discord token — get a fresh token from "
            f"Discord DevTools and update your .env"
        ) from exc


async def main_async() -> None:
    settings = load_settings()
    data_dir = Path(settings.data_dir)
    join_store = JoinStore(data_dir / "join_history.json")
    server_store = ServerStore(data_dir / "server_watch.json")
    accounts = load_accounts()
    print(f"Starting {len(accounts)} Discord account(s)...")
    await asyncio.gather(
        *(
            run_account(
                account,
                join_store=join_store,
                server_store=server_store,
                settings=settings,
            )
            for account in accounts
        )
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
```

**Burst fix in implementation:** replace the provisional burst logic with:

```python
window = self.settings.join_burst_window_seconds
threshold = self.settings.join_burst_threshold
# count existing in window, then +1 for this joiner
existing_burst = self.join_store.is_join_burst(
    str(member.guild.id),
    now=now,
    window_seconds=window,
    threshold=threshold,
)
# is_join_burst uses >= threshold on *existing* rows only.
# Add method or inline: burst if count_in_window + 1 >= threshold.
```

Add to `join_store.py` during this task if needed:

```python
def count_joins_in_window(self, guild_id: str, *, now: datetime, window_seconds: int) -> int:
    ...
```

Then `join_burst = count + 1 >= threshold`.

- [ ] **Step 3: Update .env.example**

Append:

```
SERVER_REPORT_DELAY_HOURS=72
JOIN_BURST_WINDOW_SECONDS=300
JOIN_BURST_THRESHOLD=5
HEALTH_MESSAGE_SAMPLING=false
DATA_DIR=data
```

- [ ] **Step 4: Update Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py notifier.py config.py risk_scorer.py health_scorer.py join_store.py server_store.py ./
RUN mkdir -p /app/data

ENV DATA_DIR=/app/data

CMD ["python", "main.py"]
```

Note for Railway: attach a volume to `/app/data` so `server_watch.json` survives redeploys (otherwise already-reported state resets and could re-schedule — `ensure_watch` only schedules unknown guilds; without volume, reported flags are lost and **servers would get a new 72h schedule after every redeploy**. Document this clearly in README.)

- [ ] **Step 5: Run unit tests**

```bash
pytest tests/ -v
```

Expected: all PASSED

- [ ] **Step 6: Syntax check main**

```bash
python -m py_compile main.py config.py
```

Expected: exit 0

- [ ] **Step 7: Commit**

```bash
git add main.py config.py .env.example Dockerfile join_store.py
git commit -m "feat: wire joiner risk alerts and 72h one-shot server reports"
```

---

### Task 6: README + manual test notes

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Document:

1. Joiner alerts include Risk score / band / flags  
2. New servers you join get one report after 72h, never again  
3. New env vars table  
4. `DATA_DIR` / Railway volume recommendation at `/app/data`  
5. Local quick test: `SERVER_REPORT_DELAY_HOURS=0.01` to force a report soon  
6. Remove any `/health` or 12h digest docs if present  

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: explain joiner risk scoring and 72h server reports"
```

---

### Task 7: Smoke verification

- [ ] **Step 1: Run full pytest**

```bash
pytest tests/ -v
```

Expected: all PASSED

- [ ] **Step 2: Optional local smoke (manual)**

```bash
SERVER_REPORT_DELAY_HOURS=0.01 python main.py
```

- Join a throwaway server with the watcher → wait ~1 minute → one server report  
- Restart → no second report  
- Have a test user join → risk-banded join alert  

- [ ] **Step 3: Final commit if any fixes**

Only if smoke found bugs; otherwise done.

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Joiner risk scores + flags | 1, 5 |
| LOW/MEDIUM/HIGH Telegram formatting | 5 |
| Join burst signal | 2, 5 |
| Persist joins | 2 |
| Schedule on guild join + startup | 3, 5 |
| 72h delay (env default) | 5 |
| One-shot report then never again | 3, 5 |
| Mark reported only after successful Telegram send | 5 |
| Join-based health + insufficient data | 4 |
| Message sampling off by default | 5 (flag present; sampling not required in v1) |
| No `/health`, no 12h digest | N/A (omitted) |
| README | 6 |
| data/ persistence for Railway | 5 Dockerfile + 6 README |

## Out of scope for this plan (explicit)

- Telegram `/health` commands  
- Recurring digests  
- Live message sampling implementation (flag reserved; join-only scoring in v1)  
- Resetting reported servers without deleting `data/server_watch.json`
