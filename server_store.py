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
