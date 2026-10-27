"""
Миграция схемы БД для PyFerro v2.1.0 (подсистема SEO, Dynamic Rendering и Site Tree).
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("pyferro.migrations")


async def upgrade(session: AsyncSession) -> None:
    """
    Применяет изменения схемы БД для версии 2.1.0:
    создает таблицу `pf_seo_config` для хранения настроек SEO и живого дерева сайта.
    """
    logger.info("Applying migration for v2.1.0 (pf_seo_config)...")
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pf_seo_config (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                site_url VARCHAR(255) DEFAULT 'http://localhost:8080' NOT NULL,
                site_name VARCHAR(255) DEFAULT 'PyFerro 2.0 Application' NOT NULL,
                default_title VARCHAR(255) DEFAULT 'PyFerro 2.0 Application' NOT NULL,
                default_description TEXT DEFAULT 'Современное реактивное веб-приложение на базе PyFerro 2.0' NOT NULL,
                default_og_image VARCHAR(512) DEFAULT '' NOT NULL,
                default_lang VARCHAR(16) DEFAULT 'ru' NOT NULL,
                indexnow_key VARCHAR(128) DEFAULT '' NOT NULL,
                sitemap_ttl INTEGER DEFAULT 3600 NOT NULL,
                tree_json TEXT DEFAULT '{}' NOT NULL,
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL
            )
            """
        )
    )
    await session.commit()


async def downgrade(session: AsyncSession) -> None:
    """
    Откат изменений схемы для версии 2.1.0.
    """
    logger.info("Reverting migration for v2.1.0 (pf_seo_config)...")
    await session.execute(text("DROP TABLE IF EXISTS pf_seo_config"))
    await session.commit()
