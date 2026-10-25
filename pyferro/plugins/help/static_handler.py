# -*- coding: utf-8 -*-
"""
HTTP-обработчик раздачи статических файлов раздела Справки и API (/admin/help).
Ограничивает доступ по принципу Zero-Leakage 404: только для пользователей
с системной ролью 'admin' или любой ролью 'adm-*' (включая 'adm-help').
"""

from __future__ import annotations
import os
import mimetypes
from pathlib import Path
from pyferro.core.router import http_route
from pyferro.core.http import extract_cookies, extract_session_token, extract_session_tokens
from pyferro.core.logger import logger
from pyferro.plugins.crud.auth import get_crud_session, get_crud_session_async

PLUGIN_STATIC_DIR = Path(__file__).parent / "static"
EXAMPLES_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "admin_help" / "public"


def _get_static_dir() -> Path:
    if PLUGIN_STATIC_DIR.exists() and any(PLUGIN_STATIC_DIR.iterdir()):
        return PLUGIN_STATIC_DIR
    return EXAMPLES_PUBLIC_DIR


@http_route("/admin/help", methods=["GET"])
@http_route("/admin/help/*", methods=["GET"])
async def serve_help_static(scope, proto) -> None:
    """Раздает статику раздела /admin/help с Zero-Leakage 404 защитой."""
    path = getattr(scope, "path", None) or (scope.get("path", "/admin/help") if isinstance(scope, dict) else "/admin/help")

    if path == "/admin/help":
        proto.response_str(
            status=307,
            headers=[
                ("location", "/admin/help/"),
                ("content-length", "0"),
            ],
            body=""
        )
        return

    # Проверка Zero-Leakage 404 (требуется admin или adm-*)
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

    # В режиме без пользовательского приложения (чистый dev-старт) Справка открыта для гостя,
    # позволяя протестировать сокеты и войти под учетной записью администратора.
    # При наличии пользовательского фронтенда активируется строгий Zero-Leakage 404.
    from pyferro.app import get_current_app
    app = get_current_app()
    allow_guest_help = False
    if app is not None:
        if getattr(app, "public_help", None) is not None:
            allow_guest_help = bool(app.public_help)
        else:
            allow_guest_help = not app.has_user_frontend

    if not is_admin and not allow_guest_help:
        logger.debug(f"[Admin Help 404] Zero-Leakage: доступ к '{path}' отклонён.")
        proto.response_str(
            status=404,
            headers=[
                ("content-type", "text/plain; charset=utf-8"),
                ("content-length", "0"),
            ],
            body=""
        )
        return

    subpath = path[len("/admin/help/"):] if path.startswith("/admin/help/") else ""
    if not subpath or subpath == "/":
        subpath = "index.html"

    static_dir = _get_static_dir()
    file_path = (static_dir / subpath).resolve()

    # Защита от Path Traversal
    try:
        file_path.relative_to(static_dir.resolve())
    except ValueError:
        proto.response_str(status=403, headers=[("content-length", "0")], body="")
        return

    if not file_path.is_file():
        # Fallback на index.html для SPA роутинга
        file_path = static_dir / "index.html"
        if not file_path.is_file():
            proto.response_str(
                status=404,
                headers=[("content-type", "text/plain; charset=utf-8"), ("content-length", "21")],
                body="Help UI not built."
            )
            return

    content_type, _ = mimetypes.guess_type(str(file_path))
    content_type = content_type or "application/octet-stream"

    try:
        data = file_path.read_bytes()
        proto.response_bytes(
            status=200,
            headers=[
                ("content-type", content_type),
                ("content-length", str(len(data))),
                ("cache-control", "no-cache"),
            ],
            body=data,
        )
    except Exception as e:
        logger.error(f"[Admin Help] Ошибка отдачи файла {file_path}: {e}")
        proto.response_str(status=500, headers=[("content-length", "0")], body="")