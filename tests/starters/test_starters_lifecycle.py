"""
Тесты полного жизненного цикла стартеров и тестовых приложений (/pyferro2/starters/).

Проверяет:
1. Список стартеров и определение статуса до установки.
2. Скачивание/установку, создание изолированных таблиц `tst_*` и сидинг 10 тем.
3. Защиту от конфликтов при повторной установке (код 409) и поддержку `overwrite=True`.
4. Генерацию SEO-разметки: BreadcrumbList (JSON-LD), DiscussionForumPosting и sitemap.xml.
5. RBAC-авторизацию RPC-методов (доступ только для `admin` и `adm_starters`).
6. Безопасную деинсталляцию и очистку базы (`DROP TABLE tst_*`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from pyferro2.core.constants import JsonRpcErrorCode, USER_ROLE, admRole
from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro2.db.engine import Database
from pyferro2.rpc.errors import ForbiddenError, RpcError, UnauthorizedError
from pyferro2.rpc.router import RpcRouter
from pyferro2.starters.manager import StartersManager
from pyferro2.starters.models import TstMessage, TstMeta, TstTopic
from pyferro2.starters.rpc import register_starters_rpc


@pytest.fixture
async def db() -> Database:
    """Создает изолированную тестовую базу данных в памяти."""
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
def manager(db: Database, tmp_path: Path) -> StartersManager:
    """Создает StartersManager с изолированной временной папкой приложений."""
    return StartersManager(db=db, apps_dir=tmp_path / "apps")


class TestStartersLifecycle:
    """Набор тестов логики StartersManager."""

    async def test_initial_catalog_and_status(self, manager: StartersManager) -> None:
        """До установки стартер должен определяться как не установленный."""
        starters = await manager.list_starters()
        assert len(starters) >= 1

        seo_starter = next(s for s in starters if s["id"] == "starter-forum-seo")
        assert seo_starter["installed"] is False
        assert seo_starter["installed_version"] is None
        assert seo_starter["existing_tables"] == []
        assert "tst_topics" in seo_starter["tables"]
        assert "tst_messages" in seo_starter["tables"]

    async def test_install_and_seed_forum(self, manager: StartersManager, db: Database) -> None:
        """Установка стартера должна создавать таблицы tst_* и наполнять их 10 темами."""
        res = await manager.install("starter-forum-seo")
        assert res["ok"] is True
        assert res["seed_stats"]["topics"] == 10
        assert res["seed_stats"]["messages"] > 0

        # Проверяем записи в БД
        async with db.session() as session:
            topics_res = await session.execute(select(TstTopic))
            topics = topics_res.scalars().all()
            assert len(topics) == 10

            # Проверяем вложенность: корневая категория "general" -> "news" -> "pyferro-2-0-release"
            news_topic = next(t for t in topics if t.slug == "news")
            assert news_topic.parent_id is not None

            sub_topic = next(t for t in topics if t.slug == "pyferro-2-0-release")
            assert sub_topic.parent_id == news_topic.id

            # Проверяем сообщения
            msgs_res = await session.execute(
                select(TstMessage).where(TstMessage.topic_id == sub_topic.id)
            )
            msgs = msgs_res.scalars().all()
            assert len(msgs) >= 2

            # Проверяем tst_meta
            meta = await session.get(TstMeta, "starter-forum-seo")
            assert meta is not None
            assert meta.installed_version == manager.current_version

        # Проверяем обновленный статус в каталоге
        updated_list = await manager.list_starters()
        seo_starter = next(s for s in updated_list if s["id"] == "starter-forum-seo")
        assert seo_starter["installed"] is True
        assert seo_starter["installed_version"] == manager.current_version
        assert "tst_topics" in seo_starter["existing_tables"]

    async def test_conflict_detection_and_overwrite(self, manager: StartersManager) -> None:
        """Повторная установка без overwrite должна вызывать RpcError 409, а с overwrite=True — перезаписывать."""
        await manager.install("starter-forum-seo")

        # 1. Попытка установить поверх без overwrite
        with pytest.raises(RpcError) as exc_info:
            await manager.install("starter-forum-seo", overwrite=False)

        assert exc_info.value.code == 409
        assert "Конфликт таблиц стартера" in exc_info.value.message

        # 2. Установка с overwrite=True (безопасный пересид)
        res = await manager.install("starter-forum-seo", overwrite=True)
        assert res["ok"] is True
        assert res["seed_stats"]["topics"] == 10

    async def test_seo_preview_generation(self, manager: StartersManager) -> None:
        """Проверяет генерацию Schema.org JSON-LD и sitemap."""
        await manager.install("starter-forum-seo")

        preview = await manager.get_seo_preview(
            "starter-forum-seo", slug="pyferro-2-0-release"
        )
        assert preview["topic"]["slug"] == "pyferro-2-0-release"

        # Проверяем BreadcrumbList
        bc = preview["breadcrumbs_json_ld"]
        assert bc["@type"] == "BreadcrumbList"
        assert len(bc["itemListElement"]) >= 3  # Форум -> Общие -> Новости -> Релиз
        assert bc["itemListElement"][0]["name"] == "Форум"

        # Проверяем DiscussionForumPosting
        disc = preview["discussion_json_ld"]
        assert disc["@type"] == "DiscussionForumPosting"
        assert "author" in disc
        assert disc["interactionStatistic"]["userInteractionCount"] >= 1
        assert "comment" in disc

        # Проверяем sitemap
        assert preview["total_sitemap_urls"] >= 10
        assert len(preview["sitemap_sample"]) <= 5
        assert any(item["loc"].endswith("/forum/pyferro-2-0-release") for item in preview["sitemap_sample"])

    async def test_uninstall_clean(self, manager: StartersManager, db: Database) -> None:
        """Деинсталляция должна полностью дропать таблицы tst_* и очищать базу."""
        await manager.install("starter-forum-seo")

        del_res = await manager.uninstall("starter-forum-seo")
        assert del_res["ok"] is True
        assert "tst_topics" in del_res["dropped_tables"]

        # Проверяем физическое отсутствие таблиц в БД
        existing = await manager.get_existing_db_tables()
        assert "tst_topics" not in existing
        assert "tst_messages" not in existing
        assert "tst_meta" not in existing


class TestStartersRpcSecurity:
    """Проверка прав доступа к RPC-методам стартеров."""

    async def test_rbac_permissions(self, db: Database, tmp_path: Path) -> None:
        router = RpcRouter()
        mgr = StartersManager(db=db, apps_dir=tmp_path / "apps")
        register_starters_rpc(router, mgr)

        admin_session = Session(
            session_id="s1",
            data=SessionData(
                user_id=1,
                username="admin",
                roles=frozenset({admRole.admin.value}),
            ),
        )
        starters_mgr_session = Session(
            session_id="s2",
            data=SessionData(
                user_id=2,
                username="starter_admin",
                roles=frozenset({admRole.adm_starters.value}),
            ),
        )
        user_session = Session(
            session_id="s3",
            data=SessionData(
                user_id=3,
                username="regular_user",
                roles=frozenset({USER_ROLE}),
            ),
        )
        guest_session = Session(
            session_id="s4",
            data=SessionData.guest(frozenset()),
        )

        # 1. Администраторы имеют доступ
        starters_admin = await router.call("starters.list", admin_session)
        assert isinstance(starters_admin, list)

        starters_sub = await router.call("starters.list", starters_mgr_session)
        assert isinstance(starters_sub, list)

        # 2. Обычный пользователь получает 403 Forbidden
        with pytest.raises(ForbiddenError) as exc_user:
            await router.call("starters.list", user_session)
        assert exc_user.value.code == JsonRpcErrorCode.FORBIDDEN

        # 3. Гость получает 401 Unauthorized
        with pytest.raises(UnauthorizedError) as exc_guest:
            await router.call("starters.list", guest_session)
        assert exc_guest.value.code == JsonRpcErrorCode.UNAUTHORIZED
