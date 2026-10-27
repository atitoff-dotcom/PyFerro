"""
Генератор карты сайта (`sitemap.xml`) с поддержкой реестра провайдеров,
обхода дерева сайта (`Site Tree`), пагинации (`sitemapindex` / `sitemap-N.xml`)
и TTL-кэширования в PyFerro 2.0 (`pyferro2/seo/sitemap.py`).
"""

from __future__ import annotations

from datetime import date, datetime
import html
import inspect
import logging
import math
import re
import time
from typing import TYPE_CHECKING, Any, Callable

from pyferro2.seo.detector import extract_header
from pyferro2.seo.models import get_seo_config
from pyferro2.seo.site_tree import collect_site_tree_sitemap_urls

if TYPE_CHECKING:
    from pyferro2.crud.engine import CrudEngine
    from pyferro2.db.engine import Database

logger = logging.getLogger("pyferro2.seo.sitemap")

SITEMAP_PROVIDERS: list[Callable[..., Any]] = []
_CACHED_SITEMAPS: dict[str | int, str] = {}
_CACHE_TIMESTAMP: float = 0.0

SITEMAP_PATH_RE = re.compile(r"^/sitemap(?:-(\d+))?\.xml$")


def register_sitemap_provider(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Декоратор для регистрации провайдера ссылок для `sitemap.xml`.
    Функция должна возвращать список словарей формата:
    `[{"loc": "/articles/my-slug", "lastmod": datetime.now(), "changefreq": "weekly", "priority": 0.8}]`
    """
    SITEMAP_PROVIDERS.append(func)
    invalidate_sitemap_cache()
    return func


def invalidate_sitemap_cache() -> None:
    """Принудительно сбрасывает закэшированный XML карты сайта."""
    global _CACHED_SITEMAPS, _CACHE_TIMESTAMP
    _CACHED_SITEMAPS.clear()
    _CACHE_TIMESTAMP = 0.0


def _format_lastmod(val: Any) -> str | None:
    """Форматирует дату для XML `lastmod` (`YYYY-MM-DD`)."""
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, str) and val:
        return val[:10] if len(val) >= 10 else val
    return None


async def collect_all_sitemap_urls(
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Собирает полный список ссылок со всех провайдеров `@register_sitemap_provider` и дерева сайта."""
    urls: list[dict[str, Any]] = []

    for provider in SITEMAP_PROVIDERS:
        try:
            res = await provider() if inspect.iscoroutinefunction(provider) else provider()
            if isinstance(res, list):
                urls.extend(res)
        except Exception as exc:
            logger.error("[SITEMAP] Ошибка при сборе URL из %s: %s", provider.__name__, exc)

    try:
        tree_urls = await collect_site_tree_sitemap_urls(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
        )
        existing_locs = {u.get("loc") for u in urls if isinstance(u, dict)}
        for tu in tree_urls:
            loc = tu.get("loc")
            if loc and loc not in existing_locs:
                urls.append(tu)
                existing_locs.add(loc)
    except Exception as exc:
        logger.error("[SITEMAP] Ошибка сбора URL из дерева сайта: %s", exc)

    return urls


def _render_urlset_xml(urls: list[dict[str, Any]], base: str) -> str:
    """Рендерит валидный XML-документ `<urlset>` для переданного среза ссылок."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for item in urls:
        raw_loc = str(item.get("loc", "")).strip()
        if not raw_loc:
            continue
        if raw_loc.startswith("http://") or raw_loc.startswith("https://"):
            full_loc = raw_loc
        else:
            full_loc = f"{base}/{raw_loc.lstrip('/')}"

        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(full_loc)}</loc>")

        lastmod_str = _format_lastmod(item.get("lastmod"))
        if lastmod_str:
            lines.append(f"    <lastmod>{html.escape(lastmod_str)}</lastmod>")

        changefreq = item.get("changefreq")
        if changefreq:
            lines.append(f"    <changefreq>{html.escape(str(changefreq))}</changefreq>")

        priority = item.get("priority")
        if priority is not None:
            lines.append(f"    <priority>{html.escape(str(priority))}</priority>")

        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines)


def _render_sitemapindex_xml(total_chunks: int, base: str) -> str:
    """Рендерит валидный XML-документ `<sitemapindex>`."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for i in range(1, total_chunks + 1):
        chunk_loc = f"{base}/sitemap-{i}.xml"
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{html.escape(chunk_loc)}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    return "\n".join(lines)


async def build_sitemap_xml(
    site_url: str | None = None,
    page: int | None = None,
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
) -> str:
    """
    Собирает XML-документ `sitemap.xml` (или `sitemapindex` при превышении лимита).
    """
    cfg = get_seo_config()
    base = (site_url or cfg.site_url).rstrip("/")
    max_per_file = max(1, cfg.sitemap_max_urls_per_file)

    urls = await collect_all_sitemap_urls(
        db=db,
        crud_engine=crud_engine,
        guest_permissions=guest_permissions,
    )
    total_urls = len(urls)

    if page is not None:
        start_idx = (max(1, page) - 1) * max_per_file
        end_idx = start_idx + max_per_file
        return _render_urlset_xml(urls[start_idx:end_idx], base)

    if total_urls <= max_per_file:
        return _render_urlset_xml(urls, base)

    total_chunks = math.ceil(total_urls / max_per_file)
    return _render_sitemapindex_xml(total_chunks, base)


def _send_xml(proto: Any, status: int, headers: list[tuple[str, str]], body: str) -> None:
    if hasattr(proto, "response_str"):
        proto.response_str(status, headers, body)
    else:
        proto.response_bytes(status, headers, body.encode("utf-8"))


async def handle_sitemap_http(
    scope: Any,
    proto: Any,
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
) -> bool:
    """
    Перехватчик HTTP-запросов карты сайта (`/sitemap.xml`, `/sitemap-N.xml`).
    Возвращает `True`, если запрос обработан.
    """
    global _CACHED_SITEMAPS, _CACHE_TIMESTAMP

    cfg = get_seo_config()
    if not cfg.enable_sitemap:
        return False

    method = getattr(scope, "method", None) or (scope.get("method") if isinstance(scope, dict) else "GET")
    if str(method).upper() not in ("GET", "HEAD"):
        return False

    path = getattr(scope, "path", None) or (scope.get("path") if isinstance(scope, dict) else None)
    if not path:
        return False

    match = SITEMAP_PATH_RE.match(str(path))
    if not match:
        return False

    page_str = match.group(1)
    cache_key: str | int = "index" if page_str is None else int(page_str)
    page_num: int | None = None if page_str is None else int(page_str)

    now = time.time()
    if cache_key in _CACHED_SITEMAPS and (now - _CACHE_TIMESTAMP) < cfg.sitemap_ttl:
        xml_body = _CACHED_SITEMAPS[cache_key]
    else:
        host = extract_header(scope, "host")
        base_url = cfg.site_url
        if host and not base_url.startswith("http"):
            base_url = f"https://{host}"

        xml_body = await build_sitemap_xml(
            base_url,
            page=page_num,
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
        )
        _CACHED_SITEMAPS[cache_key] = xml_body
        _CACHE_TIMESTAMP = now

    _send_xml(
        proto,
        200,
        [
            ("content-type", "application/xml; charset=utf-8"),
            ("cache-control", f"public, max-age={cfg.sitemap_ttl}"),
        ],
        xml_body,
    )
    return True
