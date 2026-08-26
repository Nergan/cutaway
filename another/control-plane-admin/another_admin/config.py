"""Загрузка конфигурации из переменных окружения — единая точка входа для
CLI и Telegram-бота (два driving-адаптера одного и того же domain-слоя,
см. §12 архитектурной спецификации).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class MissingConfigError(RuntimeError):
    """Обязательная переменная окружения не задана."""


@dataclass(frozen=True)
class AdminConfig:
    mongo_uri: str
    mongo_db_name: str
    control_plane_url: str
    telegram_bot_token: str
    telegram_admin_ids: frozenset[int] = field(default_factory=frozenset)


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise MissingConfigError(
            f"переменная окружения {key} не задана — см. .env.example в корне репозитория"
        )
    return value


def load_config() -> AdminConfig:
    """Читает конфигурацию из окружения процесса.

    ``telegram_bot_token``/``telegram_admin_ids`` не обязательны для команд
    CLI, не использующих Telegram (invite без --notify-telegram, revoke,
    list, report) — отсутствие токена проверяется только в точке
    использования (adapters/telegram_notifier.py, bot/main.py), а не здесь,
    чтобы не блокировать чисто-Mongo операции требованием настроить бота.
    """
    admin_ids_raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    admin_ids = frozenset(int(x) for x in admin_ids_raw.split(",") if x.strip())

    return AdminConfig(
        mongo_uri=_require("MONGO_URI"),
        mongo_db_name=os.environ.get("MONGO_DB_NAME", "another"),
        control_plane_url=os.environ.get("ANOTHER_CONTROL_PLANE_URL", "http://127.0.0.1:8787"),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_admin_ids=admin_ids,
    )
