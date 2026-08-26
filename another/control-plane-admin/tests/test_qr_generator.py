from __future__ import annotations

from another_admin.adapters.qr_generator import generate_qr_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_generate_qr_png_returns_valid_png_bytes():
    result = generate_qr_png("another://enroll?token=abc123&cp=https://cf-worker.another.example")
    assert result.startswith(PNG_MAGIC)
    assert len(result) > 100  # не пустая заглушка


def test_different_payloads_produce_different_images():
    a = generate_qr_png("payload-a")
    b = generate_qr_png("payload-b")
    assert a != b
