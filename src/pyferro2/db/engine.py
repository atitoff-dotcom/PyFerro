"""
Управление асинхронным подключением к базе данных (`Database`).

По умолчанию использует базу `sqlite+aiosqlite:///pyferro2.db`
и автоматически включает для SQLite:
- `PRAGMA foreign_keys=ON` (каскадные внешние ключи)
- `PRAGMA journal_mode=WAL` (конкурентное чтение и запись без блокировок)
- `PRAGMA synchronous=NORMAL` (высокая скорость записи при сохранении надежности WAL)
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pyferro2.db.base import Base

DEFAULT_DB_URL = "sqlite+aiosqlite:///pyferro2.db"


class Database:
    """
    Понятный менеджер подключения к БД и фабрики сессий.
    """

    __slots__ = ("url", "engine", "session_factory")

    def __init__(self, url: str = DEFAULT_DB_URL, **engine_kwargs: Any) -> None:
        self.url: str = url
        self.engine: AsyncEngine = create_async_engine(url, **engine_kwargs)

        if url.startswith("sqlite"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def _configure_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Открывает асинхронную сессию БД и гарантированно закрывает её по завершении блока."""
        async with self.session_factory() as db_session:
            yield db_session

    async def create_tables(self) -> None:
        """Создает все зарегистрированные в `Base.metadata` таблицы (если они еще не созданы)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Корректно закрывает пул соединений движка."""
        await self.engine.dispose()
