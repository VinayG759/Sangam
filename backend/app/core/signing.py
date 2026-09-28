"""
Tamper-evident briefs. Each exported PDF is signed with an Ed25519 private key that
lives only in the server's environment (BRIEF_SIGNING_KEY). The signature covers every
byte of the PDF and is appended after the PDF's end-of-file marker, where readers ignore
it. Anyone with the public key (docs/brief-signing-key.pub) can check that not one byte
has changed — editing the text, or re-saving in a PDF editor, breaks the signature.

Without a key, briefs are exported unsigned and say so.

Generate a key:
    python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
Print its public key:
    python -m app.core.signing
"""

import base64
import hashlib
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.core.config import get_settings

MARKER = b"\n%SANGAM-SIGNATURE "

VALID = "valid"  # signed by this key, unchanged
TAMPERED = "tampered"  # signed, but the bytes no longer match the signature
UNSIGNED = "unsigned"  # no signature line
OTHER_KEY = "other_key"  # signed by a key this server does not hold


@dataclass
class Verification:
    status: str
    key_id: str | None = None


def _private_key() -> Ed25519PrivateKey | None:
    raw = get_settings().BRIEF_SIGNING_KEY.strip()
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw)) if raw else None


def signing_enabled() -> bool:
    return _private_key() is not None


def public_key_b64(key: Ed25519PublicKey) -> str:
    return base64.b64encode(key.public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def key_id(public_b64: str) -> str:
    """Short fingerprint, printed on each signature so a verifier knows which key to use."""
    return hashlib.sha256(base64.b64decode(public_b64)).hexdigest()[:16]


def server_public_key() -> str | None:
    private = _private_key()
    return public_key_b64(private.public_key()) if private else None


def sign_pdf(pdf: bytes) -> bytes:
    private = _private_key()
    if private is None:
        return pdf
    signature = base64.b64encode(private.sign(pdf)).decode()
    return pdf + MARKER + f"{key_id(public_key_b64(private.public_key()))} {signature}\n".encode()


def verify_pdf(data: bytes, public_b64: str) -> Verification:
    """Check a signed PDF against a base64 Ed25519 public key. Needs no server and no database."""
    cut = data.rfind(MARKER)
    if cut < 0:
        return Verification(UNSIGNED)
    try:
        signed_key_id, signature = data[cut + len(MARKER):].decode().split()
        signature_bytes = base64.b64decode(signature, validate=True)
    except ValueError:
        return Verification(TAMPERED)
    if signed_key_id != key_id(public_b64):
        return Verification(OTHER_KEY, signed_key_id)
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64)).verify(signature_bytes, data[:cut])
    except InvalidSignature:
        return Verification(TAMPERED, signed_key_id)
    return Verification(VALID, signed_key_id)


if __name__ == "__main__":
    print(server_public_key() or "BRIEF_SIGNING_KEY is not set")
