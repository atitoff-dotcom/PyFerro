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
]
