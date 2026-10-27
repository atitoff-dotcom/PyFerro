"""
JSON-RPC обработчики подсистемы SEO и Dynamic Rendering для панели управления (`/pyferro_admin`).

Все методы защищены системной ролью `admRole.adm_seo` (а также доступны главному `admin`)
и регистрируются в единой карточке `seo.*`:
- `seo.get_tree`
- `seo.save_tree`
- `seo.apply_preset`
- `seo.validate_template`
- `seo.preview_node`
- `seo.ping_indexnow`
- `seo.toggle_guest_read`
"""

from __future__ import annotations

import copy
import html
import re
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.auth.models import Role
from pyferro2.core.constants import GUEST_ROLE, admRole
from pyferro2.rpc.errors import ForbiddenError, InvalidParamsError
from pyferro2.seo.indexnow import notify_indexnow
from pyferro2.seo.jinja_engine import (
    SYSTEM_SECURITY_MODELS,
    SYSTEM_SECURITY_PREFIXES,
    is_model_allowed_for_seo,
    resolve_foreign_target_spec,
    validate_jinja_template,
)
from pyferro2.seo.models import get_seo_config
from pyferro2.seo.router import BOT_ROUTES
from pyferro2.seo.site_tree import (
    STRUCTURE_PRESETS,
    compile_pattern_to_regex,
    get_cached_site_tree,
    get_model_schema_for_seo,
    render_collection_node,
    render_detail_node,
    render_static_node,
    save_seo_to_db,
)

if TYPE_CHECKING:
    from pyferro2.crud.engine import CrudEngine
    from pyferro2.db.engine import Database
    from pyferro2.rpc.router import RpcRouter


def _validate_tree_security(
    node: dict[str, Any],
    crud_engine: CrudEngine,
    guest_permissions: frozenset[str] | None,
) -> None:
    """Рекурсивно проверяет, что ни один узел дерева не ссылается на запрещенные системные таблицы."""
    m_key = node.get("model_key")
    if m_key:
        if m_key in SYSTEM_SECURITY_MODELS:
            raise ForbiddenError(f"Системная модель '{m_key}' запрещена для использования в SEO")
        spec = crud_engine.models.get(m_key)
        if spec is not None and not is_model_allowed_for_seo(spec, guest_permissions):
            raise ForbiddenError(
                f"Модель '{m_key}' недоступна для гостей (нет права '{spec.perm_read}' у роли 'guest')"
            )
    for child in node.get("children", []):
        if isinstance(child, dict):
            _validate_tree_security(child, crud_engine, guest_permissions)


def register_seo_rpc(
    router: RpcRouter,
    db: Database,
    crud_engine: CrudEngine,
    get_guest_permissions: Callable[[], frozenset[str]],
) -> None:
    """Регистрирует административные RPC-методы `seo.*` (доступные по роли `admRole.adm_seo`)."""

    class seo:
        @router.rpc_method(role=[admRole.adm_seo])
        async def get_tree() -> dict[str, Any]:
            """Возвращает актуальное дерево сайта, доступные прикладные модели, пресеты и настройки SEO."""
            cfg = get_seo_config()
            tree = get_cached_site_tree()
            guest_perms = get_guest_permissions()

            models_info: list[dict[str, Any]] = []
            for spec in crud_engine.models.values():
                if spec.name in SYSTEM_SECURITY_MODELS or spec.table_name.startswith(SYSTEM_SECURITY_PREFIXES):
                    continue
                schema_info = get_model_schema_for_seo(crud_engine, spec.name, guest_perms)
                models_info.append(schema_info)

            presets_list = [
                {
                    "key": k,
                    "title": v["title"],
                    "description": v["description"],
                    "icon": v.get("icon", "📄"),
                }
                for k, v in STRUCTURE_PRESETS.items()
            ]

            return {
                "tree": tree,
                "site_url": cfg.site_url,
                "site_name": cfg.site_name,
                "default_title": cfg.default_title,
                "default_description": cfg.default_description,
                "default_og_image": cfg.default_og_image or "",
                "indexnow_key": cfg.indexnow_key or "",
                "sitemap_ttl": cfg.sitemap_ttl,
                "available_models": models_info,
                "presets": presets_list,
                "bot_routes": [r.raw_path for r in BOT_ROUTES],
            }

        @router.rpc_method(role=[admRole.adm_seo])
        async def save_tree(
            db: AsyncSession,
            tree: dict[str, Any],
            site_url: str | None = None,
            site_name: str | None = None,
            default_title: str | None = None,
            default_description: str | None = None,
            default_og_image: str | None = None,
            indexnow_key: str | None = None,
            sitemap_ttl: int | None = None,
        ) -> dict[str, Any]:
            """Сохраняет структуру дерева сайта и настройки SEO в таблицу `pf_seo_config`."""
            if not isinstance(tree, dict) or "id" not in tree:
                raise InvalidParamsError("Поле 'tree' должно быть корректным объектом корневого узла")

            _validate_tree_security(tree, crud_engine, None)

            saved_tree = await save_seo_to_db(
                db,
                tree=tree,
                site_url=site_url,
                site_name=site_name,
                default_title=default_title,
                default_description=default_description,
                default_og_image=default_og_image,
                indexnow_key=indexnow_key,
                sitemap_ttl=sitemap_ttl,
            )
            return {
                "status": "ok",
                "message": "Дерево сайта и параметры поисковой оптимизации сохранены в БД",
                "tree": saved_tree,
            }

        @router.rpc_method(role=[admRole.adm_seo])
        async def apply_preset(db: AsyncSession, preset_key: str) -> dict[str, Any]:
            """Применяет универсальный шаблон структуры сайта (`clean`, `catalog`, `blog`)."""
            preset = STRUCTURE_PRESETS.get(preset_key)
            if not preset:
                raise InvalidParamsError(f"Неизвестный шаблон структуры: '{preset_key}'")

            new_tree = copy.deepcopy(preset["tree"])
            saved_tree = await save_seo_to_db(db, tree=new_tree)
            return {
                "status": "ok",
                "message": f"Шаблон «{preset['title']}» успешно применен",
                "tree": saved_tree,
            }

        @router.rpc_method(role=[admRole.adm_seo])
        async def validate_template(template: str) -> dict[str, Any]:
            """Проверяет синтаксис шаблона Jinja2 в реальном времени."""
            return validate_jinja_template(template)

        @router.rpc_method(role=[admRole.adm_seo])
        async def ping_indexnow(urls: list[str] | None = None) -> dict[str, Any]:
            """Отправляет ручной push-запрос в поисковые системы (Яндекс / Bing) по протоколу IndexNow."""
            cfg = get_seo_config()
            if not cfg.indexnow_key:
                raise InvalidParamsError("Ключ IndexNow не задан. Сначала укажите и сохраните ключ в настройках SEO.")

            target_urls = urls or [f"{cfg.site_url}/"]
            await notify_indexnow(target_urls)
            return {
                "status": "ok",
                "pushed_urls": target_urls,
                "message": f"Запрос на индексацию ({len(target_urls)} URL) отправлен в IndexNow",
            }

        @router.rpc_method(role=[admRole.adm_seo])
        async def toggle_guest_read(
            db: AsyncSession,
            model_key: str,
            allowed: bool,
        ) -> dict[str, Any]:
            """
            Включает или выключает право публичного чтения (`Model.read`) у роли `guest`
            (позволяя открывать таблицу для поисковых ботов и гостей прямо из вкладки SEO).
            """
            if model_key in SYSTEM_SECURITY_MODELS:
                raise ForbiddenError(f"Системная модель '{model_key}' запрещена для публичной индексации")
            spec = crud_engine.models.get(model_key)
            if spec is None or spec.table_name.startswith(SYSTEM_SECURITY_PREFIXES):
                raise InvalidParamsError(f"Прикладная модель '{model_key}' не найдена")

            guest_role = (await db.execute(select(Role).where(Role.name == GUEST_ROLE))).scalar_one_or_none()
            if guest_role is None:
                raise InvalidParamsError("Системная роль 'guest' не найдена")

            current_perms = set(guest_role.get_permissions())
            if allowed:
                current_perms.add(spec.perm_read)
            else:
                current_perms.discard(spec.perm_read)
                current_perms.discard(spec.perm_read_own)

            await crud_engine.set_role_permissions(db, GUEST_ROLE, sorted(current_perms))
            return {
                "status": "ok",
                "model_key": model_key,
                "seo_allowed": allowed,
            }

        @router.rpc_method(role=[admRole.adm_seo])
        async def preview_node(
            node: dict[str, Any],
            parents: list[dict[str, Any]] | None = None,
            sample_id: Any = None,
        ) -> dict[str, Any]:
            """Генерирует живое превью того, что увидит бот (Google, Telegram, семантический HTML) для узла дерева."""
            if not isinstance(node, dict):
                raise InvalidParamsError("Параметр 'node' должен быть словарем")

            m_key = node.get("model_key")
            if m_key and m_key in SYSTEM_SECURITY_MODELS:
                raise ForbiddenError(f"Модель '{m_key}' запрещена для использования в SEO")

            p_list = parents or []
            for p in p_list:
                p_key = p.get("model_key") if isinstance(p, dict) else None
                if p_key and p_key in SYSTEM_SECURITY_MODELS:
                    raise ForbiddenError(f"Модель '{p_key}' запрещена для использования в SEO")

            guest_perms = get_guest_permissions()
            node_type = node.get("node_type", "static")
            pattern = node.get("url_pattern", "/")

            try:
                _compiled, keys = compile_pattern_to_regex(pattern)
                page_data = None

                if node_type == "static":
                    page_data = await render_static_node(
                        node,
                        p_list,
                        pattern,
                        db=db,
                        crud_engine=crud_engine,
                        guest_permissions=guest_perms,
                    )
                elif node_type == "collection":
                    sample_params: dict[str, str] = {}
                    for _fk, ck in keys:
                        sample_params[ck] = "sample"
                    sim_path = re.sub(r"\{[a-zA-Z0-9_.]+\}", "sample", pattern)
                    page_data = await render_collection_node(
                        node,
                        p_list,
                        sim_path,
                        sample_params,
                        keys,
                        db=db,
                        crud_engine=crud_engine,
                        guest_permissions=guest_perms,
                    )
                elif node_type == "detail":
                    sample_params = {}
                    spec = crud_engine.models.get(m_key) if m_key else None
                    if spec and is_model_allowed_for_seo(spec, guest_perms):
                        async with db.session() as session:
                            row = (await session.execute(select(spec.model_cls).limit(1))).scalar_one_or_none()
                            if row:
                                slug_val = getattr(row, "slug", None)
                                id_val = getattr(row, "id", None)
                                for fk_tuple, clean_key in keys:
                                    if "." in fk_tuple:
                                        rel_name, fld = fk_tuple.split(".", 1)
                                        for f in spec.fields:
                                            if rel_name == "parent" or f.name.startswith(rel_name):
                                                p_spec = resolve_foreign_target_spec(
                                                    crud_engine, f.name, f.foreign_key_table
                                                )
                                                if p_spec:
                                                    p_fk_val = getattr(row, f.name, None)
                                                    if p_fk_val is not None:
                                                        p_row = (
                                                            await session.execute(
                                                                select(p_spec.model_cls).where(
                                                                    p_spec.model_cls.id == p_fk_val
                                                                )
                                                            )
                                                        ).scalar_one_or_none()
                                                        if p_row:
                                                            sample_params[clean_key] = str(
                                                                getattr(p_row, fld, "sample")
                                                            )
                                    else:
                                        val = getattr(row, fk_tuple, None) or slug_val or id_val or 1
                                        sample_params[clean_key] = str(val)
                    if not sample_params and keys:
                        for _fk, ck in keys:
                            sample_params[ck] = str(sample_id or 1)
                    sim_path = re.sub(r"\{[a-zA-Z0-9_.]+\}", "sample", pattern)
                    page_data = await render_detail_node(
                        node,
                        p_list,
                        sim_path,
                        sample_params,
                        keys,
                        db=db,
                        crud_engine=crud_engine,
                        guest_permissions=guest_perms,
                    )

                if page_data is not None:
                    return {
                        "title": page_data.title,
                        "description": page_data.description,
                        "url": page_data.canonical_url,
                        "og_image": page_data.og_image or "",
                        "schema_type": page_data.schema_type,
                        "breadcrumbs": [
                            {"title": b[0], "url": b[1]} for b in (page_data.breadcrumbs or [])
                        ],
                        "body_html": page_data.body_html,
                    }
            except Exception:
                pass

            # Фолбэк превью (если в таблице пока нет записей или модель еще не открыта для гостей)
            raw_title = node.get("meta_title") or node.get("title", "")
            raw_desc = node.get("meta_description", "")
            return {
                "title": raw_title,
                "description": raw_desc,
                "url": pattern,
                "og_image": node.get("og_image") or "",
                "schema_type": node.get("schema_type", "WebPage"),
                "breadcrumbs": [
                    {"title": p.get("title", ""), "url": p.get("url_pattern", "/")}
                    for p in p_list
                    if isinstance(p, dict)
                ]
                + [{"title": node.get("title", ""), "url": pattern}],
                "body_html": f"<h1>{html.escape(str(raw_title))}</h1><p>{html.escape(str(raw_desc))}</p>",
            }
