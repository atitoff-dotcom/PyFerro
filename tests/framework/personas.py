# -*- coding: utf-8 -*-
"""
Управление тестовыми персонами (Admin, Regular User, Guest).
Обеспечивает автоматическую аутентификацию через WebSocket-метод login.submit,
а при локальном тестировании — автоматическое создание/проверку тестовых пользователей в БД.
"""

import os
from typing import Optional

from tests.framework.client import TestClient
from tests.framework.config import TargetConfig, get_target


class PersonaManager:
    """Фабрика предварительно авторизованных клиентов для различных ролей."""

    ADMIN_LOGIN = os.getenv("TEST_ADMIN_LOGIN", "admin")
    ADMIN_PASS = os.getenv("TEST_ADMIN_PASS", "admin")

    USER_LOGIN = os.getenv("TEST_USER_LOGIN", "test_user")
    USER_PASS = os.getenv("TEST_USER_PASS", "Test123456!")

    @classmethod
    async def as_guest(cls, target: Optional[TargetConfig] = None) -> TestClient:
        """Создает неавторизованного клиента (Guest)."""
        client = TestClient(target)
        await client.connect()
        return client

    @classmethod
    async def as_user(
        cls,
        login: Optional[str] = None,
        password: Optional[str] = None,
        target: Optional[TargetConfig] = None,
        role: str = "user",
    ) -> TestClient:
        """
        Создает клиента и авторизует его как обычного пользователя.
        При локальном запуске автоматически гарантирует наличие пользователя в БД.
        """
        username = login or cls.USER_LOGIN
        pwd = password or cls.USER_PASS

        # Если локальная цель — гарантируем пользователя в локальной БД
        tgt = target or get_target()
        if tgt.name == "local":
            await cls._ensure_local_user(username, pwd, role=role)

        client = TestClient(tgt)
        await client.connect()

        res = await client.call("login.submit", {
            "username": username,
            "password": pwd,
            "user_agent": "AgritaTestRunner/1.0",
        })

        client.token = res.get("token")
        client.user_info = res
        return client

    @classmethod
    async def as_admin(
        cls,
        login: Optional[str] = None,
        password: Optional[str] = None,
        target: Optional[TargetConfig] = None,
    ) -> TestClient:
        """Создает клиента и авторизует его с правами администратора."""
        username = login or cls.ADMIN_LOGIN
        pwd = password or cls.ADMIN_PASS

        tgt = target or get_target()
        if tgt.name == "local":
            await cls._ensure_local_user(username, pwd, role="admin")

        client = TestClient(tgt)
        await client.connect()

        res = await client.call("login.submit", {
            "username": username,
            "password": pwd,
            "user_agent": "AgritaTestRunner/1.0",
        })

        client.token = res.get("token")
        client.user_info = res
        return client

    @classmethod
    async def as_existing_user(
        cls,
        user_id_or_login: int | str,
        target: Optional[TargetConfig] = None,
        via_cookie: bool = False,
    ) -> TestClient:
        """
        Создает клиента и авторизует его под существующим реальным пользователем из БД
        БЕЗ знания его пароля (через короткоживущий сервисный RefreshToken и login.refresh либо HTTP Cookie).
        """
        import secrets
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from pyferro.db import system_db_session
        from pyferro.auth.models import User, RefreshToken

        tgt = target or get_target()
        async with system_db_session() as db:
            if isinstance(user_id_or_login, int):
                stmt = select(User).where(User.id == user_id_or_login)
            else:
                stmt = select(User).where(User.login == str(user_id_or_login))
            user = (await db.execute(stmt)).scalar_one_or_none()
            if not user:
                raise ValueError(f"Пользователь '{user_id_or_login}' не найден в БД")

            temp_token = f"persona_{secrets.token_urlsafe(32)}"
            rt = RefreshToken(
                user_id=user.id,
                token=temp_token,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            db.add(rt)
            await db.commit()

        if via_cookie:
            client = TestClient(tgt, cookies={"ferro_session": temp_token})
            await client.connect()
            client.token = temp_token
            return client

        client = TestClient(tgt)
        await client.connect()
        res = await client.call("login.refresh", {
            "token": temp_token,
            "user_agent": "AgritaTestRunner/1.0",
        })
        client.token = res.get("token")
        client.user_info = res
        return client
    @classmethod
    async def _ensure_local_user(cls, login: str, password: str, role: str = "user"):
        """Вспомогательный метод для гарантии наличия пользователя в локальной БД."""
        try:
            from pyferro.db import async_session
            from pyferro.auth.models import User, Role
            from pyferro.auth.core import system_bypass_ctx
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            from core.logger import logger

            system_bypass_ctx.set(True)
            async with async_session() as db:
                stmt = select(User).options(selectinload(User.roles)).where(User.login == login)
                user = (await db.execute(stmt)).scalar_one_or_none()

                # Проверяем или создаем роль
                stmt_role = select(Role).where(Role.name == role)
                role_obj = (await db.execute(stmt_role)).scalar_one_or_none()
                if not role_obj:
                    role_obj = Role(name=role, description=f"{role.capitalize()} Role")
                    db.add(role_obj)
                    await db.flush()

                if not user:
                    user = User(
                        name=login,
                        login=login,
                        email=f"{login}@agrita.local",
                        password_hash=User._hash_password(password),
                        roles=[role_obj],
                    )
                    db.add(user)
                    await db.commit()
                    logger.info(f"[PersonaManager] Создан тестовый пользователь '{login}' с ролью '{role}'")
                else:
                    if not user.verify_password(password):
                        user.password_hash = User._hash_password(password)
                        if role_obj not in user.roles:
                            user.roles.append(role_obj)
                        await db.commit()
                        logger.info(f"[PersonaManager] Обновлен пароль тестового пользователя '{login}'")
        except Exception as e:
            from core.logger import logger
            logger.warning(f"[PersonaManager] Ошибка при создании тестового пользователя: {e}")
