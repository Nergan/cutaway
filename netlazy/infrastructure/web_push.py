"""Web Push encryption (RFC 8291) and delivery for browser subscriptions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.error
import urllib.request
from fnmatch import fnmatch
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared.network import SafeRedirectHandler, validate_outbound_url

WEB_PUSH_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "*.push.services.mozilla.com",
    "web.push.apple.com",
    "*.push.apple.com",
    "*.notify.windows.com",
)

_RECORD_SIZE = 4096


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    pad = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + pad)


def generate_vapid_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def load_vapid_key(pem: str):
    return serialization.load_pem_private_key(pem.encode("ascii"), password=None)


def uncompressed_public(key) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


def vapid_public_b64url(key) -> str:
    return b64url_encode(uncompressed_public(key))


def push_endpoint_allowed(url: str, hosts: tuple[str, ...] = WEB_PUSH_HOSTS) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower().rstrip(".")
    return any(fnmatch(host, pattern) for pattern in hosts)


def _private_from_raw(raw: bytes):
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def encrypt_push_payload(
    plaintext: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    as_private: bytes | None = None,
    salt: bytes | None = None,
) -> bytes:
    """Encrypt one Web Push record. Returns the aes128gcm body, including the header."""
    if len(ua_public) != 65 or ua_public[0] != 0x04:
        raise ValueError("user agent key must be an uncompressed P-256 point")
    if len(auth_secret) != 16:
        raise ValueError("auth secret must be 16 bytes")
    if len(plaintext) > 3993:
        raise ValueError("push payload is too large")

    private_key = ec.generate_private_key(ec.SECP256R1()) if as_private is None else _private_from_raw(as_private)
    if salt is None:
        salt = os.urandom(16)
    if len(salt) != 16:
        raise ValueError("salt must be 16 bytes")

    as_public = uncompressed_public(private_key)
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = private_key.exchange(ec.ECDH(), peer)
    key_info = b"WebPush: info\x00" + ua_public + as_public
    prk_key = hmac.new(auth_secret, ecdh_secret, hashlib.sha256).digest()
    ikm = hmac.new(prk_key, key_info + b"\x01", hashlib.sha256).digest()
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = hmac.new(prk, b"Content-Encoding: aes128gcm\x00\x01", hashlib.sha256).digest()[:16]
    nonce = hmac.new(prk, b"Content-Encoding: nonce\x00\x01", hashlib.sha256).digest()[:12]
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", b"")
    header = salt + struct.pack(">I", _RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_authorization(endpoint: str, key, subject: str) -> str:
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("push endpoint must be https")
    audience = f"https://{parts.hostname}"
    if parts.port:
        audience += f":{parts.port}"
    header = b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode("utf-8"))
    claims = {
        "aud": audience,
        "exp": int(time.time()) + 12 * 60 * 60,
        "sub": subject,
    }
    payload = b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{payload}".encode("ascii")
    der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    token = f"{header}.{payload}.{signature}"
    return f"vapid t={token},k={vapid_public_b64url(key)}"


def post_push(request: urllib.request.Request, hosts: tuple[str, ...]) -> int:
    validate_outbound_url(request.full_url, allowed_hosts=hosts)
    opener = urllib.request.build_opener(SafeRedirectHandler(allowed_hosts=hosts))
    try:
        with opener.open(request, timeout=10) as response:
            response.read(1024)
            return int(response.status)
    except urllib.error.HTTPError as exc:
        exc.read(2048)
        return int(exc.code)


def send_web_push(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: bytes,
    private_key,
    subject: str,
    topic: str,
) -> int:
    if not push_endpoint_allowed(endpoint):
        raise ValueError("push endpoint host is not supported")
    body = encrypt_push_payload(payload, b64url_decode(p256dh), b64url_decode(auth))
    headers = {
        "Authorization": vapid_authorization(endpoint, private_key, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": "86400",
        "Urgency": "high",
    }
    safe_topic = "".join(ch for ch in topic if ch.isalnum() or ch in "-_")[:32]
    if safe_topic:
        headers["Topic"] = safe_topic
    request = urllib.request.Request(endpoint, data=body, method="POST", headers=headers)
    return post_push(request, WEB_PUSH_HOSTS)
