"""CLI — composition root для консольного использования (см. §12
спецификации). Связывает конкретные адаптеры (MongoUserRepository,
TelegramNotifier) с domain-сервисами; сам domain-слой ничего не знает про
Typer.

Использование:
    another-admin invite --comment "Друг из Питера" --quota-gb 50
    another-admin invite --comment "Друг из Питера" --notify-telegram 123456789
    another-admin revoke --client-id drug-iz-pitera-a1b2c3
    another-admin list
    another-admin report
"""

from __future__ import annotations

from pathlib import Path

import typer
from pymongo import MongoClient

from another_admin.adapters.mongo_repository import MongoUserRepository
from another_admin.adapters.qr_generator import generate_qr_png
from another_admin.adapters.telegram_notifier import TelegramNotifier
from another_admin.config import load_config
from another_admin.domain.device_provisioning_service import (
    ClientNotFoundError,
    DeviceProvisioningService,
)
from another_admin.domain.quota_report_service import QuotaReportService

app = typer.Typer(help="Another VPN — консольная админка (см. control-plane-admin/README.md)")

GIGABYTE = 1024**3


def _build_repo() -> MongoUserRepository:
    cfg = load_config()
    client: MongoClient = MongoClient(cfg.mongo_uri)
    collection = client[cfg.mongo_db_name]["users"]
    return MongoUserRepository(collection)


def _build_provisioning_service() -> DeviceProvisioningService:
    cfg = load_config()
    return DeviceProvisioningService(repo=_build_repo(), control_plane_url=cfg.control_plane_url)


@app.command()
def invite(
    comment: str = typer.Option(..., "--comment", help="Человекочитаемая метка (см. §10: поле comment)"),
    quota_gb: float = typer.Option(50.0, "--quota-gb", help="Лимит трафика в ГБ, 0 = безлимит"),
    notify_telegram: str | None = typer.Option(
        None, "--notify-telegram", help="Chat ID — отправить QR-код приглашения прямо в Telegram"
    ),
    output: Path | None = typer.Option(None, "--output", help="Сохранить QR-код в PNG-файл"),
) -> None:
    """Создаёт одноразовое приглашение для нового устройства (§7.1)."""
    service = _build_provisioning_service()
    quota_bytes = int(quota_gb * GIGABYTE) if quota_gb > 0 else 0

    result = service.create_invite(comment, quota_bytes)
    qr_bytes = generate_qr_png(result.qr_payload)

    if output is not None:
        output.write_bytes(qr_bytes)
        typer.echo(f"QR сохранён: {output}")

    if notify_telegram is not None:
        cfg = load_config()
        notifier = TelegramNotifier(cfg.telegram_bot_token)
        notifier.send_invite(
            notify_telegram,
            qr_bytes,
            caption=f"Приглашение для «{comment}». Действительно 24 часа.",
        )
        typer.echo(f"QR отправлен в Telegram chat_id={notify_telegram}")

    typer.echo(f"client_id: {result.client_id}")
    typer.echo(f"enrollment_token: {result.enrollment_token}")
    typer.secho(
        "Токен показан ОДИН РАЗ — в БД хранится только его хэш (см. §7.1). "
        "Если потерян, нужно выпускать новое приглашение.",
        fg=typer.colors.YELLOW,
    )


@app.command()
def revoke(client_id: str = typer.Option(..., "--client-id")) -> None:
    """Отзывает устройство (§7.3) — блокирует немедленно на следующем /auth."""
    service = _build_provisioning_service()
    try:
        service.revoke_device(client_id)
    except ClientNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(f"{client_id}: заблокирован")


@app.command("list")
def list_devices() -> None:
    """Список всех устройств с их статусом."""
    service = _build_provisioning_service()
    devices = service.list_devices()
    if not devices:
        typer.echo("Устройств пока нет.")
        return
    for c in devices:
        status = "BANNED" if c.is_banned else ("enrolled" if c.is_enrolled else "pending enrollment")
        typer.echo(f"{c.client_id}\t{c.comment}\t{status}\t{c.bytes_used}/{c.quota_limit_bytes or '∞'} bytes")


@app.command()
def report() -> None:
    """Отчёт по использованию квоты, отсортированный по проценту использования (§8.4)."""
    service = QuotaReportService(repo=_build_repo())
    rows = service.generate_report()
    if not rows:
        typer.echo("Нет данных для отчёта.")
        return
    for row in rows:
        marker = " [BANNED]" if row.is_banned else ""
        typer.echo(f"{row.client_id}\t{row.percent_used:5.1f}%\t{row.bytes_used}/{row.quota_limit_bytes}{marker}")


@app.command()
def reissue(client_id: str = typer.Option(..., "--client-id")) -> None:
    """Банит старое устройство и выдаёт новое приглашение тому же user_id."""
    service = _build_provisioning_service()
    try:
        result = service.reissue_device(client_id)
    except ClientNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(f"отозван: {client_id}")
    typer.echo(f"client_id: {result.client_id}")
    typer.echo(f"enrollment_token: {result.enrollment_token}")


@app.command()
def keygen(
    admin_id: str = typer.Option(..., "--admin-id"),
    output: Path = typer.Option(..., "--output", help="Путь к .another-admin-key (passphrase-обёртка)"),
    passphrase: str = typer.Option(
        ...,
        "--passphrase",
        prompt=True,
        confirmation_prompt=True,
        hide_input=True,
    ),
    register: bool = typer.Option(False, "--register", help="Сразу записать публичные ключи в Mongo"),
) -> None:
    """Генерирует гибридную админ-пару (Ed25519+ML-DSA-65). Приватное — только в файле."""
    from another_admin.adapters.keyfile import create_wrapped_keyfile, dumps_keyfile
    from another_admin.domain.admin_auth import genesis_admin

    keypair, doc = create_wrapped_keyfile(admin_id, passphrase)
    output.write_text(dumps_keyfile(doc), encoding="utf-8")
    typer.echo(f"ключ записан: {output}")
    typer.echo(f"ed25519_public: {keypair.ed25519_public_hex}")
    typer.echo(f"mldsa65_public: {keypair.mldsa65_public_hex}")
    typer.secho("Файл защищён passphrase. Не кладите его в git и не в localStorage.", fg=typer.colors.YELLOW)

    if register:
        _register_admin_record(genesis_admin(admin_id, keypair.ed25519_public_hex, keypair.mldsa65_public_hex))
        typer.echo(f"admin {admin_id} записан в Mongo")


@app.command("admin-register")
def admin_register(
    keyfile: Path = typer.Option(..., "--keyfile", help="Ранее созданный .another-admin-key"),
) -> None:
    """Регистрирует публичные ключи админа в Mongo (аварийный канал, без API)."""
    import json

    from another_admin.domain.admin_auth import genesis_admin

    doc = json.loads(keyfile.read_text(encoding="utf-8"))
    _register_admin_record(
        genesis_admin(doc["admin_id"], doc["ed25519_public_hex"], doc["mldsa65_public_hex"])
    )
    typer.echo(f"admin {doc['admin_id']} записан в Mongo")


def _register_admin_record(record) -> None:
    from pymongo.errors import DuplicateKeyError

    from another_admin.adapters.async_mongo_store import _admin_to_doc

    cfg = load_config()
    client = MongoClient(cfg.mongo_uri)
    admins = client[cfg.mongo_db_name]["admins"]
    admins.create_index("admin_id", unique=True)
    try:
        admins.insert_one(_admin_to_doc(record))
    except DuplicateKeyError as exc:
        typer.secho(f"admin_id {record.admin_id!r} уже есть в базе", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
