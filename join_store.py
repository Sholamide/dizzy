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
