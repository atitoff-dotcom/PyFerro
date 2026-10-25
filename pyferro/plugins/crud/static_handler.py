# -*- coding: utf-8 -*-
"""
HTTP-обработчик для раздачи автономной панели CRUD (Svelte 5 + Tailwind v4).
Раздает статические файлы из папки static/ по маршрутам /crud (или /admin)
и обеспечивает абсолютную изоляцию (Zero-Leakage 404) для не-администраторов.
"""

import mimetypes
from pathlib import Path

from pyferro.core.router import http_route
from pyferro.core.http import (
    extract_header,
    extract_cookies,
    extract_session_token,
    extract_session_tokens,
    get_session_cookie_names,
)
from pyferro.core.logger import logger
from .auth import (
    get_crud_session,
    get_crud_session_async,
    revoke_crud_session,
)

STATIC_DIR = Path(__file__).parent / "static"


def _extract_crud_token(scope) -> str:
    return extract_session_token(scope)


@http_route("/admin", methods=["GET"])
@http_route("/admin/*", methods=["GET"])
async def serve_crud_static(scope, proto) -> None:
    """
    Раздает автономную сборку админки из папки static/.
    Для гостей и не-администраторов возвращает строгий 404 Not Found (Zero-Leakage).
    Поддерживает канонические подмаршруты /admin/crud, /admin/seo, /admin/users и т.д.
    """
    path = getattr(scope, "path", None) or (scope.get("path", "/admin") if isinstance(scope, dict) else "/admin")

    if path == "/admin":
        proto.response_str(
            status=307,
            headers=[
                ("location", "/admin/"),
                ("content-length", "0"),
            ],
            body=""
        )
        return

    prefix = "/admin/"
    subpath = path[len(prefix):] if path.startswith(prefix) else ""

    # Проверка сессии администратора: перебираем токены из cookies с асинхронным fallback на DB
    candidate_tokens = extract_session_tokens(scope)
    session_data = None
    token = ""
    for cand in candidate_tokens:
        session_data = await get_crud_session_async(cand)
        if session_data:
            token = cand
            break

    from pyferro.core.identity import get_session_identity
    identity = get_session_identity(session_data)
    is_admin = identity.has_admin_access if identity else False
    roles = identity.roles if identity else []

    # Безопасность (Zero-Leakage): скрываем существование панели от не-администраторов
    if not is_admin:
        cookies_found = list(extract_cookies(scope).keys())
        logger.debug(
            f"[CRUD 404] Zero-Leakage: доступ к '{path}' отклонён. "
            f"Токен: {'найден' if token else 'не найден'}. "
            f"Сессия: {'роли=' + str(roles) if session_data else 'не найдена'}. "
            f"Входящие cookie: {cookies_found}"
        )
        proto.response_str(
            status=404,
            headers=[
                ("content-type", "text/plain; charset=utf-8"),
                ("content-length", "0"),
            ],
            body=""
        )
        return

    # Завершение сессии CRUD
    if subpath == "logout":
        if token:
            revoke_crud_session(token)
        logout_headers = [
            ("location", "/"),
            ("content-length", "0"),
        ]
        for cname in get_session_cookie_names():
            logout_headers.append(("set-cookie", f"{cname}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"))
        proto.response_str(
            status=303,
            headers=logout_headers,
            body=""
        )
        return

    # Раздача статических ресурсов панели
    known_spa_sections = {"crud", "seo", "users", "roles", "rpc", "delegations", "settings", "database"}
    clean_subpath = subpath.strip("/")
    is_spa_route = (
        not subpath
        or subpath == "index.html"
        or clean_subpath in known_spa_sections
        or ("." not in clean_subpath and not clean_subpath.startswith("assets/"))
    )

    if is_spa_route:
        target_file = STATIC_DIR / "index.html"
    else:
        target_file = (STATIC_DIR / subpath).resolve()

    # Path traversal защита
    try:
        resolved_static = STATIC_DIR.resolve()
        target_resolved = target_file.resolve()
        if not str(target_resolved).startswith(str(resolved_static)):
            proto.response_str(
                status=403,
                headers=[("content-type", "text/plain; charset=utf-8")],
                body="403 Forbidden"
            )
            return
    except Exception:
        proto.response_str(
            status=400,
            headers=[("content-type", "text/plain; charset=utf-8")],
            body="400 Bad Request"
        )
        return

    if not target_resolved.is_file():
        if not subpath.startswith("assets/"):
            target_resolved = (STATIC_DIR / "index.html").resolve()
        else:
            proto.response_str(
                status=404,
                headers=[("content-type", "text/plain; charset=utf-8")],
                body="404 Not Found"
            )
            return

    content_type, _ = mimetypes.guess_type(str(target_resolved))
    if not content_type:
        content_type = "application/octet-stream"
    if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
        content_type += "; charset=utf-8"

    cache_control = "no-cache" if target_resolved.name == "index.html" else "public, max-age=31536000, immutable"

    proto.response_file(
        status=200,
        headers=[
            ("content-type", content_type),
            ("cache-control", cache_control),
        ],
        file=str(target_resolved)
    )
