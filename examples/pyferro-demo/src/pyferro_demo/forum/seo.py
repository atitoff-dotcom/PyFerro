"""
Генератор SEO-микроразметки Schema.org (BreadcrumbList, DiscussionForumPosting) и sitemap.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pyferro_demo.forum.models import Message, Topic


async def get_topic_breadcrumbs(
    session: AsyncSession, topic_id: int, base_url: str = "http://localhost:8080"
) -> dict[str, Any]:
    """Строит хлебные крошки Schema.org BreadcrumbList."""
    base_url = base_url.rstrip("/")
    chain: list[Topic] = []
    curr_id: int | None = topic_id
    visited: set[int] = set()

    while curr_id is not None and curr_id not in visited:
        visited.add(curr_id)
        topic = await session.get(Topic, curr_id)
        if not topic:
            break
        chain.append(topic)
        curr_id = topic.parent_id

    chain.reverse()

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
    session: AsyncSession, topic_id: int, base_url: str = "http://localhost:8080"
) -> dict[str, Any] | None:
    """Генерирует микроразметку DiscussionForumPosting для сниппетов поисковиков."""
    base_url = base_url.rstrip("/")
    stmt = (
        select(Topic)
        .where(Topic.id == topic_id)
        .options(selectinload(Topic.messages))
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
        "description": topic.seo_description or topic.title,
        "url": url,
        "datePublished": topic.created_at.isoformat(),
        "dateModified": topic.updated_at.isoformat(),
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/CommentAction",
            "userInteractionCount": len(topic.messages),
        },
    }

    if first_post:
        ld["author"] = {
            "@type": "Person",
            "name": first_post.author_name,
        }
        ld["articleBody"] = first_post.content

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
