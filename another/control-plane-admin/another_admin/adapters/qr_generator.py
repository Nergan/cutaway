"""generate_qr_png — не оформлен как порт/адаптер в строгом смысле (нет
внешнего состояния, нет альтернативных реализаций, которые имело бы смысл
подменять), это чистая функция-утилита поверх библиотеки ``qrcode``.
Используется и CLI, и Telegram-ботом (§12 спецификации)."""

from __future__ import annotations

import io

import qrcode


def generate_qr_png(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
