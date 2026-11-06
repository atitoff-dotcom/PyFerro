"""
Менеджер бизнес-логики внешней авторизации, брендинга и регистрации.
"""

import re
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import orjson

from pyferro2.auth.models import Role, User
from pyferro2.core.session_data import SessionData
from pyferro2.oauth.models import AuthConfig, OAuthAccount
from pyferro2.oauth.providers import ExternalUserProfile, PROVIDERS
from pyferro2.rpc.errors import ForbiddenError, NotFoundError, ValidationError

DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "branding": {
        "is_enabled": True,
        "config": {
            "app_title": "PyFerro 2.0 Admin",
            "app_logo_svg": "",
        },
    },
    "registration": {
        "is_enabled": True,
        "config": {
            "allow_registration": True,
            "require_email_verification": False,
        },
    },
    "smtp": {
        "is_enabled": False,
        "config": {
            "host": "smtp.gmail.com",
            "port": 587,
            "user": "",
            "password": "",
            "from_email": "",
            "use_ssl": False,
            "use_starttls": True,
        },
    },
    "vk": {
        "is_enabled": True,
        "config": {
            "client_id": "54878944",
            "client_secret": "",
            "redirect_uri": "https://stage.agrita.ru/auth/callback",
        },
    },
    "yandex": {
        "is_enabled": False,
        "config": {
            "client_id": "",
            "client_secret": "",
            "redirect_uri": "https://stage.agrita.ru/auth/callback",
        },
    },
    "telegram": {
        "is_enabled": False,
        "config": {
            "bot_token": "",
            "bot_username": "",
        },
    },
    "google": {
        "is_enabled": False,
        "config": {
            "client_id": "",
            "client_secret": "",
            "redirect_uri": "https://stage.agrita.ru/auth/callback",
        },
    },
}


async def seed_auth_configs(db: AsyncSession) -> None:
    """Инициализирует дефолтные системные настройки брендинга и провайдеров, если они отсутствуют."""
    for key, spec in DEFAULT_CONFIGS.items():
        stmt = select(AuthConfig).where(AuthConfig.key == key)
        record = (await db.execute(stmt)).scalar_one_or_none()
        if record is None:
            record = AuthConfig(
                key=key,
                is_enabled=spec["is_enabled"],
                config_json=orjson.dumps(spec["config"]).decode("utf-8"),
            )
            db.add(record)
    await db.commit()


async def get_auth_config(db: AsyncSession, key: str) -> AuthConfig | None:
    """Получает запись конфигурации по ключу."""
    stmt = select(AuthConfig).where(AuthConfig.key == key)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_or_create_config(db: AsyncSession, key: str) -> AuthConfig:
    """Получает или создает запись конфигурации."""
    cfg = await get_auth_config(db, key)
    if cfg is None:
        def_spec = DEFAULT_CONFIGS.get(key, {"is_enabled": False, "config": {}})
        cfg = AuthConfig(
            key=key,
            is_enabled=def_spec["is_enabled"],
            config_json=orjson.dumps(def_spec["config"]).decode("utf-8"),
        )
        db.add(cfg)
        await db.commit()
    return cfg


def sanitize_username(raw: str) -> str:
    """Очищает строку логина, оставляя безопасные символы [a-zA-Z0-9_-]."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", raw.strip().lower())
    return cleaned or "user"


async def find_available_username(db: AsyncSession, base_name: str) -> str:
    """Генерирует свободный username на основе базы, добавляя суффикс при коллизиях."""
    candidate = sanitize_username(base_name)
    suffix = 1
    current = candidate
    while True:
        stmt = select(User.id).where(User.username == current)
        exists = (await db.execute(stmt)).scalar_one_or_none()
        if exists is None:
            return current
        current = f"{candidate}_{suffix}"
        suffix += 1


async def link_or_create_oauth_user(
    db: AsyncSession,
    profile: ExternalUserProfile,
    session_data: SessionData,
) -> User:
    """
    Основная логика связывания пользователя:
    1. Если сессия авторизована -> привязываем к текущему user_id.
    2. Если есть связка в pf_auth_oauth -> авторизуем найденного пользователя.
    3. Если email совпал с существующим в pf_auth_user -> привязываем к нему.
    4. Иначе -> проверяем флаг регистрации, создаем User + OAuthAccount.
    """
    # 1. Если пользователь уже вошел в систему
    if not session_data.is_guest and session_data.user_id is not None:
        user_stmt = select(User).where(User.id == session_data.user_id)
        current_user = (await db.execute(user_stmt)).scalar_one_or_none()
        if current_user is None:
            raise NotFoundError("Текущий пользователь не найден")

        # Проверяем, не привязан ли этот внешний аккаунт уже к кому-то
        acc_stmt = select(OAuthAccount).where(
            OAuthAccount.provider == profile.provider,
            OAuthAccount.provider_user_id == profile.provider_user_id,
        )
        existing_acc = (await db.execute(acc_stmt)).scalar_one_or_none()
        if existing_acc is not None:
            if existing_acc.user_id != current_user.id:
                raise ValidationError("Этот внешний профиль уже привязан к другому пользователю")
            existing_acc.profile_data = profile.raw_data
        else:
            new_acc = OAuthAccount(
                user_id=current_user.id,
                provider=profile.provider,
                provider_user_id=profile.provider_user_id,
            )
            new_acc.profile_data = profile.raw_data
            db.add(new_acc)
        await db.commit()
        return current_user

    # 2. Поиск существующей связки в pf_auth_oauth
    acc_stmt = select(OAuthAccount).where(
        OAuthAccount.provider == profile.provider,
        OAuthAccount.provider_user_id == profile.provider_user_id,
    )
    oauth_acc = (await db.execute(acc_stmt)).scalar_one_or_none()
    if oauth_acc is not None:
        user_stmt = select(User).where(User.id == oauth_acc.user_id)
        existing_user = (await db.execute(user_stmt)).scalar_one_or_none()
        if existing_user is not None:
            if not existing_user.is_active:
                raise ForbiddenError("Учетная запись заблокирована")
            oauth_acc.profile_data = profile.raw_data
            await db.commit()
            return existing_user

    # 3. Бесшовное связывание по Email
    if profile.email:
        email_stmt = select(User).where(User.email == profile.email.strip().lower())
        matched_user = (await db.execute(email_stmt)).scalar_one_or_none()
        if matched_user is not None:
            if not matched_user.is_active:
                raise ForbiddenError("Учетная запись заблокирована")
            new_acc = OAuthAccount(
                user_id=matched_user.id,
                provider=profile.provider,
                provider_user_id=profile.provider_user_id,
            )
            new_acc.profile_data = profile.raw_data
            db.add(new_acc)
            await db.commit()
            return matched_user

    # 4. Регистрация нового пользователя
    reg_cfg = await get_or_create_config(db, "registration")
    if not reg_cfg.is_enabled or not reg_cfg.config.get("allow_registration", True):
        raise ForbiddenError("Регистрация новых пользователей отключена администратором")

    base_username = profile.username or (profile.email.split("@")[0] if profile.email else f"{profile.provider}_{profile.provider_user_id}")
    final_username = await find_available_username(db, base_username)

    new_user = User(
        username=final_username,
        email=profile.email.strip().lower() if profile.email else None,
        full_name=profile.display_name or final_username,
        is_active=True,
    )
    # Случайный надежный пароль (вход по паролю пока не активен)
    new_user.set_password(secrets.token_urlsafe(32))

    # Выдаем стандартную роль 'user'
    role_stmt = select(Role).where(Role.name == "user")
    user_role = (await db.execute(role_stmt)).scalar_one_or_none()
    if user_role is not None:
        new_user.roles.append(user_role)

    db.add(new_user)
    await db.flush()

    new_acc = OAuthAccount(
        user_id=new_user.id,
        provider=profile.provider,
        provider_user_id=profile.provider_user_id,
    )
    new_acc.profile_data = profile.raw_data
    db.add(new_acc)

    await db.commit()
    await db.refresh(new_user)
    return new_user
