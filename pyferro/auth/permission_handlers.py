# -*- coding: utf-8 -*-
"""
WSRPC-хендлеры управления правами и разрешениями (plugins/auth/permission_handlers.py).
Реализует методы:
- permissions.get_schema
- permissions.get
- permissions.save
"""

import inspect
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pyferro.core.session import (
    JsonRpcSession,
    rpc_method,
    RPCError,
    require_admin,
    RPC_REGISTRY,
    is_guest_rpc_allowed,
    is_framework_handler,
)
from pyferro.core.constants import ADMIN_ROLE
from pyferro.db import system_db_session
from .models import Role, User, RolePermission, UserPermission, RpcPermission

def _inspect_handler_params(handler) -> Dict[str, Any]:
    """Извлекает описание параметров RPC-хэндлера для схемы интроспекции."""
    params_info = {}
    if not handler or not callable(handler):
        return params_info
    try:
        sig = inspect.signature(handler)
        for param_name, param in sig.parameters.items():
            if param_name in ("session", "ws", "context", "self", "cls"):
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            ann = param.annotation
            type_name = "any"
            if ann != inspect.Parameter.empty:
                if hasattr(ann, "__name__"):
                    type_name = ann.__name__
                else:
                    type_name = str(ann).replace("typing.", "")
            has_default = param.default != inspect.Parameter.empty
            default_val = None if not has_default else (
                param.default if isinstance(param.default, (int, float, str, bool, list, dict, type(None)))
                else str(param.default)
            )
            params_info[param_name] = {
                "type": type_name,
                "required": not has_default,
                "default": default_val,
            }
    except Exception:
        pass
    return params_info

@rpc_method("permissions.get_schema")
@rpc_method("permissions.schema")
async def handle_permissions_get_schema(session: JsonRpcSession, all: bool = False) -> Dict[str, Any]:
    """Возвращает список зарегистрированных моделей и RPC-методов для конфигурации прав и интроспекции."""
    require_admin(session)

    from pyferro.plugins.crud.registry import ModelRegistry
    from pyferro.db import Base
    if not ModelRegistry.all():
        ModelRegistry.auto_discover(Base)

    models_info = []
    # Технические связующие таблицы, которыми не нужно управлять вручную через матрицу прав
    blacklist = {
        "UserRole", "UserTeam", "RoleRpcPermission", "UserRpcPermission",
        "UserPermission", "RolePermission", "RefreshToken", "ActiveSession",
        "OAuthAccount", "CacheTagVersion", "SystemData"
    }

    for meta in sorted(ModelRegistry.all().values(), key=lambda m: m.verbose_name or m.key):
        if not all and meta.key in blacklist:
            continue
        models_info.append({
            "key": meta.key,
            "verbose_name": meta.verbose_name or meta.key,
            "table_name": meta.table_name,
            "is_row_secure": meta.is_row_secure
        })

    # Список RPC-методов: объединяем методы из памяти и из БД
    rpc_list = []
    seen = set()

    # 1. Из памяти RPC_REGISTRY
    for name in sorted(RPC_REGISTRY.keys()):
        if name in seen:
            continue
        if not all and (name.startswith("crud.") or name.startswith("permissions.") or name in ("system.ping", "system.status", "system.ws_status")):
            continue
        seen.add(name)
        group = name.split(".")[0] if "." in name else "other"
        handler = RPC_REGISTRY.get(name)
        full_doc = ""
        first_line = ""
        params_info = {}
        if handler:
            full_doc = inspect.getdoc(handler) or getattr(handler, "__doc__", "") or ""
            if full_doc:
                lines = [l.strip() for l in full_doc.strip().split("\n") if l.strip()]
                if lines:
                    first_line = lines[0]
            if all:
                params_info = _inspect_handler_params(handler)

        is_fw_rpc = getattr(handler, "is_framework", None)
        if is_fw_rpc is None:
            is_fw_rpc = is_framework_handler(handler)
        is_fw_rpc = bool(is_fw_rpc)

        item = {
            "name": name,
            "group": group,
            "is_public": is_guest_rpc_allowed(name),
            "is_framework": is_fw_rpc,
            "description": first_line or f"RPC method {name}",
            "help": full_doc.strip(),
            "params": params_info or (_inspect_handler_params(handler) if handler else {})
        }
        rpc_list.append(item)

    # 2. Дополняем описаниями из БД
    async with system_db_session() as db:
            stmt = select(RpcPermission).order_by(RpcPermission.name)
            db_rpcs = (await db.execute(stmt)).scalars().all()
            db_rpc_map = {rp.name: rp for rp in db_rpcs}

            for rpc_item in rpc_list:
                db_item = db_rpc_map.get(rpc_item["name"])
                if db_item:
                    if db_item.description and not db_item.description.startswith("Обертка для") and not db_item.description.startswith("RPC method"):
                        rpc_item["description"] = db_item.description

            # Также добавляем методы из БД, которых еще не было в rpc_list
            for db_item in db_rpcs:
                if db_item.name not in seen:
                    if not all and (db_item.name.startswith("crud.") or db_item.name.startswith("permissions.")):
                        continue
                    if db_item.name not in RPC_REGISTRY and not db_item.name.endswith("*"):
                        continue
                    seen.add(db_item.name)
                    group = db_item.name.split(".")[0] if "." in db_item.name else "other"
                    handler = RPC_REGISTRY.get(db_item.name)
                    full_doc = ""
                    params_info = {}
                    if handler:
                        full_doc = inspect.getdoc(handler) or getattr(handler, "__doc__", "") or ""
                        if all:
                            params_info = _inspect_handler_params(handler)

                    is_fw_from_db = getattr(db_item, "is_framework", None)
                    if is_fw_from_db is None:
                        is_fw_from_db = is_framework_handler(handler)

                    item = {
                        "name": db_item.name,
                        "group": group,
                        "is_public": is_guest_rpc_allowed(db_item.name),
                        "is_framework": bool(is_fw_from_db),
                        "description": db_item.description or f"RPC method {db_item.name}",
                        "help": full_doc.strip()
                    }
                    if all:
                        item["params"] = params_info
                    rpc_list.append(item)

    # Сортируем RPC методы по группе и имени
    rpc_list.sort(key=lambda x: (x["group"], x["name"]))

    from pyferro.core.lib.config import settings
    allow_guests = bool(settings.security.get("allow_guests", True))

    return {
        "models": models_info,
        "rpc_methods": rpc_list,
        "allow_guests": allow_guests
    }


@rpc_method("permissions.get")
async def handle_permissions_get(
    session: JsonRpcSession,
    target_type: str,
    target_id: int = 0
) -> Dict[str, Any]:
    """Возвращает текущие права для роли, пользователя или гостей."""
    require_admin(session)
    if target_type not in ("role", "user", "guest"):
        raise RPCError(-32602, "Параметр 'target_type' должен быть 'role', 'user' или 'guest'")

    async with system_db_session() as db:
            if target_type == "guest":
                from pyferro.core.constants import GUEST_ROLE
                stmt_guest = select(Role).options(
                    selectinload(Role.permissions),
                    selectinload(Role.rpc_permissions)
                ).where(Role.name == GUEST_ROLE)
                guest_role = (await db.execute(stmt_guest)).scalar_one_or_none()
                if not guest_role:
                    guest_role = Role(name=GUEST_ROLE, description="Гость / Неавторизованный посетитель")
                    db.add(guest_role)
                    await db.commit()
                    await db.refresh(guest_role, ["permissions", "rpc_permissions"])

                crud_perms = {}
                for p in guest_role.permissions:
                    if p.can_read:
                        crud_perms[p.model_name] = {
                            "can_create": False,
                            "can_read": True,
                            "can_update": False,
                            "can_delete": False,
                            "read_global": True,
                            "update_global": False,
                            "delete_global": False,
                        }

                rpc_perms = {rp.name for rp in guest_role.rpc_permissions}
                from pyferro.core.lib.config import settings
                login_rpc = settings.security.get("login_rpc")
                for name in RPC_REGISTRY.keys():
                    if name.startswith("login.") or (bool(login_rpc) and name.startswith(login_rpc)):
                        rpc_perms.add(name)

                return {
                    "target_type": "guest",
                    "target_id": guest_role.id,
                    "target_name": "Гости",
                    "target_description": "Разрешения для незарегистрированных пользователей (роль guest)",
                    "is_immutable": False,
                    "crud_permissions": crud_perms,
                    "rpc_permissions": sorted(list(rpc_perms))
                }

            elif target_type == "role":
                stmt = select(Role).options(
                    selectinload(Role.permissions),
                    selectinload(Role.rpc_permissions)
                ).where(Role.id == target_id)
                role = (await db.execute(stmt)).scalar_one_or_none()
                if not role:
                    raise RPCError(-32004, f"Роль с ID {target_id} не найдена")

                crud_perms = {}
                for p in role.permissions:
                    crud_perms[p.model_name] = {
                        "can_create": p.can_create,
                        "can_read": p.can_read,
                        "can_update": p.can_update,
                        "can_delete": p.can_delete,
                        "read_global": getattr(p, "read_global", False),
                        "update_global": getattr(p, "update_global", False),
                        "delete_global": getattr(p, "delete_global", False),
                    }
                rpc_perms = [rp.name for rp in role.rpc_permissions]

                return {
                    "target_type": "role",
                    "target_id": role.id,
                    "target_name": role.name,
                    "target_description": role.description,
                    "is_immutable": role.name in ("admin", ADMIN_ROLE),
                    "crud_permissions": crud_perms,
                    "rpc_permissions": rpc_perms
                }

            elif target_type == "user":
                stmt = select(User).options(
                    selectinload(User.roles).selectinload(Role.permissions),
                    selectinload(User.roles).selectinload(Role.rpc_permissions),
                    selectinload(User.permissions),
                    selectinload(User.rpc_permissions)
                ).where(User.id == target_id)
                user = (await db.execute(stmt)).scalar_one_or_none()
                if not user:
                    raise RPCError(-32004, f"Пользователь с ID {target_id} не найден")

                # Унаследованные ролевые права
                inherited_crud = {}
                inherited_rpc = set()
                for r in user.roles:
                    for p in getattr(r, "permissions", []):
                        m = p.model_name
                        if m not in inherited_crud:
                            inherited_crud[m] = {
                                "can_create": False, "can_read": False,
                                "can_update": False, "can_delete": False,
                                "read_global": False, "update_global": False, "delete_global": False,
                            }
                        if p.can_create:
                            inherited_crud[m]["can_create"] = True
                        if p.can_read:
                            inherited_crud[m]["can_read"] = True
                            if getattr(p, "read_global", False):
                                inherited_crud[m]["read_global"] = True
                        if p.can_update:
                            inherited_crud[m]["can_update"] = True
                            if getattr(p, "update_global", False):
                                inherited_crud[m]["update_global"] = True
                        if p.can_delete:
                            inherited_crud[m]["can_delete"] = True
                            if getattr(p, "delete_global", False):
                                inherited_crud[m]["delete_global"] = True
                    for rp in getattr(r, "rpc_permissions", []):
                        inherited_rpc.add(rp.name)

                # Персональные надбавки
                personal_crud = {}
                for p in user.permissions:
                    personal_crud[p.model_name] = {
                        "can_create": p.can_create,
                        "can_read": p.can_read,
                        "can_update": p.can_update,
                        "can_delete": p.can_delete,
                        "read_global": getattr(p, "read_global", False),
                        "update_global": getattr(p, "update_global", False),
                        "delete_global": getattr(p, "delete_global", False),
                    }
                personal_rpc = [rp.name for rp in user.rpc_permissions]

                return {
                    "target_type": "user",
                    "target_id": user.id,
                    "target_name": user.login or user.name,
                    "target_roles": [r.name for r in user.roles],
                    "is_superadmin": user.is_superadmin,
                    "inherited_crud": inherited_crud,
                    "inherited_rpc": sorted(list(inherited_rpc)),
                    "personal_crud": personal_crud,
                    "personal_rpc": sorted(personal_rpc),
                    "effective_crud": user._get_permissions_dict(),
                    "effective_rpc": sorted(list(user.get_allowed_rpc_methods()))
                }



@rpc_method("permissions.save")
async def handle_permissions_save(
    session: JsonRpcSession,
    target_type: str,
    target_id: int = 0,
    crud_permissions: Optional[Dict[str, Dict[str, Any]]] = None,
    rpc_permissions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Атомарно сохраняет CRUD и RPC права для роли, пользователя или гостей."""
    require_admin(session)
    if target_type not in ("role", "user", "guest"):
        raise RPCError(-32602, "Параметр 'target_type' должен быть 'role', 'user' или 'guest'")

    crud_permissions = crud_permissions or {}
    rpc_permissions = rpc_permissions or []

    async with system_db_session() as db:
            if target_type == "guest":
                from pyferro.core.constants import GUEST_ROLE
                from pyferro.core.lib.config import settings
                login_rpc = settings.security.get("login_rpc")

                stmt_guest = select(Role).options(
                    selectinload(Role.permissions),
                    selectinload(Role.rpc_permissions)
                ).where(Role.name == GUEST_ROLE)
                guest_role = (await db.execute(stmt_guest)).scalar_one_or_none()
                if not guest_role:
                    guest_role = Role(name=GUEST_ROLE, description="Гость / Неавторизованный посетитель")
                    db.add(guest_role)
                    await db.commit()
                    stmt_guest = select(Role).options(
                        selectinload(Role.permissions),
                        selectinload(Role.rpc_permissions)
                    ).where(Role.name == GUEST_ROLE)
                    guest_role = (await db.execute(stmt_guest)).scalar_one()

                # 1. Обновляем RPC-права для роли guest
                final_rpc_names = set(rpc_permissions)
                for name in RPC_REGISTRY.keys():
                    if name.startswith("login.") or (bool(login_rpc) and name.startswith(login_rpc)):
                        final_rpc_names.add(name)

                stmt_rpc = select(RpcPermission).where(RpcPermission.name.in_(final_rpc_names))
                rpc_objs = list((await db.execute(stmt_rpc)).scalars().all())
                existing_names = {rp.name for rp in rpc_objs}

                for m_name in final_rpc_names:
                    if m_name not in existing_names:
                        new_rp = RpcPermission(name=m_name, description=f"Метод {m_name}")
                        db.add(new_rp)
                        rpc_objs.append(new_rp)

                guest_role.rpc_permissions = rpc_objs

                # 2. Обновляем CRUD-права для роли guest (строго только can_read)
                for old_p in list(guest_role.permissions):
                    await db.delete(old_p)
                guest_role.permissions.clear()

                for m_name, p_data in crud_permissions.items():
                    if p_data.get("can_read"):
                        perm_obj = RolePermission(
                            role_id=guest_role.id,
                            model_name=m_name,
                            can_create=False,
                            can_read=True,
                            can_update=False,
                            can_delete=False,
                            read_global=True,
                            update_global=False,
                            delete_global=False
                        )
                        db.add(perm_obj)

                await db.commit()
                from .discovery import reload_guest_permissions_cache
                await reload_guest_permissions_cache()
                return {"success": True}

            # Получаем или синхронизируем объекты RpcPermission
            rpc_objs = []
            if rpc_permissions:
                stmt_rpc = select(RpcPermission).where(RpcPermission.name.in_(rpc_permissions))
                rpc_objs = list((await db.execute(stmt_rpc)).scalars().all())

            if target_type == "role":
                stmt = select(Role).options(
                    selectinload(Role.permissions),
                    selectinload(Role.rpc_permissions)
                ).where(Role.id == target_id)
                role = (await db.execute(stmt)).scalar_one_or_none()
                if not role:
                    raise RPCError(-32004, f"Роль с ID {target_id} не найдена")
                if role.name in ("admin", ADMIN_ROLE):
                    raise RPCError(-32000, "Права роли 'admin' неизменяемы.")

                # Удаляем старые разрешения
                for old_p in list(role.permissions):
                    await db.delete(old_p)
                role.permissions.clear()

                # Создаем новые разрешения для непустых записей
                for m_name, p_data in crud_permissions.items():
                    if any(p_data.get(k) for k in ("can_create", "can_read", "can_update", "can_delete")):
                        new_p = RolePermission(
                            role_id=role.id,
                            model_name=m_name,
                            can_create=bool(p_data.get("can_create", False)),
                            can_read=bool(p_data.get("can_read", False)),
                            can_update=bool(p_data.get("can_update", False)),
                            can_delete=bool(p_data.get("can_delete", False)),
                            read_global=bool(p_data.get("read_global", False)),
                            update_global=bool(p_data.get("update_global", False)),
                            delete_global=bool(p_data.get("delete_global", False)),
                        )
                        db.add(new_p)

                role.rpc_permissions = rpc_objs

            elif target_type == "user":
                stmt = select(User).options(
                    selectinload(User.permissions),
                    selectinload(User.rpc_permissions)
                ).where(User.id == target_id)
                user = (await db.execute(stmt)).scalar_one_or_none()
                if not user:
                    raise RPCError(-32004, f"Пользователь с ID {target_id} не найден")

                # Удаляем старые персональные разрешения
                for old_p in list(user.permissions):
                    await db.delete(old_p)
                user.permissions.clear()

                # Создаем новые персональные разрешения
                for m_name, p_data in crud_permissions.items():
                    if any(p_data.get(k) for k in ("can_create", "can_read", "can_update", "can_delete")):
                        new_p = UserPermission(
                            user_id=user.id,
                            model_name=m_name,
                            can_create=bool(p_data.get("can_create", False)),
                            can_read=bool(p_data.get("can_read", False)),
                            can_update=bool(p_data.get("can_update", False)),
                            can_delete=bool(p_data.get("can_delete", False)),
                            read_global=bool(p_data.get("read_global", False)),
                            update_global=bool(p_data.get("update_global", False)),
                            delete_global=bool(p_data.get("delete_global", False)),
                        )
                        db.add(new_p)

                user.rpc_permissions = rpc_objs

            await db.commit()

            # Горячая перезагрузка прав для всех открытых WebSocket-сессий
            try:
                from pyferro.auth.auditor import reload_active_sessions_permissions
                await reload_active_sessions_permissions()
            except Exception:
                pass

            # Оповещаем подписчиков через broadcast
            try:
                from pyferro.broadcast import broadcast_notification
                await broadcast_notification("permissions.updated", {
                    "target_type": target_type,
                    "target_id": target_id
                })
            except Exception:
                pass

            return {"success": True, "target_type": target_type, "target_id": target_id}


@rpc_method("permissions.audit_access")
async def handle_permissions_audit_access(
    session: JsonRpcSession,
    target_type: str,
    target_id: int = 0,
) -> Dict[str, Any]:
    """
    Аудит реального доступа к RPC и CRUD через живое WS/HTTP-соединение.

    Подключается под целевым пользователем (без знания его пароля через сервисный токен и HTTP Cookie),
    ролью или гостем, проверяет все методы в режиме check_access=True (без запуска обработчиков)
    и сверяет фактический ответ сокета с базой данных CRUD.
    """
    require_admin(session)

    if target_type not in ("role", "user", "guest"):
        raise RPCError(-32602, "Параметр target_type должен быть 'role', 'user' или 'guest'")

    try:
        from pyferro.auth.auditor import audit_target_permissions
        return await audit_target_permissions(target_type=target_type, target_id=int(target_id or 0))
    except ValueError as ve:
        raise RPCError(-32004, str(ve))
    except Exception as e:
        raise RPCError(-32000, f"Ошибка аудита прав доступа: {e}")
