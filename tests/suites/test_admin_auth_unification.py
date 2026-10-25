# -*- coding: utf-8 -*-
"""
Тест-сьют: Унификация сессионных токенов и защита /admin (Zero-Leakage SSO).
Проверяет:
1. Приоритет единой куки ferro_session в extract_session_tokens.
2. Асинхронное разрешение прав администратора через get_crud_session_async по RefreshToken из БД.
3. Доступ к /admin/ по ferro_session без 404.
4. Отказоустойчивость: если ferro_crud_session содержит невалидный/истёкший токен,
   но ferro_session валиден — доступ к /admin/ успешно предоставляется.
5. Строгий 404 для гостей без валидного токена (Zero-Leakage).
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from unittest.mock import MagicMock, AsyncMock
from pyferro.core.http import (
    extract_session_tokens,
    extract_session_token,
    get_session_cookie_names,
)
from pyferro.plugins.crud.auth import (
    get_crud_session,
    get_crud_session_async,
    _ACTIVE_CRUD_SESSIONS,
)
from pyferro.plugins.crud.static_handler import serve_crud_static
from pyferro.db import system_db_session, engine, Base
from pyferro.auth.models import User, Role, RefreshToken


@pytest.fixture(autouse=True)
async def init_auth_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def test_unified_cookie_priority():
    """Проверяет, что ferro_session имеет наивысший приоритет."""
    names = get_session_cookie_names("ferro")
    assert names[0] == "ferro_session"
    assert "ferro_crud_session" in names
    assert "ferro_jwt" in names

    # Извлечение токенов в правильном порядке
    cookies = {
        "ferro_jwt": "jwt_token_123",
        "ferro_session": "session_token_abc",
        "ferro_crud_session": "crud_token_xyz",
    }
    tokens = extract_session_tokens(cookies)
    assert tokens[0] == "session_token_abc"
    assert "crud_token_xyz" in tokens
    assert "jwt_token_123" in tokens
    assert extract_session_token(cookies) == "session_token_abc"


@pytest.mark.asyncio
async def test_crud_session_async_db_resolution():
    """Проверяет, что get_crud_session_async восстанавливает права админа по RefreshToken из БД."""
    async with system_db_session() as db:
        role_admin = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if not role_admin:
            role_admin = Role(name="admin", description="Admin")
            db.add(role_admin)
            await db.flush()

        stmt = select(User).options(selectinload(User.roles)).where(User.login == "unify_admin")
        admin_user = (await db.execute(stmt)).scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                login="unify_admin",
                name="Unify Admin",
                email="unify@example.com",
                password_hash="dummy",
                roles=[role_admin],
            )
            db.add(admin_user)
            await db.flush()
        else:
            admin_user.roles = [role_admin]

        stmt_rt = select(RefreshToken).where(RefreshToken.token == "unify_rt_secret_token_123")
        rt = (await db.execute(stmt_rt)).scalar_one_or_none()
        if not rt:
            rt = RefreshToken(
                user_id=admin_user.id,
                token="unify_rt_secret_token_123",
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(rt)
        else:
            rt.user_id = admin_user.id
            rt.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        await db.commit()

    # Очищаем память, имитируя перезапуск сервера
    _ACTIVE_CRUD_SESSIONS.pop("unify_rt_secret_token_123", None)

    # Синхронный вызов без кэша вернет None
    assert get_crud_session("unify_rt_secret_token_123") is None

    # Асинхронный вызов найдет пользователя в SQLite и прогреет кэш
    sdata = await get_crud_session_async("unify_rt_secret_token_123")
    assert sdata is not None
    assert sdata["username"] == "unify_admin"
    assert "admin" in sdata["roles"]

    # Теперь токен есть и в in-memory кэше
    assert get_crud_session("unify_rt_secret_token_123") is not None


@pytest.mark.asyncio
async def test_serve_crud_static_with_ferro_session():
    """Проверяет, что запрос к /admin/ по ferro_session не возвращает 404."""
    class MockRsgiProto:
        def __init__(self):
            self.status = None
            self.headers = []
            self.body = None
            self.file_path = None

        def response_str(self, status, headers, body):
            self.status = status
            self.headers = headers
            self.body = body

        def response_file(self, status, headers, file):
            self.status = status
            self.headers = headers
            self.file_path = file

    class MockScope:
        def __init__(self, path="/admin/", method="GET", cookie=""):
            self.path = path
            self.method = method
            self.headers = [("cookie", cookie)]

    async with system_db_session() as db:
        role_admin = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if not role_admin:
            role_admin = Role(name="admin", description="Admin")
            db.add(role_admin)
            await db.flush()

        stmt = select(User).options(selectinload(User.roles)).where(User.login == "static_admin")
        admin_user = (await db.execute(stmt)).scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                login="static_admin",
                name="Static Admin",
                email="st@example.com",
                password_hash="dummy",
                roles=[role_admin],
            )
            db.add(admin_user)
            await db.flush()
        else:
            admin_user.roles = [role_admin]

        stmt_rt = select(RefreshToken).where(RefreshToken.token == "valid_session_token_999")
        rt = (await db.execute(stmt_rt)).scalar_one_or_none()
        if not rt:
            rt = RefreshToken(
                user_id=admin_user.id,
                token="valid_session_token_999",
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(rt)
        else:
            rt.user_id = admin_user.id
            rt.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        await db.commit()

    _ACTIVE_CRUD_SESSIONS.pop("valid_session_token_999", None)

    # 1. Запрос с валидной ferro_session
    scope = MockScope(path="/admin/", cookie="ferro_session=valid_session_token_999")
    proto = MockRsgiProto()
    await serve_crud_static(scope, proto)

    # Доступ разрешен: возвращает 200 и отдает index.html
    assert proto.status == 200
    assert proto.file_path is not None and "index.html" in proto.file_path

    # 2. Запрос с битым ferro_crud_session, но валидным ferro_session
    scope_fallback = MockScope(
        path="/admin/",
        cookie="ferro_crud_session=expired_or_invalid_jwt; ferro_session=valid_session_token_999"
    )
    proto_fallback = MockRsgiProto()
    await serve_crud_static(scope_fallback, proto_fallback)
    assert proto_fallback.status == 200
    assert proto_fallback.file_path is not None and "index.html" in proto_fallback.file_path

    # 3. Запрос от гостя (без валидных кук) — строгий 404 Zero-Leakage
    scope_guest = MockScope(path="/admin/", cookie="ferro_session=invalid_guest_token")
    proto_guest = MockRsgiProto()
    await serve_crud_static(scope_guest, proto_guest)
    assert proto_guest.status == 404


@pytest.mark.asyncio
async def test_non_system_role_cannot_execute_system_rpcs():
    """Проверяет жесткое правило: несистемные роли не могут вызывать системные RPC даже с wildcard '*'."""
    from pyferro.core.session import JsonRpcSession
    from pyferro.core.constants import is_system_rpc_name

    assert is_system_rpc_name("admin.sessions_list") is True
    assert is_system_rpc_name("system.cache_stats") is True
    assert is_system_rpc_name("seo.update_config_admin") is True
    assert is_system_rpc_name("tasks.create") is False

    from pyferro.core.session import RPC_REGISTRY
    saved = dict(RPC_REGISTRY)
    try:
        RPC_REGISTRY.setdefault("tasks.create", lambda s, p: "created")
        RPC_REGISTRY.setdefault("admin.sessions_list", lambda s, p: [])
        RPC_REGISTRY.setdefault("system.cache_stats", lambda s, p: {})
        RPC_REGISTRY.setdefault("seo.update_config_admin", lambda s, p: True)

        # 1. Пользователь Alice с ролью 'editor' и wildcard '*' правами
        mock_ws = MagicMock()
        session = JsonRpcSession(mock_ws, session_id=101)

        class TestUserSessionData:
            user_role = "editor"
            user_roles = ["editor"]
            allowed_rpc_methods = {"*"}
            is_superadmin = False

        session.data = TestUserSessionData()

        # Бизнес-метод разрешен
        ok, code, msg = session.check_rpc_access("tasks.create")
        assert ok is True

        # Системные методы категорически заблокированы
        ok, code, msg = session.check_rpc_access("admin.sessions_list")
        assert ok is False
        assert code == -32003
        assert "является системным" in msg

        ok, code, msg = session.check_rpc_access("system.cache_stats")
        assert ok is False
        assert code == -32003

        ok, code, msg = session.check_rpc_access("seo.update_config_admin")
        assert ok is False
        assert code == -32003

        # 2. Пользователь с ролью 'adm_seo' имеет доступ к SEO RPC
        session.data.user_roles = ["editor", "adm_seo"]
        ok, code, msg = session.check_rpc_access("seo.update_config_admin")
        assert ok is True

        # Но не имеет доступа к системным сессиям (для этого нужна роль admin)
        ok, code, msg = session.check_rpc_access("admin.sessions_list")
        assert ok is False
        assert code == -32003
    finally:
        RPC_REGISTRY.clear()
        RPC_REGISTRY.update(saved)


@pytest.mark.asyncio
async def test_permissions_schema_filters_system_rpcs_for_gui():
    """Проверяет, что permissions.get_schema скрывает системные методы от GUI конфигуратора ролей (all=False)."""
    from pyferro.auth.permission_handlers import handle_permissions_get_schema
    from pyferro.core.session import RPC_REGISTRY

    saved = dict(RPC_REGISTRY)
    try:
        RPC_REGISTRY["test_biz.action"] = lambda s, p: "ok"
        RPC_REGISTRY.setdefault("admin.sessions_list", lambda s, p: [])
        RPC_REGISTRY.setdefault("system.cache_stats", lambda s, p: {})

        admin_session = MagicMock()
        admin_session.is_superadmin = True

        # 1. Для GUI модалки ролей (all=False) — системных методов НЕТ
        schema = await handle_permissions_get_schema(admin_session, all=False)
        rpc_names = {r["name"] for r in schema["rpc_methods"]}

        assert "test_biz.action" in rpc_names
        assert "admin.sessions_list" not in rpc_names
        assert "system.cache_stats" not in rpc_names

        # 2. Для API Каталога Explorer (all=True) — системные методы ЕСТЬ
        schema_all = await handle_permissions_get_schema(admin_session, all=True)
        rpc_names_all = {r["name"] for r in schema_all["rpc_methods"]}

        assert "test_biz.action" in rpc_names_all
        assert "admin.sessions_list" in rpc_names_all
        assert "system.cache_stats" in rpc_names_all
    finally:
        RPC_REGISTRY.clear()
        RPC_REGISTRY.update(saved)
