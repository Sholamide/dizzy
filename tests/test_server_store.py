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
