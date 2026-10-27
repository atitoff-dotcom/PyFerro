"""
Диспетчер бот-маршрутов (`@bot_page`) с типизированными параметрами URL и
перехватчик HTTP-запросов для Dynamic Rendering в PyFerro 2.0 (`pyferro2/seo/router.py`).
"""

from __future__ import annotations

import inspect
import logging
import re
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

from pyferro2.seo.detector import (
    extract_cookies,
    extract_header,
    extract_query_params,
    is_bot,
)
from pyferro2.seo.models import SeoPageData
from pyferro2.seo.page_cache import get_cached, set_cached
from pyferro2.seo.renderer import render_404_html, render_seo_page
from pyferro2.seo.site_tree import match_and_render_site_tree

if TYPE_CHECKING:
    from pyferro2.crud.engine import CrudEngine
    from pyferro2.db.engine import Database

logger = logging.getLogger("pyferro2.seo.router")

TYPE_CONVERTERS: dict[str, tuple[str, Callable[[str], Any]]] = {
    "int": (r"\d+", int),
    "str": (r"[^/]+", str),
    "float": (r"\d+(?:\.\d+)?", float),
    "uuid": (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        UUID,
    ),
}

PARAM_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-zA-Z_]+))?\}")


class BotRoute:
    """Маршрут для кодовой генерации SEO-страниц ботам (`@bot_page`)."""

    __slots__ = ("raw_path", "handler", "is_async", "param_types", "compiled_regex")

    def __init__(self, raw_path: str, handler: Callable[..., Any]) -> None:
        self.raw_path = raw_path
        self.handler = handler
        self.is_async = inspect.iscoroutinefunction(handler)
        self.param_types: dict[str, Callable[[str], Any]] = {}

        regex_pattern = "^"
        last_idx = 0

        for match in PARAM_RE.finditer(raw_path):
            start, end = match.span()
            regex_pattern += re.escape(raw_path[last_idx:start])
            param_name = match.group(1)
            type_name = match.group(2) or "str"

            param_regex, converter_fn = TYPE_CONVERTERS.get(type_name, (r"[^/]+", str))
            regex_pattern += f"(?P<{param_name}>{param_regex})"
            self.param_types[param_name] = converter_fn
            last_idx = end

        regex_pattern += re.escape(raw_path[last_idx:]) + "$"
        self.compiled_regex = re.compile(regex_pattern)

    def match(self, path: str) -> dict[str, Any] | None:
        """Проверяет совпадение пути и извлекает типизированные параметры."""
        m = self.compiled_regex.match(path)
        if not m:
            return None

        raw_dict = m.groupdict()
        typed_dict: dict[str, Any] = {}
        for k, v in raw_dict.items():
            converter = self.param_types.get(k, str)
            try:
                typed_dict[k] = converter(v)
            except (ValueError, TypeError):
                return None
        return typed_dict


BOT_ROUTES: list[BotRoute] = []


def bot_page(path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Декоратор для регистрации SEO-страницы бота.
    Пример:
        @bot_page("/articles/{slug}")
        async def get_article_seo(slug: str) -> SeoPageData | None:
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        route = BotRoute(path, func)
        BOT_ROUTES.append(route)
        return func
    return decorator


def _send_html(proto: Any, status: int, headers: list[tuple[str, str]], body: str) -> None:
    if hasattr(proto, "response_str"):
        proto.response_str(status, headers, body)
    else:
        proto.response_bytes(status, headers, body.encode("utf-8"))


async def handle_bot_http(
    scope: Any,
    proto: Any,
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
    admin_path: str = "/pyferro_admin",
) -> bool:
    """
    RSGI-перехватчик входящих HTTP-запросов для Dynamic Rendering.
    Если клиент является ботом (или активна сессия эмуляции `?bot=1`) и маршрут найден —
    отдает полный семантический HTML и возвращает `True`.
    Для обычных браузеров возвращает `False`.
    """
    method = getattr(scope, "method", None) or (scope.get("method") if isinstance(scope, dict) else "GET")
    if str(method).upper() not in ("GET", "HEAD"):
        return False

    path = getattr(scope, "path", None) or (scope.get("path") if isinstance(scope, dict) else None)
    if not path:
        return False
    path = str(path)

    # Никогда не перехватываем служебные маршруты фреймворка и статику
    if (
        path == admin_path
        or path.startswith(f"{admin_path}/")
        or path.startswith(("/rpc", "/ws", "/upload", "/files/", "/assets/", "/static/"))
        or path.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".xml", ".txt"))
    ):
        return False

    query = extract_query_params(scope)
    cookies = extract_cookies(scope)
    bot_param = query.get("bot", "").lower()

    # Выход из режима эмуляции бота (?bot=0)
    if bot_param in ("0", "false", "off"):
        _send_html(
            proto,
            302,
            [
                ("location", path),
                ("set-cookie", "pf_bot_mode=0; Path=/; Max-Age=0; SameSite=Lax"),
            ],
            "",
        )
        return True

    is_emulation = (
        bot_param in ("1", "true", "yes")
        or cookies.get("pf_bot_mode") == "1"
    )
    extra_cookie_headers: list[tuple[str, str]] = []
    if bot_param in ("1", "true", "yes") and cookies.get("pf_bot_mode") != "1":
        extra_cookie_headers.append(("set-cookie", "pf_bot_mode=1; Path=/; Max-Age=86400; SameSite=Lax"))

    if not is_emulation and not is_bot(scope):
        return False

    def _make_headers(custom: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
        h: list[tuple[str, str]] = [("content-type", "text/html; charset=utf-8")]
        if custom:
            h.extend(custom)
        if extra_cookie_headers:
            h.extend(extra_cookie_headers)
        return h

    # 1. Ищем совпадение среди зарегистрированных кодовых @bot_page маршрутов
    for route in BOT_ROUTES:
        params = route.match(path)
        if params is None:
            continue

        try:
            page_data = await route.handler(**params) if route.is_async else route.handler(**params)
        except Exception as exc:
            logger.error("[SEO] Ошибка в хендлере бот-страницы %s: %s", route.raw_path, exc)
            _send_html(
                proto,
                500,
                [("content-type", "text/plain; charset=utf-8")],
                "500 Internal Server Error",
            )
            return True

        if page_data is None:
            _send_html(
                proto,
                404,
                _make_headers(),
                render_404_html(is_emulation=is_emulation),
            )
            return True

        if not isinstance(page_data, SeoPageData):
            return False

        host = extract_header(scope, "host")
        html_content = render_seo_page(page_data, current_path=path, host=host, is_emulation=is_emulation)
        _send_html(proto, 200, _make_headers([("x-seo-engine", "bot-route")]), html_content)
        return True

    # 2. Проверяем кэш для Site Tree Engine
    found, cached = get_cached(path)
    if found:
        if cached is None:
            return False
        engine_name, page_data = cached
        host = extract_header(scope, "host")
        html_content = render_seo_page(page_data, current_path=path, host=host, is_emulation=is_emulation)
        _send_html(proto, 200, _make_headers([("x-seo-engine", engine_name)]), html_content)
        return True

    # 3. Проверяем Живое дерево сайта (Site Tree Engine)
    if db is not None and crud_engine is not None:
        had_error = False
        try:
            page_data = await match_and_render_site_tree(
                path,
                db=db,
                crud_engine=crud_engine,
                guest_permissions=guest_permissions,
            )
            if page_data is not None:
                set_cached(path, ("site-tree", page_data))
                host = extract_header(scope, "host")
                html_content = render_seo_page(
                    page_data, current_path=path, host=host, is_emulation=is_emulation
                )
                _send_html(proto, 200, _make_headers([("x-seo-engine", "site-tree")]), html_content)
                return True
        except Exception as exc:
            had_error = True
            logger.error("[SEO] Ошибка обработки дерева сайта для %s: %s", path, exc)

        if not had_error:
            set_cached(path, None)

    return False
