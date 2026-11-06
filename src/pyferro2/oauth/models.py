"""
Модели внешней авторизации (OAuth/SSO) и системной конфигурации PyFerro 2.0.

Таблицы:
1. `OAuthAccount` (`pf_auth_oauth`) — связки внешних профилей (VK, Yandex, Telegram) с пользователями.
2. `AuthConfig` (`pf_auth_config`) — системные настройки: провайдеры, брендинг, регистрация, SMTP.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import orjson

from pyferro2.db.base import Base

if TYPE_CHECKING:
    from pyferro2.auth.models import User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OAuthAccount(Base):
    """
    Привязанный профиль внешней авторизации (`pf_auth_oauth`).
    
    Гарантирует уникальность: один внешний аккаунт привязан ровно к одному пользователю.
    Все вариативные поля профиля хранятся в `data_json`.
    """

    __tablename__ = "pf_auth_oauth"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_pf_auth_oauth_provider_user"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pf_auth_user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    user: Mapped["User"] = relationship("pyferro2.auth.models.User", back_populates="oauth_accounts")

    @property
    def profile_data(self) -> dict[str, Any]:
        """Парсит сохраненный снимок профиля через orjson."""
        try:
            return orjson.loads(self.data_json.encode("utf-8")) if self.data_json else {}
        except Exception:
            return {}

    @profile_data.setter
    def profile_data(self, val: dict[str, Any]) -> None:
        self.data_json = orjson.dumps(val).decode("utf-8")


class AuthConfig(Base):
    """
    Системная конфигурация авторизации, брендинга и провайдеров (`pf_auth_config`).
    
    Ключи (`key`):
    - 'branding'     -> { app_title, app_logo_svg }
    - 'registration' -> { allow_registration: bool, require_email_verification: bool }
    - 'smtp'         -> { host, port, user, password, from_email, use_ssl, use_starttls }
    - 'vk', 'yandex', 'telegram', 'google' -> { client_id, client_secret, redirect_uri, bot_token... }
    """

    __tablename__ = "pf_auth_config"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    config_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    @property
    def config(self) -> dict[str, Any]:
        """Возвращает распакованный конфиг."""
        try:
            return orjson.loads(self.config_json.encode("utf-8")) if self.config_json else {}
        except Exception:
            return {}

    @config.setter
    def config(self, val: dict[str, Any]) -> None:
        self.config_json = orjson.dumps(val).decode("utf-8")
