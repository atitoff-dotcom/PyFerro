# -*- coding: utf-8 -*-
"""
Автоматическая синхронизация RPC-методов и прав доступа с базой данных (Service Discovery).
Гарантирует начальный бутстрап системных ролей (admin, user), базовых публичных методов
и O(1) in-memory кэш публичных маршрутов (PUBLIC_RPC_METHODS).
"""

from __future__ import annotations
import inspect
from typing import Set
from sqlalchemy import select, delete

from pyferro.core.logger import logger
from pyferro.core.constants import ADMIN_ROLE, GUEST_ROLE, SEO_ROLE, ADM_SECTION_ROLES, ADM_HELP_ROLE, SYSTEM_ROLES

ADM_ROLE_DESCRIPTIONS = {
    "adm-crud": "Администратор базы данных (CRUD)",
    "adm-seo": "Администратор соцсетей и SEO (Search & Social Previews)",
    "adm-users": "Администратор пользователей (User Management)",
    "adm-roles": "Администратор прав и ролей (RBAC Management)",
    "adm-rpc": "Администратор RPC API (API Explorer)",
    "adm-settings": "Администратор настроек платформы (System Settings)",
    "adm-help": "Администратор раздела Справки и API (Help & API Explorer)",
}
from pyferro.core.session import (
    RPC_REGISTRY,
    GUEST_ALLOWED_RPC_METHODS,
    GUEST_ALLOWED_CRUD_MODELS,
    is_framework_handler,
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


async def ensure_system_roles(db) -> tuple[Role, Role]:
    """Гарантирует наличие обязательных системных ролей admin и guest в БД."""
    try:
        from pyferro.db import engine
        async with engine.begin() as conn:
            def _sync_col(connection):
                try:
                    res = connection.exec_driver_sql("PRAGMA table_info(pf_auth_rpc_permission)").fetchall()
                    existing_cols = {row[1] for row in res}
                    if existing_cols and "is_framework" not in existing_cols:
                        connection.exec_driver_sql("ALTER TABLE pf_auth_rpc_permission ADD COLUMN is_framework BOOLEAN DEFAULT 0")
                except Exception:
                    pass
            await conn.run_sync(_sync_col)
    except Exception:
        pass

    stmt_roles = select(Role).options(selectinload(Role.rpc_permissions))
    existing = {r.name: r for r in (await db.execute(stmt_roles)).scalars().all()}

    if ADMIN_ROLE not in existing:
        admin_role = Role(name=ADMIN_ROLE, description="Системный администратор (Superadmin)")
        db.add(admin_role)
        existing[ADMIN_ROLE] = admin_role

    if GUEST_ROLE not in existing:
        guest_role = Role(name=GUEST_ROLE, description="Гость / Неавторизованный посетитель")
        db.add(guest_role)
        existing[GUEST_ROLE] = guest_role

    roles_added = False
    if SEO_ROLE not in existing:
        seo_role = Role(name=SEO_ROLE, description="Поисковая оптимизация и индексация (SEO Bot / Crawler)")
        db.add(seo_role)
        existing[SEO_ROLE] = seo_role
        roles_added = True

    for adm_r in ADM_SECTION_ROLES:
        if adm_r not in existing:
            desc = ADM_ROLE_DESCRIPTIONS.get(adm_r, f"Администратор подраздела {adm_r}")
            r_obj = Role(name=adm_r, description=desc)
            db.add(r_obj)
            existing[adm_r] = r_obj
            roles_added = True

    if roles_added or ADMIN_ROLE not in existing or GUEST_ROLE not in existing:
        await db.commit()
        stmt_roles = select(Role).options(selectinload(Role.rpc_permissions))
        existing = {r.name: r for r in (await db.execute(stmt_roles)).scalars().all()}
    return existing[ADMIN_ROLE], existing[GUEST_ROLE]


async def sync_rpc_permissions() -> None:
    """
    Синхронизирует зарегистрированные в коде RPC-методы с базой данных.
    1. Проверяет наличие обязательных системных ролей (admin, guest); если отсутствуют - падает.
    2. Сканирует RPC_REGISTRY и добавляет новые методы в auth_rpc_permission.
    3. Привязывает к роли guest только методы логина (Default Deny).
    4. Загружает права гостя в O(1) in-memory кэш (GUEST_ALLOWED_RPC_METHODS / GUEST_ALLOWED_CRUD_MODELS).
    """
    try:
        from ..db import engine, Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def _sync_rpc_perm_columns(connection):
                try:
                    res = connection.exec_driver_sql("PRAGMA table_info(pf_auth_rpc_permission)").fetchall()
                    existing_cols = {row[1] for row in res}
                    if existing_cols and "is_framework" not in existing_cols:
                        connection.exec_driver_sql("ALTER TABLE pf_auth_rpc_permission ADD COLUMN is_framework BOOLEAN DEFAULT 0")
                except Exception:
                    pass

            await conn.run_sync(_sync_rpc_perm_columns)

        async with system_db_session() as db:
            # 1. Проверяем обязательные системные роли (admin, guest)
            stmt_roles = select(Role).options(selectinload(Role.rpc_permissions))
            existing_roles = {r.name: r for r in (await db.execute(stmt_roles)).scalars().all()}

            missing_roles = [r for r in (ADMIN_ROLE, GUEST_ROLE) if r not in existing_roles]
            if missing_roles:
                error_msg = (
                    f"CRITICAL: В базе данных отсутствуют обязательные системные роли {missing_roles}! "
                    f"Запуск сервера невозможен. Инициализируйте базу через CLI ('createsuperuser')."
                )
                logger.critical(f"[Discovery] {error_msg}")
                raise RuntimeError(error_msg)

            # Гарантируем наличие системной роли seo и ролей подразделов в существующей БД
            roles_created = False
            if SEO_ROLE not in existing_roles:
                seo_role = Role(
                    name=SEO_ROLE,
                    description="Поисковая оптимизация и индексация (SEO Bot / Crawler)",
                )
                db.add(seo_role)
                roles_created = True

            for adm_r in ADM_SECTION_ROLES:
                if adm_r not in existing_roles:
                    desc = ADM_ROLE_DESCRIPTIONS.get(adm_r, f"Администратор подраздела {adm_r}")
                    r_obj = Role(name=adm_r, description=desc)
                    db.add(r_obj)
                    roles_created = True

            if roles_created:
                await db.commit()
                stmt_roles = select(Role).options(selectinload(Role.rpc_permissions))
                existing_roles = {r.name: r for r in (await db.execute(stmt_roles)).scalars().all()}

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
                is_fw = getattr(handler, "is_framework", None)
                if is_fw is None:
                    is_fw = is_framework_handler(handler)
                is_fw = bool(is_fw)

                if method_name not in existing_perms:
                    new_perm = RpcPermission(
                        name=method_name,
                        description=first_line,
                        is_framework=is_fw,
                    )
                    db.add(new_perm)
                    existing_perms[method_name] = new_perm
                    added_count += 1
                else:
                    perm = existing_perms[method_name]
                    if getattr(perm, "is_framework", None) != is_fw:
                        perm.is_framework = is_fw
                        updated_count += 1
                    if not perm.description or perm.description.startswith("Обертка для") or perm.description.startswith("RPC method") or perm.description != first_line:
                        if first_line and perm.description != first_line:
                            perm.description = first_line
                            updated_count += 1

            # 3. Удаляем устаревшие методы, которых больше нет в RPC_REGISTRY
            # (не затрагивая wildcard-маски прав вида '*' или 'orders.*')
            stale_perms = [
                perm for name, perm in existing_perms.items()
                if name not in RPC_REGISTRY and not name.endswith("*")
            ]
            deleted_count = 0
            if stale_perms:
                stale_ids = [p.id for p in stale_perms]
                from .models import RoleRpcPermission, UserRpcPermission
                await db.execute(delete(RoleRpcPermission).where(RoleRpcPermission.rpc_permission_id.in_(stale_ids)))
                await db.execute(delete(UserRpcPermission).where(UserRpcPermission.rpc_permission_id.in_(stale_ids)))
                for p in stale_perms:
                    await db.delete(p)
                    existing_perms.pop(p.name, None)
                deleted_count = len(stale_perms)

            if added_count > 0 or updated_count > 0 or deleted_count > 0:
                await db.flush()

            # 4. Гарантируем привязку методов логина к роли guest
            guest_role_updated = False
            for method_name, perm in existing_perms.items():
                is_login = method_name in DEFAULT_LOGIN_METHODS or method_name.startswith("login.")
                if is_login and perm.id not in guest_rpc_ids:
                    guest_role.rpc_permissions.append(perm)
                    guest_rpc_ids.add(perm.id)
                    guest_role_updated = True

            # 5. Привязываем help.* методы к роли adm-help
            help_updated = False
            if ADM_HELP_ROLE in existing_roles:
                help_role = existing_roles[ADM_HELP_ROLE]
                help_rpc_ids = {rp.id for rp in help_role.rpc_permissions}
                for method_name, perm in existing_perms.items():
                    if method_name.startswith("help.") and perm.id not in help_rpc_ids:
                        help_role.rpc_permissions.append(perm)
                        help_rpc_ids.add(perm.id)
                        help_updated = True

            # 6. Инициализируем CRUD-разрешения по умолчанию для роли seo (тестовые модели форума)
            seo_updated = False
            if SEO_ROLE in existing_roles:
                seo_role = existing_roles[SEO_ROLE]
                stmt_seo_perms = select(RolePermission).where(RolePermission.role_id == seo_role.id)
                existing_seo_models = {p.model_name for p in (await db.execute(stmt_seo_perms)).scalars().all()}
                for m_key in ["ForumCategory", "ForumTopic", "ForumPost"]:
                    if m_key not in existing_seo_models:
                        db.add(RolePermission(
                            role_id=seo_role.id,
                            model_name=m_key,
                            can_read=True,
                            can_create=False,
                            can_update=False,
                            can_delete=False,
                            read_global=True,
                        ))
                        seo_updated = True

            if added_count > 0 or updated_count > 0 or deleted_count > 0 or guest_role_updated or help_updated or seo_updated:
                await db.commit()
                if added_count > 0:
                    logger.info(f"[Discovery] Зарегистрировано {added_count} новых RPC-методов в базе данных")
                if updated_count > 0:
                    logger.info(f"[Discovery] Обновлено {updated_count} описаний RPC-методов из docstrings")
                if deleted_count > 0:
                    logger.info(f"[Discovery] Удалено {deleted_count} устаревших RPC-методов из базы данных")

            # 7. Актуализируем in-memory кэш гостя
            await reload_guest_permissions_cache()

    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(f"[Discovery] Пропущен авто-синк RPC методов (БД не инициализирована или офлайн): {e}")
        GUEST_ALLOWED_RPC_METHODS.update(DEFAULT_LOGIN_METHODS)


# Регистрируем авто-синк при старте приложения
@on_startup
async def _on_startup_sync_rpc():
    await sync_rpc_permissions()
