import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".env.local", override=True)


@dataclass(frozen=True)
class AccountConfig:
    name: str
    discord_token: str
    telegram_bot_token: str
    telegram_chat_id: str


def _load_account(
    *,
    suffix: str,
    default_name: str,
    use_unsuffixed: bool,
) -> AccountConfig | None:
    if use_unsuffixed:
        discord_token = os.getenv("DISCORD_TOKEN")
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        name = os.getenv("ACCOUNT_1_NAME", default_name)
    else:
        discord_token = os.getenv(f"DISCORD_TOKEN_{suffix}")
        telegram_bot_token = os.getenv(f"TELEGRAM_BOT_TOKEN_{suffix}")
        telegram_chat_id = os.getenv(f"TELEGRAM_CHAT_ID_{suffix}")
        name = os.getenv(f"ACCOUNT_{suffix}_NAME", default_name)

    if not discord_token:
        return None

    if not telegram_bot_token or not telegram_chat_id:
        raise ValueError(f"{name}: Telegram bot token and chat ID are required")

    return AccountConfig(
        name=name,
        discord_token=discord_token.strip().strip('"').strip("'"),
        telegram_bot_token=telegram_bot_token.strip().strip('"').strip("'"),
        telegram_chat_id=telegram_chat_id.strip().strip('"').strip("'"),
    )


def load_accounts() -> list[AccountConfig]:
    accounts: list[AccountConfig] = []

    account_1 = _load_account(suffix="1", default_name="Account 1", use_unsuffixed=True)
    if account_1:
        accounts.append(account_1)

    account_2 = _load_account(suffix="2", default_name="Account 2", use_unsuffixed=False)
    if account_2:
        accounts.append(account_2)

    if not accounts:
        raise ValueError(
            "No accounts configured. Set DISCORD_TOKEN (and Telegram vars) in .env"
        )

    return accounts
