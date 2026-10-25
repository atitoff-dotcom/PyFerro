# core/constants.py
from enum import Enum

WS_CLOSE_CODES = {
    1000: "Normal Closure (Штатный выход)",
    1001: "Going Away (Вкладка закрыта или страница обновлена)",
    1002: "Protocol Error (Ошибка протокола вебсокета)",
    1003: "Unsupported Data (Получен неподдерживаемый тип данных)",
    1005: "No Status Rcvd (Ожидался код закрытия, но ничего не пришло)",
    1006: "Abnormal Closure (Аварийный обрыв: обрыв сети, таймаут heartbeat)",
    1007: "Invalid frame payload data (Некорректные данные внутри фрейма)",
    1008: "Policy Violation (Нарушение политики безопасности)",
    1009: "Message Too Big (Клиент прислал слишком большой пакет)",
    1011: "Internal Error (Критическая ошибка на стороне сервера)",
}


class admRole(str, Enum):
    """Единое типизированное перечисление системных и административных ролей."""
    admin = "admin"
    guest = "guest"
    seo = "seo"
    adm_crud = "adm_crud"
    adm_seo = "adm_seo"
    adm_users = "adm_users"
    adm_roles = "adm_roles"
    adm_rpc = "adm_rpc"
    adm_settings = "adm_settings"
    adm_help = "adm_help"


# Системные роли безопасности
ADMIN_ROLE = admRole.admin.value
GUEST_ROLE = admRole.guest.value
SEO_ROLE = admRole.seo.value

# Постоянные роли доступа к подразделам панели управления (adm_*)
ADM_CRUD_ROLE = admRole.adm_crud.value
ADM_SEO_ROLE = admRole.adm_seo.value
ADM_USERS_ROLE = admRole.adm_users.value
ADM_ROLES_ROLE = admRole.adm_roles.value
ADM_RPC_ROLE = admRole.adm_rpc.value
ADM_SETTINGS_ROLE = admRole.adm_settings.value
ADM_HELP_ROLE = admRole.adm_help.value

ADM_SECTION_ROLES = frozenset({
    ADM_CRUD_ROLE,
    ADM_SEO_ROLE,
    ADM_USERS_ROLE,
    ADM_ROLES_ROLE,
    ADM_RPC_ROLE,
    ADM_SETTINGS_ROLE,
    ADM_HELP_ROLE,
})

SYSTEM_ROLES = frozenset({
    ADMIN_ROLE,
    GUEST_ROLE,
    SEO_ROLE,
    ADM_CRUD_ROLE,
    ADM_SEO_ROLE,
    ADM_USERS_ROLE,
    ADM_ROLES_ROLE,
    ADM_RPC_ROLE,
    ADM_SETTINGS_ROLE,
    ADM_HELP_ROLE,
})

SYSTEM_PUBLIC_EXEMPT_RPCS = frozenset({
    "system.ping",
    "system.status",
    "system.ws_status",
})


def is_system_rpc_name(method_name: str) -> bool:
    """Определяет, относится ли RPC-метод к системным/административным операциям платформы."""
    if not method_name or not isinstance(method_name, str):
        return False
    if method_name in SYSTEM_PUBLIC_EXEMPT_RPCS:
        return False
    parts = method_name.split(".")
    group = parts[0]
    if group in ("admin", "system", "permissions", "crud", "login", "auth"):
        return True
    if method_name.endswith("_admin") or ".admin_" in method_name or group == "delegations":
        return True
    return False
