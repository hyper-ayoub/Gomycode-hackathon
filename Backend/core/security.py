from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from cryptography.fernet import Fernet

from core.config import settings


def create_access_token(subject: str, expires_days: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days or settings.JWT_EXPIRES_DAYS)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


@lru_cache
def _fernet() -> Fernet:
    if not settings.CREDENTIALS_ENCRYPTION_KEY:
        raise RuntimeError(
            "CREDENTIALS_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.CREDENTIALS_ENCRYPTION_KEY)


def encrypt_credential(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
