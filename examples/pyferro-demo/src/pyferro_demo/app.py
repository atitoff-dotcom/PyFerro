"""
Демонстрационное приложение PyFerro Demo (Форум, SEO, JSON-RPC).
Обычное стандартное приложение фреймворка.
"""

from __future__ import annotations

import os

from pyferro2.db import Database
from pyferro2.server import PyFerroApp
from pyferro_demo.forum.models import Message, Topic
from pyferro_demo.forum.rpc import register_forum_rpc
from pyferro_demo.forum.seeder import seed_forum_data


class DemoApp(PyFerroApp):
    """Демонстрационное приложение на базе PyFerro."""

    async def startup(self) -> None:
        await super().startup()
        async with self.db.session() as session:
            await seed_forum_data(session)


db_path = os.environ.get("PYFERRO_DEMO_DB", "demo.db")
db = Database(f"sqlite+aiosqlite:///{db_path}")

app = DemoApp(
    db=db,
    secret_key="pyferro-demo-secret-key-32-chars-long!",
)

register_forum_rpc(app.router, db)
