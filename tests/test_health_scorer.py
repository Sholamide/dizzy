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
