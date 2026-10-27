"""
Комплексные модульные и интеграционные тесты SEO-подсистемы PyFerro 2.0 (`pyferro2.seo`):
1. Двухуровневый детектор ботов (`is_bot`: поисковики, соцсети, AI-краулеры, CLI-утилиты vs обычные браузеры).
2. Генератор семантического HTML5 (`render_seo_page`, OpenGraph, Twitter Cards, Schema.org JSON-LD, хлебные крошки, баннер `?bot=1`).
3. Движок Дерева Сайта (`static`, `collection`, `detail`), песочница Jinja2 и строгая привязка доступа к правам роли `guest` (`Model.read`).
4. Защита системных таблиц (`User`, `Role`, `RolePermission`, `StoredFile`, `SeoConfigRecord`) от экспозиции в SEO и Jinja2.
5. Хранение конфигурации в БД (`SeoConfigRecord` в таблице `pf_seo_config`), RPC-методы админки (`seo.*`) и миграция `v2.1.0`.
6. RSGI HTTP перехватчик (`handle_bot_http`, `@bot_page`, `/sitemap.xml`, `/<indexnow_key>.txt`).
"""

from pathlib import Path

import pytest
from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.auth import ensure_admin_user, seed_system_roles
from pyferro2.core import Session
from pyferro2.db import Database, RowSecureModel
from pyferro2.files import FileStorage
from pyferro2.migrations.migration_v2_1_0 import downgrade as downgrade_v2_1_0
from pyferro2.migrations.migration_v2_1_0 import upgrade as upgrade_v2_1_0
from pyferro2.rpc import ForbiddenError
from pyferro2.seo import (
    BOT_ROUTES,
    SITEMAP_PROVIDERS,
    SeoPageData,
    bot_page,
    clear_seo_cache,
    configure_seo,
    get_seo_config,
    invalidate_sitemap_cache,
    is_bot,
    load_seo_from_db,
    register_sitemap_provider,
    render_seo_page,
    validate_jinja_template,
)
from pyferro2.server import MockRSGIScope, PyFerroApp, call_rsgi_http


class Category(RowSecureModel):
    """Тестовая модель категории каталога."""

    __tablename__ = "shop_categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    class Crud:
        title = "Категории"
        searchable = ("name",)


class Product(RowSecureModel):
    """Тестовая модель товара с внешним ключом на категорию."""

    __tablename__ = "shop_products"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[int] = mapped_column(Integer, default=0)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("shop_categories.id"), nullable=True
    )

    class Crud:
        title = "Товары"
        searchable = ("title", "summary")


class TestBotDetector:
    """Проверка двухуровневого гибридного детектора ботов."""

    @pytest.mark.parametrize(
        "ua",
        [
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
            "TelegramBot (like TwitterBot)",
            "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)",
            "ClaudeBot/1.0 (+https://anthropic.com)",
            "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "curl/8.5.0",
            "python-requests/2.31.0",
            "Wget/1.21.4",
        ],
    )
    def test_detects_search_social_ai_and_cli_bots(self, ua: str) -> None:
        assert is_bot(ua) is True

    @pytest.mark.parametrize(
        "ua",
        [
            "",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
        ],
    )
    def test_ignores_regular_human_browsers(self, ua: str) -> None:
        assert is_bot(ua) is False


class TestRendererAndTemplateValidation:
    """Проверка генератора семантического HTML5 и валидатора шаблонов Jinja2."""

    def test_renders_full_semantic_html_and_emulation_banner(self) -> None:
        configure_seo(site_url="https://shop.example.com", site_name="PyFerro Shop")
        page = SeoPageData(
            title="Смартфон X1",
            description="Флагманский смартфон",
            body_html="<h1>Смартфон X1 Pro</h1><p>Подробное описание характеристик.</p>",
            canonical_url="https://shop.example.com/products/1",
            og_image="/files/phone.jpg",
            breadcrumbs=[
                ("Главная", "https://shop.example.com/"),
                ("Товары", "https://shop.example.com/products"),
                ("Смартфон X1", "https://shop.example.com/products/1"),
            ],
            schema_type="Product",
            schema_data={"brand": "PyFerro"},
        )
        html = render_seo_page(page, current_path="/products/1", is_emulation=True)

        assert "<title>Смартфон X1</title>" in html
        assert 'content="Флагманский смартфон"' in html
        assert 'property="og:image" content="https://shop.example.com/files/phone.jpg"' in html
        assert '"@type":"BreadcrumbList"' in html
        assert '"@type":"Product"' in html
        assert "pyferro-bot-emulation-banner" in html
        assert "?bot=0" in html

    def test_validates_jinja_syntax(self) -> None:
        valid_res = validate_jinja_template("<h1>{{ record.title }}</h1>")
        assert valid_res["valid"] is True

        invalid_res = validate_jinja_template("{% for item in Product %}<b>{{ item.title }}")
        assert invalid_res["valid"] is False
        assert invalid_res["error"] is not None


class TestSeoSiteTreeRpcAndHttpIntegration:
    """Интеграционные тесты дерева сайта, прав роли guest, RPC `seo.*` и HTTP-ответов ботам."""

    @pytest.fixture(autouse=True)
    def _clean_global_seo_state(self):
        saved_routes = list(BOT_ROUTES)
        saved_providers = list(SITEMAP_PROVIDERS)
        clear_seo_cache()
        invalidate_sitemap_cache()
        yield
        BOT_ROUTES.clear()
        BOT_ROUTES.extend(saved_routes)
        SITEMAP_PROVIDERS.clear()
        SITEMAP_PROVIDERS.extend(saved_providers)
        clear_seo_cache()
        invalidate_sitemap_cache()

    async def test_site_tree_guest_permissions_and_bot_rendering(self, tmp_path: Path) -> None:
        db = Database("sqlite+aiosqlite:///:memory:")
        storage = FileStorage(storage_dir=tmp_path / "storage", tmp_root=tmp_path / "tmp")
        app = PyFerroApp(
            db=db,
            file_storage=storage,
            secret_key="seo-integration-secret-key-32bytes!!",
        )
        app.crud.register(Category)
        app.crud.register(Product)
        await app.startup()

        async with db.session() as s:
            await seed_system_roles(s)
            await ensure_admin_user(s, username="admin", password="AdminPassword1!")

        try:
            admin_session = Session(session_id="seo-admin-1")
            await app.router.call(
                "auth.login",
                admin_session,
                {"username": "admin", "password": "AdminPassword1!"},
                db=app.db,
            )

            # Создаём категорию и два товара от имени админа
            cat = await app.router.call(
                "Category.create",
                admin_session,
                {"data": {"name": "Ноутбуки"}},
                db=app.db,
            )
            prod1 = await app.router.call(
                "Product.create",
                admin_session,
                {
                    "data": {
                        "title": "UltraBook Pro 16",
                        "summary": "Мощный ноутбук для разработки",
                        "price": 189000,
                        "category_id": cat["id"],
                    }
                },
                db=app.db,
            )
            await app.router.call(
                "Product.create",
                admin_session,
                {
                    "data": {
                        "title": "AirBook Lite 13",
                        "summary": "Лёгкий ультрабук в дорогу",
                        "price": 99000,
                        "category_id": cat["id"],
                    }
                },
                db=app.db,
            )

            # 1. Изначально у роли guest НЕТ прав на чтение Product и Category
            tree_info = await app.router.call("seo.get_tree", admin_session, db=app.db)
            models_by_key = {m["key"]: m for m in tree_info["available_models"]}
            assert models_by_key["Product"]["seo_allowed"] is False
            assert models_by_key["Category"]["seo_allowed"] is False
            # Системные модели (User, Role и т.д.) вообще не попадают в список моделей для SEO
            assert "User" not in models_by_key
            assert "Role" not in models_by_key

            # 2. Попытка включить гостевое чтение для системной модели User блокируется
            with pytest.raises(ForbiddenError):
                await app.router.call(
                    "seo.toggle_guest_read",
                    admin_session,
                    {"model_key": "User", "allowed": True},
                    db=app.db,
                )

            # 3. Попытка сохранить дерево сайта с системной моделью User блокируется
            with pytest.raises(ForbiddenError):
                await app.router.call(
                    "seo.save_tree",
                    admin_session,
                    {
                        "tree": {
                            "id": "root",
                            "title": "Главная",
                            "url_pattern": "/",
                            "node_type": "collection",
                            "model_key": "User",
                            "children": [],
                        }
                    },
                    db=app.db,
                )

            # 4. Сохраняем дерево сайта для Product и Category + проверяем персистентность в БД
            site_tree = {
                "id": "root",
                "title": "Главная",
                "url_pattern": "/",
                "node_type": "static",
                "meta_title": "Главная — {site_name}",
                "meta_description": "Официальный магазин техники",
                "template": (
                    "<section><h2>Новинки ({{ Product.count() }})</h2>"
                    "<ul>{% for p in Product.order_by('-id') %}"
                    "<li>{{ p.title }} — {{ p.price }} ₽</li>"
                    "{% endfor %}</ul></section>"
                ),
                "children": [
                    {
                        "id": "catalog",
                        "title": "Каталог ноутбуков",
                        "url_pattern": "/products",
                        "node_type": "collection",
                        "model_key": "Product",
                        "meta_title": "Каталог ноутбуков | {site_name}",
                        "meta_description": "Каталог ноутбуков по выгодным ценам",
                        "item_link_pattern": "/products/{id}",
                        "item_title_pattern": "{title}",
                        "item_desc_pattern": "{summary}",
                        "children": [
                            {
                                "id": "product_detail",
                                "title": "Карточка товара",
                                "url_pattern": "/products/{id}",
                                "node_type": "detail",
                                "model_key": "Product",
                                "meta_title": "{{ record.title }} — купить за {{ record.price }} ₽",
                                "meta_description": "{{ record.summary }}",
                                "template": (
                                    "<div class='spec'>"
                                    "<p>Категория: {{ category.name if category else 'Без категории' }}</p>"
                                    "<p>Цена: <strong>{{ record.price }} ₽</strong></p>"
                                    "</div>"
                                ),
                                "schema_type": "Product",
                                "children": [],
                            }
                        ],
                    }
                ],
            }

            await app.router.call(
                "seo.save_tree",
                admin_session,
                {
                    "tree": site_tree,
                    "site_url": "https://tech.example.com",
                    "site_name": "TechStore",
                    "default_description": "Магазин ноутбуков",
                    "indexnow_key": "mysecretindexnowkey123",
                },
                db=app.db,
            )

            # Пока у guest нет права Product.read:
            # - На главной странице Product.count() в шаблоне возвращает 0 (защита данных)
            # - Страница /products для бота возвращает 404
            status_home_before, _, body_home_before, _ = await call_rsgi_http(
                app,
                "GET",
                "/",
                headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
            )
            assert status_home_before == 200
            assert "Новинки (0)" in body_home_before.decode("utf-8")
            assert "UltraBook Pro 16" not in body_home_before.decode("utf-8")

            status_catalog_before, _, _, _ = await call_rsgi_http(
                app,
                "GET",
                "/products",
                headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
            )
            assert status_catalog_before == 404

            # 5. Включаем гостевой доступ на чтение для Product и Category через `seo.toggle_guest_read`
            toggle_prod = await app.router.call(
                "seo.toggle_guest_read",
                admin_session,
                {"model_key": "Product", "allowed": True},
                db=app.db,
            )
            assert toggle_prod["seo_allowed"] is True

            toggle_cat = await app.router.call(
                "seo.toggle_guest_read",
                admin_session,
                {"model_key": "Category", "allowed": True},
                db=app.db,
            )
            assert toggle_cat["seo_allowed"] is True

            # 6. Теперь главная страница рендерит список товаров из Jinja2-цикла!
            status_home_after, _, body_home_after, _ = await call_rsgi_http(
                app,
                "GET",
                "/",
                headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
            )
            home_html = body_home_after.decode("utf-8")
            assert status_home_after == 200
            assert "Новинки (2)" in home_html
            assert "UltraBook Pro 16 — 189000 ₽" in home_html
            assert "AirBook Lite 13 — 99000 ₽" in home_html

            # 7. Каталог `/products` рендерит коллекцию с прямыми ссылками на карточки `/products/{id}`
            status_catalog_after, _, body_catalog_after, _ = await call_rsgi_http(
                app,
                "GET",
                "/products",
                headers={"user-agent": "Mozilla/5.0 (compatible; YandexBot/3.0)"},
            )
            catalog_html = body_catalog_after.decode("utf-8")
            assert status_catalog_after == 200
            assert "<title>Каталог ноутбуков | TechStore</title>" in catalog_html
            assert f'href="/products/{prod1["id"]}"' in catalog_html

            # 8. Детальная страница `/products/{id}` подтягивает запись, родительскую Category и JSON-LD
            status_detail, _, body_detail, _ = await call_rsgi_http(
                app,
                "GET",
                f"/products/{prod1['id']}",
                headers={"user-agent": "TelegramBot (like TwitterBot)"},
            )
            detail_html = body_detail.decode("utf-8")
            assert status_detail == 200
            assert "<title>UltraBook Pro 16 — купить за 189000 ₽</title>" in detail_html
            assert "Категория: Ноутбуки" in detail_html
            assert '"@type":"Product"' in detail_html
            assert '"@type":"BreadcrumbList"' in detail_html

            # 9. Обычный браузер с ?bot=1 получает HTML с баннером эмуляции и кукой pyferro_bot_mode=1
            status_emul, headers_emul, body_emul, _ = await call_rsgi_http(
                app,
                "GET",
                f"/products/{prod1['id']}",
                query_string="bot=1",
                headers={
                    "user-agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
                    )
                },
            )
            assert status_emul == 200
            assert "pyferro-bot-emulation-banner" in body_emul.decode("utf-8")
            assert any(
                k.lower() == "set-cookie" and "pf_bot_mode=1" in v
                for k, v in headers_emul.items()
            )

            # 10. Тестируем `seo.preview_node` из админки
            preview_res = await app.router.call(
                "seo.preview_node",
                admin_session,
                {
                    "node": site_tree["children"][0]["children"][0],
                    "parents": [site_tree, site_tree["children"][0]],
                    "sample_id": prod1["id"],
                },
            )
            assert preview_res["title"] == "UltraBook Pro 16 — купить за 189000 ₽"
            assert "Категория: Ноутбуки" in preview_res["body_html"]

            # 11. Декоратор `@bot_page` и `@register_sitemap_provider` + `/sitemap.xml` + `/<indexnow_key>.txt`
            @bot_page("/landing/{slug}")
            async def custom_landing(slug: str) -> SeoPageData:
                return SeoPageData(
                    title=f"Спецпроект {slug}",
                    description="Кастомный лендинг",
                    body_html=f"<h1>Лендинг {slug}</h1><p>Эксклюзивное предложение</p>",
                )

            @register_sitemap_provider
            async def custom_sitemap_urls() -> list[dict[str, str]]:
                return [{"loc": "/landing/summer-sale", "changefreq": "weekly", "priority": "0.9"}]

            invalidate_sitemap_cache()

            status_landing, _, body_landing, _ = await call_rsgi_http(
                app,
                "GET",
                "/landing/summer-sale",
                headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
            )
            assert status_landing == 200
            assert "<title>Спецпроект summer-sale</title>" in body_landing.decode("utf-8")

            status_sitemap, _, body_sitemap, _ = await call_rsgi_http(
                app,
                "GET",
                "/sitemap.xml",
            )
            sitemap_xml = body_sitemap.decode("utf-8")
            assert status_sitemap == 200
            assert "https://tech.example.com/" in sitemap_xml
            assert "https://tech.example.com/products" in sitemap_xml
            assert f"https://tech.example.com/products/{prod1['id']}" in sitemap_xml
            assert "https://tech.example.com/landing/summer-sale" in sitemap_xml

            # Проверка верификационного файла IndexNow: GET /mysecretindexnowkey123.txt
            status_indexnow, _, body_indexnow, _ = await call_rsgi_http(
                app,
                "GET",
                "/mysecretindexnowkey123.txt",
            )
            assert status_indexnow == 200
            assert body_indexnow.decode("utf-8") == "mysecretindexnowkey123"

            # 12. Проверяем перезагрузку конфигурации из БД (имитируем рестарт сервера)
            configure_seo(site_url="http://localhost:8000", site_name="ResetName")
            assert get_seo_config().site_name == "ResetName"
            async with db.session() as s:
                await load_seo_from_db(s)
            assert get_seo_config().site_name == "TechStore"
            assert get_seo_config().site_url == "https://tech.example.com"

        finally:
            await app.shutdown()


class TestMigrationV210:
    """Проверка миграции БД `migrations/migration_v2_1_0.py`."""

    async def test_migration_upgrade_and_downgrade(self) -> None:
        db = Database("sqlite+aiosqlite:///:memory:")
        try:
            async with db.session() as session:
                await upgrade_v2_1_0(session)
                res = await session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='pf_seo_config'"
                    )
                )
                assert res.scalar_one_or_none() == "pf_seo_config"

                await downgrade_v2_1_0(session)
                res_after = await session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='pf_seo_config'"
                    )
                )
                assert res_after.scalar_one_or_none() is None
        finally:
            await db.close()
