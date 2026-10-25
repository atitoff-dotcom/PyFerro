# -*- coding: utf-8 -*-
"""
pyferro.core.http: Базовые протокольные утилиты для работы с RSGI HTTP-запросами.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs


def extract_header(scope: Any, header_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Извлекает HTTP-заголовок из RSGI scope в независимом от регистра формате.
    Поддерживает Granian Headers, dict, список кортежей (строк или байтов).
    """
    target = header_name.lower()
    headers = getattr(scope, "headers", None)
    if headers is None and isinstance(scope, dict):
        headers = scope.get("headers")

    if headers is None:
        return default

    # 1. Если это dict или Granian Headers с методом .get()
    if hasattr(headers, "get"):
        try:
            val = headers.get(target)
            if val is not None:
                return val.decode("latin1") if isinstance(val, bytes) else str(val)
        except (TypeError, KeyError, AttributeError):
            pass

        # Fallback по байтовому ключу только для стандартных python dict
        if isinstance(headers, dict):
            try:
                val = headers.get(target.encode("latin1"))
                if val is not None:
                    return val.decode("latin1") if isinstance(val, bytes) else str(val)
            except (TypeError, KeyError, AttributeError):
                pass

    # 2. Если это список/кортеж пар (k, v) или объект с .items()
    items = headers.items() if hasattr(headers, "items") else headers
    try:
        for k, v in items:
            k_str = k.decode("latin1").lower() if isinstance(k, bytes) else str(k).lower()
            if k_str == target:
                return v.decode("latin1") if isinstance(v, bytes) else str(v)
    except Exception:
        pass

    return default


def extract_query_params(scope: Any) -> Dict[str, str]:
    """
    Извлекает query-параметры из RSGI scope в виде плоского словаря {param: first_value}.
    """
    qs = getattr(scope, "query_string", None)
    if qs is None and isinstance(scope, dict):
        qs = scope.get("query_string", "")

    if isinstance(qs, bytes):
        qs = qs.decode("utf-8", errors="replace")
    elif not isinstance(qs, str):
        qs = str(qs or "")

    parsed = parse_qs(qs)
    return {k: v[0] if v else "" for k, v in parsed.items()}


async def read_request_body(proto: Any) -> bytes:
    """
    Асинхронно считывает тело HTTP-запроса из RSGI proto.
    Поддерживает потоковый асинхронный итератор Granian RSGI (__aiter__),
    callable-протокол, метод .read() и fallback для тестов.
    """
    if hasattr(proto, "__aiter__"):
        chunks = []
        async for chunk in proto:
            if chunk:
                chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
        return b"".join(chunks)

    if callable(proto):
        b = await proto()
        return b if isinstance(b, bytes) else str(b).encode("utf-8")

    if hasattr(proto, "read"):
        b = await proto.read()
        return b if isinstance(b, bytes) else str(b).encode("utf-8")

    if hasattr(proto, "receive_bytes"):
        chunks = []
        while True:
            c = await proto.receive_bytes()
            if not c:
                break
            chunks.append(c)
        return b"".join(chunks)

    if hasattr(proto, "receive"):
        chunks = []
        while True:
            m = await proto.receive()
            c = m if isinstance(m, bytes) else (m.get("body", b"") if isinstance(m, dict) else b"")
            if not c:
                break
            chunks.append(c)
        return b"".join(chunks)

    return b""


def extract_cookies(scope: Any) -> Dict[str, str]:
    """
    Извлекает все HTTP Cookie из RSGI scope или объекта в виде словаря {имя: значение}.
    """
    raw_cookie = extract_header(scope, "cookie", "")
    if not raw_cookie:
        return {}
    cookies: Dict[str, str] = {}
    for part in raw_cookie.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def extract_bearer_token(scope: Any) -> Optional[str]:
    """
    Извлекает Bearer-токен из HTTP заголовка Authorization.
    """
    auth_hdr = extract_header(scope, "authorization")
    if auth_hdr and auth_hdr.lower().startswith("bearer "):
        token = auth_hdr[7:].strip()
        return token if token else None
    return None


def get_session_cookie_names(prefix: Optional[str] = None) -> List[str]:
    """
    Возвращает упорядоченный список имён cookie для поиска сессионного токена:
    1. Канонический {prefix}_session (или ferro_session)
    2. Fallbacks ({prefix}_crud_session, ferro_crud_session, {prefix}_jwt, ferro_jwt)
    """
    if not prefix:
        try:
            from pyferro.core.lib.config import settings
            prefix = settings.security.get("session_prefix", "ferro")
        except Exception:
            prefix = "ferro"
    prefix = (prefix or "ferro").strip()

    names = [
        f"{prefix}_session",
        "ferro_session",
        f"{prefix}_crud_session",
        "ferro_crud_session",
        f"{prefix}_jwt",
        "ferro_jwt",
        "rpc_jwt",
        "token",
        "rsgi_session",
        "rsgi_crud_session",
        "rsgi_jwt",
    ]
    seen = set()
    result = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def extract_session_tokens(scope_or_cookies: Any, session_prefix: Optional[str] = None) -> List[str]:
    """
    Извлекает все сессионные токены из запроса (Bearer заголовок и Cookie) в строгом порядке приоритета.
    """
    tokens: List[str] = []

    # Если передан scope с заголовками
    if hasattr(scope_or_cookies, "headers") or (isinstance(scope_or_cookies, dict) and "headers" in scope_or_cookies):
        bearer = extract_bearer_token(scope_or_cookies)
        if bearer and bearer not in tokens:
            tokens.append(bearer)
        cookies = extract_cookies(scope_or_cookies)
    elif isinstance(scope_or_cookies, dict):
        # Передан чистый словарь {cookie_name: cookie_val}
        cookies = scope_or_cookies
    else:
        bearer = extract_bearer_token(scope_or_cookies)
        if bearer and bearer not in tokens:
            tokens.append(bearer)
        cookies = extract_cookies(scope_or_cookies)

    for name in get_session_cookie_names(session_prefix):
        val = cookies.get(name)
        if val and val not in tokens:
            tokens.append(val)
    return tokens

def extract_session_token(scope_or_cookies: Any, session_prefix: Optional[str] = None) -> str:
    """
    Универсальное извлечение основного токена сессии / JWT из Bearer заголовка или Cookie.
    """
    tokens = extract_session_tokens(scope_or_cookies, session_prefix)
    return tokens[0] if tokens else ""


__all__ = [
    "extract_header",
    "extract_bearer_token",
    "extract_query_params",
    "extract_cookies",
    "get_session_cookie_names",
    "extract_session_token",
    "extract_session_tokens",
    "read_request_body",
]
