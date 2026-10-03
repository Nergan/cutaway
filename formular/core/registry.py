"""Реестр форматов и операций formular.

Граф прямых шагов и список целей интерфейса живут здесь. Движки конвертера
подключаются отдельно, поэтому планировщик можно проверять без них.
"""

from __future__ import annotations

DIRECT_EDGES: dict[str, list[str]] = {
    "docx": ["pdf", "html", "txt", "md"],
    "doc": ["pdf", "docx"],
    "pptx": ["pdf"],
    "rtf": ["pdf", "docx", "html", "txt", "md"],
    "odt": ["pdf", "docx"],
    "txt": ["pdf", "html", "md", "docx", "json"],
    "html": ["pdf", "md", "txt", "docx"],
    "md": ["html", "txt", "docx"],
    "epub": ["html", "txt", "md"],
    "pdf": ["html", "txt"],
    "djvu": ["pdf"],
    "csv": ["pdf"],
    "xlsx": ["csv", "pdf"],
    "svg": ["png", "pdf"],
    "jpg": ["png", "webp", "pdf"],
    "png": ["jpg", "webp", "pdf"],
    "webp": ["jpg", "png", "pdf"],
    "gif": ["png", "mp4"],
    "mp4": ["webm", "gif", "mp3", "ogg"],
    "webm": ["mp4", "gif", "mp3", "ogg"],
    "mp3": ["wav", "ogg", "mp4", "webm"],
    "wav": ["mp3", "ogg", "mp4", "webm"],
    "ogg": ["mp3", "wav", "mp4", "webm"],
    "zip": ["7z", "tar", "gz"],
    "rar": ["zip", "7z", "tar", "gz"],
    "7z": ["zip", "tar", "gz"],
    "tar": ["zip", "7z", "gz"],
    "gz": ["zip", "7z", "tar"],
    "json": ["yaml", "toml", "xml", "txt"],
    "yaml": ["json", "toml", "xml", "txt"],
    "toml": ["json", "yaml", "xml", "txt"],
    "xml": ["json", "yaml", "toml", "txt"],
}

# Цели, которые интерфейс показывает сразу. Часть из них — несколько шагов графа.
ALLOWED_CONVERSIONS: dict[str, list[str]] = {
    "docx": ["pdf", "html", "txt", "md"],
    "doc": ["pdf", "html", "txt", "md"],
    "pptx": ["pdf", "html", "txt", "md", "xml"],
    "pdf": ["html", "txt", "md"],
    "html": ["pdf", "md", "txt", "xml"],
    "md": ["pdf", "html", "txt"],
    "txt": ["pdf", "html", "md", "json", "yaml", "toml", "xml"],
    "rtf": ["pdf", "html", "txt", "md"],
    "odt": ["pdf", "html", "txt", "md"],
    "epub": ["pdf", "html", "txt", "md"],
    "djvu": ["pdf", "html", "txt", "md"],
    "json": ["yaml", "toml", "xml", "md", "txt", "html", "pdf"],
    "yaml": ["json", "toml", "xml", "md", "txt", "html", "pdf"],
    "toml": ["json", "yaml", "xml", "md", "txt", "html", "pdf"],
    "xml": ["json", "yaml", "toml", "md", "txt", "html", "pdf"],
    "jpg": ["jpg", "png", "webp", "pdf"],
    "png": ["png", "jpg", "webp", "pdf"],
    "webp": ["webp", "jpg", "png", "pdf"],
    "svg": ["png", "jpg", "pdf"],
    "gif": ["gif", "mp4", "png"],
    "mp3": ["mp3", "wav", "ogg", "mp4", "webm"],
    "wav": ["wav", "mp3", "ogg", "mp4", "webm"],
    "ogg": ["ogg", "mp3", "wav", "mp4", "webm"],
    "mp4": ["mp4", "webm", "gif", "mp3", "ogg"],
    "webm": ["webm", "mp4", "gif", "mp3", "ogg"],
    "csv": ["pdf"],
    "xlsx": ["csv", "pdf"],
    "zip": ["7z", "tar", "gz"],
    "rar": ["zip", "7z", "tar", "gz"],
    "7z": ["zip", "tar", "gz"],
    "tar": ["zip", "7z", "gz"],
    "gz": ["zip", "7z", "tar"],
}

MEDIA_OPTION_FIELDS = (
    "trim_start",
    "trim_end",
    "resize",
    "crop",
    "filter",
    "tempo",
    "reverb",
    "bass",
    "custom_ffmpeg",
)

# Поздние этапы. Доступны в каталоге как явный отказ, без зависимостей и сети.
UNAVAILABLE_OPERATIONS = (
    {
        "id": "pdf.translate",
        "kind": "ai",
        "available": False,
        "reason": "Document translation is planned for a later stage.",
    },
    {
        "id": "speech.transcribe",
        "kind": "ai",
        "available": False,
        "reason": "Speech models are not loaded on this server yet.",
    },
    {
        "id": "bytecode.recover",
        "kind": "decompile",
        "available": False,
        "reason": "A runtime for bytecode recovery is not included until its resource cost is planned.",
    },
)


def conversion_operations() -> list[dict]:
    operations = []
    for source, targets in sorted(DIRECT_EDGES.items()):
        for target in targets:
            operations.append(
                {
                    "id": f"convert.{source}.{target}",
                    "kind": "convert",
                    "source": source,
                    "target": target,
                    "available": True,
                }
            )
    return operations


def public_operations() -> list[dict]:
    ready = [
        {
            "id": "text.language",
            "kind": "ai",
            "available": True,
            "reason": "Local language cues. Downloaded weights are removed when the task finishes.",
        }
    ]
    return ready + conversion_operations() + [dict(item) for item in UNAVAILABLE_OPERATIONS]
