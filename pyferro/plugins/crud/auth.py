# -*- coding: utf-8 -*-
"""
pyferro.plugins.crud.auth: Аутентификация и управление сессиями для панели CRUD.
Обеспечивает бесшовную SSO-интеграцию с приложением и изоляцию панели (Zero-Leakage).
"""

from __future__ import annotations
import secrets
from typing import Dict, Any, Optional, Callable

# Реестр активных сессий администраторов CRUD: token -> {username, role, ...}
_ACTIVE_CRUD_SESSIONS: Dict[str, Dict[str, Any]] = {}

# Пользовательский верификатор сессионного токена из основного приложения: fn(token) -> Optional[dict]
_crud_session_validator: Optional[Callable[[str], Any]] = None


def set_crud_session_validator(func: Callable[[str], Any]) -> None:
    """Устанавливает функцию валидации сессионного токена из основного приложения fn(token) -> user_info."""
    global _crud_session_validator
    _crud_session_validator = func


def get_crud_session_validator() -> Optional[Callable[[str], Any]]:
    """Возвращает текущую функцию валидации сессий."""
    return _crud_session_validator


def create_crud_session(user_info: Dict[str, Any], token: Optional[str] = None) -> str:
    """Создает или регистрирует защищенный токен сессии администратора."""
    if not token:
        token = secrets.token_hex(24)
    _ACTIVE_CRUD_SESSIONS[token] = user_info
    return token


_in_validator: bool = False


def get_crud_session(token: str) -> Optional[Dict[str, Any]]:
    """Возвращает информацию о сессии по токену через локальный кэш, системный SSO валидатор или нативный JWT."""
    global _in_validator
    if not token:
        return None
    if token in _ACTIVE_CRUD_SESSIONS:
        return _ACTIVE_CRUD_SESSIONS[token]

    # 1. Пользовательский SSO валидатор с защитой от рекурсии
    if _crud_session_validator and not _in_validator:
        _in_validator = True
        try:
            res = _crud_session_validator(token)
            if res:
                return res
        except Exception:
            pass
        finally:
            _in_validator = False

    # 2. Нативная валидация JWT токенов фреймворка PyFerro из коробки
    try:
        from pyferro.core.security import decode_access_token
        payload = decode_access_token(token)
        if payload:
            roles = payload.get("roles", [])
            role = payload.get("role") or (roles[0] if roles else "user")
            is_superadmin = bool(
                "admin" in roles
                or "ADMIN" in roles
                or "superadmin" in roles
                or payload.get("is_superadmin")
                or role in ("admin", "ADMIN", "superadmin")
            )
            raw_sub = payload.get("sub")
            if raw_sub is None or not str(raw_sub).isdigit() or int(raw_sub) <= 0:
                return None
            uid = int(raw_sub)
            return {
                "uid": uid,
                "user_id": uid,
                "username": payload.get("username", "admin" if is_superadmin else "user"),
                "role": "admin" if is_superadmin else role,
                "roles": roles if roles else [role],
                "is_superadmin": is_superadmin,
                "perms_dict": payload.get("permissions") or payload.get("perms_dict") or {},
                "allowed_rpc_methods": {"*"} if is_superadmin else set(payload.get("allowed_rpc_methods", [])),
            }
    except Exception:
        pass

    return None


async def get_crud_session_async(token: str) -> Optional[Dict[str, Any]]:
    """
    Асинхронно возвращает сессию администратора.
    1. Проверяет быстрый путь (память, SSO валидатор, JWT).
    2. При отсутствии или истечении JWT делает fallback-проверку в базе данных (таблица RefreshToken),
       точно так же, как WebSocket auto_auth, и кэширует результат в память.
    """
    if not token:
        return None

    sdata = get_crud_session(token)
    if sdata:
        return sdata

    try:
        from datetime import datetime, timezone
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from pyferro.db import system_db_session
        from pyferro.auth.models import User, Role, RefreshToken

        async with system_db_session() as db:
            stmt_rt = select(RefreshToken).where(
                RefreshToken.token == token,
                RefreshToken.expires_at > datetime.now(timezone.utc)
            )
            rt_obj = (await db.execute(stmt_rt)).scalar_one_or_none()
            if not rt_obj:
                return None

            stmt_user = select(User).options(
                selectinload(User.roles).selectinload(Role.permissions),
                selectinload(User.roles).selectinload(Role.rpc_permissions),
                selectinload(User.teams),
                selectinload(User.permissions),
                selectinload(User.rpc_permissions),
                selectinload(User.delegations_received),
            ).where(User.id == rt_obj.user_id)
            user = (await db.execute(stmt_user)).scalar_one_or_none()
            if not user:
                return None

            raw_roles = [r.name for r in user.roles] if user.roles else []
            admin_scopes = user.get_admin_roles() if hasattr(user, "get_admin_roles") else set()
            is_superadmin = getattr(user, "is_superadmin", False)
            if is_superadmin:
                role_names = ["admin"]
                role_name = "admin"
            else:
                role_names = list(set(raw_roles) | admin_scopes) if (raw_roles or admin_scopes) else ["user"]
                role_name = raw_roles[0] if raw_roles else (sorted(admin_scopes)[0] if admin_scopes else "user")

            is_admin = bool(
                is_superadmin
                or role_name in ("admin", "ADMIN")
                or "admin" in role_names
                or "ADMIN" in role_names
                or any(isinstance(r, str) and (r == "admin" or r.startswith("adm_")) for r in role_names)
            )
            if not is_admin:
                return None

            perms = user._get_permissions_dict() if hasattr(user, "_get_permissions_dict") else {}
            allowed_rpc = {"*"} if is_superadmin else (user.get_permissions().allowed_rpc_methods if hasattr(user, "get_permissions") else {"*"})
            user_info = {
                "uid": user.id,
                "user_id": user.id,
                "username": user.login,
                "role": role_name,
                "roles": role_names,
                "is_superadmin": is_superadmin,
                "perms_dict": perms,
                "allowed_rpc_methods": allowed_rpc,
            }
            create_crud_session(user_info, token=token)
            return user_info
    except Exception:
        return None


def revoke_crud_session(token: str) -> None:
    """Завершает сессию администратора."""
    if token:
        _ACTIVE_CRUD_SESSIONS.pop(token, None)
