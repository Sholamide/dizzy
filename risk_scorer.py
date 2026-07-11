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
