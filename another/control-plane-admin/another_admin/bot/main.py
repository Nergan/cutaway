"""Telegram-бот — второй driving-адаптер тех же domain-сервисов, что и CLI
(§12 спецификации: "CLI и бот — просто два разных driving-адаптера одного и
того же use-case"). Только администраторы из TELEGRAM_ADMIN_IDS (§.env.example)
могут выполнять команды.

ВАЖНО (осознанное упрощение v1): pymongo — синхронный драйвер, а aiogram —
асинхронный фреймворк. Вызовы репозитория внутри async-хендлеров блокируют
event loop на время запроса к MongoDB. Для масштаба "закрытая группа
пользователей" (единицы административных команд в день) это не проблема;
при заметной нагрузке — заменить на ``motor`` (асинхронный драйвер Mongo) —
TODO v2, см. control-plane-admin/README.md.

Запуск: python -m another_admin.bot.main
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from pymongo import MongoClient

from another_admin.adapters.mongo_repository import MongoUserRepository
from another_admin.adapters.qr_generator import generate_qr_png
from another_admin.config import AdminConfig, load_config
from another_admin.domain.device_provisioning_service import (
    ClientNotFoundError,
    DeviceProvisioningService,
)
from another_admin.domain.quota_report_service import QuotaReportService

logger = logging.getLogger("another_admin.bot")

DEFAULT_QUOTA_BYTES = 50 * 1024**3  # 50 ГБ — как в дефолте CLI (cli/main.py: --quota-gb 50.0)


def _build_provisioning_service(cfg: AdminConfig) -> DeviceProvisioningService:
    client: MongoClient = MongoClient(cfg.mongo_uri)
    repo = MongoUserRepository(client[cfg.mongo_db_name]["users"])
    return DeviceProvisioningService(repo=repo, control_plane_url=cfg.control_plane_url)


def _is_admin(message: Message, cfg: AdminConfig) -> bool:
    return message.from_user is not None and message.from_user.id in cfg.telegram_admin_ids


def create_dispatcher(cfg: AdminConfig) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(Command("invite"))
    async def cmd_invite(message: Message) -> None:
        if not _is_admin(message, cfg):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Использование: /invite <комментарий>")
            return
        comment = parts[1]

        service = _build_provisioning_service(cfg)
        result = service.create_invite(comment, DEFAULT_QUOTA_BYTES)
        qr_bytes = generate_qr_png(result.qr_payload)

        await message.answer_photo(
            BufferedInputFile(qr_bytes, filename="invite.png"),
            caption=(
                f"client_id: {result.client_id}\n"
                f"enrollment_token: {result.enrollment_token}\n\n"
                "Токен показан один раз — в БД хранится только хэш (§7.1)."
            ),
        )

    @dp.message(Command("devices"))
    async def cmd_devices(message: Message) -> None:
        if not _is_admin(message, cfg):
            return
        service = _build_provisioning_service(cfg)
        devices = service.list_devices()
        if not devices:
            await message.answer("Устройств пока нет.")
            return
        lines = []
        for c in devices:
            status = "🚫 BANNED" if c.is_banned else ("✅ enrolled" if c.is_enrolled else "⏳ pending")
            lines.append(f"{c.client_id} — {c.comment} — {status}")
        await message.answer("\n".join(lines))

    @dp.message(Command("revoke"))
    async def cmd_revoke(message: Message) -> None:
        if not _is_admin(message, cfg):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Использование: /revoke <client_id>")
            return
        client_id = parts[1].strip()

        service = _build_provisioning_service(cfg)
        try:
            service.revoke_device(client_id)
        except ClientNotFoundError:
            await message.answer(f"Устройство {client_id} не найдено.")
            return
        await message.answer(f"{client_id}: заблокирован.")

    @dp.message(Command("report"))
    async def cmd_report(message: Message) -> None:
        if not _is_admin(message, cfg):
            return
        client: MongoClient = MongoClient(cfg.mongo_uri)
        repo = MongoUserRepository(client[cfg.mongo_db_name]["users"])
        rows = QuotaReportService(repo=repo).generate_report()
        if not rows:
            await message.answer("Нет данных для отчёта.")
            return
        lines = [
            f"{r.client_id}: {r.percent_used:.1f}% ({r.bytes_used}/{r.quota_limit_bytes})"
            + (" 🚫" if r.is_banned else "")
            for r in rows
        ]
        await message.answer("\n".join(lines))

    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    if not cfg.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан — см. .env.example")
    if not cfg.telegram_admin_ids:
        logger.warning("TELEGRAM_ADMIN_IDS пуст — ни одна команда не будет выполняться никем")

    bot = Bot(token=cfg.telegram_bot_token)
    dp = create_dispatcher(cfg)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
