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
