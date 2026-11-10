"""
JSON-RPC обработчики подсистемы кеширования и Offline-First для панели управления (`/pyferro_admin`).

Все административные методы защищены системной ролью `admRole.adm_cache` (а также `adm_settings` и `admin`)
и регистрируются в карточке `cache.*`:
- `cache.get_settings`
- `cache.save_settings`
- `cache.purge_all`
- `cache.get_manifest` (публичный манифест для синхронизации клиентского IndexedDB)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.cache.manager import (
    cache_manager,
    load_cache_from_db,
    purge_all_cache,
    save_cache_to_db,
)
from pyferro2.core.constants import admRole

if TYPE_CHECKING:
    from pyferro2.rpc.router import RpcRouter, RpcMethodSpec

_SYSTEM_CARD_PREFIXES: tuple[str, ...] = (
    "auth.",
    "oauth.",
    "system.",
    "admin.",
    "crud.",
    "seo.",
    "help.",
    "files.",
    "cache.",
    "User.",
    "Role.",
    "RolePermission.",
    "StoredFile.",
    "SeoConfigRecord.",
    "CacheConfigRecord.",
    "CacheRuleRecord.",
)


def is_app_cacheable_method(spec: RpcMethodSpec) -> bool:
    """Проверяет, является ли RPC-метод прикладным методом приложения (включая public=True и CRUD)."""
    if spec.name.startswith(_SYSTEM_CARD_PREFIXES):
        return False
    return True


def infer_method_cache_scope(spec: RpcMethodSpec) -> str:
    """
    Автоматически определяет область видимости кеша по сигнатуре метода:
    - Если метод публичный (`public=True`) и не запрашивает `session_data` или `session` -> `"public"`.
    - Иначе -> `"user"` (изолирован по `user_id`).
    """
    if spec.public and spec.session_data_arg is None and spec.session_arg is None:
        return "public"
    return "user"


def register_cache_rpc(router: RpcRouter) -> None:
    """Регистрирует RPC-методы `cache.*` в роутере."""

    class cache:
        @router.rpc_method(public=True)
        async def get_manifest() -> dict[str, Any]:
            """Возвращает компактный манифест правил кеширования для клиентского IndexedDB."""
            return cache_manager.config.to_public_manifest()

        @router.rpc_method(role=[admRole.adm_cache, admRole.adm_settings, admRole.adm_rpc])
        async def get_settings(db: AsyncSession) -> dict[str, Any]:
            """
            Возвращает глобальные настройки кеша, список всех прикладных методов с их правилами
            и живую статистику серверного L1-кеша.
            """
            await load_cache_from_db(db)
            cfg = cache_manager.config

            methods_info: list[dict[str, Any]] = []
            for name in sorted(router.methods.keys()):
                spec = router.methods[name]
                if not is_app_cacheable_method(spec):
                    continue
                rule = cfg.rules.get(name)
                scope = infer_method_cache_scope(spec)
                methods_info.append({
                    "name": name,
                    "scope": scope,
                    "public": spec.public,
                    "is_stream": spec.is_stream,
                    "has_required_params": len(spec.required_params) > 0,
                    "cache_enabled": rule.cache_enabled if rule else False,
                    "strategy": rule.strategy if rule else "auto",
                    "ttl_sec": rule.ttl_sec if rule else 300,
                    "prefetch_media": rule.prefetch_media if rule else False,
                    "preload_on_boot": rule.preload_on_boot if rule else False,
                    "offline_outbox": rule.offline_outbox if rule else False,
                })

            return {
                "config": {
                    "enabled": cfg.enabled,
                    "liefi_timeout_ms": cfg.liefi_timeout_ms,
                    "max_media_mb": cfg.max_media_mb,
                    "max_rpc_entries": cfg.max_rpc_entries,
                    "cache_epoch": cfg.cache_epoch,
                },
                "methods": methods_info,
                "stats": cache_manager.stats(),
            }

        @router.rpc_method(role=[admRole.adm_cache, admRole.adm_settings, admRole.adm_rpc])
        async def save_settings(
            db: AsyncSession,
            config: dict[str, Any],
            rules: list[dict[str, Any]],
        ) -> dict[str, Any]:
            """Сохраняет глобальные настройки и правила кеширования методов в БД."""
            updated_cfg = await save_cache_to_db(db, config, rules)
            return {
                "status": "saved",
                "cache_epoch": updated_cfg.cache_epoch,
                "stats": cache_manager.stats(),
            }

        @router.rpc_method(role=[admRole.adm_cache, admRole.adm_settings, admRole.adm_rpc])
        async def purge_all(db: AsyncSession) -> dict[str, Any]:
            """Принудительно сбрасывает серверный L1-кеш и увеличивает эпоху кеша для всех клиентов."""
            new_epoch = await purge_all_cache(db)
            return {
                "status": "purged",
                "cache_epoch": new_epoch,
                "stats": cache_manager.stats(),
            }
