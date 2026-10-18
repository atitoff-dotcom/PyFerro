# -*- coding: utf-8 -*-
"""
Управление именованием системных таблиц фреймворка PyFerro.
Позволяет изолировать таблицы фреймворка от прикладных моделей приложения
с помощью конфигурируемого префикса (по умолчанию 'pf_').
"""

from typing import Dict, Optional, Set, Type, Any
from sqlalchemy import Table

DEFAULT_TABLE_PREFIX = "pf_"

# Базовые суффиксы системных таблиц фреймворка (без префикса)
SYSTEM_TABLE_BASES: Set[str] = {
    # Подсистема аутентификации и авторизации (pyferro.auth)
    "auth_user",
    "auth_role",
    "auth_team",
    "auth_rpc_permission",
    "auth_role_permission",
    "auth_user_permission",
    "auth_user_delegation",
    "auth_user_auth_role",
    "auth_user_auth_team",
    "auth_role_auth_rpc_permission",
    "auth_user_auth_rpc_permission",
    "refresh_tokens",
    "active_sessions",
    "system_data",
    "oauth_accounts",
    # Smart Cache (pyferro.smart_cache)
    "cache_tag_versions",
    # Universal Metadata Registry (pyferro.plugins.files)
    "file_metadata",
}

# Текущий активный префикс в рантайме
_current_prefix = DEFAULT_TABLE_PREFIX


def get_system_table_prefix() -> str:
    """Возвращает текущий префикс системных таблиц фреймворка."""
    global _current_prefix
    return _current_prefix


def is_system_table_name(table_name: str) -> bool:
    """Проверяет, относится ли имя таблицы к системным таблицам фреймворка."""
    if not table_name:
        return False
    global _current_prefix
    # Проверка с текущим префиксом
    if _current_prefix and table_name.startswith(_current_prefix):
        suffix = table_name[len(_current_prefix):]
        if suffix in SYSTEM_TABLE_BASES:
            return True
    # Проверка с дефолтным префиксом 'pf_'
    if table_name.startswith(DEFAULT_TABLE_PREFIX):
        suffix = table_name[len(DEFAULT_TABLE_PREFIX):]
        if suffix in SYSTEM_TABLE_BASES:
            return True
    # Проверка без префикса (исторические имена для обратной совместимости)
    if table_name in SYSTEM_TABLE_BASES:
        return True
    return False


def set_system_table_prefix(new_prefix: str) -> None:
    """
    Динамически обновляет префикс системных таблиц в DeclarativeBase SQLAlchemy.
    Используется при инициализации FerroApp(table_prefix="...").
    """
    global _current_prefix
    if new_prefix == _current_prefix:
        return

    from pyferro.db.session import Base
    old_prefix = _current_prefix
    _current_prefix = new_prefix

    # Проходим по всем зарегистрированным таблицам в метаданных SQLAlchemy
    metadata = Base.metadata
    tables_to_rename: Dict[str, Table] = {}

    for base_name in SYSTEM_TABLE_BASES:
        expected_old_name = f"{old_prefix}{base_name}"
        expected_new_name = f"{new_prefix}{base_name}"

        # Ищем таблицу по старому имени
        if expected_old_name in metadata.tables:
            tables_to_rename[expected_old_name] = (metadata.tables[expected_old_name], expected_new_name)
        elif base_name in metadata.tables:
            tables_to_rename[base_name] = (metadata.tables[base_name], expected_new_name)

    # Применяем переименование
    for old_name, (table, new_name) in tables_to_rename.items():
        if old_name != new_name:
            metadata.remove(table)
            table.name = new_name
            metadata._add_table(new_name, table.schema, table)

    # Обновляем ссылки ForeignKey
    for table in metadata.tables.values():
        for fk in table.foreign_keys:
            tokens = getattr(fk, "_given_tokens", None)
            if tokens and hasattr(tokens, "table_name"):
                for base_name in SYSTEM_TABLE_BASES:
                    old_target_name = f"{old_prefix}{base_name}"
                    new_target_name = f"{new_prefix}{base_name}"
                    if tokens.table_name in (old_target_name, base_name):
                        fk._given_tokens = tokens._replace(table_name=new_target_name)
                        break

