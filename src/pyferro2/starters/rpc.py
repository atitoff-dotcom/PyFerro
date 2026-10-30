"""
JSON-RPC 2.0 интерфейс управления стартовыми приложениями (/pyferro_admin/starters).
Доступ разрешен системным ролям `admin` и `adm_starters`.
"""

from __future__ import annotations

from typing import Any

from pyferro2.core.constants import admRole
from pyferro2.core.session_data import SessionData
from pyferro2.rpc.router import RpcRouter
from pyferro2.starters.manager import StartersManager


def register_starters_rpc(
    router: RpcRouter,
    manager: StartersManager,
) -> None:
    """Регистрирует методы `starters.*` в RPC-роутере."""

    class starters:
        @router.rpc_method(role=[admRole.adm_starters])
        async def list(session_data: SessionData) -> list[dict[str, Any]]:
            """Возвращает каталог всех стартеров с их текущим статусом установки и проверкой версий."""
            return await manager.list_starters()

        @router.rpc_method(role=[admRole.adm_starters])
        async def install(
            session_data: SessionData,
            starter_id: str,
            overwrite: bool = False,
        ) -> dict[str, Any]:
            """
            Устанавливает стартер из GitHub релиза, создаёт таблицы tst_* и наполняет сид-данными.
            При наличии существующих таблиц и overwrite=False вернет ошибку конфликта (код 409).
            """
            return await manager.install(starter_id=starter_id, overwrite=overwrite)

        @router.rpc_method(role=[admRole.adm_starters])
        async def uninstall(
            session_data: SessionData,
            starter_id: str,
        ) -> dict[str, Any]:
            """Безопасно удаляет стартер: дропает таблицы tst_* и очищает директорию."""
            return await manager.uninstall(starter_id=starter_id)

        @router.rpc_method(role=[admRole.adm_starters])
        async def seo_preview(
            session_data: SessionData,
            starter_id: str,
            slug: str | None = None,
        ) -> dict[str, Any]:
            """Формирует предпросмотр SEO-разметки (BreadcrumbList, DiscussionForumPosting, sitemap)."""
            return await manager.get_seo_preview(starter_id=starter_id, slug=slug)
