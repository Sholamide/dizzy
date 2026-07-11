import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

import discord

from config import AccountConfig, AppSettings, load_accounts, load_settings
from health_scorer import HealthResult, score_guild_from_joins
from join_store import JoinStore
from notifier import send_telegram
from risk_scorer import RiskResult, score_member_signals
from server_store import ServerStore


def format_account_age(created_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    delta = now - created_at
    days = delta.days

    if days < 1:
        age = "less than a day ago"
    elif days < 30:
        age = f"{days} day{'s' if days != 1 else ''} ago"
    elif days < 365:
        months = days // 30
        age = f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = days // 365
        age = f"{years} year{'s' if years != 1 else ''} ago"

    created_str = created_at.strftime("%b %d, %Y")
    return f"{created_str} ({age})"


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _flags_text(flags: list[str]) -> str:
    return ", ".join(flags) if flags else "none"


def _risk_header(band: str) -> str:
    return {
        "HIGH": "🚨 HIGH RISK JOIN ALERT 🚨",
        "MEDIUM": "⚠️ MEDIUM RISK JOIN ALERT ⚠️",
        "LOW": "🔔 LOW RISK JOIN ALERT 🔔",
    }.get(band, f"{band} RISK JOIN ALERT")


def build_join_message(
    member: discord.Member,
    account: AccountConfig,
    risk: RiskResult,
) -> str:
    joined_at = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    display_name = member.display_name
    username = str(member)
    guild = member.guild
    default_avatar = member.avatar is None

    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{_risk_header(risk.band)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Watcher: {account.name}\n\n"
        "🧮 RISK\n"
        f"   📊 Risk score: {risk.score}/100\n"
        f"   🏷️ Band: {risk.band}\n"
        f"   🚩 Flags: {_flags_text(risk.flags)}\n\n"
        "📌 SERVER INFO\n"
        f"   📂 Name: {guild.name}\n"
        f"   🆔 ID: `{guild.id}`\n\n"
        "👤 MEMBER INFO\n"
        f"   🏷️ Display: **{display_name}**\n"
        f"   📛 Username: `{username}`\n"
        f"   🆔 ID: `{member.id}`\n\n"
        "📅 TIMESTAMPS\n"
        f"   🎂 Account created: {format_account_age(member.created_at)}\n"
        f"   🚪 Joined server at: {joined_at}\n"
        f"   🖼️ Default avatar: {'yes' if default_avatar else 'no'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )


def build_server_report_message(
    *,
    account: AccountConfig,
    guild_name: str,
    guild_id: str,
    joined_at: datetime,
    stats: dict[str, Any],
    health: HealthResult,
) -> str:
    score = "n/a" if health.score is None else f"{health.score}/100"
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 NEW SERVER REPORT (72h)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Watcher: {account.name}\n\n"
        "📌 SERVER INFO\n"
        f"   📂 Name: {guild_name}\n"
        f"   🆔 ID: `{guild_id}`\n"
        f"   🚪 Watch started: {joined_at.strftime('%b %d, %Y %H:%M UTC')}\n\n"
        "🩺 HEALTH\n"
        f"   📊 Health score: {score}\n"
        f"   🏷️ Label: {health.label}\n"
        f"   🔎 Confidence: {health.confidence}\n"
        f"   📚 Data source: {health.data_source}\n"
        f"   🚩 Flags: {_flags_text(health.flags)}\n\n"
        "👥 JOIN STATS\n"
        f"   Total joins: {stats['total']}\n"
        f"   HIGH: {stats['high']} | MEDIUM: {stats['medium']} | LOW: {stats['low']}\n"
        f"   Default avatar rate: {stats['default_avatar_pct']}%\n"
        f"   Average risk: {stats['avg_risk']}/100\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )


async def process_due_reports(
    *,
    account: AccountConfig,
    join_store: JoinStore,
    server_store: ServerStore,
    now: datetime,
    send: Callable[..., None] = send_telegram,
) -> None:
    for row in server_store.due_reports(now=now):
        if row["account"] != account.name:
            continue

        joined_at = _parse_ts(row["joined_at"])
        stats = join_store.guild_stats(row["guild_id"], since=joined_at)
        health = score_guild_from_joins(stats)
        message = build_server_report_message(
            account=account,
            guild_name=row["guild_name"],
            guild_id=row["guild_id"],
            joined_at=joined_at,
            stats=stats,
            health=health,
        )

        try:
            send(
                message,
                bot_token=account.telegram_bot_token,
                chat_id=account.telegram_chat_id,
            )
        except Exception as exc:
            print(
                f"[{account.name}] Failed to send server report for "
                f"{row['guild_name']}: {exc}"
            )
            continue

        server_store.mark_reported(
            account=account.name,
            guild_id=row["guild_id"],
            reported_at=now,
            last_score=health.score,
            last_label=health.label,
        )


_process_due_reports = process_due_reports


class JoinNotifierClient(discord.Client):
    def __init__(
        self,
        account: AccountConfig,
        settings: AppSettings,
        join_store: JoinStore,
        server_store: ServerStore,
    ) -> None:
        super().__init__()
        self.account = account
        self.settings = settings
        self.join_store = join_store
        self.server_store = server_store
        self._report_task: asyncio.Task[None] | None = None

    async def on_ready(self) -> None:
        guild_count = len(self.guilds)
        print(
            f"[{self.account.name}] Logged in as {self.user} — "
            f"watching {guild_count} server(s)"
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
        if self._report_task is None or self._report_task.done():
            self._report_task = asyncio.create_task(self._report_ticker())

    async def on_guild_join(self, guild: discord.Guild) -> None:
        created = self.server_store.ensure_watch(
            account=self.account.name,
            guild_id=str(guild.id),
            guild_name=guild.name,
            now=datetime.now(timezone.utc),
            delay_hours=self.settings.server_report_delay_hours,
        )
        if created:
            print(f"[{self.account.name}] Scheduled server report for {guild.name}")

    async def on_member_join(self, member: discord.Member) -> None:
        if self.user and member.id == self.user.id:
            return

        now = datetime.now(timezone.utc)
        join_burst = (
            self.join_store.count_joins_in_window(
                str(member.guild.id),
                now=now,
                window_seconds=self.settings.join_burst_window_seconds,
            )
            + 1
            >= self.settings.join_burst_threshold
        )
        default_avatar = member.avatar is None
        avatar_url = None if default_avatar else str(member.avatar.url)
        try:
            risk = score_member_signals(
                created_at=member.created_at,
                avatar_url=avatar_url,
                username=str(member),
                is_bot=member.bot,
                join_burst=join_burst,
            )
        except Exception as exc:
            print(f"[{self.account.name}] Risk scoring failed: {exc}")
            risk = RiskResult(score=0, band="LOW", flags=["scoring_error"])

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
            f"[{self.account.name}] {risk.band} member joined: "
            f"{member} in {member.guild.name}"
        )

        try:
            send_telegram(
                message,
                bot_token=self.account.telegram_bot_token,
                chat_id=self.account.telegram_chat_id,
            )
        except Exception as exc:
            print(
                f"[{self.account.name}] Failed to send Telegram notification: {exc}"
            )

    async def _report_ticker(self) -> None:
        while not self.is_closed():
            await process_due_reports(
                account=self.account,
                join_store=self.join_store,
                server_store=self.server_store,
                now=datetime.now(timezone.utc),
            )
            await asyncio.sleep(60)


async def run_account(
    account: AccountConfig,
    settings: AppSettings,
    join_store: JoinStore,
    server_store: ServerStore,
) -> None:
    client = JoinNotifierClient(account, settings, join_store, server_store)
    try:
        await client.start(account.discord_token)
    except discord.LoginFailure as exc:
        raise discord.LoginFailure(
            f"[{account.name}] Invalid Discord token — get a fresh token from "
            f"Discord DevTools and update your .env"
        ) from exc


async def main_async() -> None:
    accounts = load_accounts()
    settings = load_settings()
    data_dir: Path = settings.data_dir
    join_store = JoinStore(data_dir / "join_history.json")
    server_store = ServerStore(data_dir / "server_watch.json")
    print(f"Starting {len(accounts)} Discord account(s)...")
    await asyncio.gather(
        *(
            run_account(account, settings, join_store, server_store)
            for account in accounts
        )
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
