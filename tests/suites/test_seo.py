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
            c = ForumCategory(name="Архитектура", slug="architecture")
            db.add(c)
            await db.flush()
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
