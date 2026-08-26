"""TelegramNotifier — реализация NotifierPort через обычные HTTPS-вызовы к
Telegram Bot API (``httpx``), НЕ через aiogram. Осознанное решение: aiogram
заточен под асинхронный long-polling/webhook цикл самого бота
(bot/main.py), а этот адаптер нужен и синхронному CLI (cli/main.py, флаг
``--notify-telegram``) — тащить туда асинхронный event loop ради одного
запроса избыточно.
"""

from __future__ import annotations

import httpx


class TelegramNotifier:
    def __init__(self, bot_token: str, timeout_seconds: float = 15.0) -> None:
        if not bot_token:
            raise ValueError("telegram_bot_token не задан — см. .env.example: TELEGRAM_BOT_TOKEN")
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._timeout = timeout_seconds

    def send_invite(self, chat_id: str, qr_image_png: bytes, caption: str) -> None:
        response = httpx.post(
            f"{self._base_url}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("invite.png", qr_image_png, "image/png")},
            timeout=self._timeout,
        )
        response.raise_for_status()
