"""
SQLAlchemy-модели таблиц стартеров (строго с префиксом tst_*).
Используют изолированный StarterBase, чтобы не попадать в системный Base.metadata ядра.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class StarterBase(DeclarativeBase):
    """Изолированный базовый класс моделей стартеров."""
    pass


class TstMeta(StarterBase):
    """Служебная таблица версионирования установленных стартеров."""

    __tablename__ = "tst_meta"

    starter_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    installed_version: Mapped[str] = mapped_column(String(50), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)


class TstTopic(StarterBase):
    """Древовидная иерархия разделов и веток форума."""

    __tablename__ = "tst_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tst_topics.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    is_category: Mapped[bool] = mapped_column(Boolean, default=False)
    seo_title: Mapped[str | None] = mapped_column(String(250), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc
    )

    # Отношение к сообщениям
    messages: Mapped[list[TstMessage]] = relationship(
        "TstMessage",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="TstMessage.created_at",
    )


class TstMessage(StarterBase):
    """Сообщения внутри форумной ветки."""

    __tablename__ = "tst_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tst_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)

    # Обратное отношение
    topic: Mapped[TstTopic] = relationship("TstTopic", back_populates="messages")
