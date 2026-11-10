"""
Управление асинхронным подключением к базе данных (`Database`) и автоматическим трекингом таблиц для кеширования.

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
from sqlalchemy.orm import Session as SyncSession

from pyferro2.db.base import Base

DEFAULT_DB_URL = "sqlite+aiosqlite:///pyferro2.db"


def _extract_from_clause_tables(clause: Any, out: set[str]) -> None:
    """Рекурсивно извлекает имена физических таблиц из объектов Table / Join / Alias SQLAlchemy."""
    if clause is None:
        return
    name = getattr(clause, "name", None)
    if isinstance(name, str) and name and not hasattr(clause, "left"):
        orig = getattr(clause, "original", None)
        orig_name = getattr(orig, "name", None)
        out.add(orig_name if isinstance(orig_name, str) and orig_name else name)
    for attr in ("left", "right", "element", "selectable"):
        sub = getattr(clause, attr, None)
        if sub is not None and sub is not clause:
            _extract_from_clause_tables(sub, out)


def _extract_statement_tables(orm_execute_state: Any) -> set[str]:
    """Извлекает имена всех задействованных таблиц из ORM/Core-выражения SQLAlchemy."""
    tables: set[str] = set()
    stmt = getattr(orm_execute_state, "statement", None)
    if stmt is not None:
        tbl = getattr(stmt, "table", None)
        if tbl is not None:
            _extract_from_clause_tables(tbl, tables)
        if hasattr(stmt, "get_final_froms"):
            froms = stmt.get_final_froms()
        else:
            froms = getattr(stmt, "froms", None)
        if froms:
            for f in froms:
                _extract_from_clause_tables(f, tables)
    bind_args = getattr(orm_execute_state, "bind_arguments", None)
    if isinstance(bind_args, dict):
        mapper = bind_args.get("mapper")
        if mapper is not None:
            persist = getattr(mapper, "persist_selectable", None)
            _extract_from_clause_tables(persist, tables)
    return tables


@event.listens_for(SyncSession, "do_orm_execute")
def _on_session_orm_execute(orm_execute_state: Any) -> None:
    if getattr(orm_execute_state, "is_select", False):
        from pyferro2.cache.manager import _active_table_tracker

        if _active_table_tracker.get() is not None:
            from pyferro2.cache.manager import record_read_table

            for tbl in _extract_statement_tables(orm_execute_state):
                record_read_table(tbl)
    elif (
        getattr(orm_execute_state, "is_insert", False)
        or getattr(orm_execute_state, "is_update", False)
        or getattr(orm_execute_state, "is_delete", False)
    ):
        mutated = _extract_statement_tables(orm_execute_state)
        if mutated:
            sess = orm_execute_state.session
            sess.info.setdefault("_pf_mutated_tables", set()).update(mutated)


@event.listens_for(SyncSession, "after_flush")
def _on_session_after_flush(session: SyncSession, _flush_context: Any) -> None:
    mutated: set[str] = session.info.setdefault("_pf_mutated_tables", set())
    for group in (session.new, session.dirty, session.deleted):
        for obj in group:
            tbl = getattr(obj, "__tablename__", None)
            if isinstance(tbl, str) and tbl:
                mutated.add(tbl)


@event.listens_for(SyncSession, "after_commit")
def _on_session_after_commit(session: SyncSession) -> None:
    mutated: set[str] | None = session.info.pop("_pf_mutated_tables", None)
    if mutated:
        from pyferro2.cache.manager import cache_manager

        cache_manager.invalidate_tables(mutated)


@event.listens_for(SyncSession, "after_rollback")
def _on_session_after_rollback(session: SyncSession) -> None:
    session.info.pop("_pf_mutated_tables", None)


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
