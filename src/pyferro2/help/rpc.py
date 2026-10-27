"""
JSON-RPC 2.0 интерфейс справочной системы (/pyferro_admin/help).
Доступ разрешен только системным ролям `admin` и `adm_help`.
Работает с предварительно скомпилированным JSON-бандлом справки,
не требуя библиотек парсинга Markdown в рантайме.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from pyferro2.core.constants import admRole
from pyferro2.core.session_data import SessionData
from pyferro2.rpc.errors import RpcError
from pyferro2.rpc.router import RpcRouter


def _resolve_bundle_path(source: Path | str | None) -> Path | None:
    """Определяет путь к скомпилированному help_data.json."""
    if source is not None:
        p = Path(source).resolve()
        if p.is_file():
            return p
        if p.is_dir() and (p / "help_data.json").is_file():
            return p / "help_data.json"

    default_pkg = Path(__file__).resolve().parent / "help_data.json"
    if default_pkg.is_file():
        return default_pkg

    return None


def register_help_rpc(
    router: RpcRouter,
    help_source: Path | str | None = None,
) -> None:
    """Регистрирует методы `help.get_tree`, `help.get_article` и `help.get_search_index` в RPC-роутере."""
    bundle_path = _resolve_bundle_path(help_source)

    tree: list[dict[str, Any]] = []
    articles: dict[str, dict[str, Any]] = {}
    search_index: list[dict[str, Any]] = []

    if bundle_path and bundle_path.is_file():
        try:
            raw = bundle_path.read_bytes()
            data = orjson.loads(raw)
            tree = data.get("tree", [])
            articles = data.get("articles", {})
            search_index = data.get("search_index", [])
        except Exception:
            tree = []
            articles = {}
            search_index = []

    class help:
        @router.rpc_method(role=[admRole.adm_help])
        async def get_tree(session_data: SessionData) -> list[dict[str, Any]]:
            """Возвращает упорядоченное оглавление всех доступных статей документации."""
            return tree

        @router.rpc_method(role=[admRole.adm_help])
        async def get_article(session_data: SessionData, slug: str) -> dict[str, Any]:
            """Возвращает скомпилированную статью со структурированными блоками и виджетами."""
            norm_target = slug.replace("_", "-").lower()
            article_data = articles.get(norm_target)
            if not article_data:
                raise RpcError(f"Статья документации '{slug}' не найдена", code=404)
            return article_data

        @router.rpc_method(role=[admRole.adm_help])
        async def get_search_index(session_data: SessionData) -> list[dict[str, Any]]:
            """Возвращает поисковый индекс для мгновенного поиска по тексту и коду."""
            return search_index

        @router.rpc_method(role=[admRole.adm_help])
        async def tree(session_data: SessionData) -> list[dict[str, Any]]:
            """Алиас для get_tree."""
            return await help.get_tree(session_data)

        @router.rpc_method(role=[admRole.adm_help])
        async def article(session_data: SessionData, slug: str) -> dict[str, Any]:
            """Алиас для get_article."""
            return await help.get_article(session_data, slug)

        @router.rpc_method(role=[admRole.adm_help])
        async def search_index(session_data: SessionData) -> list[dict[str, Any]]:
            """Алиас для get_search_index."""
            return await help.get_search_index(session_data)
