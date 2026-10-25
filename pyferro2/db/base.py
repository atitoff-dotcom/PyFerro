"""
Базовые классы ORM SQLAlchemy 2.0 для PyFerro 2.0.

Разделение ответственности:
- `Base` — чистый фундамент с первичным ключом `id` (используется для системных
  и справочных таблиц, которым не нужны лишние служебные колонки).
- `RowSecureModel` — базовый класс для бизнес-сущностей, где требуется
  построчное разграничение доступа («редактировать только свои записи» по `creator_id`).
"""

from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    """Возвращает текущее время в UTC."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """
    Чистый базовый класс для всех моделей SQLAlchemy 2.0 в PyFerro 2.0.
    Определяет только стандартный автоинкрементный первичный ключ `id`.
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class RowSecureModel(Base):
    """
    Базовый класс для прикладных таблиц с поддержкой владельца записи (`creator_id`)
    и временных меток создания/обновления.
    """

    __abstract__ = True

    creator_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )
