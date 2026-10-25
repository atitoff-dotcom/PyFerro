"""
Ядро PyFerro 2.0: системные константы, паспорт сессии (`SessionData`), контекст связи (`Session`)
и табличное сжатие (`pack_tabular`, `unpack_tabular`).
"""

from pyferro2.core.constants import (
    ADM_SECTION_ROLES,
    GUEST_ROLE,
    SESSION_COOKIE_NAME,
    SYSTEM_ROLES,
    USER_ROLE,
    JsonRpcErrorCode,
    WsCloseCode,
    admRole,
)
from pyferro2.core.session import CloseCallback, NotifyCallback, Session
from pyferro2.core.session_data import GUEST_SESSION_DATA, SessionData
from pyferro2.core.tabular import is_tabular, pack_tabular, unpack_tabular

__all__ = [
    "admRole",
    "GUEST_ROLE",
    "USER_ROLE",
    "ADM_SECTION_ROLES",
    "SYSTEM_ROLES",
    "SESSION_COOKIE_NAME",
    "JsonRpcErrorCode",
    "WsCloseCode",
    "SessionData",
    "GUEST_SESSION_DATA",
    "Session",
    "NotifyCallback",
    "CloseCallback",
    "pack_tabular",
    "unpack_tabular",
    "is_tabular",
]
