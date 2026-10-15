from netlazy.application.push_service import PushService
from netlazy.domain.models import PushPreferences, PushSubscription
from netlazy.infrastructure.fcm_push import fcm_message
from netlazy.infrastructure.web_push import b64url_decode, b64url_encode, encrypt_push_payload


RFC_BODY = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
    "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
    "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)
UA_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcx"
    "aOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
AUTH_SECRET = "BTBZMqHH6r4Tts7J_aSIgg"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"


def test_web_push_matches_rfc8291_example():
    body = encrypt_push_payload(
        b"When I grow up, I want to be a watermelon",
        b64url_decode(UA_PUBLIC),
        b64url_decode(AUTH_SECRET),
        as_private=b64url_decode(AS_PRIVATE),
        salt=b64url_decode(SALT),
    )
    assert b64url_encode(body) == RFC_BODY


class MemoryPushRepo:
    def __init__(self):
        self.prefs = {}
        self.subs = []
        self.removed = []

    async def get_preferences(self, user_id):
        return self.prefs.get(user_id, PushPreferences())

    async def save_preferences(self, user_id, prefs):
        self.prefs[user_id] = prefs

    async def list_subscriptions(self, user_id):
        return [item for item in self.subs if item.user_id == user_id]

    async def upsert_subscription(self, sub):
        self.subs = [
            item for item in self.subs
            if not ((sub.endpoint and item.endpoint == sub.endpoint) or (sub.token and item.token == sub.token))
        ]
        self.subs.append(sub)

    async def delete_subscription(self, user_id, *, endpoint="", token=""):
        self.removed.append((user_id, endpoint, token))
        self.subs = [
            item for item in self.subs
            if item.user_id != user_id or (endpoint and item.endpoint != endpoint) or (token and item.token != token)
        ]

    async def delete_user(self, user_id):
        self.subs = [item for item in self.subs if item.user_id != user_id]
        self.prefs.pop(user_id, None)

    async def get_vapid_pem(self):
        return None

    async def save_vapid_pem(self, pem):
        return pem


def _service():
    sent = []

    async def deliver(sub, payload):
        sent.append((sub, payload))
        return 201

    return PushService(MemoryPushRepo(), deliver=deliver), sent


def test_missing_preferences_allow_every_request_type():
    prefs = PushPreferences()
    assert prefs.enabled and prefs.share and prefs.exchange and prefs.demand


async def test_demand_can_be_silenced_without_silencing_share():
    service, sent = _service()
    service._repo.prefs["receiver"] = PushPreferences(demand=False)
    service._repo.subs.append(PushSubscription(
        user_id="receiver", platform="windows", transport="webpush", endpoint="https://fcm.googleapis.com/wp/1"
    ))
    await service.notify_request("receiver", "demand", "a" * 32)
    await service.notify_request("receiver", "share", "b" * 32)
    assert [item[1]["type"] for item in sent] == ["share"]
    assert sent[0][1]["platform"] == "windows"
    assert sent[0][1]["color"] == "#6e9dae"
    assert sent[0][1]["icon"].endswith("/push/share.png")


async def test_windows_web_push_and_android_app_are_separate_devices():
    service, sent = _service()
    service._repo.subs.extend([
        PushSubscription(user_id="receiver", platform="windows", transport="webpush", endpoint="https://fcm.googleapis.com/wp/1", lang="en"),
        PushSubscription(user_id="receiver", platform="android", transport="fcm", token="device-token", lang="ru", origin="https://example.com"),
    ])
    await service.notify_request("receiver", "exchange", "c" * 32)
    platforms = {item[0].transport: item[1] for item in sent}
    assert set(platforms) == {"webpush", "fcm"}
    assert platforms["webpush"]["platform"] == "windows"
    assert platforms["fcm"]["platform"] == "android"
    assert platforms["fcm"]["title"] == "обменяться"
    android = fcm_message("device-token", platforms["fcm"])
    note = android["message"]["android"]["notification"]
    assert note["channel_id"] == "handshakes"
    assert note["color"] == "#8da970"
    assert note["icon"] == "ic_stat_netlazy"
    assert android["message"]["notification"]["image"].endswith("/push/exchange.png")


async def test_gone_subscription_is_removed():
    service, sent = _service()

    async def gone(sub, payload):
        sent.append((sub, payload))
        return 410

    service._deliver = gone
    service._repo.subs.append(PushSubscription(
        user_id="receiver", platform="android", transport="fcm", token="old"
    ))
    await service.notify_request("receiver", "share", "d" * 32)
    assert service._repo.removed == [("receiver", "", "old")]


async def test_unknown_push_host_is_rejected():
    service, _sent = _service()
    try:
        await service.register("receiver", PushSubscription(
            user_id="receiver",
            platform="windows",
            transport="webpush",
            endpoint="https://evil.example/push",
            p256dh=UA_PUBLIC,
            auth=AUTH_SECRET,
        ))
        assert False, "expected rejection"
    except ValueError as exc:
        assert "not supported" in str(exc)


async def test_android_app_token_is_accepted():
    service, _sent = _service()
    await service.register("receiver", PushSubscription(
        user_id="receiver",
        platform="android",
        transport="fcm",
        token="device-token",
        open_path="/netlazy/inbox",
    ))
    assert service._repo.subs[0].transport == "fcm"
    assert service._repo.subs[0].token == "device-token"


async def test_disabled_master_sends_nothing():
    service, sent = _service()
    service._repo.prefs["receiver"] = PushPreferences(enabled=False)
    service._repo.subs.append(PushSubscription(
        user_id="receiver", platform="windows", transport="webpush", endpoint="https://fcm.googleapis.com/wp/1"
    ))
    await service.notify_request("receiver", "exchange", "e" * 32)
    assert sent == []
