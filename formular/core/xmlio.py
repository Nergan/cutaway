"""Разбор XML без внешних сущностей и без разворачивания DTD."""

from __future__ import annotations

import re

from formular.core.errors import FormularError

_DANGEROUS = re.compile(r"<!DOCTYPE|<!ENTITY", re.IGNORECASE)
_MAX_CHARS = 8_000_000

try:
    from defusedxml.ElementTree import fromstring as _safe_fromstring
except ImportError:  # pragma: no cover - в окружении тестов пакета может не быть
    _safe_fromstring = None


def assert_plain_xml(content: str) -> None:
    if len(content) > _MAX_CHARS:
        raise FormularError("XML is too large.", 413)
    if _DANGEROUS.search(content):
        raise FormularError("XML with a document type or entities is not allowed.", 422)


def parse_xml(content: str):
    assert_plain_xml(content)
    if _safe_fromstring is not None:
        try:
            _safe_fromstring(content)
        except Exception as exc:
            raise FormularError("XML could not be read.", 422) from exc
    import xmltodict

    try:
        return xmltodict.parse(content, disable_entities=True)
    except Exception as exc:
        raise FormularError("XML could not be read.", 422) from exc
