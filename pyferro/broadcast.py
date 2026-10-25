# -*- coding: utf-8 -*-
"""
Подсистема WebSocket-рассылок и событий реального времени PyFerro (pyferro.broadcast).
Реализует RFC 0006: неблокирующая Zero-Copy рассылка через WSRPC.
"""

import asyncio
from typing import List, Dict, Any, Optional
import orjson

from pyferro.core.session import ACTIVE_SESSIONS_SET, current_transport_ctx
from pyferro.core.logger import logger


async def _safe_send(session, payload_str: str) -> bool:
    """
    Безопасная неблокирующая отправка сериализованной строки в сокет.
    Изолирует ошибки сетевого уровня конкретного клиента.
    """
    try:
        if getattr(session, "_closed", True):
            return False
        if hasattr(session, "send_str"):
            return await session.send_str(payload_str)
        if not getattr(session, "ws", None):
            return False
        awaitable = session.ws.send_str(payload_str)
        if not hasattr(awaitable, "cancelled"):
            try:
                awaitable.cancelled = lambda: False
            except AttributeError:
                pass
        await awaitable
        return True
    except Exception as e:
        logger.debug(f"[Broadcast] Ошибка отправки в сессию {getattr(session, 'session_id', '?')}: {e}")
        return False


async def broadcast_notification(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    exclude_current: bool = False,
) -> int:
    """
    Рассылает JSON-RPC нотификацию (без 'id') всем активным WebSocket клиентам.
    Оверхед O(1): данные сериализуются один раз и отправляются в память сокетов.
    """
    if not ACTIVE_SESSIONS_SET:
        return 0

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {}
    }
    payload_str = orjson.dumps(payload).decode("utf-8")

    current_transport = current_transport_ctx.get() if exclude_current else None

    # Делаем снимок текущих сессий
    sessions = list(ACTIVE_SESSIONS_SET)
    tasks = []
    for s in sessions:
        if current_transport and s == current_transport:
            continue
        tasks.append(_safe_send(s, payload_str))

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = sum(1 for r in results if r is True)
    logger.debug(f"[Broadcast] {method} отправлен {sent_count} клиентам")
    return sent_count


# Удобный короткий алиас
broadcast = broadcast_notification


def get_session_uid(session: Any) -> Optional[int]:
    """Извлекает ID пользователя из сессии."""
    from pyferro.core.identity import get_session_identity
    ident = get_session_identity(session)
    return ident.user_id if ident else None

async def send_to_user(
    user_id: int,
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Отправляет JSON-RPC нотификацию конкретному пользователю во все его активные сессии (вкладки/устройства).
    """
    if not ACTIVE_SESSIONS_SET:
        return 0

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {}
    }
    payload_str = orjson.dumps(payload).decode("utf-8")

    try:
        target_uid = int(user_id)
    except (ValueError, TypeError):
        return 0

    tasks = []
    for s in list(ACTIVE_SESSIONS_SET):
        if get_session_uid(s) == target_uid:
            tasks.append(_safe_send(s, payload_str))

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = sum(1 for r in results if r is True)
    logger.debug(f"[DirectSend] {method} отправлен пользователю {user_id} в {sent_count} сессий")
    return sent_count


async def send_to_role(
    role: str,
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Отправляет JSON-RPC нотификацию всем активным сессиям пользователей с указанной ролью.
    """
    if not ACTIVE_SESSIONS_SET:
        return 0

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {}
    }
    payload_str = orjson.dumps(payload).decode("utf-8")

    tasks = []
    for s in list(ACTIVE_SESSIONS_SET):
        user_role = getattr(s, "user_role", None)
        if hasattr(user_role, "value"):
            user_role = user_role.value
        if not user_role and hasattr(s, "user_data") and isinstance(s.user_data, dict):
            user_role = s.user_data.get("role")
        if str(user_role) == str(role):
            tasks.append(_safe_send(s, payload_str))

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = sum(1 for r in results if r is True)
    logger.debug(f"[RoleSend] {method} отправлен роли {role} в {sent_count} сессий")
    return sent_count


__all__ = [
    "broadcast",
    "broadcast_notification",
    "send_to_user",
    "send_to_role",
    "get_session_uid",
    "_safe_send",
]
