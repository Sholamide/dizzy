from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import AccountConfig
from health_scorer import HealthResult
from join_store import JoinStore
from main import build_join_message, build_server_report_message, process_due_reports
from risk_scorer import RiskResult
from server_store import ServerStore


class FakeGuild:
    id = 123
    name = "Test Guild"


class FakeMember:
    id = 456
    display_name = "New Joiner"
    created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    guild = FakeGuild()
    bot = False
    avatar = None

    def __str__(self) -> str:
        return "newjoiner1234"


def _account() -> AccountConfig:
    return AccountConfig(
        name="Account 1",
        discord_token="discord-token",
        telegram_bot_token="telegram-token",
        telegram_chat_id="chat-id",
    )


def test_join_message_uses_risk_header_and_flags():
    message = build_join_message(
        FakeMember(),
        _account(),
        RiskResult(score=75, band="HIGH", flags=["join_burst", "default_avatar"]),
    )

    assert "HIGH RISK JOIN ALERT" in message
    assert "Risk score: 75/100" in message
    assert "join_burst" in message
    assert "default_avatar" in message
    assert "Watcher: Account 1" in message


def test_server_report_message_includes_join_stats_and_health_result():
    message = build_server_report_message(
        account=_account(),
        guild_name="Test Guild",
        guild_id="123",
        joined_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        stats={
            "total": 12,
            "high": 2,
            "medium": 3,
            "low": 7,
            "default_avatar_pct": 25.0,
            "avg_risk": 18.5,
        },
        health=HealthResult(
            score=91,
            label="LIKELY REAL",
            confidence="medium",
            flags=["low_joiner_risk_avg"],
            insufficient_data=False,
            data_source="joins only",
        ),
    )

    assert "NEW SERVER REPORT (72h)" in message
    assert "LIKELY REAL" in message
    assert "Health score: 91/100" in message
    assert "Total joins: 12" in message
    assert "Data source: joins only" in message


def test_process_due_reports_marks_reported_after_success(tmp_path: Path):
    account = _account()
    now = datetime.now(timezone.utc)
    join_store = JoinStore(tmp_path / "joins.json")
    server_store = ServerStore(tmp_path / "servers.json")
    server_store.schedule_watch(
        account=account.name,
        guild_id="123",
        guild_name="Test Guild",
        joined_at=now - timedelta(hours=73),
        report_due_at=now - timedelta(minutes=1),
    )

    sent_messages: list[str] = []

    asyncio.run(
        process_due_reports(
            account=account,
            join_store=join_store,
            server_store=server_store,
            now=now,
            send=lambda message, **kwargs: sent_messages.append(message),
        )
    )

    assert len(sent_messages) == 1
    assert server_store.due_reports(now=now) == []


def test_process_due_reports_leaves_due_after_send_failure(tmp_path: Path):
    account = _account()
    now = datetime.now(timezone.utc)
    join_store = JoinStore(tmp_path / "joins.json")
    server_store = ServerStore(tmp_path / "servers.json")
    server_store.schedule_watch(
        account=account.name,
        guild_id="123",
        guild_name="Test Guild",
        joined_at=now - timedelta(hours=73),
        report_due_at=now - timedelta(minutes=1),
    )

    def fail_send(message: str, **kwargs: str) -> None:
        raise RuntimeError("telegram down")

    asyncio.run(
        process_due_reports(
            account=account,
            join_store=join_store,
            server_store=server_store,
            now=now,
            send=fail_send,
        )
    )

    assert len(server_store.due_reports(now=now)) == 1
