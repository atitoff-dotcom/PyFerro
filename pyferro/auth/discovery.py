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
from pyferro.core.constants import ADMIN_ROLE, DEFAULT_USER_ROLE, GUEST_ROLE, SYSTEM_ROLES
from pyferro.core.session import (
    RPC_REGISTRY,
    GUEST_ALLOWED_RPC_METHODS,
    GUEST_ALLOWED_CRUD_MODELS,
)
from pyferro.core.lifecycle import on_startup
from pyferro.db import system_db_session
from sqlalchemy.orm import selectinload
from .models import Role, RpcPermission, RolePermission, user_role_association, role_rpc_permission_association

# Системные методы авторизации, доступные роли guest по умолчанию
DEFAULT_LOGIN_METHODS = frozenset({
    "login.get_key",
    "login.secure",
    "login.submit",
    "login.refresh",
    "login.register",
    "login.get_oauth_providers",
    "login.oauth_vk",
    "login.whoami",
    "auth.login",
    "auth.submit",
    "auth.whoami",
    "auth.me",
})


async def reload_guest_permissions_cache() -> None:
    """
    Перезагружает in-memory кэш разрешенных RPC-методов и CRUD-моделей для роли guest из БД.
    """
    try:
        async with system_db_session() as db:
            stmt = select(Role).where(Role.name == GUEST_ROLE).options(
                selectinload(Role.rpc_permissions),
                selectinload(Role.permissions)
            )
            guest_role = (await db.execute(stmt)).scalar_one_or_none()

            allowed_rpcs = set()
            allowed_crud = set()

            if guest_role:
                for rp in guest_role.rpc_permissions:
                    allowed_rpcs.add(rp.name)
                for cp in guest_role.permissions:
                    if cp.can_read:
                        allowed_crud.add(cp.model_name)

            # Всегда гарантируем методы логина в памяти для роли guest
            for name in RPC_REGISTRY.keys():
                if name.startswith("login."):
                    allowed_rpcs.add(name)
            allowed_rpcs.update(DEFAULT_LOGIN_METHODS)

            GUEST_ALLOWED_RPC_METHODS.clear()
            GUEST_ALLOWED_RPC_METHODS.update(allowed_rpcs)

            GUEST_ALLOWED_CRUD_MODELS.clear()
            GUEST_ALLOWED_CRUD_MODELS.update(allowed_crud)
    except Exception as e:
        logger.warning(f"[Discovery] Не удалось перезагрузить кэш гостя из БД: {e}")
        GUEST_ALLOWED_RPC_METHODS.update(DEFAULT_LOGIN_METHODS)


async def sync_rpc_permissions() -> None:
    """
    Синхронизирует зарегистрированные в коде RPC-методы с базой данных.
    1. Создает системные роли (admin, user, guest), если их еще нет.
    2. Сканирует RPC_REGISTRY и добавляет новые методы в auth_rpc_permission.
    3. Привязывает к роли guest только методы логина (Default Deny).
    4. Загружает права гостя в O(1) in-memory кэш (GUEST_ALLOWED_RPC_METHODS / GUEST_ALLOWED_CRUD_MODELS).
    """
    try:
        from ..db import engine, Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with system_db_session() as db:
            # 1. Проверяем и создаем системные роли
            stmt_roles = select(Role).options(selectinload(Role.rpc_permissions))
            existing_roles = {r.name: r for r in (await db.execute(stmt_roles)).scalars().all()}

            if ADMIN_ROLE not in existing_roles:
                admin_role = Role(name=ADMIN_ROLE, description="Системный администратор (Superadmin)")
                db.add(admin_role)
                existing_roles[ADMIN_ROLE] = admin_role
                logger.info(f"[Discovery] Создана системная роль '{ADMIN_ROLE}'")

            if DEFAULT_USER_ROLE not in existing_roles:
                user_role = Role(name=DEFAULT_USER_ROLE, description="Базовый зарегистрированный пользователь")
                db.add(user_role)
                existing_roles[DEFAULT_USER_ROLE] = user_role
                logger.info(f"[Discovery] Создана системная роль '{DEFAULT_USER_ROLE}'")

            if GUEST_ROLE not in existing_roles:
                guest_role = Role(name=GUEST_ROLE, description="Гость / Неавторизованный посетитель")
                db.add(guest_role)
                existing_roles[GUEST_ROLE] = guest_role
                logger.info(f"[Discovery] Создана системная роль '{GUEST_ROLE}'")

            await db.commit()

            guest_role = existing_roles[GUEST_ROLE]
            guest_rpc_ids = {rp.id for rp in guest_role.rpc_permissions}

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

                # Дефолтная привязка к guest: строго только методы логина
                is_login = method_name in DEFAULT_LOGIN_METHODS or method_name.startswith("login.")

                if method_name not in existing_perms:
                    new_perm = RpcPermission(
                        name=method_name,
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

            # 3. Гарантируем привязку методов логина к роли guest
            guest_role_updated = False
            for method_name, perm in existing_perms.items():
                is_login = method_name in DEFAULT_LOGIN_METHODS or method_name.startswith("login.")
                if is_login and perm.id not in guest_rpc_ids:
                    guest_role.rpc_permissions.append(perm)
                    guest_rpc_ids.add(perm.id)
                    guest_role_updated = True

            if guest_role_updated:
                await db.commit()

            # 4. Актуализируем in-memory кэш гостя
            await reload_guest_permissions_cache()

    except Exception as e:
        logger.warning(f"[Discovery] Пропущен авто-синк RPC методов (БД не инициализирована или офлайн): {e}")
        GUEST_ALLOWED_RPC_METHODS.update(DEFAULT_LOGIN_METHODS)


# Регистрируем авто-синк при старте приложения
@on_startup
async def _on_startup_sync_rpc():
    await sync_rpc_permissions()
