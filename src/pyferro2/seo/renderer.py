"""
Быстрый сборщик валидного семантического HTML, OpenGraph, Twitter Cards
и Schema.org JSON-LD для поисковых ботов (`pyferro2/seo/renderer.py`).
"""

from __future__ import annotations

from datetime import datetime
import html
from typing import Any

import orjson

from pyferro2.seo.models import SeoPageData, get_seo_config


def _format_datetime(dt: datetime | None) -> str | None:
    """Форматирует дату/время в стандартный ISO-8601 формат."""
    if not dt:
        return None
    return dt.isoformat()


def render_seo_page(
    page: SeoPageData,
    current_path: str = "/",
    host: str | None = None,
    is_emulation: bool = False,
) -> str:
    """
    Генерирует полный валидный HTML-документ для отдачи краулерам и ботам.
    """
    cfg = get_seo_config()

    base_url = cfg.site_url
    if host and not base_url.startswith("https://") and not base_url.startswith("http://"):
        base_url = f"https://{host}"

    canonical = page.canonical_url
    if canonical and not (canonical.startswith("http://") or canonical.startswith("https://")):
        canonical = f"{base_url.rstrip('/')}/{canonical.lstrip('/')}"
    elif not canonical:
        canonical = f"{base_url.rstrip('/')}/{current_path.lstrip('/')}"

    og_image = page.og_image or cfg.default_og_image
    if og_image and not (og_image.startswith("http://") or og_image.startswith("https://")):
        og_image = f"{base_url.rstrip('/')}/{og_image.lstrip('/')}"

    title_escaped = html.escape(page.title)
    desc_escaped = html.escape(page.description, quote=True)
    canonical_escaped = html.escape(canonical, quote=True)
    site_name_escaped = html.escape(cfg.site_name, quote=True)
    lang = page.lang or cfg.default_lang

    head_lines: list[str] = [
        '    <meta charset="utf-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"    <title>{title_escaped}</title>",
        f'    <meta name="description" content="{desc_escaped}">',
        f'    <meta name="robots" content="{html.escape(page.robots, quote=True)}">',
        f'    <link rel="canonical" href="{canonical_escaped}">',
    ]

    # OpenGraph
    head_lines.extend([
        f'    <meta property="og:title" content="{title_escaped}">',
        f'    <meta property="og:description" content="{desc_escaped}">',
        f'    <meta property="og:type" content="{html.escape(page.og_type, quote=True)}">',
        f'    <meta property="og:url" content="{canonical_escaped}">',
        f'    <meta property="og:site_name" content="{site_name_escaped}">',
    ])
    if og_image:
        head_lines.append(f'    <meta property="og:image" content="{html.escape(og_image, quote=True)}">')

    pub_iso = _format_datetime(page.published_time)
    if pub_iso:
        head_lines.append(f'    <meta property="article:published_time" content="{pub_iso}">')

    mod_iso = _format_datetime(page.modified_time)
    if mod_iso:
        head_lines.append(f'    <meta property="article:modified_time" content="{mod_iso}">')

    if page.author:
        head_lines.append(f'    <meta property="article:author" content="{html.escape(page.author, quote=True)}">')

    # Twitter Cards
    twitter_card = "summary_large_image" if og_image else "summary"
    head_lines.extend([
        f'    <meta name="twitter:card" content="{twitter_card}">',
        f'    <meta name="twitter:title" content="{title_escaped}">',
        f'    <meta name="twitter:description" content="{desc_escaped}">',
    ])
    if og_image:
        head_lines.append(f'    <meta name="twitter:image" content="{html.escape(og_image, quote=True)}">')

    # Schema.org JSON-LD
    json_ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": page.schema_type,
        "name": page.title,
        "description": page.description,
        "url": canonical,
    }
    if page.schema_type == "Article":
        json_ld["headline"] = page.title
    if og_image:
        json_ld["image"] = og_image
    if pub_iso:
        json_ld["datePublished"] = pub_iso
    if mod_iso:
        json_ld["dateModified"] = mod_iso
    if page.author:
        json_ld["author"] = {"@type": "Person", "name": page.author}
    if page.schema_data:
        json_ld.update(page.schema_data)

    json_ld_str = orjson.dumps(json_ld).decode("utf-8").replace("</", "<\\/")
    head_lines.append(f'    <script type="application/ld+json">{json_ld_str}</script>')

    # Хлебные крошки (Schema.org BreadcrumbList + HTML <nav>)
    breadcrumbs_html = ""
    if page.breadcrumbs:
        bc_items = []
        nav_items = []
        for idx, (bc_name, bc_url) in enumerate(page.breadcrumbs, start=1):
            full_bc_url = (
                bc_url
                if (bc_url.startswith("http://") or bc_url.startswith("https://"))
                else f"{base_url.rstrip('/')}/{bc_url.lstrip('/')}"
            )
            bc_items.append({
                "@type": "ListItem",
                "position": idx,
                "name": bc_name,
                "item": full_bc_url,
            })
            nav_items.append(
                f'<li><a href="{html.escape(bc_url, quote=True)}">{html.escape(bc_name)}</a></li>'
            )

        bc_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": bc_items,
        }
        bc_ld_str = orjson.dumps(bc_ld).decode("utf-8").replace("</", "<\\/")
        head_lines.append(f'    <script type="application/ld+json">{bc_ld_str}</script>')
        breadcrumbs_html = f'    <nav aria-label="Breadcrumb"><ol>{"".join(nav_items)}</ol></nav>\n'

    body_content = page.body_html
    if not body_content:
        body_content = f"<h1>{title_escaped}</h1>\n<p>{html.escape(page.description)}</p>"

    emulation_banner = ""
    if is_emulation:
        head_lines.append(
            "    <style>\n"
            "      body { font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; color: #1e293b; background: #f8fafc; margin: 0; padding: 0; }\n"
            "      main { max-width: 900px; margin: 24px auto; padding: 28px 32px; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }\n"
            "      nav[aria-label='Breadcrumb'] { max-width: 900px; margin: 16px auto 0; padding: 0 16px; font-size: 13px; }\n"
            "      nav[aria-label='Breadcrumb'] ol { display: flex; flex-wrap: wrap; gap: 8px; list-style: none; padding: 0; margin: 0; }\n"
            "      nav[aria-label='Breadcrumb'] li + li::before { content: '›'; margin-right: 8px; color: #94a3b8; }\n"
            "      a { color: #2563eb; text-decoration: none; }\n"
            "      a:hover { text-decoration: underline; }\n"
            "      h1 { margin-top: 0; color: #0f172a; font-size: 26px; }\n"
            "      h2 { color: #1e293b; font-size: 18px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; margin-top: 24px; }\n"
            "      ul { padding-left: 20px; }\n"
            "      li { margin-bottom: 8px; }\n"
            "    </style>"
        )
        emulation_banner = (
            '    <div id="pyferro-bot-emulation-banner" style="'
            "background:#0f172a;color:#f8fafc;padding:12px 20px;font-family:system-ui,-apple-system,sans-serif;"
            "font-size:13px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;"
            'border-bottom:2px solid #10b981;box-shadow:0 4px 12px rgba(0,0,0,0.3);position:sticky;top:0;z-index:99999;">\n'
            '      <div style="display:flex;align-items:center;gap:10px;">\n'
            '        <span style="font-size:20px;">🤖</span>\n'
            "        <div>\n"
            '          <strong style="color:#34d399;display:block;">Режим эмуляции поискового робота (Googlebot / Яндекс)</strong>\n'
            '          <span style="color:#94a3b8;font-size:11px;">Вы видите чистый семантический HTML и ссылки без JavaScript. Нажимайте на любые ссылки для проверки обхода сайта!</span>\n'
            "        </div>\n"
            "      </div>\n"
            '      <div style="display:flex;align-items:center;gap:12px;">\n'
            f'        <span style="background:#1e293b;padding:4px 10px;border-radius:6px;font-family:monospace;font-size:11px;color:#cbd5e1;border:1px solid #334155;">Schema: {html.escape(page.schema_type)}</span>\n'
            '        <a href="?bot=0" style="background:#ef4444;color:#ffffff;text-decoration:none;padding:6px 14px;'
            'border-radius:6px;font-weight:600;font-size:12px;">✕ Выйти в обычный режим</a>\n'
            "      </div>\n"
            "    </div>\n"
        )

    head_block = "\n".join(head_lines)
    return (
        f"<!DOCTYPE html>\n"
        f'<html lang="{html.escape(lang, quote=True)}">\n'
        f"  <head>\n"
        f"{head_block}\n"
        f"  </head>\n"
        f"  <body>\n"
        f"{emulation_banner}"
        f"{breadcrumbs_html}"
        f"    <main>\n"
        f"      {body_content}\n"
        f"    </main>\n"
        f"  </body>\n"
        f"</html>"
    )


def render_404_html(site_name: str | None = None, is_emulation: bool = False) -> str:
    """Генерирует чистую семантическую страницу 404 для краулеров."""
    cfg = get_seo_config()
    name = site_name or cfg.site_name
    banner = ""
    if is_emulation:
        banner = (
            '    <div id="pyferro-bot-emulation-banner" style="'
            "background:#0f172a;color:#f8fafc;padding:12px 20px;font-family:system-ui,-apple-system,sans-serif;"
            "font-size:13px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;"
            'border-bottom:2px solid #ef4444;box-shadow:0 4px 12px rgba(0,0,0,0.3);">\n'
            '      <div style="display:flex;align-items:center;gap:10px;">\n'
            '        <span style="font-size:20px;">🤖</span>\n'
            "        <div>\n"
            '          <strong style="color:#f87171;">Режим эмуляции бота (Страница 404)</strong>\n'
            "        </div>\n"
            "      </div>\n"
            '      <a href="?bot=0" style="background:#ef4444;color:#ffffff;text-decoration:none;padding:6px 14px;'
            'border-radius:6px;font-weight:600;font-size:12px;">✕ Выйти</a>\n'
            "    </div>\n"
        )
    return (
        f"<!DOCTYPE html>\n"
        f'<html lang="ru">\n'
        f"  <head>\n"
        f'    <meta charset="utf-8">\n'
        f"    <title>404 Not Found - {html.escape(name)}</title>\n"
        f'    <meta name="robots" content="noindex, nofollow">\n'
        f"  </head>\n"
        f"  <body>\n"
        f"{banner}"
        f"    <h1>404 Not Found</h1>\n"
        f"    <p>Запрошенная страница не найдена.</p>\n"
        f"  </body>\n"
        f"</html>"
    )


class HtmlBuilder:
    """
    Легковесный zero-dependency билдер валидного семантического HTML для краулеров.
    Автоматически экранирует пользовательский ввод для предотвращения XSS.
    """

    __slots__ = ("_elements",)

    def __init__(self) -> None:
        self._elements: list[str] = []

    def h1(self, text: str) -> HtmlBuilder:
        self._elements.append(f"<h1>{html.escape(text)}</h1>")
        return self

    def h2(self, text: str) -> HtmlBuilder:
        self._elements.append(f"<h2>{html.escape(text)}</h2>")
        return self

    def h3(self, text: str) -> HtmlBuilder:
        self._elements.append(f"<h3>{html.escape(text)}</h3>")
        return self

    def h4(self, text: str) -> HtmlBuilder:
        self._elements.append(f"<h4>{html.escape(text)}</h4>")
        return self

    def p(self, text: str) -> HtmlBuilder:
        self._elements.append(f"<p>{html.escape(text)}</p>")
        return self

    def text(self, text: str) -> HtmlBuilder:
        self._elements.append(html.escape(text))
        return self

    def raw(self, raw_html: str) -> HtmlBuilder:
        """Вставляет сырой HTML без экранирования (для доверенного содержимого)."""
        self._elements.append(raw_html)
        return self

    def link(self, text: str, href: str) -> HtmlBuilder:
        self._elements.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(text)}</a>')
        return self

    def img(self, src: str, alt: str = "") -> HtmlBuilder:
        self._elements.append(f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">')
        return self

    def list(self, items: list[str], ordered: bool = False) -> HtmlBuilder:
        tag = "ol" if ordered else "ul"
        lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
        self._elements.append(f"<{tag}>{lis}</{tag}>")
        return self

    def article(self, content: Any) -> HtmlBuilder:
        inner = content.to_html() if isinstance(content, HtmlBuilder) else str(content)
        self._elements.append(f"<article>\n{inner}\n</article>")
        return self

    def section(self, content: Any) -> HtmlBuilder:
        inner = content.to_html() if isinstance(content, HtmlBuilder) else str(content)
        self._elements.append(f"<section>\n{inner}\n</section>")
        return self

    def to_html(self) -> str:
        return "\n".join(self._elements)

    def __str__(self) -> str:
        return self.to_html()
