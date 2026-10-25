"""
Гибридный менеджер JWT-токенов (`TokenManager`) для PyFerro 2.0.

Сочетает два преимущества:
1. **Совместимость с Nginx**: каждый токен — это стандартный JWT (`HS256`),
   который может проверяться напрямую прокси-сервером Nginx (`auth_jwt`).
2. **Мгновенная O(1) скорость в Python**: выпущенные и проверенные токены кэшируются
   в оперативной памяти (`token_str -> SessionData`), поэтому повторные HTTP/WS-запросы
   не тратят CPU на криптографию `jwt.decode` и не обращаются к базе данных (~20 нс).
"""

from http.cookies import SimpleCookie
import secrets
import time
from typing import Any
from urllib.parse import parse_qs

import jwt

from pyferro2.core.constants import SESSION_COOKIE_NAME
from pyferro2.core.session_data import SessionData

JWT_ALGORITHM = "HS256"
DEFAULT_TOKEN_TTL = 7 * 24 * 3600  # 7 суток


class TokenManager:
    """
    Управляет сессионными JWT-токенами и целевыми (capability) токенами для файлов.
    """

    __slots__ = ("secret_key", "default_ttl", "_cache", "_revoked_jtis")

    def __init__(
        self,
        secret_key: str = "pyferro2-dev-secret-key-change-in-prod-32b",
        default_ttl: int = DEFAULT_TOKEN_TTL,
    ) -> None:
        if not secret_key:
            raise ValueError("secret_key не может быть пустым")
        self.secret_key: str = secret_key
        self.default_ttl: int = default_ttl
        # Кэш активных токенов в памяти: token_str -> (SessionData, exp_timestamp, jti)
        self._cache: dict[str, tuple[SessionData, int, str]] = {}
        self._revoked_jtis: set[str] = set()

    def issue_token(self, session_data: SessionData, ttl_seconds: int | None = None) -> str:
        """
        Выпускает стандартный JWT (`HS256`) для авторизованного пользователя
        и сохраняет его `SessionData` в O(1) кэше памяти.
        """
        if session_data.is_guest:
            raise ValueError("Нельзя выпустить сессионный токен для гостя")

        now = int(time.time())
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        exp = now + ttl
        jti = secrets.token_hex(12)

        payload: dict[str, Any] = {
            "typ": "access",
            "user_id": session_data.user_id,
            "username": session_data.username,
            "roles": sorted(session_data.roles),
            "permissions": sorted(session_data.permissions),
            "iat": now,
            "exp": exp,
            "jti": jti,
        }
        token_str = jwt.encode(payload, self.secret_key, algorithm=JWT_ALGORITHM)
        self._cache[token_str] = (session_data, exp, jti)
        return token_str

    def resolve_token(self, token: str | None) -> SessionData | None:
        """
        Проверяет токен и возвращает `SessionData` (или `None`, если токен невалиден/истек/отозван).

        Быстрый путь (99.9% вызовов): берет готовый `SessionData` из словаря в RAM за ~20 нс.
        Холодный путь (после перезапуска сервера): проверяет подпись JWT и восстанавливает `SessionData`.
        """
        if not token or type(token) is not str:
            return None

        now = int(time.time())

        # 1. Быстрый O(1) поиск в кэше памяти без вызова jwt.decode
        cached = self._cache.get(token)
        if cached is not None:
            session_data, exp, jti = cached
            if now < exp and jti not in self._revoked_jtis:
                return session_data
            self._cache.pop(token, None)
            return None

        # 2. Холодная проверка подписи JWT (например, если токен пережил рестарт воркера)
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[JWT_ALGORITHM])
        except Exception:
            return None

        if payload.get("typ") != "access":
            return None

        jti = str(payload.get("jti") or "")
        if jti and jti in self._revoked_jtis:
            return None

        try:
            session_data = SessionData(
                user_id=payload.get("user_id"),
                username=str(payload.get("username") or ""),
                roles=frozenset(payload.get("roles") or ()),
                permissions=frozenset(payload.get("permissions") or ()),
            )
        except (TypeError, ValueError):
            return None

        exp = int(payload.get("exp") or (now + self.default_ttl))
        self._cache[token] = (session_data, exp, jti)
        return session_data

    def revoke_token(self, token: str | None) -> None:
        """Мгновенно аннулирует токен (при вызове `auth.logout`)."""
        if not token:
            return
        cached = self._cache.pop(token, None)
        if cached is not None:
            _, _, jti = cached
            if jti:
                self._revoked_jtis.add(jti)
            return

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[JWT_ALGORITHM],
                options={"verify_exp": False},
            )
            jti = payload.get("jti")
            if jti:
                self._revoked_jtis.add(str(jti))
        except Exception:
            pass

    def revoke_user(self, user_id: int) -> None:
        """Отзывает все активные токены указанного пользователя (например, при блокировке или смене ролей)."""
        to_remove = [
            tok for tok, (sd, _, _) in self._cache.items() if sd.user_id == user_id
        ]
        for tok in to_remove:
            cached = self._cache.pop(tok, None)
            if cached and cached[2]:
                self._revoked_jtis.add(cached[2])

    def issue_file_token(self, file_id: int, ttl_seconds: int = 3600) -> str:
        """
        Выпускает короткоживущий JWT-токен (`typ: 'file_download'`) для скачивания
        приватного файла через Nginx или файловый эндпоинт.
        """
        if type(file_id) is not int or file_id <= 0:
            raise ValueError("file_id должен быть положительным целым числом")
        now = int(time.time())
        payload = {
            "typ": "file_download",
            "file_id": file_id,
            "iat": now,
            "exp": now + ttl_seconds,
        }
        return jwt.encode(payload, self.secret_key, algorithm=JWT_ALGORITHM)

    def verify_file_token(self, token: str | None) -> int | None:
        """Проверяет файловый JWT-токен и возвращает `file_id` (или `None`)."""
        if not token or type(token) is not str:
            return None
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[JWT_ALGORITHM])
        except Exception:
            return None
        if payload.get("typ") != "file_download":
            return None
        file_id = payload.get("file_id")
        return file_id if type(file_id) is int and file_id > 0 else None


def extract_token_from_scope(scope: dict[str, Any]) -> str | None:
    """
    Извлекает токен сессии из ASGI `scope` в строгом порядке приоритета:
    1. Заголовок `Authorization: Bearer <token>`.
    2. Кука `ferro_session`.
    3. Query-параметр `?token=<token>` (для WebSocket-хендшейков и прямых ссылок).
    """
    headers: list[tuple[bytes, bytes]] = scope.get("headers") or []
    cookie_header: str | None = None

    for name_bytes, value_bytes in headers:
        name_lower = name_bytes.lower()
        if name_lower == b"authorization":
            auth_val = value_bytes.decode("latin-1").strip()
            if auth_val.lower().startswith("bearer "):
                token = auth_val[7:].strip()
                if token:
                    return token
        elif name_lower == b"cookie":
            cookie_header = value_bytes.decode("latin-1")

    if cookie_header:
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
            if SESSION_COOKIE_NAME in cookie:
                val = cookie[SESSION_COOKIE_NAME].value.strip()
                if val:
                    return val
        except Exception:
            pass

    query_bytes: bytes = scope.get("query_string") or b""
    if query_bytes:
        parsed = parse_qs(query_bytes.decode("latin-1"))
        token_list = parsed.get("token")
        if token_list and token_list[0]:
            return token_list[0].strip()

    return None
