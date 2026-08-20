import hashlib

_CHAIN_TAG = b"PQDA-CHAIN-v1"
_REQUEST_TAG = "PQDA-v1"
_IDENTITY_TAG = "PQDA-ANCHOR-v1"


def compute_genesis_anchor(user_id: str) -> str:
    return hashlib.sha256(_CHAIN_TAG + b"|genesis|" + user_id.encode("utf-8")).hexdigest()


def compute_next_anchor(
    current_head: str,
    user_id: str,
    method: str,
    path: str,
    body_hash: str,
    nonce: str,
    timestamp: int,
) -> str:
    link = "|".join([current_head, user_id, method, path, body_hash, nonce, str(timestamp)])
    return hashlib.sha256(_CHAIN_TAG + b"|" + link.encode("utf-8")).hexdigest()


def build_request_payload(
    method: str, path: str, query: str, timestamp: int, nonce: str, body_hash: str, prev_anchor: str
) -> bytes:
    """Canonical bytes signed for every anchor-checked (mutating/stateful) request."""
    return "\n".join(
        [_REQUEST_TAG, method, path, query, str(timestamp), nonce, body_hash, prev_anchor]
    ).encode("utf-8")


def build_identity_payload(method: str, path: str, timestamp: int, nonce: str, body_hash: str) -> bytes:
    """Canonical bytes for the anchor-free identity check (GET /auth/anchor only).
    Deliberately a different tag/shape than build_request_payload so a signature
    over one can never be replayed as the other."""
    return "\n".join([_IDENTITY_TAG, method, path, str(timestamp), nonce, body_hash]).encode("utf-8")