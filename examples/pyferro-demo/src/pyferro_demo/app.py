"""
Фабрика демонстрационного приложения PyFerro Demo.
"""

from __future__ import annotations

from pathlib import Path

from pyferro2.db import Database
from pyferro2.server import PyFerroApp
from pyferro_demo.forum.models import ForumBase
from pyferro_demo.forum.rpc import register_forum_rpc
from pyferro_demo.forum.seeder import seed_forum_data


async def create_demo_app(
    db_url: str = "sqlite+aiosqlite:///demo.db",
    secret_key: str = "pyferro-demo-secret-key-32-chars-long!",
) -> PyFerroApp:
    """
    Создает и настраивает экземпляр PyFerroApp с демонстрационным форумом.
    """
    db = Database(db_url)
    # Создаем таблицы ядра PyFerro (pf_*)
    await db.create_tables()

    # Создаем таблицы демонстрационного форума в той же изолированной demo.db
    async with db.engine.begin() as conn:
        await conn.run_sync(ForumBase.metadata.create_all)

    # Инициализируем сид-данные форума
    async with db.session() as session:
        await seed_forum_data(session)

    # Создаем приложение PyFerro
    app = PyFerroApp(
        db=db,
        secret_key=secret_key,
    )

    # Регистрируем RPC-методы форума
    register_forum_rpc(app.router, db)

    return app
