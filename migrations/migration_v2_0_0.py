"""
Миграция схемы БД для PyFerro v2.0.0.
Сгенерировано автоматически релиз-скриптом.
"""

from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger("pyferro.migrations")


async def upgrade(session: AsyncSession) -> None:
    """
    Применяет изменения схемы или данных для версии 2.0.0.
    """
    logger.info("Applying migration for v2.0.0...")
    # TODO: Добавьте DDL или миграционные SQL-запросы здесь
    await session.commit()


async def downgrade(session: AsyncSession) -> None:
    """
    Откат изменений схемы для версии 2.0.0.
    """
    logger.info("Reverting migration for v2.0.0...")
    # TODO: Добавьте откат DDL запросов здесь
    await session.commit()
