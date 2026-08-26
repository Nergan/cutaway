"""NotifierPort — доставка приглашения адресату. В v1 единственная
реализация — Telegram (adapters/telegram_notifier.py), но порт намеренно не
называется TelegramNotifierPort: смена канала (Matrix/Signal-бот и т.п.,
см. §19 архитектурной спецификации) — это замена одного адаптера, а не
переписывание domain-слоя."""

from __future__ import annotations

from typing import Protocol


class NotifierPort(Protocol):
    def send_invite(self, chat_id: str, qr_image_png: bytes, caption: str) -> None: ...
