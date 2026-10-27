"""
Серверная и транспортная подсистема PyFerro 2.0 (`pyferro2/server/`).
"""

from pyferro2.server.app import PyFerroApp
from pyferro2.server.auth_rpc import register_auth_rpc, serialize_session_data
from pyferro2.server.test_client import (
    MockRSGIHTTPProtocol,
    MockRSGIScope,
    MockRSGIWebsocketProtocol,
    MockRSGIWebsocketTransport,
    call_rsgi_http,
    make_ws_close,
    make_ws_message,
)
from pyferro2.server.tokens import TokenManager, extract_token_from_scope

__all__ = [
    "PyFerroApp",
    "TokenManager",
    "extract_token_from_scope",
    "register_auth_rpc",
    "serialize_session_data",
    "MockRSGIScope",
    "MockRSGIHTTPProtocol",
    "MockRSGIWebsocketProtocol",
    "MockRSGIWebsocketTransport",
    "call_rsgi_http",
    "make_ws_message",
    "make_ws_close",
]
