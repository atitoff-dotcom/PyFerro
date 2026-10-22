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

# Системные роли безопасности
ADMIN_ROLE = "admin"
GUEST_ROLE = "guest"
SEO_ROLE = "seo"

# Постоянные роли доступа к подразделам панели управления (adm-*)
ADM_CRUD_ROLE = "adm-crud"
ADM_SEO_ROLE = "adm-seo"
ADM_USERS_ROLE = "adm-users"
ADM_ROLES_ROLE = "adm-roles"
ADM_RPC_ROLE = "adm-rpc"
ADM_SETTINGS_ROLE = "adm-settings"
ADM_HELP_ROLE = "adm-help"

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