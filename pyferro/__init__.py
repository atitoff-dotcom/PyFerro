# -*- coding: utf-8 -*-
"""
pyferro: High-performance reactive fullstack Python framework on Rust RSGI (Granian)
with symmetric WSRPC (JSON-RPC 2.0) and Tabular Data Compression (RFC 0002).
"""

__version__ = "0.7.0"

# Модули ядра первого уровня
from pyferro import core
from pyferro import db
from pyferro import auth
from pyferro import broadcast as broadcast_module
from pyferro import smart_cache
from pyferro import plugins

# Базовые сущности ядра (WSRPC, Сессии, Табличные данные)
from pyferro.core.session import (
    rpc_method, RPCError, JsonRpcSession,
    current_user_ctx, current_session_ctx, current_rpc_id_ctx, current_transport_ctx,
    ACTIVE_SESSIONS_SET
)
from pyferro.core.tabular import pack_tabular, unpack_tabular, tabular_response, is_tabular
from pyferro.core.constants import ADMIN_ROLE, GUEST_ROLE, SYSTEM_ROLES
from pyferro.core.router import http_route, HTTP_ROUTES
from pyferro.core.http import (
    extract_header, extract_query_params,
    extract_cookies, get_session_cookie_names, extract_session_token
)
from pyferro.core.lifecycle import (
    on_startup, on_shutdown, run_startup_callbacks, run_shutdown_callbacks
)
from pyferro.core.logger import (
    logger, setup_logging, get_runtime_log_level, set_runtime_log_level
)
from pyferro.core.lib.config import configure, get_config
from pyferro.app import FerroApp

# База данных (pyferro.db)
from pyferro.db import (
    Base, engine, async_session, system_db_session, system_bypass, DATABASE_URL, configure_db, set_db_echo, get_db_echo,
    DEFAULT_TABLE_PREFIX, get_system_table_prefix, set_system_table_prefix, is_system_table_name
)
from pyferro.core.lib.config import get_table_prefix

# Аутентификация и пользователи (pyferro.auth)
from pyferro.auth import (
    User, Role, RpcPermission, AuthSession, system_bypass_ctx, BasicSecureModel, RowSecureModel
)
from pyferro.auth.oauth import VkOAuth, YandexOAuth

# Рассылки реального времени (pyferro.broadcast)
from pyferro.broadcast import (
    broadcast, broadcast_notification, send_to_user, send_to_role
)

# Реактивное кэширование (pyferro.smart_cache)
from pyferro.smart_cache import (
    invalidates, invalidate_tags, version_registry
)

__all__ = [
    # Главный класс приложения
    "FerroApp",

    # Подсистемы первого уровня
    "core",
    "db",
    "auth",
    "broadcast_module",
    "smart_cache",
    "plugins",

    # RPC & Сессии
    "rpc_method",
    "RPCError",
    "JsonRpcSession",
    "current_user_ctx",
    "current_session_ctx",
    "current_rpc_id_ctx",
    "current_transport_ctx",
    "ACTIVE_SESSIONS_SET",

    # RFC 0002 Tabular Data
    "pack_tabular",
    "unpack_tabular",
    "tabular_response",
    "is_tabular",

    # Константы ролей
    "ADMIN_ROLE",
    "GUEST_ROLE",
    "SYSTEM_ROLES",

    # HTTP & Cookies
    "http_route",
    "HTTP_ROUTES",
    "extract_header",
    "extract_query_params",
    "extract_cookies",
    "get_session_cookie_names",
    "extract_session_token",

    # Жизненный цикл и логирование
    "on_startup",
    "on_shutdown",
    "run_startup_callbacks",
    "run_shutdown_callbacks",
    "logger",
    "setup_logging",
    "configure",
    "get_config",
    "get_table_prefix",

    # База данных (pyferro.db)
    "Base",
    "engine",
    "async_session",
    "system_db_session",
    "system_bypass",
    "DATABASE_URL",
    "configure_db",
    "set_db_echo",
    "get_db_echo",
    "DEFAULT_TABLE_PREFIX",
    "get_system_table_prefix",
    "set_system_table_prefix",
    "is_system_table_name",

    # Аутентификация (pyferro.auth)
    "User",
    "Role",
    "RpcPermission",
    "AuthSession",
    "system_bypass_ctx",
    "BasicSecureModel",
    "RowSecureModel",
    "VkOAuth",
    "YandexOAuth",

    # Рассылки (pyferro.broadcast)
    "broadcast",
    "broadcast_notification",
    "send_to_user",
    "send_to_role",

    # Реактивный кэш (pyferro.smart_cache)
    "invalidates",
    "invalidate_tags",
    "version_registry",
]
