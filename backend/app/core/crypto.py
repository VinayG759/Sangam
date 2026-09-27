"""
Encryption for the one piece of contact data Sangam keeps: a citizen's chat ID,
so it can tell them when their report is prioritised. The key lives only in the
server's environment (CONTACT_ENCRYPTION_KEY). Without a key, contact storage
is switched off entirely — nothing is kept.

Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from cryptography.fernet import Fernet

from app.core.config import get_settings


def contacts_enabled() -> bool:
    return bool(get_settings().CONTACT_ENCRYPTION_KEY)


def _fernet() -> Fernet:
    return Fernet(get_settings().CONTACT_ENCRYPTION_KEY.encode())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(token: bytes) -> str:
    return _fernet().decrypt(token).decode()
