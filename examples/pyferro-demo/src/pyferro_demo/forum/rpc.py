"""
JSON-RPC 2.0 интерфейс форума (forum.*).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pyferro2.core.session_data import SessionData
from pyferro2.db.engine import Database
from pyferro2.rpc.router import RpcRouter
from pyferro_demo.forum.models import Message, Topic
from pyferro_demo.forum.seo import get_topic_breadcrumbs, get_topic_discussion_posting


def register_forum_rpc(router: RpcRouter, db: Database) -> None:
    """Регистрирует методы `forum.*` в RPC-роутере PyFerro."""

    class forum:
        @router.rpc_method(public=True)
        async def list_topics(
            session_data: SessionData, parent_id: int | None = None
        ) -> list[dict[str, Any]]:
            """Возвращает список тем форума."""
            async with db.session() as session:
                stmt = select(Topic).where(Topic.parent_id == parent_id)
                res = await session.execute(stmt)
                topics = res.scalars().all()
                return [
                    {
                        "id": t.id,
                        "parent_id": t.parent_id,
                        "title": t.title,
                        "slug": t.slug,
                        "is_category": t.is_category,
                        "seo_title": t.seo_title,
                        "seo_description": t.seo_description,
                        "created_at": t.created_at.isoformat(),
                    }
                    for t in topics
                ]

        @router.rpc_method(public=True)
        async def get_topic(
            session_data: SessionData, slug: str
        ) -> dict[str, Any] | None:
            """Возвращает тему и сообщения по slug."""
            async with db.session() as session:
                stmt = (
                    select(Topic)
                    .where(Topic.slug == slug)
                    .options(selectinload(Topic.messages))
                )
                res = await session.execute(stmt)
                topic = res.scalar_one_or_none()
                if not topic:
                    return None

                breadcrumbs = await get_topic_breadcrumbs(session, topic.id)
                discussion_ld = await get_topic_discussion_posting(session, topic.id)

                return {
                    "id": topic.id,
                    "title": topic.title,
                    "slug": topic.slug,
                    "is_category": topic.is_category,
                    "seo_title": topic.seo_title,
                    "seo_description": topic.seo_description,
                    "breadcrumbs": breadcrumbs,
                    "json_ld": discussion_ld,
                    "messages": [
                        {
                            "id": m.id,
                            "author_name": m.author_name,
                            "content": m.content,
                            "created_at": m.created_at.isoformat(),
                        }
                        for m in topic.messages
                    ],
                }

        @router.rpc_method(role=["user", "admin"])
        async def create_message(
            session_data: SessionData,
            topic_id: int,
            content: str,
            author_name: str | None = None,
        ) -> dict[str, Any]:
            """Создает новое сообщение в теме (доступно авторизованным пользователям)."""
            name = author_name or session_data.username or "Пользователь"
            async with db.session() as session:
                msg = Message(
                    topic_id=topic_id,
                    author_name=name,
                    content=content,
                )
                session.add(msg)
                await session.commit()
                return {
                    "id": msg.id,
                    "topic_id": msg.topic_id,
                    "author_name": msg.author_name,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                }
