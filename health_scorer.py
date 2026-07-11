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
