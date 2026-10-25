"""
Чистые модели авторизации и ролевого доступа (RBAC) для PyFerro 2.0.

Схема состоит ровно из трех основных сущностей:
1. `User` (`pf_auth_user`) — учетная запись пользователя (без дублей `login`, `is_admin`, `admin_roles`).
2. `Role` (`pf_auth_role`) — роль (пользовательская или системная с флагом `is_system=True`).
3. `RolePermission` (`pf_auth_role_permission`) — разрешения роли, хранящиеся 1-в-1
   в том же формате, что и в `SessionData.permissions` (например, `"catalog.get_items"` или `"Article:read"`).
"""

from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pyferro2.auth.passwords import hash_password, verify_password
from pyferro2.core.session_data import SessionData
from pyferro2.db.base import Base

# Таблица связи Многие-ко-Многим: Пользователи <-> Роли
user_role_table = Table(
    "pf_auth_user_role",
    Base.metadata,
    Column(
        "user_id",
        Integer,
        ForeignKey("pf_auth_user.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Integer,
        ForeignKey("pf_auth_role.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class RolePermission(Base):
    """
    Разрешение, выданное конкретной роли.

    Поле `permission` хранит точную строку права:
    - имя бизнес-RPC метода (например, `"orders.create"`),
    - или операцию CRUD над моделью (например, `"Order:read"`).
    При логине эти строки без преобразований загружаются в `SessionData.permissions`.
    """

    __tablename__ = "pf_auth_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission", name="uq_pf_role_permission"),
    )

    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pf_auth_role.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    permission: Mapped[str] = mapped_column(String(150), nullable=False)

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")


class Role(Base):
    """
    Роль безопасности (`pf_auth_role`).

    Системные роли (`guest`, `user`, `admin`, `adm_*`) помечаются флагом `is_system=True`
    и защищены на уровне ORM от удаления и смены имени.
    """

    __tablename__ = "pf_auth_role"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    role_permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary=user_role_table,
        back_populates="roles",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("role_permissions", [])
        super().__init__(**kwargs)

    def get_permissions(self) -> frozenset[str]:
        """Возвращает неизменяемый набор всех строковых разрешений этой роли."""
        return frozenset(rp.permission for rp in self.role_permissions)

    def add_permission(self, permission: str) -> None:
        """Добавляет разрешение роли (если оно еще не было добавлено)."""
        if not any(rp.permission == permission for rp in self.role_permissions):
            self.role_permissions.append(RolePermission(permission=permission))

    def remove_permission(self, permission: str) -> None:
        """Удаляет разрешение у роли."""
        self.role_permissions = [
            rp for rp in self.role_permissions if rp.permission != permission
        ]


@event.listens_for(Role, "before_delete")
def _prevent_system_role_deletion(_mapper: Any, _connection: Any, target: Role) -> None:
    """Гарантирует, что системную роль (`is_system=True`) невозможно удалить из БД."""
    if target.is_system:
        raise ValueError(f"Запрещено удалять системную роль '{target.name}'")


@event.listens_for(Role, "before_update")
def _prevent_system_role_modification(_mapper: Any, _connection: Any, target: Role) -> None:
    """Гарантирует, что у системной роли нельзя изменить имя (`name`) или снять флаг `is_system`."""
    state = inspect(target)
    is_sys_hist = state.attrs.is_system.history
    was_system = target.is_system or (is_sys_hist.deleted and is_sys_hist.deleted[0] is True)

    if not was_system:
        return

    if is_sys_hist.has_changes() and not target.is_system:
        raise ValueError(f"Запрещено снимать флаг is_system у системной роли '{target.name}'")

    name_hist = state.attrs.name.history
    if name_hist.has_changes():
        old_name = name_hist.deleted[0] if name_hist.deleted else target.name
        raise ValueError(f"Запрещено переименовывать системную роль '{old_name}'")


class User(Base):
    """
    Учетная запись пользователя (`pf_auth_user`).

    Золотые правила:
    - Единственный логин: `username`.
    - Единственный источник прав администратора: наличие роли `'admin'` в `user.roles`.
    """

    __tablename__ = "pf_auth_user"

    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="", server_default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=user_role_table,
        back_populates="users",
        lazy="selectin",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("roles", [])
        super().__init__(**kwargs)

    def set_password(self, raw_password: str) -> None:
        """Хэширует и устанавливает пароль пользователя."""
        self.password_hash = hash_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Проверяет пароль пользователя."""
        return verify_password(raw_password, self.password_hash)

    def to_session_data(self) -> SessionData:
        """
        Собирает неизменяемый паспорт сессии (`SessionData`) со всеми ролями
        и объединенным кэшем разрешений. Вызывается 1 раз при входе в систему.
        """
        role_names = frozenset(role.name for role in self.roles)
        merged_permissions = frozenset(
            rp.permission
            for role in self.roles
            for rp in role.role_permissions
        )
        return SessionData(
            user_id=self.id,
            username=self.username,
            roles=role_names,
            permissions=merged_permissions,
        )
