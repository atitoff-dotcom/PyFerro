# -*- coding: utf-8 -*-
"""
Тестирование новой гибкой ролевой модели PyFerro:
1. Залогиненный без ролей не должен успешно логиниться.
2. Пользователь с ролью admin является только admin (roles=["admin"]).
3. Обычный пользователь имеет гибкий набор ролей (например, ['editor', 'reader']).
4. На старте отсутствие ролей admin или guest вызывает падение (RuntimeError).
5. При генерации/установке пароля администратора (set-admin-password) пользователь обязательно включается в роль admin.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pyferro.core.constants import ADMIN_ROLE, GUEST_ROLE, SYSTEM_ROLES
from pyferro.core.session import RPCError
from pyferro.auth.models import User, Role, RefreshToken
from pyferro.auth.handlers import (
    handle_login,
    handle_register,
    handle_refresh_token,
    handle_whoami,
    issue_refresh_token,
)
from pyferro.auth.discovery import sync_rpc_permissions, ensure_system_roles
from pyferro.cli import async_set_password
from pyferro.db import system_db_session, async_session, Base, engine
from pyferro.auth.core import system_bypass_ctx


@pytest.mark.asyncio
async def test_system_roles_startup_and_fail_fast():
    """Проверяет, что при отсутствии admin или guest sync_rpc_permissions падает с RuntimeError."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 1. Если база пуста без ролей - sync_rpc_permissions обязан упасть!
    async with system_db_session() as db:
        roles = (await db.execute(select(Role))).scalars().all()
        for r in roles:
            await db.delete(r)
        await db.commit()

    with pytest.raises(RuntimeError) as exc_info:
        await sync_rpc_permissions()
    assert "CRITICAL" in str(exc_info.value)
    assert "отсутствуют обязательные системные роли" in str(exc_info.value)

    # 2. Восстанавливаем обязательные системные роли
    async with system_db_session() as db:
        await ensure_system_roles(db)

    # Теперь sync_rpc_permissions должен успешно пройти
    await sync_rpc_permissions()


@pytest.mark.asyncio
async def test_user_without_roles_cannot_login():
    """Пользователь без ролей не может успешно авторизоваться (login.submit / login.refresh)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        await ensure_system_roles(db)

    mock_sess = MagicMock()
    mock_sess.ip = "127.0.0.1"

    # 1. Регистрируем пользователя
    import secrets
    username = f"no_role_{secrets.token_hex(4)}"
    email = f"{username}@example.com"
    reg_res = await handle_register(mock_sess, {
        "username": username,
        "password": "Password123!",
        "email": email,
    })
    assert reg_res["success"] is True

    # Проверяем, что у него действительно нет ролей (роль 'user' не назначается!)
    async with system_db_session() as db:
        stmt = select(User).options(selectinload(User.roles)).where(User.login == username)
        u = (await db.execute(stmt)).scalar_one()
        assert len(u.roles) == 0

    # 2. Попытка входа через login.submit -> отказ
    with pytest.raises(RPCError) as exc_login:
        await handle_login(mock_sess, {
            "username": username,
            "password": "Password123!",
        })
    assert "не имеет назначенных ролей" in str(exc_login.value)

    # 3. Попытка входа через login.refresh для пользователя без ролей -> отказ
    async with system_db_session() as db:
        rt = await issue_refresh_token(db, u.id)
        await db.commit()
        rt_token = rt.token
    with pytest.raises(RPCError) as exc_refresh:
        await handle_refresh_token(mock_sess, {
            "token": rt_token,
        })
    assert "не имеет назначенных ролей" in str(exc_refresh.value)


@pytest.mark.asyncio
async def test_admin_is_admin_and_only_admin():
    """Если у пользователя есть роль admin, его эффективная роль только admin (без мусорных дублей)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        admin_role, guest_role = await ensure_system_roles(db)

        # Создаем кастомные роли editor и reader
        stmt_e = select(Role).where(Role.name == "editor")
        editor_role = (await db.execute(stmt_e)).scalar_one_or_none()
        if not editor_role:
            editor_role = Role(name="editor", description="Editor")
            db.add(editor_role)

        stmt_r = select(Role).where(Role.name == "reader")
        reader_role = (await db.execute(stmt_r)).scalar_one_or_none()
        if not reader_role:
            reader_role = Role(name="reader", description="Reader")
            db.add(reader_role)

        await db.commit()
        await db.refresh(admin_role)
        await db.refresh(editor_role)
        await db.refresh(reader_role)

        # Создаем пользователя, у которого есть И admin, И editor, И reader
        stmt_u = select(User).options(selectinload(User.roles)).where(User.login == "super_combo_admin")
        combo_user = (await db.execute(stmt_u)).scalar_one_or_none()
        if not combo_user:
            combo_user = User(
                login="super_combo_admin",
                name="Combo Admin",
                password_hash=User._hash_password("AdminPass123!"),
                roles=[admin_role, editor_role, reader_role],
            )
            db.add(combo_user)
        else:
            combo_user.roles = [admin_role, editor_role, reader_role]
        await db.commit()

    mock_sess = MagicMock()
    mock_sess.ip = "127.0.0.1"

    login_res = await handle_login(mock_sess, {
        "username": "super_combo_admin",
        "password": "AdminPass123!",
    })

    assert login_res["role"] == "admin"
    assert login_res["roles"] == ["admin"]
    assert login_res["is_superadmin"] is True


@pytest.mark.asyncio
async def test_flexible_roles_multiple():
    """Обычный пользователь может иметь несколько предметных ролей: ['editor', 'reader']."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        await ensure_system_roles(db)

        # Убеждаемся в наличии ролей editor и reader
        stmt_e = select(Role).where(Role.name == "editor")
        editor_role = (await db.execute(stmt_e)).scalar_one_or_none()
        if not editor_role:
            editor_role = Role(name="editor", description="Editor")
            db.add(editor_role)

        stmt_r = select(Role).where(Role.name == "reader")
        reader_role = (await db.execute(stmt_r)).scalar_one_or_none()
        if not reader_role:
            reader_role = Role(name="reader", description="Reader")
            db.add(reader_role)

        await db.commit()
        await db.refresh(editor_role)
        await db.refresh(reader_role)

        stmt_u = select(User).options(selectinload(User.roles)).where(User.login == "multi_role_user")
        user = (await db.execute(stmt_u)).scalar_one_or_none()
        if not user:
            user = User(
                login="multi_role_user",
                name="Multi Role User",
                password_hash=User._hash_password("MultiPass123!"),
                roles=[editor_role, reader_role],
            )
            db.add(user)
        else:
            user.roles = [editor_role, reader_role]
        await db.commit()

    mock_sess = MagicMock()
    mock_sess.ip = "127.0.0.1"

    login_res = await handle_login(mock_sess, {
        "username": "multi_role_user",
        "password": "MultiPass123!",
    })

    assert login_res["role"] == "editor"
    assert set(login_res["roles"]) == {"editor", "reader"}
    assert login_res["is_superadmin"] is False


@pytest.mark.asyncio
async def test_cli_set_admin_password_ensures_admin_role():
    """CLI set-admin-password гарантирует наделение пользователя ролью admin."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        await ensure_system_roles(db)

        # Создаем пользователя без каких-либо ролей
        stmt_u = select(User).options(selectinload(User.roles)).where(User.login == "dormant_admin")
        dormant = (await db.execute(stmt_u)).scalar_one_or_none()
        if not dormant:
            dormant = User(
                login="dormant_admin",
                name="Dormant Admin",
                password_hash=User._hash_password("OldPass123!"),
                roles=[],
            )
            db.add(dormant)
        else:
            dormant.roles = []
        await db.commit()

    # Сбрасываем/устанавливаем пароль через CLI-функцию
    new_pwd = await async_set_password(login="dormant_admin", password="NewAdminPass123!")
    assert new_pwd == "NewAdminPass123!"

    # Проверяем, что в БД пользователю теперь жестко назначена роль admin
    async with system_db_session() as db:
        stmt_u = select(User).options(selectinload(User.roles)).where(User.login == "dormant_admin")
        updated_user = (await db.execute(stmt_u)).scalar_one()
        role_names = [r.name for r in updated_user.roles]
        assert "admin" in role_names

    # Проверяем, что теперь этот пользователь может успешно войти и является admin
    mock_sess = MagicMock()
    mock_sess.ip = "127.0.0.1"
    login_res = await handle_login(mock_sess, {
        "username": "dormant_admin",
        "password": "NewAdminPass123!",
    })
    assert login_res["role"] == "admin"
    assert login_res["roles"] == ["admin"]