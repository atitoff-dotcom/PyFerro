"""
Системные RPC-методы сессии и аутентификации (`system.ping`, `auth.login`, `auth.logout`, `auth.me`).

При вызове `auth.login` через WebSocket сессия обновляется прямо на лету (`session.authenticate`),
без необходимости переоткрывать соединение.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.auth.models import User
from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro2.rpc.errors import ForbiddenError, UnauthorizedError
from pyferro2.rpc.router import RpcRouter
from pyferro2.server.tokens import TokenManager


def serialize_session_data(session_data: SessionData) -> dict[str, Any]:
    """Сериализует `SessionData` в канонический словарь для фронтенда (`authStore`)."""
    return {
        "user_id": session_data.user_id,
        "username": session_data.username,
        "roles": sorted(session_data.roles),
        "permissions": sorted(session_data.permissions),
        "is_admin": session_data.is_admin,
        "is_guest": session_data.is_guest,
    }


def register_auth_rpc(router: RpcRouter, token_manager: TokenManager) -> None:
    """Регистрирует системные методы `system.ping`, `auth.login`, `auth.logout` и `auth.me`."""

    class system:
        @router.rpc_method(public=True)
        async def ping() -> str:
            return "pong"

    class auth:
        @router.rpc_method(public=True)
        async def login(
            session: Session,
            db: AsyncSession,
            username: str,
            password: str,
        ) -> dict[str, Any]:
            stmt = select(User).where(User.username == username)
            user = (await db.execute(stmt)).scalar_one_or_none()

            if user is None or not user.check_password(password):
                raise UnauthorizedError("Неверный логин или пароль")

            if not user.is_active:
                raise ForbiddenError("Учетная запись заблокирована")

            session_data = user.to_session_data()
            session.authenticate(session_data)

            token = token_manager.issue_token(session_data)
            return {
                "token": token,
                "user": serialize_session_data(session_data),
            }

        @router.rpc_method(public=True)
        async def logout(
            session: Session,
            token: str | None = None,
        ) -> dict[str, Any]:
            if token:
                token_manager.revoke_token(token)
            elif not session.data.is_guest and session.data.user_id is not None:
                token_manager.revoke_user(session.data.user_id)

            session.reset_to_guest()
            return {
                "status": "logged_out",
                "user": serialize_session_data(session.data),
            }

        @router.rpc_method(public=True)
        async def me(session_data: SessionData) -> dict[str, Any]:
            return serialize_session_data(session_data)
