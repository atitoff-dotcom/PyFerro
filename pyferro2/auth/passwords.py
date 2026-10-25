"""
Криптографическое хэширование и проверка паролей на базе стандартного `hashlib.scrypt` (OpenSSL).

Формат хранения: `scrypt$<salt_hex>$<digest_hex>`
Не требует внешних C-зависимостей и защищен от атак по времени (`hmac.compare_digest`).
"""

import hashlib
import hmac
import secrets

_SCRYPT_N = 16384  # 2^14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32


def hash_password(raw_password: str) -> str:
    """Хэширует открытый пароль со случайной 16-байтовой криптостойкой солью."""
    if not isinstance(raw_password, str) or not raw_password:
        raise ValueError("Пароль не может быть пустым")

    salt_hex = secrets.token_hex(16)
    digest = hashlib.scrypt(
        raw_password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    )
    return f"scrypt${salt_hex}${digest.hex()}"


def verify_password(raw_password: str, password_hash: str) -> bool:
    """Безопасно проверяет соответствие открытого пароля сохраненному хэшу."""
    if not raw_password or not password_hash:
        return False

    parts = password_hash.split("$")
    if len(parts) != 3 or parts[0] != "scrypt":
        return False

    _, salt_hex, expected_hex = parts
    try:
        salt_bytes = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    computed = hashlib.scrypt(
        raw_password.encode("utf-8"),
        salt=salt_bytes,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    ).hex()

    return hmac.compare_digest(computed, expected_hex)
