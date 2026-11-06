"""
Миграция схемы БД для PyFerro v2.2.0 (OAuth, SSO, внешняя аутентификация и системная конфигурация).
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("pyferro.migrations")


async def upgrade(session: AsyncSession) -> None:
    """
    Применяет изменения схемы БД для версии 2.2.0:
    1. Создает таблицу `pf_auth_config` для хранения настроек провайдеров, SMTP и брендинга.
    2. Создает таблицу `pf_auth_oauth` для связывания внешних профилей с пользователями.
    """
    logger.info("Applying migration for v2.2.0 (pf_auth_config & pf_auth_oauth)...")
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pf_auth_config (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(64) NOT NULL UNIQUE,
                is_enabled BOOLEAN DEFAULT 1 NOT NULL,
                config_json TEXT DEFAULT '{}' NOT NULL,
                updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL
            );
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pf_auth_oauth (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider VARCHAR(32) NOT NULL,
                provider_user_id VARCHAR(128) NOT NULL,
                data_json TEXT DEFAULT '{}' NOT NULL,
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                CONSTRAINT fk_pf_auth_oauth_user FOREIGN KEY (user_id) REFERENCES pf_auth_user(id) ON DELETE CASCADE,
                CONSTRAINT uq_pf_auth_oauth_provider_user UNIQUE (provider, provider_user_id)
            );
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pf_auth_config_key ON pf_auth_config (key);
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pf_auth_oauth_user_id ON pf_auth_oauth (user_id);
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pf_auth_oauth_provider ON pf_auth_oauth (provider);
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pf_auth_oauth_provider_user_id ON pf_auth_oauth (provider_user_id);
            """
        )
    )
    await session.commit()


async def downgrade(session: AsyncSession) -> None:
    """
    Откат изменений схемы для версии 2.2.0.
    """
    logger.info("Reverting migration for v2.2.0 (pf_auth_oauth & pf_auth_config)...")
    await session.execute(text("DROP TABLE IF EXISTS pf_auth_oauth"))
    await session.execute(text("DROP TABLE IF EXISTS pf_auth_config"))
    await session.commit()
