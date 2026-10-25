"""
Паспортные данные сессии пользователя (`SessionData`).

Отвечает на вопрос «Кто вызывает метод и какие у него права?».
Объект полностью неизменяем (`frozen=True, slots=True`), создается один раз при логине
(или входе гостя) и проверяет роли и разрешения за O(1) в оперативной памяти
без обращений к базе данных.
"""

from dataclasses import dataclass
from typing import Final

from pyferro2.core.constants import GUEST_ROLE, admRole

_EMPTY_FROZENSET: Final[frozenset[str]] = frozenset()
_GUEST_ROLES: Final[frozenset[str]] = frozenset({GUEST_ROLE})


@dataclass(frozen=True, slots=True)
class SessionData:
    """
    Неизменяемый снимок авторизации и разрешений пользователя в памяти.

    Атрибуты:
        user_id: Числовой ID пользователя из БД (или `None` для гостя).
        username: Логин пользователя (для гостя — `"guest"`).
        roles: Набор имен ролей пользователя (`frozenset[str]`).
        permissions: Единый кэш разрешений из БД (в формате `Плашка.метод` и `Плашка.метод_own`),
                     загружаемый ровно один раз при логине.
    """

    user_id: int | None
    username: str
    roles: frozenset[str]
    permissions: frozenset[str] = _EMPTY_FROZENSET

    def __post_init__(self) -> None:
        if self.user_id is not None and (type(self.user_id) is not int or self.user_id <= 0):
            raise TypeError(
                f"user_id должен быть положительным int или None, получено: {self.user_id!r}"
            )
        if type(self.username) is not str or not self.username:
            raise ValueError("username должен быть непустой строкой")
        if type(self.roles) is not frozenset:
            raise TypeError("roles должен иметь тип frozenset[str]")
        if type(self.permissions) is not frozenset:
            raise TypeError("permissions должен иметь тип frozenset[str]")

    @property
    def is_admin(self) -> bool:
        """Единственный источник правды об администраторе — наличие роли 'admin'."""
        return admRole.admin.value in self.roles

    @property
    def is_guest(self) -> bool:
        """Возвращает True, если пользователь не авторизован (гость)."""
        return self.user_id is None

    def has_role(self, role: str) -> bool:
        """Мгновенная O(1) проверка наличия указанной роли."""
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """
        Мгновенная O(1) проверка права (`Плашка.метод` или `Плашка.метод_own`).
        Администратор (`is_admin`) имеет доступ ко всем операциям автоматически.
        """
        return admRole.admin.value in self.roles or permission in self.permissions

    def is_own_only(self, method_name: str) -> bool:
        """
        Возвращает True, если пользователь вошел в метод исключительно по праву
        «Только свои» (`<method_name>_own`), и у него нет полного права `<method_name>`.
        """
        if admRole.admin.value in self.roles or method_name in self.permissions:
            return False
        return f"{method_name}_own" in self.permissions

    def has_admin_access(self, section: str) -> bool:
        """
        Проверяет доступ к разделу панели управления (например, 'crud' или 'adm_crud').
        Доступ открыт главному администратору или обладателю соответствующей роли `adm_*`.
        """
        if admRole.admin.value in self.roles:
            return True
        scope = section if section.startswith("adm_") else f"adm_{section}"
        return scope in self.roles

    @classmethod
    def guest(cls, permissions: frozenset[str] = _EMPTY_FROZENSET) -> "SessionData":
        """
        Возвращает паспорт гостевой сессии.
        Если дополнительные права гостя не переданы, возвращает переиспользуемый синглтон
        (0 байт новых аллокаций в памяти).
        """
        if not permissions:
            return GUEST_SESSION_DATA
        return cls(
            user_id=None,
            username=GUEST_ROLE,
            roles=_GUEST_ROLES,
            permissions=permissions,
        )


# Базовый неизменяемый синглтон гостя — переиспользуется всеми неавторизованными сессиями
GUEST_SESSION_DATA: Final[SessionData] = SessionData(
    user_id=None,
    username=GUEST_ROLE,
    roles=_GUEST_ROLES,
    permissions=_EMPTY_FROZENSET,
)
