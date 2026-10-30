"""
Генератор эталонной SEO-микроразметки и карты сайта для форума (Schema.org / JSON-LD / Sitemap).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pyferro2.starters.models import TstMessage, TstTopic


async def get_topic_breadcrumbs(
    session: AsyncSession, topic_id: int, base_url: str = "https://example.com"
) -> dict[str, Any]:
    """
    Рекурсивно строит цепочку хлебных крошек от корня дерева до текущего топика
    и формирует валидный JSON-LD блок Schema.org `BreadcrumbList`.
    """
    base_url = base_url.rstrip("/")
    chain: list[TstTopic] = []

    curr_id: int | None = topic_id
    # Защита от бесконечного цикла на случай битых ссылок
    visited: set[int] = set()

    while curr_id is not None and curr_id not in visited:
        visited.add(curr_id)
        topic = await session.get(TstTopic, curr_id)
        if not topic:
            break
        chain.append(topic)
        curr_id = topic.parent_id

    # Разворачиваем: от корня к текущему топику
    chain.reverse()

    # Собираем путь для ЧПУ
    path_segments: list[str] = []
    items: list[dict[str, Any]] = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Форум",
            "item": f"{base_url}/forum",
        }
    ]

    for idx, t in enumerate(chain, start=2):
        path_segments.append(t.slug)
        full_url = f"{base_url}/forum/{'/'.join(path_segments)}"
        items.append(
            {
                "@type": "ListItem",
                "position": idx,
                "name": t.title,
                "item": full_url,
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }


async def get_topic_discussion_posting(
    session: AsyncSession, topic_id: int, base_url: str = "https://example.com"
) -> dict[str, Any] | None:
    """
    Генерирует специализированную микроразметку `DiscussionForumPosting`
    для поисковых сниппетов Google и Яндекса.
    """
    base_url = base_url.rstrip("/")

    stmt = (
        select(TstTopic)
        .where(TstTopic.id == topic_id)
        .options(selectinload(TstTopic.messages))
    )
    result = await session.execute(stmt)
    topic = result.scalar_one_or_none()

    if not topic:
        return None

    messages = sorted(topic.messages, key=lambda m: m.created_at)
    first_post = messages[0] if messages else None
    replies = messages[1:] if len(messages) > 1 else []

    url = f"{base_url}/forum/{topic.slug}"

    ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "DiscussionForumPosting",
        "headline": topic.seo_title or topic.title,
        "description": topic.seo_description or (first_post.content[:200] if first_post else ""),
        "url": url,
        "datePublished": (first_post.created_at if first_post else topic.created_at).isoformat(),
        "dateModified": topic.updated_at.isoformat(),
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/CommentAction",
            "userInteractionCount": len(replies),
        },
    }

    if first_post:
        ld["author"] = {
            "@type": "Person",
            "name": first_post.author_name,
        }
        ld["text"] = first_post.content

    if replies:
        ld["comment"] = [
            {
                "@type": "Comment",
                "text": rep.content,
                "dateCreated": rep.created_at.isoformat(),
                "author": {
                    "@type": "Person",
                    "name": rep.author_name,
                },
            }
            for rep in replies
        ]

    return ld


async def get_forum_sitemap(
    session: AsyncSession, base_url: str = "https://example.com"
) -> list[dict[str, Any]]:
    """
    Строит список URL для `sitemap.xml` с вычислением динамического `lastmod`
    на основе самого свежего сообщения в каждой теме.
    """
    base_url = base_url.rstrip("/")

    # Выбираем топики и максимальную дату сообщения
    stmt = (
        select(
            TstTopic.id,
            TstTopic.slug,
            TstTopic.is_category,
            TstTopic.updated_at,
            func.max(TstMessage.created_at).label("last_message_at"),
        )
        .outerjoin(TstMessage, TstMessage.topic_id == TstTopic.id)
        .group_by(TstTopic.id)
    )

    result = await session.execute(stmt)
    rows = result.all()

    sitemap_items: list[dict[str, Any]] = [
        {
            "loc": f"{base_url}/forum",
            "changefreq": "daily",
            "priority": "0.9",
        }
    ]

    for row in rows:
        lastmod_dt = row.last_message_at or row.updated_at
        sitemap_items.append(
            {
                "loc": f"{base_url}/forum/{row.slug}",
                "lastmod": lastmod_dt.strftime("%Y-%m-%d"),
                "changefreq": "daily" if not row.is_category else "weekly",
                "priority": "0.8" if not row.is_category else "0.6",
            }
        )

    return sitemap_items
