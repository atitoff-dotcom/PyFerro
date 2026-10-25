# -*- coding: utf-8 -*-
"""
Базовые классы и контексты плагина авторизации (plugins/auth/core.py).
Обеспечивают Row-Level Security (RLS) на уровне ORM SQLAlchemy.
"""

from contextvars import ContextVar
from typing import Optional, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column, declared_attr
from sqlalchemy import Integer, DateTime, func

from pyferro.db import Base
from pyferro.core.session import current_user_ctx
from pyferro.core.identity import UserIdentity

# Контекстная переменная для обхода проверок прав системными операциями (Bypass)
system_bypass_ctx: ContextVar[bool] = ContextVar("system_bypass", default=False)


class BasicSecureModel(Base):
    """
    Базовый класс для моделей с проверкой прав на уровне модели (без row-level полей).
    """
    __abstract__ = True

    @declared_attr
    def __table_args__(cls):
        return {"extend_existing": True}


class RowSecureModel(BasicSecureModel):
    """
    Расширение с поддержкой row-level разграничения прав (содержит id, creator_id, team_id).
    """
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    team_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc)
    )


class AuthSession:
    """
    Канонический объект сессии пользователя, привязанный к WebSocket-соединению.
    """
    def __init__(
        self,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        roles: Optional[list] = None,
        user: Any = None,
        session_db_id: int = 0,
        user_ctx: Any = None,
        allowed_rpc_methods: Any = None,
        send_request_cb: Any = None,
        send_stream_cb: Any = None,
        close_cb: Any = None,
        is_superadmin: Optional[bool] = None,
        uid: Optional[int] = None,
        user_name: Optional[str] = None,
        user_role: Optional[str] = None,
        user_roles: Optional[list] = None,
    ):
        raw_uid = user_id if user_id is not None else uid
        self.user_id = int(raw_uid) if raw_uid is not None else 0
        self.username = str(username or user_name or (f"user_{self.user_id}" if self.user_id else "guest"))
        effective_roles = roles if roles is not None else (user_roles if user_roles is not None else None)
        if effective_roles:
            self.roles = list(effective_roles)
        else:
            r = user_role or "user"
            self.roles = [r]
        self.role = self.roles[0] if self.roles else "user"
        self.user = user
        self.session_db_id = session_db_id
        self.user_ctx = user_ctx
        self.allowed_rpc_methods = set(allowed_rpc_methods) if allowed_rpc_methods else set()
        self._send_request_cb = send_request_cb
        self._send_stream_cb = send_stream_cb
        self._close_cb = close_cb

        if is_superadmin is not None:
            self._is_superadmin = bool(is_superadmin)
        elif self.user_ctx and getattr(self.user_ctx, 'is_superadmin', False):
            self._is_superadmin = True
        else:
            self._is_superadmin = (
                "admin" in self.roles
                or "ADMIN" in self.roles
                or self.role in ("admin", "ADMIN", "superadmin")
            )

    @property
    def identity(self) -> UserIdentity:
        return UserIdentity(
            user_id=self.user_id,
            username=self.username,
            roles=tuple(self.roles),
            is_superadmin=self.is_superadmin,
            session_db_id=self.session_db_id,
        )

    # Синонимы для обратной совместимости
    @property
    def uid(self) -> int:
        return self.user_id

    @property
    def user_name(self) -> str:
        return self.username

    @property
    def user_role(self) -> str:
        return self.role

    @property
    def user_roles(self) -> list:
        return self.roles

    @property
    def authenticated(self) -> bool:
        return True

    @property
    def role_name(self) -> str:
        return self.role

    @property
    def is_superadmin(self) -> bool:
        return self._is_superadmin

    @property
    def is_admin(self) -> bool:
        return self._is_superadmin or any(r in ("admin", "ADMIN") or r.startswith("adm_") for r in self.roles)

    def has_rpc_permission(self, method_name: str) -> bool:
        """Проверяет право на вызов RPC-метода (O(1) in-memory)."""
        if self.is_superadmin:
            return True
        if "admin" in self.roles or self.role == "admin":
            return True
        if "*" in self.allowed_rpc_methods or method_name in self.allowed_rpc_methods:
            return True
        for m in self.allowed_rpc_methods:
            if m.endswith(".*") and method_name.startswith(m[:-1]):
                return True
        return False

    @property
    def session_id(self) -> int:
        """Возвращает ID текущего транспортного сокета или идентификатор сессии из БД."""
        try:
            from pyferro.core.session import current_transport_ctx
            transport = current_transport_ctx.get()
            if transport and hasattr(transport, "session_id"):
                return transport.session_id
        except Exception:
            pass
        return getattr(self, "session_db_id", 0)

    async def send_notification(self, method: str, params: Optional[dict] = None) -> None:
        """Отправляет асинхронное push-уведомление клиенту через активный WebSocket."""
        try:
            from pyferro.core.session import current_transport_ctx
            transport = current_transport_ctx.get()
            if transport and hasattr(transport, "send_notification"):
                return await transport.send_notification(method, params or {})
        except Exception as e:
            from pyferro.core.logger import logger
            logger.warning(f"[AuthSession] Ошибка отправки уведомления {method}: {e}")

    async def send_request(self, method: str, params: dict = None, timeout: float = 5.0):
        if self._send_request_cb:
            return await self._send_request_cb(method, params, timeout=timeout)
        raise ConnectionError("No transport available")

    async def send_stream(self, rpc_id: Any, chunk: Any):
        if self._send_stream_cb:
            return await self._send_stream_cb(rpc_id, chunk)

    async def send_stream_chunk(self, rpc_id: Any, chunk: Any):
        """Алиас для send_stream для соответствия контракту session.send_stream_chunk."""
        return await self.send_stream(rpc_id, chunk)

    async def close(self):
        if self._close_cb:
            return await self._close_cb()


# Регистрируем SQLAlchemy event listeners для автоматического контроля прав на уровне ORM
from . import security  # noqa: F401
