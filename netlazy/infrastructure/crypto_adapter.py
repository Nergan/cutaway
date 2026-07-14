import hashlib
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

class InvalidPublicKeyError(ValueError):
    pass

class SignatureVerificationError(Exception):
    pass

def get_canonical_key_bytes(public_key_pem: str) -> bytes:
    """Parses the PEM and returns canonical DER format bytes. Enforces RSA >= 2048."""
    try:
        key = load_pem_public_key(public_key_pem.encode('utf-8'))
    except Exception as e:
        raise InvalidPublicKeyError("Invalid public key format") from e

    if not isinstance(key, rsa.RSAPublicKey):
        raise InvalidPublicKeyError("Only RSA public keys are supported")
    if key.key_size < 2048:
        raise InvalidPublicKeyError("RSA key size must be >= 2048 bits")

    return key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

def derive_user_id(public_key_pem: str) -> str:
    """Hashes the strict DER bytes, not the raw fragile PEM string."""
    der_bytes = get_canonical_key_bytes(public_key_pem)
    return hashlib.sha256(der_bytes).hexdigest()

def verify_signature(public_key_pem: str, payload: bytes, signature: bytes) -> None:
    """Verifies an RSA-PSS/SHA256 signature over payload. Raises
    SignatureVerificationError on any failure (mismatch, malformed key/signature)."""
    try:
        public_key = load_pem_public_key(public_key_pem.encode('utf-8'))
        public_key.verify(
            signature,
            payload,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.AUTO
            ),
            hashes.SHA256()
        )
    except InvalidSignature as e:
        raise SignatureVerificationError("Signature mismatch") from e
    except (ValueError, TypeError) as e:
        raise SignatureVerificationError("Malformed signature or key") from e