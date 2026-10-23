# -*- coding: utf-8 -*-
"""
Модели данных для демонстрационного форума PyFerro Showcase (префикс pf_showcase_...).
Используются для проверки многоуровневого No-Code SEO, связей по внешним ключам
и генерации разметки Schema.org DiscussionForumPosting.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from pyferro.db import Base


class ForumCategory(Base):
    __tablename__ = "pf_showcase_forum_category"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_id = Column(Integer, ForeignKey("pf_showcase_forum_category.id"), nullable=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, default="", nullable=False)
    icon = Column(String(50), default="folder", nullable=False)
    display_order = Column(Integer, default=0, nullable=False)

    class Crud:
        verbose_name = "Категория форума"
        verbose_name_plural = "Категории форума"
        searchable = {"name", "slug", "description"}
        readonly = {"id"}

    def to_dict(self):
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "icon": self.icon,
            "display_order": self.display_order,
        }

class ForumTopic(Base):
    __tablename__ = "pf_showcase_forum_topic"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("pf_showcase_forum_category.id"), nullable=False)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    author_name = Column(String(100), default="Admin", nullable=False)
    views_count = Column(Integer, default=0, nullable=False)
    replies_count = Column(Integer, default=0, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    first_post_text = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class Crud:
        verbose_name = "Ветка форума"
        verbose_name_plural = "Ветки форума"
        searchable = {"title", "slug", "author_name"}
        readonly = {"id", "created_at", "updated_at"}

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "title": self.title,
            "slug": self.slug,
            "author_name": self.author_name,
            "views_count": self.views_count,
            "replies_count": self.replies_count,
            "is_pinned": self.is_pinned,
            "first_post_text": self.first_post_text,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }


class ForumPost(Base):
    __tablename__ = "pf_showcase_forum_post"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("pf_showcase_forum_topic.id"), nullable=False)
    author_name = Column(String(100), default="Пользователь", nullable=False)
    content = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class Crud:
        verbose_name = "Ответ в теме"
        verbose_name_plural = "Ответы в темах"
        searchable = {"author_name", "content"}
        readonly = {"id", "created_at"}

    def to_dict(self):
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "author_name": self.author_name,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


__all__ = [
    "ForumCategory",
    "ForumTopic",
    "ForumPost",
]