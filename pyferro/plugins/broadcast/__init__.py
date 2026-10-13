# -*- coding: utf-8 -*-
"""
Официальный плагин WebSocket-рассылок (pyferro.plugins.broadcast).
Для обратной совместимости реэкспортирует подсистему ядра pyferro.broadcast.
"""

from pyferro.broadcast import (
    broadcast,
    broadcast_notification,
    send_to_user,
    send_to_role,
    get_session_uid,
    _safe_send,
)

__all__ = [
    "broadcast",
    "broadcast_notification",
    "send_to_user",
    "send_to_role",
    "get_session_uid",
    "_safe_send",
]
