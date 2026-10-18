# -*- coding: utf-8 -*-
"""
Подсистема базы данных фреймворка PyFerro (pyferro.db).
Экспортирует Base, engine, async_session, configure_db и утилиты управления БД.
"""

from .session import (
    Base,
    engine,
    async_session,
    system_db_session,
    system_bypass,
    DATABASE_URL,
    configure_db,
    set_db_echo,
    get_db_echo,
    apply_pagination,
    orjson_dumps,
    AsyncEngineProxy,
)
from .naming import (
    DEFAULT_TABLE_PREFIX,
    get_system_table_prefix,
    set_system_table_prefix,
    is_system_table_name,
    SYSTEM_TABLE_BASES,
)

__all__ = [
    "Base",
    "engine",
    "async_session",
    "system_db_session",
    "system_bypass",
    "DATABASE_URL",
    "configure_db",
    "set_db_echo",
    "get_db_echo",
    "apply_pagination",
    "orjson_dumps",
    "AsyncEngineProxy",
    "DEFAULT_TABLE_PREFIX",
    "get_system_table_prefix",
    "set_system_table_prefix",
    "is_system_table_name",
    "SYSTEM_TABLE_BASES",
]

