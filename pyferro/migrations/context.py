# -*- coding: utf-8 -*-
"""
Контекст выполнения миграций PyFerro (MigrationContext).
Предоставляет кросс-СУБД абстракции для безопасных DDL/DML операций и нативного бэкапа.
"""

from __future__ import annotations
import os
import glob
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncConnection

from pyferro.core.logger import logger


class MigrationContext:
    """Асинхронный контекст для выполнения шагов миграции."""

    def __init__(
        self,
        conn: AsyncConnection,
        progress_callback: Optional[Callable[[int, str], Any]] = None,
    ):
        self.conn = conn
        self.progress_callback = progress_callback
        self.dialect_name: str = conn.dialect.name

    async def report_progress(self, percent: int, message: str) -> None:
        """Информирует о прогрессе выполнения текущего шага миграции."""
        logger.info(f"[Migration] [{percent}%] {message}")
        if self.progress_callback:
            try:
                res = self.progress_callback(percent, message)
                if hasattr(res, "__await__"):
                    await res
            except Exception as e:
                logger.warning(f"[Migration] Ошибка в progress_callback: {e}")

    # --- ИНСПЕКЦИЯ СХЕМЫ (КРОСС-СУБД) ---

    async def has_table(self, table_name: str) -> bool:
        """Проверяет наличие таблицы в базе данных."""
        return await self.conn.run_sync(
            lambda sync_conn: inspect(sync_conn).has_table(table_name)
        )

    async def get_table_names(self) -> List[str]:
        """Возвращает список всех существующих таблиц."""
        return await self.conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )

    async def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Возвращает список словарей с описанием колонок таблицы."""
        if not await self.has_table(table_name):
            return []
        return await self.conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns(table_name)
        )

    async def has_column(self, table_name: str, column_name: str) -> bool:
        """Проверяет наличие конкретной колонки в таблице."""
        cols = await self.get_columns(table_name)
        return any(c.get("name") == column_name for c in cols)

    async def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Возвращает список индексов для указанной таблицы."""
        if not await self.has_table(table_name):
            return []
        return await self.conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes(table_name)
        )

    async def has_index(self, name: str, table_name: Optional[str] = None) -> bool:
        """Проверяет наличие индекса по имени."""
        if table_name:
            indexes = await self.get_indexes(table_name)
            return any(idx.get("name") == name for idx in indexes)
        tables = await self.get_table_names()
        for t in tables:
            indexes = await self.get_indexes(t)
            if any(idx.get("name") == name for idx in indexes):
                return True
        return False

    # --- DDL ОПЕРАЦИИ (КРОСС-СУБД) ---

    async def add_column(
        self,
        table_name: str,
        column_name: str,
        col_type: str,
        default: Any = None,
        nullable: bool = True,
    ) -> None:
        """Безопасно добавляет колонку в существующую таблицу."""
        if await self.has_column(table_name, column_name):
            logger.debug(f"[Migration] Колонка {table_name}.{column_name} уже существует, пропускаем.")
            return

        default_clause = ""
        if default is not None:
            if isinstance(default, str) and not default.upper().startswith(("CURRENT_", "NULL")):
                default_clause = f" DEFAULT '{default}'"
            else:
                default_clause = f" DEFAULT {default}"

        null_clause = " NULL" if nullable else " NOT NULL"
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {col_type}{default_clause}{null_clause}"
        await self.execute_raw(sql)

    async def drop_column(self, table_name: str, column_name: str) -> None:
        """Удаляет колонку из таблицы (если колонка существует)."""
        if not await self.has_column(table_name, column_name):
            return
        sql = f"ALTER TABLE {table_name} DROP COLUMN {column_name}"
        await self.execute_raw(sql)

    async def rename_table(self, old_name: str, new_name: str) -> None:
        """Переименовывает таблицу."""
        if not await self.has_table(old_name):
            return
        sql = f"ALTER TABLE {old_name} RENAME TO {new_name}"
        await self.execute_raw(sql)

    async def create_index(
        self,
        name: str,
        table_name: str,
        columns: List[str],
        unique: bool = False,
        if_not_exists: bool = True,
    ) -> None:
        """Создает индекс по колонкам."""
        cols_str = ", ".join(columns)
        unique_clause = "UNIQUE " if unique else ""
        exists_clause = "IF NOT EXISTS " if if_not_exists else ""
        sql = f"CREATE {unique_clause}INDEX {exists_clause}{name} ON {table_name} ({cols_str})"
        await self.execute_raw(sql)

    async def drop_index(self, name: str, if_exists: bool = True) -> None:
        """Удаляет индекс."""
        exists_clause = "IF EXISTS " if if_exists else ""
        sql = f"DROP INDEX {exists_clause}{name}"
        await self.execute_raw(sql)

    async def execute_raw(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Выполняет произвольный SQL-запрос в рамках текущей транзакции."""
        return await self.conn.execute(text(sql), params or {})

    # --- РЕЗЕРВНОЕ КОПИРОВАНИЕ (ZERO-DATA-LOSS) ---

    async def create_sqlite_snapshot(
        self,
        backup_dir: str = ".ferro_snapshots",
        max_backups: int = 5,
    ) -> Optional[str]:
        """
        Создает нативный снимок базы SQLite через VACUUM INTO без блокировки читателей.
        Автоматически ротирует старые копии.
        """
        if self.dialect_name != "sqlite":
            return None

        # Проверяем, что это не база в памяти (:memory:)
        db_file = None
        if hasattr(self.conn.sync_connection, "dbapi_connection"):
            # Попытка получить имя файла из соединения
            pass

        try:
            # Создаем директорию под бэкапы
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"snapshot_{ts}.db"
            snapshot_path = os.path.join(backup_dir, snapshot_filename)
            normalized_path = snapshot_path.replace("\\", "/")

            await self.conn.execute(text(f"VACUUM INTO '{normalized_path}'"))
            logger.info(f"[Migration] Создан резервный снимок SQLite: {snapshot_path}")

            # Ротация: оставляем только последние max_backups
            pattern = os.path.join(backup_dir, "snapshot_*.db")
            existing_backups = sorted(glob.glob(pattern), key=os.path.getmtime)
            if len(existing_backups) > max_backups:
                to_delete = existing_backups[:-max_backups]
                for old_f in to_delete:
                    try:
                        os.remove(old_f)
                        logger.debug(f"[Migration] Ротация старого бэкапа: {old_f}")
                    except Exception as ex:
                        logger.warning(f"[Migration] Не удалось удалить старый бэкап {old_f}: {ex}")

            return snapshot_path
        except Exception as e:
            # Если база :memory: или VACUUM INTO не поддерживается, логируем предупреждение
            logger.warning(f"[Migration] Не удалось создать снимок через VACUUM INTO (возможно :memory:): {e}")
            return None