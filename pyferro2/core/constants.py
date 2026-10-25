"""
Системные константы, роли безопасности и коды протоколов PyFerro 2.0.

Все множества ролей объявлены как `frozenset` для мгновенной O(1) проверки
на уровне C без выделения памяти в рантайме.
"""

from enum import IntEnum, StrEnum
from typing import Final


class admRole(StrEnum):
    """
    Системные административные роли и скоупы разделов панели управления.

    - `admin` — полный доступ ко всей платформе и бизнес-методам.
    - `adm_*` — доступ к конкретным разделам панели управления (Control Plane).
    """

    admin = "admin"
    adm_crud = "adm_crud"
    adm_users = "adm_users"
    adm_roles = "adm_roles"
    adm_settings = "adm_settings"
    adm_rpc = "adm_rpc"
    adm_help = "adm_help"
    adm_seo = "adm_seo"


# Базовые роли пользователей в системе
GUEST_ROLE: Final[str] = "guest"
USER_ROLE: Final[str] = "user"

# Набор скоупов разделов админ-панели (все роли adm_*, кроме главного admin)
ADM_SECTION_ROLES: Final[frozenset[str]] = frozenset(
    role.value for role in admRole if role is not admRole.admin
)

# Полный набор системных ролей, защищенных от удаления и переименования в БД (is_system=True)
SYSTEM_ROLES: Final[frozenset[str]] = frozenset(
    {GUEST_ROLE, USER_ROLE, admRole.admin.value} | ADM_SECTION_ROLES
)

# Единое имя сессионной куки транспорта
SESSION_COOKIE_NAME: Final[str] = "ferro_session"


class JsonRpcErrorCode(IntEnum):
    """Стандартные и платформенные коды ошибок протокола JSON-RPC 2.0."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Платформенные коды безопасности PyFerro 2.0
    UNAUTHORIZED = -32001
    FORBIDDEN = -32003


class WsCloseCode(IntEnum):
    """Стандартные и платформенные коды закрытия WebSocket-соединения."""

    NORMAL = 1000
    GOING_AWAY = 1001
    PROTOCOL_ERROR = 1002
    UNSUPPORTED_DATA = 1003
    POLICY_VIOLATION = 1008
    MESSAGE_TOO_BIG = 1009
    INTERNAL_ERROR = 1011

    # Прикладные коды закрытия сессии PyFerro 2.0
    UNAUTHORIZED = 4001
    FORBIDDEN = 4003
