# -*- coding: utf-8 -*-
"""
Официальный плагин базы данных фреймворка PyFerro (pyferro.plugins.db).
Для обратной совместимости реэкспортирует подсистему ядра pyferro.db.
"""

from pyferro.db import (
    Base,
    engine,
    async_session,
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
    "DATABASE_URL",
    "configure_db",
    "set_db_echo",
    "get_db_echo",
    "apply_pagination",
    "orjson_dumps",
    "AsyncEngineProxy",
]
