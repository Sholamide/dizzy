import os
from datetime import datetime, timezone

import discord
from dotenv import load_dotenv

from notifier import send_telegram

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


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


def build_join_message(member: discord.Member) -> str:
    joined_at = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    display_name = member.display_name
    username = str(member)
    guild = member.guild

    return (
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🔔 NEW MEMBER ALERT 🔔\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
    async def on_ready(self) -> None:
        guild_count = len(self.guilds)
        print(f"Logged in as {self.user} — watching {guild_count} server(s)")

    async def on_member_join(self, member: discord.Member) -> None:
        message = build_join_message(member)
        print(f"Member joined: {member} in {member.guild.name}")

        try:
            send_telegram(message)
        except Exception as exc:
            print(f"Failed to send Telegram notification: {exc}")


def main() -> None:
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN must be set in .env")

    client = JoinNotifierClient()
    client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
