# -*- coding: utf-8 -*-
"""
Автоматическая синхронизация RPC-методов и прав доступа с базой данных (Service Discovery).
Гарантирует начальный бутстрап системных ролей (admin, user), базовых публичных методов
и O(1) in-memory кэш публичных маршрутов (PUBLIC_RPC_METHODS).
"""

from __future__ import annotations
import inspect
from typing import Set
from sqlalchemy import select

from pyferro.core.logger import logger
from pyferro.core.constants import ADMIN_ROLE, DEFAULT_USER_ROLE, SYSTEM_ROLES
from pyferro.core.session import RPC_REGISTRY, PUBLIC_RPC_METHODS
from pyferro.core.lifecycle import on_startup
from pyferro.db import system_db_session
from .models import Role, RpcPermission, user_role_association, role_rpc_permission_association

# Системные методы, которые по умолчанию публичны при начальной инициализации
DEFAULT_PUBLIC_METHODS = frozenset({
    "login.get_key",
    "login.secure",
    "login.submit",
    "login.refresh",
    "login.register",
    "login.get_oauth_providers",
    "login.oauth_vk",
    "system.ping",
    "system.info",
})


async def reload_public_rpc_cache() -> Set[str]:
    """
    Перезагружает in-memory кэш публичных RPC-методов (PUBLIC_RPC_METHODS) из БД.
    """
    try:
        async with system_db_session() as db:
            stmt = select(RpcPermission.name).where(RpcPermission.is_public == True)
            result = await db.execute(stmt)
            public_names = set(result.scalars().all())

            # Всегда гарантируем доступность базовых методов логина в памяти
            public_names.update(DEFAULT_PUBLIC_METHODS)

            PUBLIC_RPC_METHODS.clear()
            PUBLIC_RPC_METHODS.update(public_names)
            return public_names
    except Exception as e:
        logger.warning(f"[Discovery] Не удалось перезагрузить публичный кэш из БД: {e}")
        PUBLIC_RPC_METHODS.update(DEFAULT_PUBLIC_METHODS)
        return set(DEFAULT_PUBLIC_METHODS)


def _ensure_auth_columns(sync_conn) -> None:
    """Безопасная эволюция схемы: добавляет недостающие колонки в существующие таблицы."""
    from sqlalchemy import inspect as sa_inspect, text
    try:
        inspector = sa_inspect(sync_conn)
        tables = set(inspector.get_table_names())

        # 1. Добавляем owner_id во все таблицы с Row-Level Security (где есть creator_id)
        for t_name in tables:
            cols = {c["name"] for c in inspector.get_columns(t_name)}
            if "creator_id" in cols and "owner_id" not in cols:
                sync_conn.execute(text(f"ALTER TABLE {t_name} ADD COLUMN owner_id INTEGER"))

        # Явный список таблиц auth на случай создания без creator_id
        for t_name in ("auth_user", "auth_role", "auth_team", "auth_rpc_permission", "auth_role_permission", "auth_user_permission"):
            if t_name in tables:
                cols = {c["name"] for c in inspector.get_columns(t_name)}
                if "owner_id" not in cols:
                    sync_conn.execute(text(f"ALTER TABLE {t_name} ADD COLUMN owner_id INTEGER"))

        # 2. Добавляем гранулярные скоупы в таблицы прав
        for t_name in ("auth_role_permission", "auth_user_permission"):
            if t_name in tables:
                cols = {c["name"] for c in inspector.get_columns(t_name)}
                if "read_global" not in cols:
                    sync_conn.execute(text(f"ALTER TABLE {t_name} ADD COLUMN read_global BOOLEAN DEFAULT 0"))
                if "update_global" not in cols:
                    sync_conn.execute(text(f"ALTER TABLE {t_name} ADD COLUMN update_global BOOLEAN DEFAULT 0"))
                if "delete_global" not in cols:
                    sync_conn.execute(text(f"ALTER TABLE {t_name} ADD COLUMN delete_global BOOLEAN DEFAULT 0"))
    except Exception as e:
        logger.debug(f"[Discovery] Пропуск автоматической миграции колонок: {e}")


async def sync_rpc_permissions() -> None:
    """
    Синхронизирует зарегистрированные в коде RPC-методы с базой данных.
    1. Создает системные роли (admin, user), если их еще нет.
    2. Сканирует RPC_REGISTRY и добавляет новые методы в auth_rpc_permission.
    3. Загружает список публичных методов в память PUBLIC_RPC_METHODS.
    """
    try:
        from ..db import engine, Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_ensure_auth_columns)

        async with system_db_session() as db:
            # 1. Проверяем и создаем системные роли
            stmt_roles = select(Role.name)
            existing_role_names = set((await db.execute(stmt_roles)).scalars().all())

            if ADMIN_ROLE not in existing_role_names:
                admin_role = Role(name=ADMIN_ROLE, description="Системный администратор (Superadmin)")
                db.add(admin_role)
                logger.info(f"[Discovery] Создана системная роль '{ADMIN_ROLE}'")

            if DEFAULT_USER_ROLE not in existing_role_names:
                user_role = Role(name=DEFAULT_USER_ROLE, description="Базовый зарегистрированный пользователь")
                db.add(user_role)
                logger.info(f"[Discovery] Создана системная роль '{DEFAULT_USER_ROLE}'")

            await db.commit()

            # 2. Сканируем зарегистрированные методы
            stmt_perms = select(RpcPermission)
            existing_perms = {p.name: p for p in (await db.execute(stmt_perms)).scalars().all()}

            added_count = 0
            updated_count = 0
            for method_name, handler in RPC_REGISTRY.items():
                full_doc = inspect.getdoc(handler) or getattr(handler, "__doc__", None)
                first_line = None
                if full_doc:
                    lines = [l.strip() for l in full_doc.strip().split("\n") if l.strip()]
                    if lines:
                        first_line = lines[0]
                if not first_line:
                    logger.warning(f"[Discovery] ⚠️ RPC-метод '{method_name}' не имеет docstring! Добавьте краткое описание функции.")
                    first_line = f"RPC method {method_name}"

                # Проверяем дефолтную публичность
                is_public = (
                    method_name in DEFAULT_PUBLIC_METHODS
                    or method_name.startswith("login.")
                    or getattr(handler, "public", False)
                )

                if method_name not in existing_perms:
                    new_perm = RpcPermission(
                        name=method_name,
                        is_public=is_public,
                        description=first_line
                    )
                    db.add(new_perm)
                    existing_perms[method_name] = new_perm
                    added_count += 1
                else:
                    perm = existing_perms[method_name]
                    if not perm.description or perm.description.startswith("Обертка для") or perm.description.startswith("RPC method"):
                        perm.description = first_line
                        updated_count += 1

            if added_count > 0 or updated_count > 0:
                await db.commit()
                if added_count > 0:
                    logger.info(f"[Discovery] Зарегистрировано {added_count} новых RPC-методов в базе данных")
                if updated_count > 0:
                    logger.info(f"[Discovery] Обновлено {updated_count} описаний RPC-методов из docstrings")

            # 3. Актуализируем in-memory кэш публичных методов
            public_names = {p.name for p in existing_perms.values() if p.is_public}
            public_names.update(DEFAULT_PUBLIC_METHODS)
            PUBLIC_RPC_METHODS.clear()
            PUBLIC_RPC_METHODS.update(public_names)

    except Exception as e:
        logger.warning(f"[Discovery] Пропущен авто-синк RPC методов (БД не инициализирована или офлайн): {e}")
        PUBLIC_RPC_METHODS.update(DEFAULT_PUBLIC_METHODS)


# Регистрируем авто-синк при старте приложения
@on_startup
async def _on_startup_sync_rpc():
    await sync_rpc_permissions()
