# -*- coding: utf-8 -*-
"""
pyferro.core.identity: Единый строгий контракт идентичности пользователя и сессии.
Устраняет зоопарк синонимов (user_id/uid/sub, username/login, role/roles)
и защитный мусор (defensive clutter) по всему фреймворку.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Optional, Any, List


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """
    Канонический неизменяемый объект идентичности пользователя.
    """
    user_id: Optional[int] = None
    username: str = "guest"
    roles: Tuple[str, ...] = ("user",)
    is_superadmin: bool = False
    permissions: Tuple[str, ...] = ()
    team_ids: Tuple[int, ...] = ()
    session_db_id: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def role(self) -> str:
        """Основная (первая) роль пользователя."""
        return self.roles[0] if self.roles else "user"

    @property
    def is_admin(self) -> bool:
        """Проверяет, обладает ли пользователь полными правами системного администратора."""
        if self.is_superadmin:
            return True
        for r in self.roles:
            r_lower = r.lower()
            if r_lower in ("admin", "superadmin", "administrator", "adm_all"):
                return True
        return False

    @property
    def has_admin_access(self) -> bool:
        """Проверяет, имеет ли пользователь доступ хотя бы к одному разделу админки (admin или adm_*)."""
        return self.is_admin or any(r.startswith("adm_") for r in self.roles)

    # Совместимость со старыми вызовами
    @property
    def uid(self) -> Optional[int]:
        return self.user_id

    @property
    def id(self) -> Optional[int]:
        return self.user_id

    @property
    def user_name(self) -> str:
        return self.username

    @property
    def login(self) -> str:
        return self.username

    @property
    def user_role(self) -> str:
        return self.role

    @property
    def user_roles(self) -> List[str]:
        return list(self.roles)


def get_session_identity(session_or_obj: Any) -> Optional[UserIdentity]:
    """
    Единая каноническая функция извлечения UserIdentity из любого объекта сессии:
    JsonRpcSession, AuthSession, словаря get_crud_session или тестового мока.
    """
    if session_or_obj is None:
        return None

    if isinstance(session_or_obj, UserIdentity):
        return session_or_obj

    # 1. Прямое свойство identity у объекта (JsonRpcSession, AuthSession)
    identity_attr = getattr(session_or_obj, "identity", None)
    if isinstance(identity_attr, UserIdentity):
        return identity_attr

    # 2. Поле data (например, transport.data = AuthSession)
    data = getattr(session_or_obj, "data", None)
    if data is not None:
        if isinstance(data, UserIdentity):
            return data
        data_ident = getattr(data, "identity", None)
        if isinstance(data_ident, UserIdentity):
            return data_ident

    # 3. Словарь (например, из get_crud_session или кэша сессий)
    target_dict = None
    if isinstance(session_or_obj, dict):
        target_dict = session_or_obj
    elif isinstance(data, dict):
        target_dict = data

    if target_dict is not None:
        raw_uid = (
            target_dict.get("user_id")
            if target_dict.get("user_id") is not None
            else (
                target_dict.get("uid")
                if target_dict.get("uid") is not None
                else (target_dict.get("id") if target_dict.get("id") is not None else target_dict.get("sub"))
            )
        )
        username = (
            target_dict.get("username")
            or target_dict.get("login")
            or target_dict.get("user_name")
        )
        raw_roles = target_dict.get("roles") or target_dict.get("user_roles")
        raw_role = target_dict.get("role") or target_dict.get("user_role")

        if raw_uid is not None or username is not None or raw_roles is not None or raw_role is not None:
            try:
                user_id = int(raw_uid) if raw_uid is not None else None
                uname = str(username or (f"user_{user_id}" if user_id else "guest"))
                if raw_roles:
                    roles = tuple(str(r) for r in raw_roles)
                else:
                    role_val = raw_role or ("admin" if target_dict.get("is_superadmin") else "user")
                    roles = (str(role_val),)
                raw_super = target_dict.get("is_superadmin")
                is_super = bool(
                    (raw_super is True or (isinstance(raw_super, str) and raw_super.lower() in ("true", "1")))
                    or any(str(r).lower() in ("admin", "superadmin", "administrator") for r in roles)
                )
                return UserIdentity(
                    user_id=user_id,
                    username=uname,
                    roles=roles,
                    is_superadmin=is_super,
                )
            except (ValueError, TypeError):
                pass

    # 4. Проверка поля user (например, MockSeoSession или SQLAlchemy User)
    user_obj = getattr(session_or_obj, "user", None) if not isinstance(session_or_obj, dict) else None
    if user_obj is not None and not hasattr(user_obj, "_mock_return_value"):
        u_roles = getattr(user_obj, "roles", None)
        if isinstance(u_roles, (list, tuple, set)):
            roles = tuple(getattr(r, "name", str(r)) for r in u_roles)
            u_id = getattr(user_obj, "id", None)
            u_name = getattr(user_obj, "login", None) or getattr(user_obj, "name", "user")
            u_super = getattr(user_obj, "is_superadmin", False) is True
            return UserIdentity(
                user_id=int(u_id) if isinstance(u_id, (int, str)) and not isinstance(u_id, bool) else None,
                username=str(u_name),
                roles=roles,
                is_superadmin=u_super or any(str(r).lower() in ("admin", "superadmin", "administrator") for r in roles),
            )

    # 5. Тестовые моки или duck-typing объекты с user_id / role / roles
    candidates = [data, session_or_obj] if data is not None else [session_or_obj]
    for target_obj in candidates:
        if target_obj is None:
            continue

        raw_uid = getattr(target_obj, "user_id", None)
        if not (isinstance(raw_uid, (int, str)) and not isinstance(raw_uid, bool)):
            raw_uid = getattr(target_obj, "uid", None)
            if not (isinstance(raw_uid, (int, str)) and not isinstance(raw_uid, bool)):
                raw_uid = getattr(target_obj, "id", None)
                if not (isinstance(raw_uid, (int, str)) and not isinstance(raw_uid, bool)):
                    raw_uid = None

        raw_uname = getattr(target_obj, "username", None)
        if not isinstance(raw_uname, str):
            raw_uname = getattr(target_obj, "user_name", None)
            if not isinstance(raw_uname, str):
                raw_uname = None

        raw_roles = getattr(target_obj, "roles", None)
        if not isinstance(raw_roles, (list, tuple, set)):
            raw_roles = getattr(target_obj, "user_roles", None)
            if not isinstance(raw_roles, (list, tuple, set)):
                raw_roles = None

        raw_role = getattr(target_obj, "role", None)
        if not isinstance(raw_role, str):
            raw_role = getattr(target_obj, "user_role", None)
            if not isinstance(raw_role, str):
                raw_role = None

        if raw_uid is not None or raw_uname is not None or raw_roles is not None or raw_role is not None:
            try:
                uid = int(raw_uid) if raw_uid is not None else None
                uname = str(raw_uname or (f"user_{uid}" if uid else "guest"))
                if raw_roles:
                    roles = tuple(getattr(r, "name", str(r)) for r in raw_roles)
                else:
                    roles = (str(raw_role),) if raw_role else ("user",)
                raw_super = getattr(target_obj, "is_superadmin", False)
                is_super = bool(
                    (raw_super is True or (isinstance(raw_super, str) and raw_super.lower() in ("true", "1")))
                    or any(str(r).lower() in ("admin", "superadmin", "administrator") for r in roles)
                )
                return UserIdentity(
                    user_id=uid,
                    username=uname,
                    roles=roles,
                    is_superadmin=is_super,
                )
            except (ValueError, TypeError):
                pass

    return None
