# -*- coding: utf-8 -*-
"""
tests/suites/test_seo.py: Модульные тесты для плагина pyferro.plugins.seo.
"""

import asyncio
from datetime import datetime
from uuid import uuid4

import pytest

from pyferro.plugins.seo import (
    HtmlBuilder,
    SeoPageData,
    bot_page,
    build_sitemap_xml,
    configure_seo,
    enqueue_indexnow_urls,
    flush_indexnow_queue,
    get_seo_config,
    handle_bot_http,
    handle_sitemap_http,
    invalidate_sitemap_cache,
    is_bot,
    notify_indexnow,
    register_indexnow_key_route,
    register_sitemap_provider,
    render_seo_page,
)
from pyferro.plugins.seo.router import BOT_ROUTES, BotRoute
from pyferro.plugins.seo.sitemap import SITEMAP_PROVIDERS

def _sync_sqlite_db():
    import sqlite3
    import os
    for db_name in ("app.db", "data/app.db", "showcase.db", "examples/admin_help/showcase.db"):
        if os.path.exists(db_name):
            try:
                con = sqlite3.connect(db_name)
                cols = [c[1] for c in con.execute("PRAGMA table_info(pf_showcase_forum_category)").fetchall()]
                if cols and "parent_id" not in cols:
                    con.execute("ALTER TABLE pf_showcase_forum_category ADD COLUMN parent_id INTEGER")
                    con.commit()
                con.close()
            except Exception:
                pass

_sync_sqlite_db()


class MockRSGIProto:
    """Мок RSGI протокола для тестирования ответов."""

    def __init__(self):
        self.status = None
        self.headers = None
        self.body = None

    def response_str(self, status: int, headers: list, body: str):
        self.status = status
        self.headers = dict(headers)
        self.body = body


# -----------------------------------------------------------------------------
# 1. Тесты детектора ботов
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("user_agent,expected", [
    # Поисковые системы
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", True),
    ("Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)", True),
    ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", True),
    ("Baiduspider+(+http://www.baidu.com/search/spider.htm)", True),
    ("DuckDuckBot/1.0; (+http://duckduckgo.com/duckduckbot.html)", True),
    # Соцсети и мессенджеры
    ("TelegramBot (like TwitterBot)", True),
    ("vkShare; +http://vk.com/dev/Share", True),
    ("Twitterbot/1.0", True),
    ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", True),
    ("WhatsApp/2.21.12.21 A", True),
    ("Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)", True),
    # ИИ-краулеры
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)", True),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", True),
    ("Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/bot)", True),
    ("Applebot-Extended/0.1", True),
    # Обычные пользовательские браузеры (не боты)
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", False),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15", False),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148", False),
    ("", False),
    (None, False),
])
def test_is_bot_user_agents(user_agent, expected):
    assert is_bot(user_agent) is expected


def test_is_bot_from_scope():
    scope_bot = {"headers": [(b"user-agent", b"Googlebot/2.1")]}
    scope_user = {"headers": [(b"user-agent", b"Mozilla/5.0 Chrome")]}
    scope_empty = {"headers": []}

    assert is_bot(scope_bot) is True
    assert is_bot(scope_user) is False
    assert is_bot(scope_empty) is False


# -----------------------------------------------------------------------------
# 2. Тесты маршрутизации и извлечения параметров
# -----------------------------------------------------------------------------

def test_bot_route_param_parsing():
    route = BotRoute("/forum/{topic_id:int}/post/{slug:str}", lambda topic_id, slug: None)

    # Успешный матчинг с типами
    params = route.match("/forum/42/post/my-first-topic")
    assert params == {"topic_id": 42, "slug": "my-first-topic"}
    assert isinstance(params["topic_id"], int)

    # Несовпадение типа (topic_id не int)
    assert route.match("/forum/abc/post/my-first-topic") is None

    # Несовпадение пути
    assert route.match("/other/path") is None


def test_bot_route_uuid_param():
    uid = uuid4()
    route = BotRoute("/items/{item_id:uuid}", lambda item_id: None)

    params = route.match(f"/items/{uid}")
    assert params == {"item_id": uid}
    assert route.match("/items/not-a-uuid") is None


def test_handle_bot_http_interceptor():
    async def _run():
        BOT_ROUTES.clear()

        @bot_page("/test-topic/{topic_id:int}")
        async def sample_view(topic_id: int):
            if topic_id == 404:
                return None
            return SeoPageData(
                title=f"Тема #{topic_id}",
                description="Описание темы",
                body_html=f"<h1>Тема {topic_id}</h1>"
            )

        proto = MockRSGIProto()

        # 1. Запрос от обычного пользователя (не бота) -> перехватчик возвращает False
        user_scope = {
            "proto": "http",
            "method": "GET",
            "path": "/test-topic/1",
            "headers": [(b"user-agent", b"Mozilla/5.0 Safari")],
        }
        handled = await handle_bot_http(user_scope, proto)
        assert handled is False
        assert proto.status is None

        # 2. Запрос от Googlebot на существующую страницу -> 200 OK, HTML
        bot_scope_200 = {
            "proto": "http",
            "method": "GET",
            "path": "/test-topic/1",
            "headers": [(b"user-agent", b"Googlebot/2.1")],
        }
        handled = await handle_bot_http(bot_scope_200, proto)
        assert handled is True
        assert proto.status == 200
        assert "text/html" in proto.headers["content-type"]
        assert "x-rendered-for" in proto.headers
        assert "Тема #1" in proto.body
        assert "<h1>Тема 1</h1>" in proto.body

        # 3. Запрос от бота на несуществующую страницу (возврат None) -> 404
        bot_scope_404 = {
            "proto": "http",
            "method": "GET",
            "path": "/test-topic/404",
            "headers": [(b"user-agent", b"TelegramBot")],
        }
        handled_404 = await handle_bot_http(bot_scope_404, proto)
        assert handled_404 is True
        assert proto.status == 404
        assert "404 Not Found" in proto.body

    asyncio.run(_run())


# -----------------------------------------------------------------------------
# 3. Тесты генерации HTML, OpenGraph, Twitter Cards и JSON-LD
# -----------------------------------------------------------------------------

def test_render_seo_page():
    now = datetime(2026, 10, 2, 12, 0, 0)
    page = SeoPageData(
        title="Тестовая статья & Гайд",
        description="Подробный разбор <тест>",
        canonical_url="https://example.com/guide",
        og_image="https://example.com/cover.jpg",
        og_type="article",
        schema_type="Article",
        author="Иван Иванов",
        published_time=now,
        breadcrumbs=[("Главная", "/"), ("Статьи", "/articles")],
        body_html="<article><p>Полезный контент</p></article>"
    )

    html_out = render_seo_page(page, current_path="/guide")

    # Проверка базовой структуры и экранирования
    assert "<!DOCTYPE html>" in html_out
    assert "<title>Тестовая статья &amp; Гайд</title>" in html_out
    assert 'meta name="description" content="Подробный разбор &lt;тест&gt;"' in html_out
    assert 'link rel="canonical" href="https://example.com/guide"' in html_out

    # OpenGraph
    assert 'meta property="og:title" content="Тестовая статья &amp; Гайд"' in html_out
    assert 'meta property="og:image" content="https://example.com/cover.jpg"' in html_out
    assert 'meta property="og:type" content="article"' in html_out
    assert 'meta property="article:author" content="Иван Иванов"' in html_out
    assert 'meta property="article:published_time" content="2026-10-02T12:00:00"' in html_out

    # Twitter Cards
    assert 'meta name="twitter:card" content="summary_large_image"' in html_out
    assert 'meta name="twitter:image" content="https://example.com/cover.jpg"' in html_out

    # Schema.org JSON-LD
    assert 'application/ld+json' in html_out
    assert '"@type": "Article"' in html_out
    assert '"author":' in html_out
    assert '"name": "Иван Иванов"' in html_out
    assert '"BreadcrumbList"' in html_out

    # Body
    assert '<article><p>Полезный контент</p></article>' in html_out
    assert '<nav aria-label="breadcrumbs"' in html_out


# -----------------------------------------------------------------------------
# 4. Тесты генерации карты сайта (sitemap.xml) и кэша
# -----------------------------------------------------------------------------

def test_sitemap_xml_generation():
    async def _run():
        invalidate_sitemap_cache()
        configure_seo(site_url="https://example.com")

        @register_sitemap_provider
        async def async_provider():
            return [
                {"loc": "/news", "changefreq": "daily", "priority": 0.9},
                {"loc": "https://example.com/static-page", "priority": 0.5},
            ]

        @register_sitemap_provider
        def sync_provider():
            return [
                {"loc": "/about", "lastmod": "2026-10-01", "changefreq": "monthly"}
            ]

        xml = await build_sitemap_xml("https://example.com")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in xml

        # Проверка URL и нормализации
        assert '<loc>https://example.com/news</loc>' in xml
        assert '<changefreq>daily</changefreq>' in xml
        assert '<priority>0.9</priority>' in xml

        assert '<loc>https://example.com/static-page</loc>' in xml
        assert '<priority>0.5</priority>' in xml

        assert '<loc>https://example.com/about</loc>' in xml
        assert '<lastmod>2026-10-01</lastmod>' in xml

    asyncio.run(_run())


# -----------------------------------------------------------------------------
# 5. Тесты гибридного детектора (CLI, Scrapers, Custom, Extra Patterns)
# -----------------------------------------------------------------------------

def test_hybrid_bot_detector_advanced():
    # CLI и утилиты автоматизации
    assert is_bot("curl/7.81.0") is True
    assert is_bot("Wget/1.21.2") is True
    assert is_bot("python-requests/2.31.0") is True
    assert is_bot("Go-http-client/1.1") is True
    assert is_bot("aiohttp/3.8.5") is True

    # Экзотический краулер без браузерного движка
    assert is_bot("CustomAiScraper/1.0 (+http://ai.example.com)") is True

    # Дополнительные пользовательские паттерны
    configure_seo(extra_bot_patterns=[r"my-internal-crawler"])
    assert is_bot("Mozilla/5.0 my-internal-crawler Chrome/120.0") is True

    # Пользовательский детектор
    def custom_det(scope_or_ua):
        if "super-vip-browser" in str(scope_or_ua):
            return False  # Принудительно считать браузером
        if "banned-client" in str(scope_or_ua):
            return True   # Принудительно считать ботом
        return None       # Передать в стандартный детектор

    configure_seo(custom_detector=custom_det)
    assert is_bot("super-vip-browser") is False
    assert is_bot("banned-client") is True

    # Сбрасываем кастомизацию
    configure_seo(extra_bot_patterns=[], custom_detector=None)


# -----------------------------------------------------------------------------
# 6. Тесты HtmlBuilder
# -----------------------------------------------------------------------------

def test_html_builder_escaping_and_structure():
    builder = HtmlBuilder()
    builder.h1("Заголовок <script>alert(1)</script>")
    builder.p("Текст & цитата \"тест\"")
    builder.link("Ссылка", "https://example.com?a=1&b=2")
    builder.img("/pic.png", "Описание <картинки>")
    builder.list(["Пункт 1", "Пункт 2 <br>"], ordered=True)
    builder.article(HtmlBuilder().p("Вложенный параграф"))
    builder.raw("<!-- доверенный комментарий -->")

    out = builder.to_html()

    # Проверка безопасного экранирования
    assert "<h1>Заголовок &lt;script&gt;alert(1)&lt;/script&gt;</h1>" in out
    assert "<p>Текст &amp; цитата &quot;тест&quot;</p>" in out
    assert '<a href="https://example.com?a=1&amp;b=2">Ссылка</a>' in out
    assert '<img src="/pic.png" alt="Описание &lt;картинки&gt;">' in out
    assert "<ol><li>Пункт 1</li><li>Пункт 2 &lt;br&gt;</li></ol>" in out
    assert "<article>\n<p>Вложенный параграф</p>\n</article>" in out
    assert "<!-- доверенный комментарий -->" in out
    assert str(builder) == out


# -----------------------------------------------------------------------------
# 7. Тесты пагинации карты сайта (Sitemap Index & Chunks)
# -----------------------------------------------------------------------------

def test_sitemap_pagination_and_index():
    async def _run():
        SITEMAP_PROVIDERS.clear()
        invalidate_sitemap_cache()
        
        # Настраиваем размер чанка в 3 URL
        configure_seo(
            site_url="https://example.com",
            sitemap_max_urls_per_file=3,
        )

        @register_sitemap_provider
        def many_urls():
            return [
                {"loc": f"/item-{i}", "lastmod": f"2026-10-0{i}" if i < 10 else "2026-10-10"}
                for i in range(1, 8)  # 7 URL -> 3 чанка: (3, 3, 1)
            ]

        # 1. /sitemap.xml должен вернуть <sitemapindex>
        index_xml = await build_sitemap_xml("https://example.com", page=None)
        assert "<sitemapindex" in index_xml
        assert "<loc>https://example.com/sitemap-1.xml</loc>" in index_xml
        assert "<loc>https://example.com/sitemap-2.xml</loc>" in index_xml
        assert "<loc>https://example.com/sitemap-3.xml</loc>" in index_xml

        # 2. /sitemap-1.xml должен вернуть <urlset> с первыми 3 элементами
        page1_xml = await build_sitemap_xml("https://example.com", page=1)
        assert "<urlset" in page1_xml
        assert "<loc>https://example.com/item-1</loc>" in page1_xml
        assert "<loc>https://example.com/item-3</loc>" in page1_xml
        assert "item-4" not in page1_xml

        # 3. /sitemap-3.xml должен содержать 7-й элемент
        page3_xml = await build_sitemap_xml("https://example.com", page=3)
        assert "<urlset" in page3_xml
        assert "<loc>https://example.com/item-7</loc>" in page3_xml

        # 4. Проверка через универсальный перехватчик handle_sitemap_http
        proto_idx = MockRSGIProto()
        handled_idx = await handle_sitemap_http({"method": "GET", "path": "/sitemap.xml", "headers": []}, proto_idx)
        assert handled_idx is True
        assert proto_idx.status == 200
        assert "<sitemapindex" in proto_idx.body

        proto_p2 = MockRSGIProto()
        handled_p2 = await handle_sitemap_http({"method": "GET", "path": "/sitemap-2.xml", "headers": []}, proto_p2)
        assert handled_p2 is True
        assert proto_p2.status == 200
        assert "<urlset" in proto_p2.body
        assert "item-4" in proto_p2.body

        # Возвращаем стандартный лимит
        configure_seo(sitemap_max_urls_per_file=50_000)

    asyncio.run(_run())


# -----------------------------------------------------------------------------
# 8. Тесты файловой очереди IndexNow и сброса пачки
# -----------------------------------------------------------------------------

def test_indexnow_file_queue_and_flushing(tmp_path, monkeypatch):
    async def _run():
        queue_file = str(tmp_path / "test_indexnow_queue.txt")
        sent_batches = []

        async def mock_send(urls, host, key, key_location=None):
            sent_batches.append(list(urls))

        monkeypatch.setattr("pyferro.plugins.seo.indexnow._send_indexnow_background", mock_send)

        configure_seo(
            site_url="https://example.com",
            indexnow_key="test-key-xyz",
            indexnow_queue_file=queue_file,
            indexnow_flush_interval=1800,
            indexnow_max_queue_size=1000,
        )

        # 1. Добавляем URLs (с повторами для проверки дедупликации)
        notify_indexnow(["https://example.com/article-1", "https://example.com/article-2"])
        notify_indexnow(["https://example.com/article-2", "https://example.com/article-3"])

        # Файл очереди должен существовать и содержать записи
        with open(queue_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 4

        # 2. Сбрасываем очередь
        sent_count = await flush_indexnow_queue(queue_file=queue_file)
        assert sent_count == 3  # Уникальных ровно 3

        # Проверяем, что в мок ушел один батч с 3 уникальными URL
        assert len(sent_batches) == 1
        assert set(sent_batches[0]) == {
            "https://example.com/article-1",
            "https://example.com/article-2",
            "https://example.com/article-3",
        }

        # После сброса временные файлы удалены
        import glob
        assert len(glob.glob(f"{queue_file}*")) == 0

    asyncio.run(_run())


# -----------------------------------------------------------------------------
# 8. Тесты No-Code динамических правил моделей (Форумы, Каталоги, Связи)
# -----------------------------------------------------------------------------

def test_dynamic_model_schema_and_preview():
    """Проверяет извлечение схемы модели и подстановку связей (Foreign Keys) в превью."""
    import pyferro.plugins.help  # Регистрация моделей форума
    from pyferro.plugins.seo.dynamic_rules import get_model_schema_for_seo, preview_model_rule

    # 1. Проверяем интроспекцию схемы
    schema = get_model_schema_for_seo("ForumTopic")
    assert schema["key"] == "ForumTopic"
    assert any(f["name"] == "title" for f in schema["fields"])
    assert any(r["relation_name"] == "category" for r in schema["relations"])
    cat_rel = next(r for r in schema["relations"] if r["relation_name"] == "category")
    assert any(f["chip"] == "category.name" for f in cat_rel["fields"])

    # 2. Проверяем генерацию превью правила со связями
    async def _run_preview():
        rule = {
            "model_key": "ForumTopic",
            "url_pattern": "/forum/{category.slug}/{slug}",
            "title_template": "{title} — раздел «{category.name}» | Форум",
            "description_template": "{first_post_text}",
            "schema_type": "DiscussionForumPosting",
            "breadcrumbs": [
                {"title": "Главная", "url": "/"},
                {"title": "{category.name}", "url": "/forum/{category.slug}"},
                {"title": "{title}", "url": ""},
            ]
        }
        res = await preview_model_rule("ForumTopic", rule)
        assert "/forum/" in res["url"]
        assert "раздел" in res["title"]
        assert res["schema_type"] == "DiscussionForumPosting"
        assert res["schema_data"]["@type"] == "DiscussionForumPosting"
        assert len(res["breadcrumbs"]) == 3
        assert res["breadcrumbs"][0]["title"] == "Главная"

    asyncio.run(_run_preview())


def test_dynamic_model_bot_rendering():
    """Проверяет перехват запроса бота динамическим правилом модели."""
    import pyferro.plugins.help
    from pyferro.plugins.seo import configure_seo, handle_bot_http

    configure_seo(
        model_rules=[
            {
                "model_key": "ForumTopic",
                "url_pattern": "/forum/{category.slug}/{slug}",
                "title_template": "{title} — раздел «{category.name}»",
                "description_template": "{first_post_text}",
                "schema_type": "DiscussionForumPosting",
            }
        ]
    )
    async def _run_http():
        from pyferro.db import engine, Base, async_session
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from pyferro.plugins.help.models import ForumCategory, ForumTopic
        async with async_session() as db:
            from sqlalchemy import select
            c = (await db.execute(select(ForumCategory).where(ForumCategory.slug == "architecture"))).scalar_one_or_none()
            if not c:
                c = ForumCategory(name="Архитектура", slug="architecture")
                db.add(c)
                await db.flush()
            t = (await db.execute(select(ForumTopic).where(ForumTopic.slug == "wsrpc-vs-rest-comparison"))).scalar_one_or_none()
            if not t:
                t = ForumTopic(category_id=c.id, title="WSRPC vs REST", slug="wsrpc-vs-rest-comparison", first_post_text="WSRPC rules!")
                db.add(t)
            await db.commit()

        # Бот запрашивает URL форума
        proto = MockRSGIProto()
        scope = {
            "method": "GET",
            "path": "/forum/architecture/wsrpc-vs-rest-comparison",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
                (b"host", b"localhost:8080"),
            ],
            "query_string": b"",
        }

        # handle_bot_http должен вернуть True и отдать семантический HTML
        handled = await handle_bot_http(scope, proto)
        assert handled is True
        assert proto.status == 200
        assert "DiscussionForumPosting" in proto.body or "og:title" in proto.body

    asyncio.run(_run_http())


def test_seo_role_rbac_and_admin_config():
    """Проверяет интеграцию роли seo в RBAC и фильтрацию моделей в admin.seo_get_config."""
    from pyferro.core.constants import SEO_ROLE, SYSTEM_ROLES
    assert SEO_ROLE == "seo"
    assert SEO_ROLE in SYSTEM_ROLES

    import asyncio
    from pyferro.db import engine, Base
    from pyferro.auth.discovery import sync_rpc_permissions
    from pyferro.plugins.crud.admin_handlers import seo_get_config_admin, seo_toggle_model_permission_admin

    class MockAdminSession:
        is_superadmin = True
        user = type("MockUser", (), {"is_superadmin": True, "id": 1, "login": "admin", "roles": [type("R", (), {"name": "admin"})()]})()
    async def _test():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await sync_rpc_permissions()

        session = MockAdminSession()
        cfg = await seo_get_config_admin(session)

        # 1. Проверяем список моделей: auth/системные таблицы не должны просачиваться
        model_keys = [m["key"] for m in cfg["available_models"]]
        assert "ForumTopic" in model_keys
        assert "ForumCategory" in model_keys
        assert "User" not in model_keys
        assert "Role" not in model_keys
        assert "UserRole" not in model_keys
        assert "RpcPermission" not in model_keys

        # 2. Проверяем свойства showcase моделей
        topic_meta = next(m for m in cfg["available_models"] if m["key"] == "ForumTopic")
        assert topic_meta["is_showcase"] is True
        assert topic_meta["seo_allowed"] is True
        assert "/forum/" in topic_meta["suggested_url_pattern"]
        assert topic_meta["suggested_title_field"] == "title"
        assert topic_meta["suggested_desc_field"] == "first_post_text"

        # 3. Проверяем переключение прав роли seo через RPC
        res = await seo_toggle_model_permission_admin(session, model_key="ForumTopic", allowed=False)
        assert res["status"] == "ok"
        assert res["seo_allowed"] is False

        # Повторно запрашиваем конфиг - seo_allowed для ForumTopic должен стать False
        cfg_after = await seo_get_config_admin(session)
        topic_after = next(m for m in cfg_after["available_models"] if m["key"] == "ForumTopic")
        assert topic_after["seo_allowed"] is False

        # Возвращаем обратно в True
        await seo_toggle_model_permission_admin(session, model_key="ForumTopic", allowed=True)

    asyncio.run(_test())



# -----------------------------------------------------------------------------
# 10. Тесты «Живого дерева сайта» (Site Tree Engine, ссылки, Sitemap)
# -----------------------------------------------------------------------------

def test_site_tree_engine_navigation_and_crawling(monkeypatch):
    """Проверяет сквозной обход дерева сайта ботом (Главная -> Форум -> Категории -> Темы)."""
    import pyferro.plugins.help
    import pyferro.plugins.seo.site_tree as site_tree_mod
    from pyferro.plugins.seo.site_tree import load_site_tree, match_and_render_site_tree, collect_site_tree_sitemap_urls
    from pyferro.plugins.seo.router import handle_bot_http

    test_tree = {
        "id": "root",
        "title": "Главная страница",
        "url_pattern": "/",
        "meta_title": "PyFerro Platform — современное реактивное веб-приложение",
        "meta_description": "Высокопроизводительное SPA-приложение с реактивными WebSocket-каналами.",
        "og_image": "",
        "schema_type": "WebPage",
        "template": "",
        "sitemap_enabled": True,
        "sitemap_priority": 1.0,
        "sitemap_changefreq": "daily",
        "children": [
            {
                "id": "forum_hub",
                "title": "Форум сообщества",
                "url_pattern": "/forum",
                "meta_title": "Форум сообщества — Главные разделы",
                "meta_description": "Обсуждения, анонсы, обмен опытом.",
                "template": "",
                "sitemap_enabled": True,
                "sitemap_priority": 0.9,
                "sitemap_changefreq": "daily",
                "children": [
                    {
                        "id": "category_root",
                        "title": "Раздел форума",
                        "url_pattern": "/forum/{slug}",
                        "model_key": "ForumCategory",
                        "meta_title": "Раздел «{{ record.name or title }}» — Форум",
                        "meta_description": "{{ record.description or description }}",
                        "template": "",
                        "sitemap_enabled": True,
                        "sitemap_priority": 0.85,
                        "sitemap_changefreq": "daily",
                        "children": [
                            {
                                "id": "topic_detail",
                                "title": "Тема форума",
                                "url_pattern": "/forum/{parent.slug}/{slug}",
                                "model_key": "ForumTopic",
                                "meta_title": "{{ record.title }} — {{ parent.name }} | Форум",
                                "meta_description": "{{ record.first_post_text }}",
                                "template": "",
                                "sitemap_enabled": True,
                                "sitemap_priority": 0.8,
                                "sitemap_changefreq": "daily",
                                "children": []
                            }
                        ]
                    }
                ]
            },
            {
                "id": "about_page",
                "title": "О проекте",
                "url_pattern": "/about",
                "meta_title": "О проекте PyFerro",
                "meta_description": "Технологический стек и возможности.",
                "template": "",
                "sitemap_enabled": True,
                "sitemap_priority": 0.5,
                "sitemap_changefreq": "monthly",
                "children": []
            }
        ]
    }
    monkeypatch.setattr(site_tree_mod, "load_site_tree", lambda: test_tree)

    async def _test_flow():
        from pyferro.db import engine, Base
        import pyferro.plugins.help.models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # 1. Загрузка дерева
        tree = load_site_tree()
        assert tree["id"] == "root"
        assert tree["url_pattern"] == "/"
        assert len(tree["children"]) >= 2
        # 2. Бот запрашивает корень "/"
        scope_root = {
            "method": "GET",
            "path": "/",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"),
                (b"host", b"example.com"),
            ],
            "query_string": b"",
        }
        proto_root = MockRSGIProto()
        handled_root = await handle_bot_http(scope_root, proto_root)
        assert handled_root is True
        assert proto_root.status == 200
        assert proto_root.headers.get("x-seo-engine") == "site-tree"
        assert '<nav class="seo-navigation"' in proto_root.body
        assert 'href="/forum"' in proto_root.body
        assert 'href="/about"' in proto_root.body

        # 3. Бот переходит по ссылке на "/forum" (Хаб категорий)
        scope_forum = {
            "method": "GET",
            "path": "/forum",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; Googlebot/2.1)"),
                (b"host", b"example.com"),
            ],
            "query_string": b"",
        }
        proto_forum = MockRSGIProto()
        handled_forum = await handle_bot_http(scope_forum, proto_forum)
        assert handled_forum is True
        assert proto_forum.status == 200
        assert proto_forum.headers.get("x-seo-engine") == "site-tree"
        assert "Форум сообщества" in proto_forum.body

        # 4. Проверяем сборку Sitemap из дерева
        sitemap_urls = await collect_site_tree_sitemap_urls()
        locs = [u["loc"] for u in sitemap_urls]
        assert "/" in locs
        assert "/forum" in locs
        assert "/about" in locs
        # Убеждаемся, что сырые шаблоны роутинга никогда не попадают в sitemap:
        assert "/forum/{slug}" not in locs
        assert "/forum/{parent.slug}/{slug}" not in locs
        for loc in locs:
            assert "{" not in loc and "}" not in loc

        # 5. Добавляем тестовые записи в БД и проверяем динамическую генерацию URL
        from pyferro.db import async_session
        from pyferro.plugins.help.models import ForumCategory, ForumTopic
        from sqlalchemy import select
        async with async_session() as session:
            cat = (await session.execute(select(ForumCategory).where(ForumCategory.slug == "test-sitemap-cat"))).scalar_one_or_none()
            if not cat:
                cat = ForumCategory(name="Тестовый раздел", slug="test-sitemap-cat", description="Все темы")
                session.add(cat)
                await session.commit()
                await session.refresh(cat)

            topic = (await session.execute(select(ForumTopic).where(ForumTopic.slug == "test-sitemap-topic"))).scalar_one_or_none()
            if not topic:
                topic = ForumTopic(
                    category_id=cat.id,
                    title="Тестовая тема",
                    slug="test-sitemap-topic",
                    first_post_text="Привет мир!",
                )
                session.add(topic)
                await session.commit()

        sitemap_urls_dynamic = await collect_site_tree_sitemap_urls()
        dyn_locs = [u["loc"] for u in sitemap_urls_dynamic]
        assert "/forum/test-sitemap-cat" in dyn_locs
        assert "/forum/test-sitemap-cat/test-sitemap-topic" in dyn_locs
        for u in sitemap_urls_dynamic:
            assert "{" not in u["loc"] and "}" not in u["loc"]
    asyncio.run(_test_flow())


def test_site_tree_rpc_methods():
    """Проверяет административные RPC-методы для управления деревом сайта."""
    from pyferro.plugins.crud.admin_handlers import seo_get_tree_admin, seo_save_tree_admin, seo_preview_tree_node_admin

    class MockAdminSession:
        is_superadmin = True
        user = type("MockUser", (), {"is_superadmin": True, "id": 1, "login": "admin", "roles": [type("R", (), {"name": "admin"})()]})()
    async def _test_rpc():
        session = MockAdminSession()
        res = await seo_get_tree_admin(session)
        assert "tree" in res
        assert "available_models" in res
        assert res["tree"]["id"] == "root"

        # Превью статического узла
        node = res["tree"]
        prev = await seo_preview_tree_node_admin(session, node=node)
        assert prev["title"]
        assert prev["body_html"]

        # Превью коллекции (например, список тем раздела)
        cat_node = {
            "id": "cat_test",
            "title": "Раздел форума (Список тем)",
            "url_pattern": "/forum/{parent.slug}",
            "node_type": "collection",
            "model_key": "ForumTopic",
            "meta_title": "Раздел «{parent.name}»",
            "meta_description": "{parent.description}",
        }
        prev_cat = await seo_preview_tree_node_admin(session, node=cat_node)
        assert prev_cat["title"]
        assert prev_cat["body_html"]

        # Превью детального узла (тема форума)
        topic_node = {
            "id": "topic_test",
            "title": "Тема форума (Карточка)",
            "url_pattern": "/forum/{parent.slug}/{slug}",
            "node_type": "detail",
            "model_key": "ForumTopic",
            "meta_title": "{title} — {parent.name}",
            "meta_description": "{first_post_text}",
        }
        prev_topic = await seo_preview_tree_node_admin(session, node=topic_node)
        assert prev_topic["title"]
        assert prev_topic["body_html"]

    asyncio.run(_test_rpc())


def test_jinja_seo_engine():
    """Тестирует движок Jinja2 шаблонов для SEO-страниц: валидацию, мультитабличные циклы и связи."""
    from pyferro.plugins.seo.jinja_engine import validate_jinja_template, build_template_context, render_jinja_template
    from pyferro.plugins.crud.admin_handlers import seo_validate_template_admin, seo_preview_tree_node_admin

    # 1. Проверка синтаксиса
    assert validate_jinja_template("<h1>{{ record.title }}</h1>")["valid"] is True
    assert validate_jinja_template("{% for x in items %} missing")["valid"] is False

    class MockAdminSession:
        is_superadmin = True
        user = type("MockUser", (), {"is_superadmin": True, "id": 1, "login": "admin", "roles": [type("R", (), {"name": "admin"})()]})()

    async def _test():
        session = MockAdminSession()
        # RPC валидация
        val_res = await seo_validate_template_admin(session, template="<h2>{{ title }}</h2>")
        assert val_res["valid"] is True

        err_res = await seo_validate_template_admin(session, template="{% for a in b %}")
        assert err_res["valid"] is False

        # Рендеринг шаблона с циклом по нескольким таблицам
        tpl = """
<h1>{{ title }}</h1>
<ul>
{% for c in ForumCategory %}
  <li>{{ c.name }}</li>
{% endfor %}
</ul>
<div>
{% for t in ForumTopic[:5] %}
  <span>{{ t.title }}</span>
{% endfor %}
</div>
"""
        ctx = build_template_context(extra={"title": "Живая страница"})
        rendered = await render_jinja_template(tpl, ctx)
        assert "<h1>Живая страница</h1>" in rendered
        assert "<ul>" in rendered
        assert "<div>" in rendered

        # Превью узла дерева с Jinja2 шаблоном
        custom_node = {
            "id": "custom_jinja",
            "title": "Кастомный узел",
            "url_pattern": "/custom-page",
            "node_type": "static",
            "meta_title": "SEO Заголовок",
            "meta_description": "SEO Описание",
            "template": "<h1>Кастомная страница: {{ title }}</h1><p>{{ description }}</p>",
        }
        prev = await seo_preview_tree_node_admin(session, node=custom_node)
        assert prev["title"] == "SEO Заголовок"
        assert "<h1>Кастомная страница: SEO Заголовок</h1>" in prev["body_html"]

    asyncio.run(_test())


def test_sitemap_xml_generation_never_contains_placeholders():
    """Проверяет, что итоговый XML sitemap никогда не содержит {slug} или {parent.slug}."""
    import asyncio
    from pyferro.plugins.seo.sitemap import build_sitemap_xml

    async def _test():
        xml = await build_sitemap_xml("https://example.com")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in xml
        assert "<loc>https://example.com/</loc>" in xml
        assert "<loc>https://example.com/forum</loc>" in xml
        assert "<loc>https://example.com/about</loc>" in xml
        assert "{slug}" not in xml
        assert "{parent.slug}" not in xml
        assert "{" not in xml
        assert "}" not in xml

    asyncio.run(_test())


def test_bot_emulation_session_and_cookie_flow():
    """Проверяет жизненный цикл эмуляции бота: активацию ?bot=1, сессионную куку при навигации и выход ?bot=0."""
    import asyncio
    from pyferro.plugins.seo.router import handle_bot_http

    class MockProto:
        def __init__(self):
            self.status = None
            self.headers = {}
            self.body = ""

        def response_str(self, status=200, headers=None, body=""):
            self.status = status
            self.headers = dict(headers or [])
            self.body = body

    async def _test():
        # 1. Обычный браузер Chrome без параметров -> бот-рендер НЕ срабатывает
        chrome_scope = {
            "method": "GET",
            "path": "/about",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
                (b"host", b"localhost:8080"),
            ],
            "query_string": b"",
        }
        p1 = MockProto()
        assert await handle_bot_http(chrome_scope, p1) is False

        # 2. Браузер переходит по ссылке из админки с ?bot=1
        chrome_scope_bot1 = {
            "method": "GET",
            "path": "/about",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
                (b"host", b"localhost:8080"),
            ],
            "query_string": b"bot=1",
        }
        p2 = MockProto()
        handled = await handle_bot_http(chrome_scope_bot1, p2)
        assert handled is True
        assert p2.status == 200
        assert p2.headers.get("set-cookie") == "pf_bot_mode=1; Path=/; SameSite=Lax"
        assert 'id="pf-bot-emulation-bar"' in p2.body
        assert 'href="?bot=0"' in p2.body

        # 3. Пользователь кликает по ссылкам на сайте (параметра bot=1 в URL уже нет, но кука шлется)
        chrome_scope_nav = {
            "method": "GET",
            "path": "/forum",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
                (b"host", b"localhost:8080"),
                (b"cookie", b"pf_bot_mode=1"),
            ],
            "query_string": b"",
        }
        p3 = MockProto()
        handled3 = await handle_bot_http(chrome_scope_nav, p3)
        assert handled3 is True
        assert p3.status == 200
        assert 'id="pf-bot-emulation-bar"' in p3.body

        # 4. Реальный бот (Googlebot) получает чистый HTML без панели эмулятора
        google_scope = {
            "method": "GET",
            "path": "/about",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
                (b"host", b"example.com"),
            ],
            "query_string": b"",
        }
        p4 = MockProto()
        handled4 = await handle_bot_http(google_scope, p4)
        assert handled4 is True
        assert p4.status == 200
        assert 'id="pf-bot-emulation-bar"' not in p4.body
        assert "set-cookie" not in p4.headers

        # 5. Пользователь нажимает "Выйти" (?bot=0) -> 302 редирект со сбросом куки
        chrome_scope_exit = {
            "method": "GET",
            "path": "/forum",
            "headers": [
                (b"user-agent", b"Mozilla/5.0"),
                (b"cookie", b"pf_bot_mode=1"),
            ],
            "query_string": b"bot=0",
        }
        p5 = MockProto()
        handled5 = await handle_bot_http(chrome_scope_exit, p5)
        assert handled5 is True
        assert p5.status == 302
        assert p5.headers.get("location") == "/forum"
        assert "Max-Age=0" in p5.headers.get("set-cookie", "")

    asyncio.run(_test())


def test_nested_subcategory_routing_and_fallback():
    """Проверяет разрешение коллизий URL: когда /forum/{parent.slug}/{slug} может быть и подразделом, и темой."""
    import asyncio
    from pyferro.db import engine, Base, async_session
    import pyferro.plugins.help.models
    from pyferro.plugins.help.models import ForumCategory, ForumTopic
    from pyferro.plugins.seo.router import handle_bot_http
    from sqlalchemy import select

    class MockProto:
        def __init__(self):
            self.status = None
            self.headers = {}
            self.body = ""

        def response_str(self, status=200, headers=None, body=""):
            self.status = status
            self.headers = dict(headers or [])
            self.body = body

    async def _test():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session() as session:
            # 1. Корневой раздел 'development'
            c_dev = (await session.execute(select(ForumCategory).where(ForumCategory.slug == "development"))).scalar_one_or_none()
            if not c_dev:
                c_dev = ForumCategory(name="Разработка", slug="development", description="Раздел разработки")
                session.add(c_dev)
                await session.commit()
                await session.refresh(c_dev)

            # 2. Подраздел 'architecture' (parent_id = c_dev.id)
            c_arch = (await session.execute(select(ForumCategory).where(ForumCategory.slug == "architecture"))).scalar_one_or_none()
            if not c_arch:
                c_arch = ForumCategory(parent_id=c_dev.id, name="Архитектура и WebSockets", slug="architecture", description="Обсуждение RSGI и WSRPC")
                session.add(c_arch)
                await session.commit()
                await session.refresh(c_arch)
            else:
                c_arch.parent_id = c_dev.id
                c_arch.name = "Архитектура и WebSockets"
                await session.commit()
                await session.refresh(c_arch)
            # 3. Тема форума 'my-topic' в корневом разделе
            topic = (await session.execute(select(ForumTopic).where(ForumTopic.slug == "my-topic"))).scalar_one_or_none()
            if not topic:
                topic = ForumTopic(
                    category_id=c_dev.id,
                    title="Тема в разработке",
                    slug="my-topic",
                    first_post_text="Обсуждаем код",
                )
                session.add(topic)
                await session.commit()

        # Запрос 1: Подраздел /forum/development/architecture (ForumCategory)
        scope_subcat = {
            "method": "GET",
            "path": "/forum/development/architecture",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; YandexBot/3.0)"),
                (b"host", b"localhost:8080"),
            ],
            "query_string": b"",
        }
        p_sub = MockProto()
        handled_sub = await handle_bot_http(scope_subcat, p_sub)
        assert handled_sub is True
        assert p_sub.status == 200
        assert "Архитектура" in p_sub.body
        assert "/forum/development" in p_sub.body

        # Запрос 2: Тема форума /forum/development/my-topic (ForumTopic)
        scope_topic = {
            "method": "GET",
            "path": "/forum/development/my-topic",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; Googlebot/2.1)"),
                (b"host", b"localhost:8080"),
            ],
            "query_string": b"",
        }
        p_top = MockProto()
        handled_top = await handle_bot_http(scope_topic, p_top)
        assert handled_top is True
        assert "Тема в разработке" in p_top.body

        # Запрос 3: Тема в подразделе /forum/development/architecture/wsrpc-vs-rest
        async with async_session() as session:
            t_sub = (await session.execute(select(ForumTopic).where(ForumTopic.slug == "wsrpc-vs-rest"))).scalar_one_or_none()
            if not t_sub:
                t_sub = ForumTopic(
                    category_id=c_arch.id,
                    title="WSRPC vs REST",
                    slug="wsrpc-vs-rest",
                    first_post_text="Сравнение протоколов",
                )
                session.add(t_sub)
                await session.commit()
            else:
                t_sub.category_id = c_arch.id
                await session.commit()

        scope_subtopic = {
            "method": "GET",
            "path": "/forum/development/architecture/wsrpc-vs-rest",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (compatible; Googlebot/2.1)"),
                (b"host", b"localhost:8080"),
            ],
            "query_string": b"",
        }
        p_subtop = MockProto()
        handled_subtop = await handle_bot_http(scope_subtopic, p_subtop)
        assert handled_subtop is True
        assert p_subtop.status == 200
        # Проверяем реальные названия категорий в хлебных крошках вместо "Раздел форума":
        assert 'href="/forum/development"' in p_subtop.body
        assert 'href="/forum/development/architecture"' in p_subtop.body
        assert "architecture/architecture" not in p_subtop.body
        assert "Раздел форума" not in p_subtop.body
        assert "Подраздел форума" not in p_subtop.body

    asyncio.run(_test())
