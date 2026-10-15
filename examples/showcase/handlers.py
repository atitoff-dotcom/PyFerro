# -*- coding: utf-8 -*-
"""
RPC handlers for the PyFerro Showcase demonstration application.
Demonstrates framework core features and plugins:
1. JSON-RPC 2.0 methods (@rpc_method / @app.rpc)
2. RFC 0002 Tabular Data Compression (@tabular_response)
3. RFC 0001 Smart Cache & Tag-based Invalidation (@invalidates, invalidate_tags)
4. Multi-return Streaming (stream: true, send_stream_chunk)
5. Symmetric Reverse RPC (server calls browser method via session.send_request)
6. Realtime Broadcast (broadcast_notification O(1))
7. RBAC & Security (roles GUEST, USER, ADMIN)
8. SEO & Bot Detector (plugins.seo.detector)
"""

import asyncio
import time
import platform
import sys
from typing import Dict, Any, List, Optional
import orjson
from sqlalchemy import select, delete, update, or_
from sqlalchemy.orm import selectinload

from pyferro.core.session import (
    rpc_method, JsonRpcSession, RPCError,
    ACTIVE_SESSIONS_SET, current_rpc_id_ctx, current_transport_ctx
)
from pyferro.core.tabular import tabular_response, pack_tabular
from pyferro.core.logger import logger
from pyferro.db import async_session
from pyferro.broadcast import broadcast_notification
from pyferro.smart_cache import invalidates, version_registry, invalidate_tags
from pyferro.plugins.seo import is_bot, is_search_bot
from pyferro.auth import User, system_bypass_ctx

try:
    from .models import Task, Document
except ImportError:
    from models import Task, Document


class DemoSessionData:
    """Lightweight session context object for showcase demonstration."""
    def __init__(self, username: str = "guest_user", role: str = "guest", session_id: int = 1, user_id: Optional[int] = None):
        self.username = username
        self.role_name = role
        self.session_id = session_id
        if user_id is not None:
            self.user_id = user_id
        elif role == "admin":
            self.user_id = 1
        elif role == "user":
            self.user_id = 2
        else:
            self.user_id = None

        if role == "admin":
            self.user_role = "admin"
            self.user_roles = ["admin", "user"]
        elif role == "user":
            self.user_role = "user"
            self.user_roles = ["user"]
        else:
            self.user_role = None
            self.user_roles = []

    @property
    def role(self) -> str:
        return self.user_role or self.role_name

    @property
    def roles(self) -> list:
        return self.user_roles

    def has_rpc_permission(self, method_name: str) -> bool:
        if self.user_role == "admin" or "admin" in self.user_roles:
            return True
        return False


def get_current_role(session) -> str:
    """Safely extracts role string from session or session.data."""
    target = getattr(session, "data", None) or session
    role = getattr(target, "user_role", None) or getattr(session, "user_role", None)
    if not role:
        return "guest"
    if hasattr(role, "value"):
        return role.value
    return str(role)


# --- 1. SYSTEM METHODS (HEALTH & PING) ---

@rpc_method("system.ping", public=True)
async def ping(session, params: dict):
    """Ultra-fast ping-pong to measure network Round Trip Time (RTT)."""
    return {
        "status": "pong",
        "server_time": time.time(),
        "granian": "rsgi"
    }


@rpc_method("system.info", public=True)
async def system_info(session, params: dict):
    """System information, active sessions, and environment metrics."""
    transport = current_transport_ctx.get() or session
    role_val = get_current_role(transport)
    sid = getattr(transport, "session_id", getattr(session, "session_id", 1))

    return {
        "framework": "PyFerro",
        "rsgi_server": "Granian (Rust)",
        "python_version": sys.version.split()[0],
        "os_platform": platform.platform(),
        "active_sessions_count": len(ACTIVE_SESSIONS_SET),
        "your_session_id": sid,
        "your_current_role": role_val,
        "database": "SQLite (aiosqlite + SQLAlchemy 2.0)",
    }


# --- 2. TABULAR COMPRESSION (RFC 0002) & TASKS ---

# Заранее сгенерированный эталонный массив для наглядного сравнения сжатия
BENCHMARK_TASKS = [
    {
        "id": i,
        "title": f"Оптимизация сетевого протокола #{i} (WSRPC High Load)",
        "completed": (i % 2 == 0),
        "priority": ["low", "normal", "high"][i % 3],
        "creator_id": (i % 3) + 1,
        "owner_id": (i % 3) + 1,
        "created_at": f"2026-10-10T12:{i:02d}:00Z",
    }
    for i in range(1, 26)
]


@rpc_method("tasks.benchmark_tabular", public=True)
@rpc_method("tasks.tabular_demo", public=True)
@rpc_method("tasks.benchmark", public=True)
async def benchmark_tabular(session: JsonRpcSession, params: dict = None):
    """
    Честное сравнение сетевого объема одного и того же заранее сгенерированного массива:
    Raw JSON (список словарей) против RFC 0002 Tabular ($tabular: true, fields, rows).
    """
    import json
    fields = ["id", "title", "completed", "priority", "creator_id", "owner_id", "created_at"]
    tabular_payload = pack_tabular(BENCHMARK_TASKS, fields=fields)

    raw_json_str = json.dumps(BENCHMARK_TASKS, ensure_ascii=False)
    tabular_json_str = json.dumps(tabular_payload, ensure_ascii=False)

    raw_bytes = len(raw_json_str.encode("utf-8"))
    tabular_bytes = len(tabular_json_str.encode("utf-8"))
    saved_percent = round((1.0 - (tabular_bytes / raw_bytes)) * 100, 1) if raw_bytes > 0 else 0

    return {
        "raw_json": raw_json_str,
        "tabular_json": tabular_json_str,
        "raw_bytes": raw_bytes,
        "tabular_bytes": tabular_bytes,
        "saved_percent": f"{saved_percent}%",
        "count": len(BENCHMARK_TASKS),
        "fields": fields
    }


@rpc_method("tasks.list", public=True)
@tabular_response(fields=["id", "title", "completed", "priority", "creator_id", "owner_id", "created_at"])
async def list_tasks(session: JsonRpcSession, params: dict = None):
    """
    Получение списка задач в сжатом табличном формате (RFC 0002).

    Возвращает список задач с поддержкой сжатия RFC 0002 ($tabular: true).
    Демонстрирует гранулярные права (read_global=True в RolePermission):
    пользователи видят все задачи, но CUD-операции разрешены только над своими.
    """
    params = params or {}
    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    uid = getattr(data, "user_id", None)
    only_mine = params.get("only_mine", False)

    async with async_session() as db:
        query = select(Task)
        if only_mine and uid:
            from pyferro.plugins.crud.identity import DefaultIdentityProvider
            identity = DefaultIdentityProvider()
            effective_ids = await identity.effective_user_ids(uid, "Task", db)
            query = query.where(Task.owner_id.in_(effective_ids))
        elif only_mine and not uid:
            return []

        result = await db.execute(query.order_by(Task.id.desc()))
        tasks = result.scalars().all()
        return [t.to_dict() for t in tasks]


@rpc_method("tasks.list_raw_json", public=True)
async def list_tasks_raw_json(session: JsonRpcSession, params: dict = None):
    """
    Returns the exact same tasks WITHOUT tabular compression (regular list of dicts).
    Used on the client for live side-by-side wire size comparison.
    """
    params = params or {}
    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    uid = getattr(data, "user_id", None)
    only_mine = params.get("only_mine", False)

    async with async_session() as db:
        query = select(Task)
        if only_mine and uid:
            from pyferro.plugins.crud.identity import DefaultIdentityProvider
            identity = DefaultIdentityProvider()
            effective_ids = await identity.effective_user_ids(uid, "Task", db)
            query = query.where(Task.owner_id.in_(effective_ids))
        elif only_mine and not uid:
            return []

        result = await db.execute(query.order_by(Task.id.desc()))
        tasks = result.scalars().all()
        return [t.to_dict() for t in tasks]


@rpc_method("tasks.add", public=True)
@rpc_method("tasks.create", public=True)
@invalidates(tags=["tasks", "tasks.list"])
async def add_task(session: JsonRpcSession, params: dict):
    """
    Creates a new task.
    In v0.5.14, creator_id is recorded immutably and owner_id can be assigned.
    """
    title = (params.get("title") or "").strip()
    if not title:
        raise RPCError(-32602, "Task title cannot be empty")

    priority = params.get("priority", "normal")
    if priority not in ("low", "normal", "high"):
        priority = "normal"

    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    creator_id = getattr(data, "user_id", None) or 1
    owner_id = params.get("owner_id") or creator_id

    async with async_session() as db:
        task = Task(title=title, priority=priority, completed=False, creator_id=creator_id, owner_id=owner_id)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_data = task.to_dict()

    await broadcast_notification("tasks.changed", {"action": "added", "id": task.id})
    return task_data


@rpc_method("tasks.complete", public=True)
@rpc_method("tasks.toggle", public=True)
@invalidates(tags=["tasks.list", "task.{id}"])
async def complete_task(session: JsonRpcSession, params: dict):
    """Toggles / completes task status and invalidates tags."""
    task_id = params.get("id") or params.get("task_id")
    if not task_id:
        raise RPCError(-32602, "Task ID is required")

    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    user_id = getattr(data, "user_id", None)
    role = getattr(data, "role_name", "guest")

    async with async_session() as db:
        result = await db.execute(select(Task).where(Task.id == int(task_id)))
        task = result.scalar_one_or_none()
        if not task:
            raise RPCError(404, f"Task #{task_id} not found")

        if role != "admin" and user_id:
            from pyferro.plugins.crud.identity import DefaultIdentityProvider
            identity = DefaultIdentityProvider()
            effective_ids = await identity.effective_user_ids(user_id, "Task", db)
            task_owner = task.owner_id or task.creator_id
            if task_owner not in effective_ids:
                raise RPCError(
                    -32003,
                    f"Доступ запрещен: задача #{task.id} принадлежит пользователю #{task_owner} (требуется активное замещение)"
                )

        task.completed = not task.completed
        await db.commit()
        task_data = task.to_dict()

    await broadcast_notification("tasks.changed", {"action": "toggled", "id": task_id})
    return task_data


@rpc_method("tasks.update", public=True)
@invalidates(tags=["tasks.list", "task.{id}"])
async def update_task(session: JsonRpcSession, params: dict):
    """
    Обновление задачи с валидацией Row-Level Security и прав замещения (v0.5.14).
    """
    task_id = params.get("id") or params.get("task_id")
    if not task_id:
        raise RPCError(-32602, "Task ID is required")

    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    user_id = getattr(data, "user_id", None)
    role = getattr(data, "role_name", "guest")

    async with async_session() as db:
        result = await db.execute(select(Task).where(Task.id == int(task_id)))
        task = result.scalar_one_or_none()
        if not task:
            raise RPCError(404, f"Task #{task_id} not found")

        # Проверка CUD прав:
        # Для admin - полный доступ.
        # Для user - проверка прав владельца или активного замещения в UserDelegation:
        if role != "admin":
            if not user_id:
                raise RPCError(-32003, "Гостям запрещено редактировать задачи")

            from pyferro.plugins.crud.identity import DefaultIdentityProvider
            identity = DefaultIdentityProvider()
            effective_ids = await identity.effective_user_ids(user_id, "Task", db)

            task_owner = task.owner_id or task.creator_id
            if task_owner not in effective_ids:
                raise RPCError(
                    -32003,
                    f"Доступ запрещен: у пользователя #{user_id} нет прав на изменение задачи #{task.id} (владелец: #{task_owner}). "
                    f"Требуется активное замещение (UserDelegation) от пользователя #{task_owner}."
                )

        if "title" in params and params["title"]:
            task.title = str(params["title"]).strip()
        if "priority" in params and params["priority"] in ("low", "normal", "high"):
            task.priority = params["priority"]
        if "completed" in params:
            task.completed = bool(params["completed"])
        if "owner_id" in params and params["owner_id"] is not None:
            # Передача ответственности новому владельцу (разрешено в v0.5.14)
            task.owner_id = int(params["owner_id"])
        if "creator_id" in params and params["creator_id"] != task.creator_id:
            # Попытка изменить автора (запрещено в v0.5.14: creator_id неизменяем)
            raise RPCError(-32003, "Поле creator_id является неизменяемым аудитом создания (Immutable)")

        await db.commit()
        await db.refresh(task)
        task_data = task.to_dict()

    await broadcast_notification("tasks.changed", {"action": "updated", "id": task_id})
    return task_data


@rpc_method("tasks.delete", public=True)
@invalidates(tags=["tasks.list", "task.{id}"])
async def delete_task(session: JsonRpcSession, params: dict):
    """Deletes a task with delegation verification."""
    task_id = params.get("id")
    if not task_id:
        raise RPCError(-32602, "Task ID is required")

    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    user_id = getattr(data, "user_id", None)
    role = getattr(data, "role_name", "guest")

    async with async_session() as db:
        result = await db.execute(select(Task).where(Task.id == int(task_id)))
        task = result.scalar_one_or_none()
        if not task:
            raise RPCError(404, f"Task #{task_id} not found")

        if role != "admin" and user_id:
            from pyferro.plugins.crud.identity import DefaultIdentityProvider
            identity = DefaultIdentityProvider()
            effective_ids = await identity.effective_user_ids(user_id, "Task", db)
            task_owner = task.owner_id or task.creator_id
            if task_owner not in effective_ids:
                raise RPCError(
                    -32003,
                    f"Доступ запрещен: нельзя удалить задачу #{task.id} пользователя #{task_owner} без активного замещения"
                )

        await db.delete(task)
        await db.commit()

    await broadcast_notification("tasks.changed", {"action": "deleted", "id": task_id})
    return {"deleted": True, "id": task_id}


# --- 3. SMART CACHE (RFC 0001) & TAG INVALIDATION ---

@rpc_method("cache.get_versions", public=True)
async def cache_get_versions(session: JsonRpcSession, params: dict = None):
    """Returns current monotonic cache tag versions directly from server memory."""
    return version_registry.get_all_versions()


@rpc_method("tasks.invalidate_cache", public=True)
@rpc_method("cache.manual_invalidate", public=True)
async def cache_manual_invalidate(session: JsonRpcSession, params: dict):
    """Manually invalidates specified tags for testing and UI demonstration."""
    tags = params.get("tags") or params.get("tag") or ["tasks.list"]
    if isinstance(tags, str):
        tags = [tags]
    new_versions = await invalidate_tags(tags, reason="manual_ui_trigger")
    return {"invalidated_tags": tags, "new_versions": new_versions}


# --- 4. MULTI-RETURN STREAMING ---

@rpc_method("analytics.generate", public=True)
@rpc_method("stream.heavy_job", public=True)
async def generate_analytics(session, params: dict = None):
    """
    Demonstrates multi-return streaming (stream: true).
    The server sends intermediate progress chunks to the client
    without blocking other requests in the same WebSocket connection!
    """
    rpc_id = current_rpc_id_ctx.get()
    transport = current_transport_ctx.get() or session
    steps = [
        (25, "1/4 Инициализация структур и прогрев кэша..."),
        (50, "2/4 Сканирование индексов SQLite..."),
        (75, "3/4 Табличное сжатие данных (RFC 0002)..."),
        (90, "4/4 Вычисление контрольных сумм SHA-256..."),
    ]

    for pct, message in steps:
        await asyncio.sleep(0.4)
        if hasattr(transport, "send_stream_chunk"):
            await transport.send_stream_chunk(rpc_id, {
                "progress": pct,
                "step": f"{pct}%",
                "message": message,
                "timestamp": time.strftime("%H:%M:%S")
            })

    await asyncio.sleep(0.3)
    return {
        "progress": 100,
        "message": "Операция аналитики успешно завершена!",
        "summary": "Обработано 1,000 записей за 1.5с.",
        "finished_at": time.strftime("%H:%M:%S")
    }


# --- 5. REVERSE RPC (SERVER CALLS CLIENT) ---

@rpc_method("admin.inspect_client", public=True)
@rpc_method("reverse_rpc.ask_client", public=True)
async def inspect_client(session, params: dict = None):
    """
    Symmetric JSON-RPC 2.0: The server initiates a request to the browser
    via session.send_request(...) and awaits the client's response!
    """
    transport = current_transport_ctx.get() or session

    try:
        client_response = await transport.send_request(
            method="client.get_env",
            params={"requested_by": "pyferro_server", "query_time": time.time()},
            timeout=5.0
        )
        return {
            "status": "success",
            "message": "Сервер успешно получил ответ от вашего браузера!",
            "client_payload": client_response.get("result") or client_response
        }
    except asyncio.TimeoutError:
        raise RPCError(-32000, "Timeout: Браузер не ответил серверу в течение 5 секунд")
    except Exception as e:
        raise RPCError(-32000, f"Reverse RPC call error: {e}")


# --- 6. REALTIME BROADCAST ---

@rpc_method("alerts.publish", public=True)
@rpc_method("broadcast.send_announcement", public=True)
async def publish_alert(session, params: dict):
    """
    Broadcasts message to all active WebSocket sessions in O(1)
    with single memory serialization.
    """
    text = (params.get("message") or params.get("text") or "").strip()
    if not text:
        raise RPCError(-32602, "Message text cannot be empty")

    transport = current_transport_ctx.get() or session
    sid = getattr(transport, "session_id", getattr(session, "session_id", 1))
    payload = {
        "message": text,
        "text": text,
        "author": f"Session #{sid}",
        "timestamp": time.strftime("%H:%M:%S"),
        "session_id": sid,
    }
    await broadcast_notification("system.alert", payload)
    return {"sent": True, "recipients_count": len(ACTIVE_SESSIONS_SET)}


# --- 7. ROLES & RBAC (DEMO AUTH & DELEGATIONS) ---

DEMO_USERS = {
    "admin": {"user_id": 1, "password": "admin123", "role": "admin", "name": "Администратор (ID #1)"},
    "user": {"user_id": 2, "password": "user123", "role": "user", "name": "Alice (ID #2)"},
    "alice": {"user_id": 2, "password": "user123", "role": "user", "name": "Alice (ID #2)"},
    "bob": {"user_id": 3, "password": "bob123", "role": "user", "name": "Bob (ID #3)"},
}

DEMO_TOKENS: Dict[str, dict] = {}


async def authenticate_credentials(username: str, password: str) -> Optional[dict]:
    """
    Валидирует учетные данные пользователя:
    1. Сначала в базе данных (auth_user) через User.verify_password (поддержка PBKDF2-SHA256).
    2. Если пользователь не найден в БД — проверяет встроенные demo-пресеты в памяти.
    """
    u = (username or "").strip()
    if not u or not password:
        return None

    # 1. Проверка в реальной базе данных (auth_user)
    from pyferro.db import system_bypass
    try:
        with system_bypass():
            async with async_session() as db:
                stmt = select(User).options(selectinload(User.roles)).where(or_(User.login == u, User.email == u))
                user = (await db.execute(stmt)).scalar_one_or_none()
                if user:
                    if user.verify_password(password):
                        roles = [r.name for r in user.roles] if user.roles else []
                        role_name = "admin" if ("admin" in roles or getattr(user, "is_superadmin", False)) else (roles[0] if roles else "user")
                        return {
                            "username": user.login or u,
                            "role": role_name,
                            "name": user.name or user.login or u,
                            "user_id": user.id,
                        }
                    else:
                        # Пользователь найден в БД, но пароль не подошел
                        return None
    except Exception as e:
        logger.warning(f"[Showcase] Ошибка проверки учетных данных в БД: {e}")

    # 2. Фолбэк на demo-аккаунты в памяти (например, быстрый логин 'user' / 'alice' / 'bob')
    u_lower = u.lower()
    if u_lower in DEMO_USERS:
        expected = DEMO_USERS[u_lower]
        if password == expected["password"] or password == u_lower or password == "user123":
            return {"username": u_lower, "role": expected["role"], "name": expected["name"], "user_id": expected["user_id"]}

    return None


@rpc_method("auth.login", public=True)
async def auth_login(session, params: dict):
    """
    Аутентификация с проверкой логина и пароля в базе данных и demo-аккаунтах.
    """
    username = params.get("username", "")
    password = params.get("password", "")

    user_info = await authenticate_credentials(username, password)
    if not user_info:
        raise RPCError(-32602, "Неверный логин или пароль")

    transport = current_transport_ctx.get() or session
    sid = getattr(transport, "session_id", getattr(session, "session_id", 1))

    from pyferro.core.security import create_access_token
    token, _, _ = create_access_token(
        user_id=user_info["user_id"],
        username=user_info["username"],
        roles=[user_info["role"]],
    )
    DEMO_TOKENS[token] = user_info

    # Если логинится администратор, регистрируем его также в сессиях CRUD-плагина
    if user_info["role"] == "admin":
        from pyferro.plugins.crud import create_crud_session
        create_crud_session(user_info, token=token)

    demo_data = DemoSessionData(
        username=user_info["username"],
        role=user_info["role"],
        session_id=sid,
        user_id=user_info["user_id"]
    )

    if hasattr(transport, "data"):
        transport.data = demo_data
    if hasattr(session, "data"):
        session.data = demo_data

    return {
        "success": True,
        "token": token,
        "username": user_info["username"],
        "name": user_info["name"],
        "role": user_info["role"],
        "user_id": user_info["user_id"],
    }


@rpc_method("auth.logout", public=True)
async def auth_logout(session, params: dict = None):
    """Выход из аккаунта и сброс роли до Guest."""
    token = (params or {}).get("token")
    if token and token in DEMO_TOKENS:
        DEMO_TOKENS.pop(token, None)

    transport = current_transport_ctx.get() or session
    sid = getattr(transport, "session_id", getattr(session, "session_id", 1))

    demo_data = DemoSessionData(username="guest_user", role="guest", session_id=sid, user_id=None)
    if hasattr(transport, "data"):
        transport.data = demo_data
    if hasattr(session, "data"):
        session.data = demo_data

    return {"success": True, "role": "guest"}


@rpc_method("auth.me", public=True)
@rpc_method("auth.whoami", public=True)
async def auth_whoami(session, params: dict = None):
    """Возвращает информацию о текущей роли и сессии сокета."""
    transport = current_transport_ctx.get() or session
    data = getattr(transport, "data", None) or getattr(session, "data", None)
    if data and getattr(data, "role_name", None) in ("admin", "user"):
        uid = getattr(data, "user_id", None)
        uname = getattr(data, "username", "")
        if uid == 1:
            name_val = "Администратор (ID #1)"
        elif uid == 2:
            name_val = "Alice (ID #2)"
        elif uid == 3:
            name_val = "Bob (ID #3)"
        else:
            name_val = uname or "Пользователь"

        return {
            "authenticated": True,
            "username": uname,
            "role": getattr(data, "role_name", "guest"),
            "name": name_val,
            "user_id": uid,
        }
    return {
        "authenticated": False,
        "username": "guest_user",
        "role": "guest",
        "name": "Гость",
        "user_id": None,
    }


@rpc_method("auth.set_role", public=True)
async def set_role(session, params: dict):
    """
    Switches session role for RBAC & delegation inspection.
    Allowed roles: 'guest', 'user', 'admin' or target user ('alice', 'bob').
    """
    role_param = str(params.get("role") or "").lower()
    target_uid = params.get("user_id")

    if target_uid == 1 or role_param == "admin":
        uid = 1
        role_name = "admin"
        username = "admin"
    elif target_uid == 2 or role_param in ("user", "alice"):
        uid = 2
        role_name = "user"
        username = "alice"
    elif target_uid == 3 or role_param == "bob":
        uid = 3
        role_name = "user"
        username = "bob"
    else:
        uid = None
        role_name = "guest"
        username = "guest_user"

    transport = current_transport_ctx.get() or session
    sid = getattr(transport, "session_id", getattr(session, "session_id", 1))

    demo_data = DemoSessionData(
        username=username,
        role=role_name,
        session_id=sid,
        user_id=uid
    )

    if hasattr(transport, "data"):
        transport.data = demo_data
    if hasattr(session, "data"):
        session.data = demo_data

    role_val = get_current_role(transport)
    return {
        "session_id": sid,
        "role": role_val,
        "user_id": uid,
        "username": username,
    }


# --- ДЕЛЕГИРОВАНИЕ И ГРАНУЛЯРНЫЙ КОНТРОЛЬ ДОСТУПА (v0.5.14) ---

@rpc_method("delegation.list", public=True)
async def list_delegations(session: JsonRpcSession, params: dict = None):
    """
    Получение списка активных замещений полномочий (v0.5.14 auth_user_delegation).
    """
    from pyferro.auth import UserDelegation, User
    from pyferro.db import system_bypass

    with system_bypass():
        async with async_session() as db:
            stmt = select(UserDelegation).order_by(UserDelegation.id.asc())
            delegations = (await db.execute(stmt)).scalars().all()

            users_stmt = select(User)
            users_map = {u.id: (u.name or u.login) for u in (await db.execute(users_stmt)).scalars().all()}

            return [
                {
                    "id": d.id,
                    "from_user_id": d.from_user_id,
                    "from_user_name": users_map.get(d.from_user_id, f"User #{d.from_user_id}"),
                    "to_user_id": d.to_user_id,
                    "to_user_name": users_map.get(d.to_user_id, f"User #{d.to_user_id}"),
                    "model_name": d.model_name or "Все модели",
                    "is_active": d.is_active,
                    "valid_from": d.valid_from.isoformat() if d.valid_from else None,
                    "valid_to": d.valid_to.isoformat() if d.valid_to else None,
                }
                for d in delegations
            ]


@rpc_method("delegation.toggle", public=True)
@invalidates(tags=["delegations", "tasks.list"])
async def toggle_delegation(session: JsonRpcSession, params: dict):
    """
    Переключение активности замещения (включение/отключение делегирования).
    """
    from pyferro.auth import UserDelegation
    from pyferro.db import system_bypass

    delegation_id = params.get("id")
    with system_bypass():
        async with async_session() as db:
            if delegation_id:
                stmt = select(UserDelegation).where(UserDelegation.id == int(delegation_id))
            else:
                # По умолчанию переключаем демо-замещение: Боб (3) -> Алиса (2)
                stmt = select(UserDelegation).where(
                    UserDelegation.from_user_id == 3,
                    UserDelegation.to_user_id == 2
                )
            delegation = (await db.execute(stmt)).scalar_one_or_none()
            if not delegation:
                delegation = UserDelegation(
                    from_user_id=3,
                    to_user_id=2,
                    model_name="Task",
                    is_active=True
                )
                db.add(delegation)
                await db.commit()
                await db.refresh(delegation)
            else:
                delegation.is_active = not delegation.is_active
                await db.commit()
                await db.refresh(delegation)

            res = {
                "id": delegation.id,
                "from_user_id": delegation.from_user_id,
                "to_user_id": delegation.to_user_id,
                "is_active": delegation.is_active,
                "model_name": delegation.model_name or "Все модели",
            }

    await broadcast_notification("delegations.changed", res)
    return res


@rpc_method("rbac.simulate", public=True)
async def rbac_simulate(session: JsonRpcSession, params: dict):
    """
    Интерактивная диагностика прав доступа по спецификации v0.5.14.

    Принимает:
    - as_user_id: 1 (Admin), 2 (Alice), 3 (Bob), None (Guest)
    - action: "read" | "update" | "delete"
    - target_task_id: ID задачи
    """
    as_user_id = params.get("as_user_id")
    action = params.get("action", "update")
    target_task_id = params.get("target_task_id", 4)  # По умолчанию задача Боба (#4 или #5)

    from pyferro.db import system_bypass
    from pyferro.auth import User
    from pyferro.plugins.crud.identity import DefaultIdentityProvider

    with system_bypass():
        async with async_session() as db:
            task = (await db.execute(select(Task).where(Task.id == int(target_task_id)))).scalar_one_or_none()
            if not task:
                # Если задачи нет, возьмем первую доступную
                task = (await db.execute(select(Task).order_by(Task.id.desc()))).scalars().first()
                if not task:
                    raise RPCError(404, "Задачи не найдены в базе данных")

            if as_user_id is None:
                return {
                    "allowed": False,
                    "reason": "❌ Отказано: Неавторизованный гость не имеет прав на изменение бизнес-данных (Default Deny)",
                    "details": {"action": action, "task_id": task.id, "creator_id": task.creator_id, "owner_id": task.owner_id}
                }

            user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == int(as_user_id)))).scalar_one_or_none()
            if not user:
                raise RPCError(404, f"User #{as_user_id} not found")

            is_admin = any(r.name == "admin" for r in user.roles)
            if is_admin:
                return {
                    "allowed": True,
                    "reason": f"✅ Разрешено: Администратор ({user.name}) обладает глобальными правами на все записи",
                    "details": {"role": "admin", "action": action, "task_id": task.id, "owner_id": task.owner_id}
                }

            # Гранулярная проверка для роли user
            identity = DefaultIdentityProvider()
            effective_ids = await identity.effective_user_ids(user.id, "Task", db)
            delegated_ids = list(effective_ids - {user.id})

            if action == "read":
                # read_global=True в RolePermission
                return {
                    "allowed": True,
                    "reason": f"✅ Разрешено: Пользователь '{user.name}' может читать задачу: в матрице прав включен глобальный скоуп read_global=True (C R U D: Все 🌐)",
                    "details": {"read_global": True, "task_id": task.id, "owner_id": task.owner_id}
                }

            task_owner = task.owner_id or task.creator_id
            is_own = (task_owner == user.id)
            is_delegated = (task_owner in delegated_ids)

            if is_own:
                return {
                    "allowed": True,
                    "reason": f"✅ Разрешено: Пользователь '{user.name}' является прямым владельцем задачи #{task.id} (owner_id={task_owner})",
                    "details": {"is_own": True, "action": action, "task_id": task.id}
                }
            elif is_delegated:
                return {
                    "allowed": True,
                    "reason": f"✅ Разрешено через делегирование: Пользователь '{user.name}' наделен правами на задачу #{task.id} через активное замещение (UserDelegation: Боб ➔ Алиса)",
                    "details": {"is_delegated": True, "delegated_from": task_owner, "action": action, "task_id": task.id}
                }
            else:
                return {
                    "allowed": False,
                    "reason": f"❌ Отказано в доступе: Задача #{task.id} принадлежит пользователю #{task_owner}. В матрице прав update_global=False (Только свои 👤), а активное замещение от пользователя #{task_owner} выключено",
                    "details": {"is_own": False, "is_delegated": False, "required_owner": task_owner, "active_delegations": delegated_ids}
                }



@rpc_method("admin.system_info", role="admin")
async def admin_system_info(session: JsonRpcSession, params: dict):
    """
    Protected method: accessible ONLY with admin role.
    If unauthorized, framework automatically returns RPCError(-32003, Access denied).
    """
    import os
    return {
        "status": "authorized",
        "secret_system_data": {
            "pid": os.getpid(),
            "active_sockets": len(ACTIVE_SESSIONS_SET),
            "cpu_count": os.cpu_count(),
            "python_implementation": platform.python_implementation(),
            "security_guard": "RBAC Verified by pyferro decorator",
        }
    }


# --- 8. DOCUMENTS (SECOND MODEL FOR CRUD & TABULAR) ---

@rpc_method("documents.list", public=True)
@tabular_response(fields=["id", "title", "category", "views", "updated_at"])
async def list_documents(session: JsonRpcSession, params: dict):
    """
    Просмотр архива документов и отчетов.

    Возвращает список документов в сжатом табличном формате RFC 0002.
    Демонстрирует раздачу данных для публичных гостей и авторизованных пользователей.
    """
    async with async_session() as db:
        result = await db.execute(select(Document).order_by(Document.id.desc()))
        docs = result.scalars().all()
        return [d.to_dict() for d in docs]


# --- 9. SEO & BOT DETECTOR (PLUGINS.SEO) ---

@rpc_method("seo.simulate_bot", public=True)
@rpc_method("seo.simulate", public=True)
async def simulate_bot_check(session: JsonRpcSession, params: dict):
    """
    Simulates User-Agent inspection using plugins.seo.detector.
    Determines whether a client is a search engine crawler or scraper.
    """
    bot_type = params.get("bot")
    if bot_type == "browser":
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    else:
        user_agent = params.get("user_agent") or "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    is_a_bot = is_bot(user_agent)
    is_a_search_bot = is_search_bot(user_agent)

    return {
        "user_agent": user_agent,
        "is_bot": is_a_bot,
        "is_search_bot": is_a_search_bot,
        "type": "SSR Static HTML" if is_a_bot else "Interactive SPA",
        "content_preview": "Bot crawler detected" if is_a_bot else "Regular browser connection",
        "recommendation": "Render Static HTML with OpenGraph tags" if is_a_bot else "Serve Single-Page App WebSockets",
    }
