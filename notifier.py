import requests


class TelegramError(Exception):
    pass


def send_telegram(message: str, *, bot_token: str, chat_id: str) -> None:
    """Send a message to a Telegram chat."""
    if not bot_token or not chat_id:
        raise ValueError("Telegram bot token and chat ID are required")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=10,
    )

    if not response.ok:
        try:
            detail = response.json().get("description", response.text)
        except ValueError:
            detail = response.text
        raise TelegramError(f"Telegram API error: {detail}")
