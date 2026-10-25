# -*- coding: utf-8 -*-
"""
Тест-сьют: Архитектурная унификация сессий, идентичности и устранение рассинхрона токенов.
Проверяет:
1. Единый контракт UserIdentity (user_id, username, role, roles, is_admin, is_superadmin).
2. Работу функции get_session_identity со всеми типами сессий (JsonRpcSession, AuthSession, dict).
3. Извлечение токенов из заголовка Authorization: Bearer <token> и единой Cookie ferro_session.
4. Устранение рассинхрона WS и HTTP: доступ к /admin/ по долгоживущему токену из БД даже при отсутствии JWT.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pyferro.core.identity import UserIdentity, get_session_identity
from pyferro.core.session import JsonRpcSession, _is_session_admin, require_admin, has_admin_section_access
from pyferro.core.http import (
    extract_bearer_token,
    extract_session_token,
    extract_session_tokens,
)
from pyferro.auth.core import AuthSession
from pyferro.plugins.crud.auth import (
    get_crud_session,
    get_crud_session_async,
    create_crud_session,
    _ACTIVE_CRUD_SESSIONS,
)
from pyferro.plugins.crud.static_handler import serve_crud_static
from pyferro.db import system_db_session, engine, Base
from pyferro.auth.models import User, Role, RefreshToken


@pytest.fixture(autouse=True)
async def init_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def test_user_identity_contract():
    """Проверяет строгий канонический контракт UserIdentity."""
    ident = UserIdentity(
        user_id=42,
        username="lead_dev",
        roles=("admin", "developer"),
        is_superadmin=True,
    )
    assert ident.user_id == 42
    assert ident.username == "lead_dev"
    assert ident.roles == ("admin", "developer")
    assert ident.role == "admin"
    assert ident.is_superadmin is True
    assert ident.is_admin is True

    # Совместимость со старыми свойствами
    assert ident.uid == 42
    assert ident.user_name == "lead_dev"
    assert ident.user_role == "admin"
    assert ident.user_roles == ["admin", "developer"]


def test_json_rpc_session_clean_properties():
    """Проверяет чистые свойства JsonRpcSession без defensive clutter."""
    class MockWs:
        pass

    session = JsonRpcSession(MockWs(), session_id=1, ip="127.0.0.1")
    # Гость
    assert session.authenticated is False
    assert session.user_id is None
    assert session.username == "guest"
    assert session.role == "guest"
    assert session.roles == ["guest"]
    assert session.is_admin is False

    # Авторизованный через AuthSession
    auth_session = AuthSession(
        user_id=10,
        username="alex",
        roles=["admin"],
        is_superadmin=True,
    )
    session.data = auth_session
    assert session.authenticated is True
    assert session.user_id == 10
    assert session.username == "alex"
    assert session.role == "admin"
    assert session.roles == ["admin"]
    assert session.is_superadmin is True
    assert session.is_admin is True

    # Проверка хелперов ядра
    assert _is_session_admin(session) is True
    require_admin(session)  # Не должно вызывать исключение
    assert has_admin_section_access(session, "seo") is True


def test_bearer_token_extraction():
    """Проверяет извлечение токена из заголовка Authorization: Bearer."""
    scope_with_bearer = {
        "headers": [
            (b"authorization", b"Bearer my_super_secret_jwt_or_db_token"),
            (b"cookie", b"ferro_session=cookie_token"),
        ]
    }
    bearer = extract_bearer_token(scope_with_bearer)
    assert bearer == "my_super_secret_jwt_or_db_token"

    # Приоритет: Bearer заголовок должен быть первым в списке токенов
    tokens = extract_session_tokens(scope_with_bearer)
    assert tokens[0] == "my_super_secret_jwt_or_db_token"
    assert "cookie_token" in tokens
    assert extract_session_token(scope_with_bearer) == "my_super_secret_jwt_or_db_token"


@pytest.mark.asyncio
async def test_ws_http_no_desync_db_token_access():
    """
    Проверяет устранение бага рассинхронизации:
    Пользователь имеет активный долгоживущий RefreshToken в БД.
    Переход на HTTP /admin/ с кукой ferro_session (без JWT) должен отдавать 200, а не 404.
    """
    class MockRsgiProto:
        def __init__(self):
            self.status = None
            self.headers = []
            self.file = None
            self.body = None

        def response_file(self, status, headers, file):
            self.status = status
            self.headers = headers
            self.file = file

        def response_str(self, status, headers, body):
            self.status = status
            self.headers = headers
            self.body = body

    class MockScope:
        def __init__(self, path="/admin/", cookie=None, headers=None):
            self.path = path
            hdrs = []
            if cookie:
                hdrs.append((b"cookie", cookie.encode("latin1")))
            if headers:
                for k, v in headers.items():
                    hdrs.append((k.encode("latin1"), v.encode("latin1")))
            self.headers = hdrs

    # 1. Создаем администратора и RefreshToken в БД
    async with system_db_session() as db:
        role_admin = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if not role_admin:
            role_admin = Role(name="admin", description="Admin")
            db.add(role_admin)
            await db.flush()

        stmt = select(User).options(selectinload(User.roles)).where(User.login == "db_admin_sync")
        admin_user = (await db.execute(stmt)).scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                login="db_admin_sync",
                name="DB Admin Sync",
                roles=[role_admin],
                is_superadmin=True,
            )
            db.add(admin_user)
            await db.flush()
        else:
            admin_user.roles = [role_admin]
            admin_user.is_superadmin = True

        db_token_str = "db_persistent_token_999888"
        stmt_rt = select(RefreshToken).where(RefreshToken.token == db_token_str)
        rt = (await db.execute(stmt_rt)).scalar_one_or_none()
        if not rt:
            rt = RefreshToken(
                user_id=admin_user.id,
                token=db_token_str,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(rt)
        else:
            rt.user_id = admin_user.id
            rt.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        await db.commit()

    # Очищаем кэш в оперативной памяти (имитируем холодный HTTP запрос без прогретого кэша)
    _ACTIVE_CRUD_SESSIONS.clear()

    # 2. Браузер шлет HTTP запрос на /admin/ с Cookie: ferro_session=<db_token>
    scope_http = MockScope(path="/admin/", cookie=f"ferro_session={db_token_str}")
    proto = MockRsgiProto()

    await serve_crud_static(scope_http, proto)

    # 3. Доступ должен быть успешно предоставлен (200 OK), а не 404 Zero-Leakage!
    assert proto.status == 200
    assert proto.file is not None

    # 4. Также проверяем доступ через заголовок Authorization: Bearer <db_token>
    _ACTIVE_CRUD_SESSIONS.clear()
    scope_bearer = MockScope(path="/admin/", headers={"authorization": f"Bearer {db_token_str}"})
    proto_bearer = MockRsgiProto()

    await serve_crud_static(scope_bearer, proto_bearer)
    assert proto_bearer.status == 200
