"""
PyFerro: High-performance reactive fullstack Python framework on Rust RSGI (Granian).
"""

from .identity import UserIdentity, get_session_identity
from .session import (
    rpc_method, RPCError, JsonRpcSession,
    current_user_ctx, current_session_ctx, current_transport_ctx,
    require_admin,
)
from .tabular import pack_tabular, unpack_tabular, tabular_response, is_tabular
from .logger import logger
from .router import http_route
from .http import extract_header, extract_query_params
from .lifecycle import on_startup, run_startup_callbacks

__all__ = [
    "UserIdentity", "get_session_identity",
    "rpc_method", "RPCError", "JsonRpcSession",
    "current_user_ctx", "current_session_ctx", "current_transport_ctx",
    "require_admin",
    "pack_tabular", "unpack_tabular", "tabular_response", "is_tabular",
    "logger", "http_route", "extract_header", "extract_query_params",
    "on_startup", "run_startup_callbacks"
]
