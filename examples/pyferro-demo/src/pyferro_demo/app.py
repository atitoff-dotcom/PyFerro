"""
Демонстрационное приложение PyFerro Demo (Форум, SEO, JSON-RPC).
Обычное стандартное приложение фреймворка.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pyferro2.core.session_data import SessionData
from pyferro2.db import Database
from pyferro2.server import PyFerroApp
from pyferro_demo.forum.models import Message, Topic
from pyferro_demo.forum.rpc import register_forum_rpc
from pyferro_demo.forum.seeder import seed_forum_data

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FORUM_HTML_PATH = _TEMPLATES_DIR / "forum.html"


class DemoApp(PyFerroApp):
    """Демонстрационное приложение на базе PyFerro."""

    async def startup(self) -> None:
        await super().startup()
        async with self.db.session() as session:
            await seed_forum_data(session)

    async def _handle_http(
        self,
        scope: Any,
        proto: Any,
        session_data: SessionData,
    ) -> None:
        path = getattr(scope, "path", "/")
        method = getattr(scope, "method", "GET").upper()

        # Отдаем витрину форума на главной странице и путях /forum
        if method == "GET" and (path == "/" or path == "/forum" or path.startswith("/forum/")):
            if _FORUM_HTML_PATH.exists():
                html = _FORUM_HTML_PATH.read_text(encoding="utf-8")
                proto.response_str(
                    200,
                    [("content-type", "text/html; charset=utf-8")],
                    html,
                )
                return

        await super()._handle_http(scope, proto, session_data)


db_path = os.environ.get("PYFERRO_DEMO_DB", "demo.db")
db = Database(f"sqlite+aiosqlite:///{db_path}")

app = DemoApp(
    db=db,
    secret_key="pyferro-demo-secret-key-32-chars-long!",
)

register_forum_rpc(app.router, db)
