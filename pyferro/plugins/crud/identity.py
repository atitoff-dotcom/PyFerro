# -*- coding: utf-8 -*-
"""
Протокол провайдера идентификации и контекст доступа для CRUD-плагина.
Позволяет отвязать плагин от конкретных моделей пользователей/команд проекта.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Set, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession


class IdentityProvider(Protocol):
    """
    Интерфейс поставщика идентификации и полномочий.
    Плагин CRUD не зависит от конкретных моделей User, Team или структуры БД проекта.
    """
    def user_id(self, session: Any) -> Optional[int]:
        """Извлекает user_id из текущей сессии."""
        ...

    def user_name(self, session: Any) -> str:
        """Извлекает отображаемое имя пользователя из сессии."""
        ...

    def is_superuser(self, user_id: Optional[int]) -> bool:
        """Проверяет, обладает ли пользователь полным административным доступом."""
        ...

    def has_permission(self, user_id: Optional[int], perm: str) -> bool:
        """Проверяет наличие атомарного права (capability) или wildcard-маски."""
        ...

    async def effective_user_ids(self, user_id: int, model_name: str, db: AsyncSession) -> Set[int]:
        """
        Возвращает множество ID пользователей, чьи записи текущий пользователь
        имеет право обрабатывать (сам пользователь + активные замещения).
        """
        ...

    async def user_team_ids(self, user_id: int, db: AsyncSession) -> Set[int]:
        """Возвращает множество ID активных команд пользователя."""
        ...

    async def primary_team_id(self, user_id: int, db: AsyncSession) -> Optional[int]:
        """Возвращает ID основной команды пользователя."""
        ...

class DefaultIdentityProvider:
    """
    Стандартный провайдер идентификации на базе контекста сессий PyFerro auth.
    Используется по умолчанию, если приложение не зарегистрировало свой провайдер.
    """
    def user_id(self, session: Any) -> Optional[int]:
        from pyferro.core.identity import get_session_identity
        ident = get_session_identity(session)
        if ident and ident.user_id is not None:
            return ident.user_id
        cookies = getattr(session, "cookies", None)
        if cookies and isinstance(cookies, dict):
            from pyferro.core.http import extract_session_token
            token = extract_session_token(cookies)
            if token:
                from pyferro.plugins.crud.auth import get_crud_session
                sdata = get_crud_session(token)
                if sdata:
                    token_identity = get_session_identity(sdata)
                    if token_identity and token_identity.user_id is not None:
                        return token_identity.user_id
        from pyferro.core.session import current_transport_ctx
        transport = current_transport_ctx.get()
        if transport and transport is not session:
            ident = get_session_identity(transport)
            if ident and ident.user_id is not None:
                return ident.user_id
        return None

    def user_name(self, session: Any) -> str:
        from pyferro.core.identity import get_session_identity
        ident = get_session_identity(session)
        if ident:
            return ident.username
        from pyferro.core.session import current_transport_ctx
        transport = current_transport_ctx.get()
        if transport and transport is not session:
            ident = get_session_identity(transport)
            if ident:
                return ident.username
        return "anonymous"

    def is_superuser(self, session: Any = None) -> bool:
        from pyferro.core.identity import get_session_identity
        ident = get_session_identity(session)
        if ident and ident.is_admin:
            return True
        cookies = getattr(session, "cookies", None)
        if cookies and isinstance(cookies, dict):
            from pyferro.core.http import extract_session_token
            token = extract_session_token(cookies)
            if token:
                from pyferro.plugins.crud.auth import get_crud_session
                sdata = get_crud_session(token)
                if sdata:
                    token_identity = get_session_identity(sdata)
                    if token_identity and token_identity.is_admin:
                        return True
        from pyferro.core.session import current_transport_ctx
        transport = current_transport_ctx.get()
        if transport and transport is not session:
            ident = get_session_identity(transport)
            if ident and ident.is_admin:
                return True
        return False
    def has_permission(self, user_id: Optional[int], perm: str) -> bool:
        if self.is_superuser(user_id):
            return True
        from pyferro.core.session import current_transport_ctx, current_user_ctx
        transport = current_transport_ctx.get()
        data = getattr(transport, "data", None) if transport else None
        user_ctx = getattr(data, "user_ctx", None) if data else None
        if not user_ctx:
            curr_u = current_user_ctx.get()
            if curr_u:
                user_ctx = curr_u
        if user_ctx and getattr(user_ctx, "is_superadmin", False):
            return True

        action = perm.split(":")[-1] if ":" in perm else perm
        model_part = perm.split(":")[0] if ":" in perm else ""

        # 1. Проверка плоского множества permissions (для обратной совместимости)
        perms = None
        if data:
            perms = getattr(data, "permissions", None) or getattr(data, "user_permissions", None)
        if perms and isinstance(perms, (set, list, tuple)):
            if "*" in perms or perm in perms:
                return True
            if ":" in perm:
                model_prefix = perm.split(":")[0] + ":*"
                if model_prefix in perms:
                    return True

        # 2. Проверка гранулярной матрицы прав perms_dict
        perms_dict = getattr(user_ctx, "perms_dict", None) if user_ctx else None
        if perms_dict is None and isinstance(data, dict):
            perms_dict = data.get("perms_dict")
            if not perms_dict and isinstance(data.get("permissions"), dict):
                perms_dict = data.get("permissions")

        if perms_dict is not None and isinstance(perms_dict, dict):
            model_perms = perms_dict.get(model_part)
            if not model_perms:
                try:
                    from pyferro.plugins.crud import ModelRegistry
                    meta = ModelRegistry.get(model_part)
                    if meta:
                        model_perms = (
                            perms_dict.get(meta.key)
                            or perms_dict.get(meta.model_cls.__name__)
                            or perms_dict.get(meta.table_name)
                        )
                except Exception:
                    pass
            if model_perms and isinstance(model_perms, dict):
                if action in ("read", "list", "get"):
                    return bool(model_perms.get("can_read") or model_perms.get("read_global"))
                if action == "view_all":
                    return bool(model_perms.get("read_global", False))
                if action in ("create",):
                    return bool(model_perms.get("can_create", False))
                if action in ("update", "update_cell", "bulk_update"):
                    return bool(model_perms.get("can_update") or model_perms.get("update_global"))
                if action == "update_all":
                    return bool(model_perms.get("update_global", False))
                if action in ("delete",):
                    return bool(model_perms.get("can_delete") or model_perms.get("delete_global"))
                if action == "delete_all":
                    return bool(model_perms.get("delete_global", False))
                if action == "transfer":
                    return bool(model_perms.get("update_global", False))
                if action == "*":
                    return bool(
                        model_perms.get("can_read")
                        and model_perms.get("can_create")
                        and model_perms.get("can_update")
                        and model_perms.get("can_delete")
                    )
                return False
            else:
                return False

        # 3. Базовый доступ для прикладных моделей
        if user_id is not None:
            if action in ("read", "create", "update", "delete", "list", "get"):
                return True
        return False


    async def effective_user_ids(self, user_id: int, model_name: str, db: AsyncSession) -> Set[int]:
        if user_id is None:
            return set()
        ids = {user_id}
        try:
            from pyferro.auth.models import UserDelegation
            from sqlalchemy import select, or_
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            stmt = select(UserDelegation.from_user_id).where(
                UserDelegation.to_user_id == user_id,
                UserDelegation.is_active == True,
                or_(UserDelegation.valid_from == None, UserDelegation.valid_from <= now),
                or_(UserDelegation.valid_to == None, UserDelegation.valid_to >= now),
                or_(UserDelegation.model_name == None, UserDelegation.model_name == model_name)
            )
            delegated = (await db.execute(stmt)).scalars().all()
            ids.update(delegated)
        except Exception:
            pass
        return ids

    async def user_team_ids(self, user_id: int, db: AsyncSession) -> Set[int]:
        if user_id is None:
            return set()
        try:
            from pyferro.auth.models import User
            user = await db.get(User, user_id)
            if user:
                return set(user.get_team_ids())
        except Exception:
            pass
        return set()

    async def primary_team_id(self, user_id: int, db: AsyncSession) -> Optional[int]:
        if user_id is None:
            return None
        try:
            from pyferro.auth.models import User
            user = await db.get(User, user_id)
            if user:
                return user.primary_team_id
        except Exception:
            pass
        return None


@dataclass
class AccessContext:
    """
    Контекст доступа текущего запроса.
    Собирается один раз за вызов хендлера и предотвращает повторные обращения к БД.
    """
    user_id: Optional[int]
    user_name: str
    is_superuser: bool
    effective_user_ids: Set[int] = field(default_factory=set)
    user_team_ids: Set[int] = field(default_factory=set)
    primary_team_id: Optional[int] = None
    _provider: Optional[IdentityProvider] = None

    def has_permission(self, perm: str) -> bool:
        if self.is_superuser:
            return True
        if self._provider:
            return self._provider.has_permission(self.user_id, perm)
        return False


async def create_access_context(
    provider: IdentityProvider,
    session: Any,
    model_name: str,
    db: AsyncSession
) -> AccessContext:
    """Создает предвычисленный контекст доступа для текущего запроса."""
    from pyferro.core.constants import ADMIN_ROLE
    uid = provider.user_id(session)
    u_name = provider.user_name(session)
    is_super = provider.is_superuser(uid)

    if not is_super and session:
        role = getattr(session, "user_role", None) or getattr(getattr(session, "data", None), "user_role", None)
        if hasattr(role, "value"):
            role = role.value
        if role in ("admin", "ADMIN", ADMIN_ROLE):
            is_super = True
        roles = getattr(session, "user_roles", [])
        for r in roles:
            val = r.value if hasattr(r, "value") else r
            if val in ("admin", "ADMIN", ADMIN_ROLE):
                is_super = True
                break

    if is_super or uid is None:
        eff_ids = {uid} if uid is not None else set()
        t_ids = set()
        p_team = None
    else:
        eff_ids = await provider.effective_user_ids(uid, model_name, db)
        t_ids = await provider.user_team_ids(uid, db)
        p_team = await provider.primary_team_id(uid, db)

    return AccessContext(
        user_id=uid,
        user_name=u_name,
        is_superuser=is_super,
        effective_user_ids=eff_ids,
        user_team_ids=t_ids,
        primary_team_id=p_team,
        _provider=provider
    )
