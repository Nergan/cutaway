import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_media_key(material: str) -> bytes:
    """AES key for a profile's media. One-way: the account id cannot be recovered from it."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"\x00" * 32,
        info=b"netlazy_media_key",
    )
    return hkdf.derive(material.encode("utf-8"))


def encode_media_key(material: str) -> str:
    if not material:
        return ""
    return base64.b64encode(derive_media_key(material)).decode("ascii")
