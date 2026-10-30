"""
E2E тесты демонстрационного приложения pyferro-demo.
Проверяют интеграцию с ядром PyFerro, работу моделей, RPC и SEO.
"""

from __future__ import annotations

import pytest

from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro_demo.app import create_demo_app


@pytest.fixture
async def app():
    """Создает тестовое демо-приложение в памяти."""
    demo_app = await create_demo_app(db_url="sqlite+aiosqlite:///:memory:")
    yield demo_app
    await demo_app.db.close()


class TestForumE2E:
    @pytest.mark.asyncio
    async def test_list_topics(self, app):
        """Проверяет получение списка тем форума через RPC."""
        session = Session(session_id="s-admin", data=SessionData(user_id=1, username="admin", roles=frozenset(["admin"])))
        topics = await app.router.call("forum.list_topics", session)
        assert isinstance(topics, list)
        assert len(topics) >= 2  # Корневые темы

    @pytest.mark.asyncio
    async def test_get_topic_with_seo(self, app):
        """Проверяет получение топика с JSON-LD разметкой."""
        session = Session(session_id="s-admin", data=SessionData(user_id=1, username="admin", roles=frozenset(["admin"])))
        topic = await app.router.call("forum.get_topic", session, {"slug": "pyferro-2-0-release"})
        assert topic is not None
        assert topic["slug"] == "pyferro-2-0-release"
        assert len(topic["messages"]) >= 1

        # Проверка хлебных крошек
        assert "breadcrumbs" in topic
        assert topic["breadcrumbs"]["@type"] == "BreadcrumbList"

        # Проверка DiscussionForumPosting
        assert "json_ld" in topic
        assert topic["json_ld"]["@type"] == "DiscussionForumPosting"
        assert "headline" in topic["json_ld"]

    @pytest.mark.asyncio
    async def test_create_message(self, app):
        """Проверяет отправку сообщения в тему через RPC."""
        session = Session(session_id="s-user", data=SessionData(user_id=1, username="tester", roles=frozenset(["user"])))
        res = await app.router.call(
            "forum.create_message",
            session,
            {"topic_id": 3, "content": "Тестовое сообщение из E2E теста"},
        )
        assert res["content"] == "Тестовое сообщение из E2E теста"
        assert res["author_name"] == "tester"
