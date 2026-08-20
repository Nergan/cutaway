import hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

# cryptography>=46 native ML-DSA support
from cryptography.hazmat.primitives.asymmetric.mldsa import MLDSA65PublicKey

from netlazy.domain.repository import HybridCryptoPort, InvalidPublicKeyError, SignatureVerificationError


class CryptographyHybridAdapter(HybridCryptoPort):
    def _get_ed25519_der(self, pem: str) -> bytes:
        try:
            key = load_pem_public_key(pem.encode('utf-8'))
            if not isinstance(key, ed25519.Ed25519PublicKey):
                raise InvalidPublicKeyError("Expected Ed25519 public key")
            return key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        except InvalidPublicKeyError:
            raise
        except Exception as e:
            raise InvalidPublicKeyError("Invalid Ed25519 public key format") from e

    def derive_user_id(self, ed25519_public_pem: str, mldsa_public_hex: str) -> str:
        ed25519_der = self._get_ed25519_der(ed25519_public_pem)
        try:
            mldsa_raw = bytes.fromhex(mldsa_public_hex)
            if len(mldsa_raw) != 1952:
                raise InvalidPublicKeyError("ML-DSA-65 public key must be exactly 1952 bytes")
            mldsa_raw = bytes.fromhex(mldsa_public_hex)
        except ValueError:
            raise InvalidPublicKeyError("ML-DSA public key must be valid hex")

        return hashlib.sha256(ed25519_der + mldsa_raw).hexdigest()

    def verify_hybrid_signature(
        self,
        ed25519_public_pem: str,
        mldsa_public_hex: str,
        payload: bytes,
        ed25519_sig: bytes,
        mldsa_sig: bytes
    ) -> None:
        try:
            ed_key = load_pem_public_key(ed25519_public_pem.encode('utf-8'))
            pq_key = MLDSA65PublicKey.from_public_bytes(bytes.fromhex(mldsa_public_hex))
            
            # 1. Classical Ed25519 Verification
            ed_key.verify(ed25519_sig, payload)
            
            # 2. Post-Quantum ML-DSA-65 Verification
            pq_key.verify(mldsa_sig, payload)
            
        except InvalidSignature as e:
            raise SignatureVerificationError("Signature mismatch") from e
        except (ValueError, TypeError) as e:
            raise SignatureVerificationError("Malformed signature or key") from e