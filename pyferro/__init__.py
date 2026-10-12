# -*- coding: utf-8 -*-
"""
pyferro: High-performance reactive fullstack Python framework on Rust RSGI (Granian)
with symmetric WSRPC (JSON-RPC 2.0) and Tabular Data Compression (RFC 0002).
"""

__version__ = "0.5.9"

# Автоматическая активация моста обратной совместимости для плоских импортов core и plugins
from pyferro.compat import install_compat
install_compat()

from pyferro.core.session import (
    rpc_method, RPCError, JsonRpcSession,
    current_user_ctx, current_session_ctx, current_rpc_id_ctx, current_transport_ctx,
    ACTIVE_SESSIONS_SET
)
from pyferro.core.tabular import pack_tabular, unpack_tabular, tabular_response, is_tabular
from pyferro.core.constants import ADMIN_ROLE, DEFAULT_USER_ROLE, SYSTEM_ROLES
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
from pyferro.plugins.db.session import set_db_echo, get_db_echo
from pyferro.plugins.auth.oauth import VkOAuth, YandexOAuth
from pyferro.app import FerroApp

from pyferro import core
from pyferro import plugins

__all__ = [
    "FerroApp",
    "VkOAuth",
    "YandexOAuth",
    "rpc_method",
    "RPCError",
    "JsonRpcSession",
    "current_user_ctx",
    "current_session_ctx",
    "current_rpc_id_ctx",
    "current_transport_ctx",
    "ACTIVE_SESSIONS_SET",
    "pack_tabular",
    "unpack_tabular",
    "tabular_response",
    "is_tabular",
    "ADMIN_ROLE",
    "DEFAULT_USER_ROLE",
    "SYSTEM_ROLES",
    "http_route",
    "HTTP_ROUTES",
    "extract_header",
    "extract_query_params",
    "extract_cookies",
    "get_session_cookie_names",
    "extract_session_token",
    "on_startup",
    "on_shutdown",
    "run_startup_callbacks",
    "run_shutdown_callbacks",
    "logger",
    "setup_logging",
    "configure",
    "get_config",
    "core",
    "plugins",
    "install_compat",
]
