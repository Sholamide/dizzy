import asyncio
from datetime import datetime, timezone

import discord

from config import AccountConfig, load_accounts
from notifier import send_telegram


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


def build_join_message(member: discord.Member, account: AccountConfig) -> str:
    joined_at = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    display_name = member.display_name
    username = str(member)
    guild = member.guild

    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 NEW MEMBER ALERT 🔔\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Watcher: {account.name}\n\n"
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
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )


class JoinNotifierClient(discord.Client):
    def __init__(self, account: AccountConfig) -> None:
        super().__init__()
        self.account = account

    async def on_ready(self) -> None:
        guild_count = len(self.guilds)
        print(
            f"[{self.account.name}] Logged in as {self.user} — "
            f"watching {guild_count} server(s)"
        )

    async def on_member_join(self, member: discord.Member) -> None:
        message = build_join_message(member, self.account)
        print(
            f"[{self.account.name}] Member joined: {member} in {member.guild.name}"
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


async def run_account(account: AccountConfig) -> None:
    client = JoinNotifierClient(account)
    try:
        await client.start(account.discord_token)
    except discord.LoginFailure as exc:
        raise discord.LoginFailure(
            f"[{account.name}] Invalid Discord token — get a fresh token from "
            f"Discord DevTools and update your .env"
        ) from exc


async def main_async() -> None:
    accounts = load_accounts()
    print(f"Starting {len(accounts)} Discord account(s)...")
    await asyncio.gather(*(run_account(account) for account in accounts))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
