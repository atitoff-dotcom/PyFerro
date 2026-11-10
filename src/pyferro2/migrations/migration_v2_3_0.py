"""
Миграция схемы БД для PyFerro v2.3.0 (Автоматическое кеширование, Offline-First и Медиа-кеш IndexedDB).
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("pyferro.migrations")


async def upgrade(session: AsyncSession) -> None:
    """
    Применяет изменения схемы БД для версии 2.3.0:
    1. Создает таблицу `pf_cache_config` для хранения глобальных настроек кеша и эпохи.
    2. Создает таблицу `pf_cache_rules` для хранения правил кеширования по методам.
    """
    logger.info("Applying migration for v2.3.0 (pf_cache_config & pf_cache_rules)...")
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pf_cache_config (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                enabled BOOLEAN DEFAULT 1 NOT NULL,
                liefi_timeout_ms INTEGER DEFAULT 2500 NOT NULL,
                max_media_mb INTEGER DEFAULT 250 NOT NULL,
                max_rpc_entries INTEGER DEFAULT 2000 NOT NULL,
                cache_epoch INTEGER DEFAULT 1 NOT NULL
            );
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pf_cache_rules (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                method_name VARCHAR(128) NOT NULL UNIQUE,
                cache_enabled BOOLEAN DEFAULT 0 NOT NULL,
                strategy VARCHAR(16) DEFAULT 'auto' NOT NULL,
                ttl_sec INTEGER DEFAULT 300 NOT NULL,
                prefetch_media BOOLEAN DEFAULT 0 NOT NULL,
                preload_on_boot BOOLEAN DEFAULT 0 NOT NULL,
                offline_outbox BOOLEAN DEFAULT 0 NOT NULL
            );
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pf_cache_rules_method_name ON pf_cache_rules (method_name);
            """
        )
    )
    await session.commit()


async def downgrade(session: AsyncSession) -> None:
    """
    Откат изменений схемы для версии 2.3.0.
    """
    logger.info("Reverting migration for v2.3.0 (pf_cache_rules & pf_cache_config)...")
    await session.execute(text("DROP TABLE IF EXISTS pf_cache_rules"))
    await session.execute(text("DROP TABLE IF EXISTS pf_cache_config"))
    await session.commit()
