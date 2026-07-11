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


def test_count_joins_in_window_for_pre_record_burst(tmp_path: Path):
    store = JoinStore(tmp_path / "joins.json", retention_days=7)
    now = datetime.now(timezone.utc)
    guild_id = "333"
    for i in range(4):
        store.record_join(
            guild_id=guild_id,
            user_id=str(i),
            timestamp=now - timedelta(seconds=10 * i),
            risk_score=10,
            band="LOW",
            flags=[],
            default_avatar=False,
        )
    count = store.count_joins_in_window(guild_id, now=now, window_seconds=300)
    assert count == 4
    assert count + 1 >= 5  # pre-record: 5th joiner should be treated as burst


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
