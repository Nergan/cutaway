"""Request notifications for share, exchange, and demand."""

from __future__ import annotations

import asyncio
import logging
import re

from netlazy.config import settings
from netlazy.domain.models import PushPreferences, PushSubscription
from netlazy.infrastructure.fcm_push import send_fcm
from netlazy.infrastructure.web_push import (
    b64url_decode,
    generate_vapid_pem,
    load_vapid_key,
    push_endpoint_allowed,
    send_web_push,
    vapid_public_b64url,
)

LANGS = ("en", "ru", "pt", "zh", "ja", "ko")
PLATFORMS = ("windows", "android", "web")
TRANSPORTS = ("webpush", "fcm")
_PREF_FOR = {"share": "share", "exchange": "exchange", "demand": "demand", "mutual": "exchange"}
_ORIGIN = re.compile(r"^https?://[A-Za-z0-9._:-]{1,200}$")

_COPY = {
    "en": {
        "share": ("share", "new share request"),
        "exchange": ("exchange", "new exchange request"),
        "demand": ("demand", "new demand request"),
    },
    "ru": {
        "share": ("поделиться", "новый запрос: поделиться"),
        "exchange": ("обменяться", "новый запрос: обменяться"),
        "demand": ("затребовать", "новый запрос: затребовать"),
    },
    "pt": {
        "share": ("compartilhar", "novo pedido para compartilhar"),
        "exchange": ("trocar", "novo pedido para trocar"),
        "demand": ("exigir", "novo pedido para exigir"),
    },
    "zh": {
        "share": ("分享", "新的分享請求"),
        "exchange": ("交換", "新的交換請求"),
        "demand": ("要求", "新的要求請求"),
    },
    "ja": {
        "share": ("共有", "新しい共有リクエスト"),
        "exchange": ("交換", "新しい交換リクエスト"),
        "demand": ("要求", "新しい要求リクエスト"),
    },
    "ko": {
        "share": ("공유", "새 공유 요청"),
        "exchange": ("교환", "새 교환 요청"),
        "demand": ("요구", "새 요구 요청"),
    },
}

_LOOK = {
    "share": ("/netlazy/static/push/share.png", "#6e9dae"),
    "exchange": ("/netlazy/static/push/exchange.png", "#8da970"),
    "demand": ("/netlazy/static/push/demand.png", "#bd6a5e"),
    "mutual": ("/netlazy/static/push/exchange.png", "#8da970"),
}


def notification_payload(sub: PushSubscription, handshake_type: str, handshake_id: str) -> dict:
    kind = "exchange" if handshake_type == "mutual" else handshake_type
    lang = sub.lang if sub.lang in _COPY else "en"
    title, body = _COPY[lang].get(kind) or _COPY["en"][kind]
    icon_path, color = _LOOK[handshake_type if handshake_type in _LOOK else kind]
    icon_url = ""
    if sub.origin.startswith("https://"):
        icon_url = sub.origin.rstrip("/") + icon_path
    return {
        "title": title,
        "body": body,
        "icon": icon_path,
        "icon_url": icon_url,
        "color": color,
        "type": handshake_type,
        "tag": handshake_id[:32],
        "open_path": sub.open_path or "/netlazy/inbox",
        "platform": sub.platform,
    }


def _clean_open_path(path: str) -> str:
    if not path or len(path) > 200 or not path.startswith("/") or path.startswith("//") or ".." in path:
        raise ValueError("invalid open_path")
    return path


def _clean_lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


def _clean_origin(origin: str) -> str:
    origin = (origin or "").strip()
    if not origin:
        return ""
    if not _ORIGIN.match(origin):
        raise ValueError("invalid origin")
    return origin


class PushService:
    def __init__(self, repo, deliver=None):
        self._repo = repo
        self._deliver = deliver

    async def public_key(self) -> str:
        return vapid_public_b64url(await self._signing_key())

    async def preferences(self, user_id: str) -> PushPreferences:
        prefs = await self._repo.get_preferences(user_id)
        prefs.lang = _clean_lang(prefs.lang)
        return prefs

    async def save_preferences(self, user_id: str, prefs: PushPreferences) -> PushPreferences:
        stored = PushPreferences(
            enabled=bool(prefs.enabled),
            share=bool(prefs.share),
            exchange=bool(prefs.exchange),
            demand=bool(prefs.demand),
            lang=_clean_lang(prefs.lang),
        )
        await self._repo.save_preferences(user_id, stored)
        return stored

    async def register(self, user_id: str, sub: PushSubscription) -> None:
        if sub.platform not in PLATFORMS or sub.transport not in TRANSPORTS:
            raise ValueError("unsupported push platform")
        if sub.platform in ("windows", "web") and sub.transport != "webpush":
            raise ValueError("this platform uses web push")
        if sub.transport == "fcm" and sub.platform != "android":
            raise ValueError("android push is only for android")
        sub.user_id = user_id
        sub.lang = _clean_lang(sub.lang)
        sub.open_path = _clean_open_path(sub.open_path)
        sub.origin = _clean_origin(sub.origin)
        if sub.transport == "webpush":
            self._check_web_push(sub)
        else:
            token = (sub.token or "").strip()
            if not token or len(token) > 4096:
                raise ValueError("token is required")
            sub.token = token
            sub.endpoint = ""
            sub.p256dh = ""
            sub.auth = ""
        await self._repo.upsert_subscription(sub)

    async def unregister(self, user_id: str, *, endpoint: str = "", token: str = "") -> None:
        if not endpoint and not token:
            raise ValueError("endpoint or token is required")
        await self._repo.delete_subscription(user_id, endpoint=endpoint, token=token)

    async def delete_user(self, user_id: str) -> None:
        try:
            await self._repo.delete_user(user_id)
        except Exception:
            logging.warning("push subscriptions were not removed")

    async def notify_request(self, user_id: str, handshake_type: str, handshake_id: str) -> None:
        try:
            await self._notify_request(user_id, handshake_type, handshake_id)
        except Exception:
            logging.warning("push notification was not delivered")

    async def _notify_request(self, user_id: str, handshake_type: str, handshake_id: str) -> None:
        pref_name = _PREF_FOR.get(handshake_type)
        if not pref_name:
            return
        prefs = await self.preferences(user_id)
        if not prefs.enabled or not getattr(prefs, pref_name):
            return
        subs = await self._repo.list_subscriptions(user_id)
        if not subs:
            return
        key = None
        if self._deliver is None and any(item.transport == "webpush" for item in subs):
            key = await self._signing_key()
        for sub in subs:
            if not sub.lang:
                sub.lang = prefs.lang
            payload = notification_payload(sub, handshake_type, handshake_id)
            try:
                if self._deliver is not None:
                    status = await self._deliver(sub, payload)
                else:
                    status = await asyncio.to_thread(self._send, sub, payload, key)
            except Exception:
                logging.warning("push delivery failed for one device")
                continue
            if status in (403, 404, 410):
                await self._repo.delete_subscription(user_id, endpoint=sub.endpoint, token=sub.token)

    def _send(self, sub: PushSubscription, payload: dict, key) -> int:
        if sub.transport == "fcm":
            return send_fcm(sub.token, payload)
        if key is None:
            raise RuntimeError("web push key is missing")
        return send_web_push(
            endpoint=sub.endpoint,
            p256dh=sub.p256dh,
            auth=sub.auth,
            payload=_payload_bytes(payload),
            private_key=key,
            subject=settings.vapid_subject,
            topic=payload["tag"],
        )

    async def _signing_key(self):
        if settings.vapid_private_pem.strip():
            return load_vapid_key(settings.vapid_private_pem)
        pem = await self._repo.get_vapid_pem()
        if not pem:
            pem = await self._repo.save_vapid_pem(generate_vapid_pem())
        return load_vapid_key(pem)

    @staticmethod
    def _check_web_push(sub: PushSubscription) -> None:
        endpoint = (sub.endpoint or "").strip()
        if not endpoint or len(endpoint) > 2000 or not push_endpoint_allowed(endpoint):
            raise ValueError("push endpoint host is not supported")
        try:
            user_key = b64url_decode(sub.p256dh or "")
            auth = b64url_decode(sub.auth or "")
        except Exception as exc:
            raise ValueError("invalid push key") from exc
        if len(user_key) != 65 or user_key[0] != 0x04 or len(auth) != 16:
            raise ValueError("invalid push key")
        sub.endpoint = endpoint
        sub.token = ""


def _payload_bytes(payload: dict) -> bytes:
    import json
    public = {
        "title": payload["title"],
        "body": payload["body"],
        "icon": payload["icon"],
        "color": payload["color"],
        "type": payload["type"],
        "tag": payload["tag"],
        "open_path": payload["open_path"],
        "platform": payload["platform"],
    }
    return json.dumps(public, ensure_ascii=False).encode("utf-8")
