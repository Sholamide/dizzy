"""One-off Telegram test. Run: python test_telegram.py"""

from config import load_accounts
from notifier import TelegramError, send_telegram


def main() -> None:
    accounts = load_accounts()
    account = next((a for a in accounts if a.name == "Account 2"), accounts[-1])

    message = (
        "🧪 TEST MESSAGE\n\n"
        f"If you see this, {account.name}'s Telegram bot is working."
    )

    print(f"Sending test message via {account.name}...")
    try:
        send_telegram(
            message,
            bot_token=account.telegram_bot_token,
            chat_id=account.telegram_chat_id,
        )
        print("SUCCESS — check Telegram on your phone.")
    except TelegramError as exc:
        print(f"FAILED — {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
