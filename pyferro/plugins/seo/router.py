# -*- coding: utf-8 -*-
"""
pyferro.plugins.seo.router: Диспетчер бот-маршрутов с типизированными параметрами URL.
"""

import inspect
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from pyferro.core.http import extract_header, extract_query_params, extract_cookies
from pyferro.core.logger import logger
from .detector import is_bot
from .renderer import render_404_html, render_seo_page
from .schemas import SeoPageData

# Поддерживаемые конвертеры типов для параметров маршрутов
TYPE_CONVERTERS: Dict[str, Tuple[str, Callable[[str], Any]]] = {
    "int": (r"\d+", int),
    "str": (r"[^/]+", str),
    "float": (r"\d+(?:\.\d+)?", float),
    "uuid": (r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", UUID),
}

# Регулярка для поиска плейсхолдеров вида {name} или {name:type}
PARAM_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-zA-Z_]+))?\}")


class BotRoute:
    """Маршрут для генерации SEO-страниц ботам."""

    def __init__(self, raw_path: str, handler: Callable):
        self.raw_path = raw_path
        self.handler = handler
        self.is_async = inspect.iscoroutinefunction(handler)
        self.param_types: Dict[str, Callable[[str], Any]] = {}

        # Преобразуем шаблон пути в регулярное выражение
        regex_pattern = "^"
        last_idx = 0

        for match in PARAM_RE.finditer(raw_path):
            start, end = match.span()
            regex_pattern += re.escape(raw_path[last_idx:start])
            param_name = match.group(1)
            type_name = match.group(2) or "str"

            converter_info = TYPE_CONVERTERS.get(type_name)
            if not converter_info:
                # Если тип неизвестен, считаем произвольной строкой до слэша
                param_regex, converter_fn = (r"[^/]+", str)
            else:
                param_regex, converter_fn = converter_info

            regex_pattern += f"(?P<{param_name}>{param_regex})"
            self.param_types[param_name] = converter_fn
            last_idx = end

        regex_pattern += re.escape(raw_path[last_idx:]) + "$"
        self.compiled_regex = re.compile(regex_pattern)

    def match(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Проверяет совпадение пути и извлекает типизированные параметры.
        Возвращает None, если путь не совпал.
        """
        m = self.compiled_regex.match(path)
        if not m:
            return None

        raw_dict = m.groupdict()
        typed_dict: Dict[str, Any] = {}
        for k, v in raw_dict.items():
            converter = self.param_types.get(k, str)
            try:
                typed_dict[k] = converter(v)
            except (ValueError, TypeError):
                return None
        return typed_dict


# Глобальный реестр маршрутов ботов
BOT_ROUTES: List[BotRoute] = []


def bot_page(path: str) -> Callable:
    """
    Декоратор для регистрации SEO-страницы бота.
    Пример:
        @bot_page("/forum/{topic_id:int}")
        async def get_topic_seo(topic_id: int) -> Optional[SeoPageData]:
            ...
    """
    def decorator(func: Callable) -> Callable:
        route = BotRoute(path, func)
        BOT_ROUTES.append(route)
        logger.debug(f"[SEO] Зарегистрирован бот-маршрут: {path} -> {func.__name__}")
        return func
    return decorator


async def handle_bot_http(scope: Any, proto: Any) -> bool:
    """
    RSGI-перехватчик входящих HTTP-запросов для Dynamic Rendering.
    Если клиент является ботом (или активна сессия эмуляции ?bot=1 / cookie pf_bot_mode=1),
    генерирует чистый семантический SSR HTML для краулера.
    """
    # 1. Проверяем метод (боты индексируют только GET и HEAD)
    method = getattr(scope, "method", None)
    if method is None and isinstance(scope, dict):
        method = scope.get("method")
    if method not in ("GET", "HEAD"):
        return False

    path = getattr(scope, "path", None)
    if path is None and isinstance(scope, dict):
        path = scope.get("path")
    if not path:
        return False

    query_params = extract_query_params(scope)
    bot_param = query_params.get("bot")

    # 1.1. Выход из режима эмуляции (?bot=0 или ?bot=false)
    # Сбрасывает сессионную куку и выполняет 302 редирект на чистый URL
    if bot_param in ("0", "false"):
        clean_path = path or "/"
        proto.response_str(
            status=302,
            headers=[
                ("location", clean_path),
                ("set-cookie", "pf_bot_mode=; Path=/; Max-Age=0; SameSite=Lax"),
            ],
            body=""
        )
        return True

    # 1.2. Проверяем сессионную куку эмуляции и параметр URL
    cookies = extract_cookies(scope)
    cookie_bot = cookies.get("pf_bot_mode") in ("1", "true")
    param_bot = bot_param in ("1", "true")

    is_emulation = param_bot or cookie_bot
    is_search_bot = is_bot(scope)

    if not (is_emulation or is_search_bot):
        return False

    def _make_headers(extra_headers: Optional[List[Tuple[str, str]]] = None) -> List[Tuple[str, str]]:
        headers: List[Tuple[str, str]] = [
            ("content-type", "text/html; charset=utf-8"),
            ("x-rendered-for", "bot"),
        ]
        if param_bot:
            # Сессионная кука без Max-Age/Expires: действует на сессию вкладки и исчезает при её закрытии
            headers.append(("set-cookie", "pf_bot_mode=1; Path=/; SameSite=Lax"))
        if extra_headers:
            headers.extend(extra_headers)
        return headers

    # 3. Ищем совпадающий зарегистрированный бот-маршрут (@bot_page)
    for route in BOT_ROUTES:
        params = route.match(path)
        if params is None:
            continue

        ua = extract_header(scope, "user-agent", default="unknown")
        logger.info(f"[SEO] Бот '{ua}' запросил '{path}'. Рендеринг через {route.handler.__name__} (emulation={is_emulation})...")

        try:
            if route.is_async:
                page_data = await route.handler(**params)
            else:
                page_data = route.handler(**params)
        except Exception as e:
            logger.error(f"[SEO] Ошибка в хендлере бот-страницы {route.raw_path}: {e}", exc_info=True)
            proto.response_str(
                status=500,
                headers=[("content-type", "text/plain; charset=utf-8")],
                body="500 Internal Server Error"
            )
            return True

        if page_data is None:
            logger.info(f"[SEO] Объект не найден ({path}). Отдаем 404.")
            proto.response_str(
                status=404,
                headers=_make_headers(),
                body=render_404_html(is_emulation=is_emulation)
            )
            return True

        if not isinstance(page_data, SeoPageData):
            logger.warning(f"[SEO] Хендлер {route.handler.__name__} вернул {type(page_data)} вместо SeoPageData.")
            return False

        host = extract_header(scope, "host")
        html_content = render_seo_page(page_data, current_path=path, host=host, is_emulation=is_emulation)

        proto.response_str(
            status=200,
            headers=_make_headers(),
            body=html_content
        )
        return True

    # 4. Проверяем кэш для Site Tree Engine и динамических правил
    from .page_cache import get_cached, set_cached
    found, cached = get_cached(path)
    if found:
        if cached is None:
            # Отрицательный кэш (страница гарантированно не существует)
            return False
        engine_name, page_data = cached
        host = extract_header(scope, "host")
        html_content = render_seo_page(page_data, current_path=path, host=host, is_emulation=is_emulation)
        proto.response_str(
            status=200,
            headers=_make_headers([("x-seo-engine", engine_name)]),
            body=html_content
        )
        return True

    # 5. Проверяем Живое дерево сайта (Site Tree Engine)
    had_error = False
    try:
        from .site_tree import match_and_render_site_tree
        page_data = await match_and_render_site_tree(path)
        if page_data:
            set_cached(path, ("site-tree", page_data))
            host = extract_header(scope, "host")
            html_content = render_seo_page(page_data, current_path=path, host=host, is_emulation=is_emulation)
            proto.response_str(
                status=200,
                headers=_make_headers([("x-seo-engine", "site-tree")]),
                body=html_content
            )
            return True
    except Exception as e:
        had_error = True
        logger.error(f"[SEO] Ошибка обработки дерева сайта для {path}: {e}", exc_info=True)

    # 6. Проверяем динамические No-Code правила моделей из админки (legacy fallback)
    try:
        from .config import get_seo_config
        from .dynamic_rules import match_and_render_model_rule
        cfg = get_seo_config()
        if cfg.model_rules:
            page_data = await match_and_render_model_rule(path, cfg.model_rules)
            if page_data:
                set_cached(path, ("dynamic-model-rule", page_data))
                host = extract_header(scope, "host")
                html_content = render_seo_page(page_data, current_path=path, host=host, is_emulation=is_emulation)
                proto.response_str(
                    status=200,
                    headers=_make_headers([("x-seo-engine", "dynamic-model-rule")]),
                    body=html_content
                )
                return True
    except Exception as e:
        had_error = True
        logger.error(f"[SEO] Ошибка обработки динамического правила для {path}: {e}", exc_info=True)

    # Ни один движок страницу не нашёл — сохраняем отрицательный кэш (если не было сбоя)
    if not had_error:
        set_cached(path, None)

    return False


__all__ = [
    "BotRoute",
    "BOT_ROUTES",
    "bot_page",
    "handle_bot_http",
]
