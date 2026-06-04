from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet | None:
    key = (get_settings().GOOGLE_TOKEN_ENCRYPTION_KEY or "").strip()
    if not key:
        logger.warning(
            "GOOGLE_TOKEN_ENCRYPTION_KEY is not set; storing tokens unencrypted (dev only)"
        )
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    fernet = _fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    fernet = _fernet()
    if fernet is None:
        return ciphertext
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt token — wrong encryption key?")
        raise
