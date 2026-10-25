# -*- coding: utf-8 -*-
"""
pyferro.auth.auditor: Реальный HTTP/WS клиент-аудитор прав доступа (RPC & CRUD).
Позволяет подключаться под любым реальным пользователем из БД без знания его пароля,
проверять доступ ко всем зарегистрированным RPC-методам и CRUD-моделям через
префлайт-режим `check_access: True` (гарантированно БЕЗ запуска самих обработчиков)
и сверять фактический ответ сокета с матрицей прав в базе данных CRUD.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import orjson
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from pyferro.auth.discovery import DEFAULT_LOGIN_METHODS, reload_guest_permissions_cache
from pyferro.auth.models import (
    ActiveSession,
    RefreshToken,
    Role,
    RpcPermission,
    User,
)
from pyferro.core.constants import ADMIN_ROLE, GUEST_ROLE
from pyferro.core.logger import logger
from pyferro.core.session import (
    ACTIVE_SESSIONS_SET,
    GUEST_ALLOWED_CRUD_MODELS,
    JsonRpcSession,
    RPC_REGISTRY,
    is_guest_rpc_allowed,
)
from pyferro.db import system_db_session


async def reload_active_sessions_permissions() -> int:
    """
    Мгновенно перезагружает права (allowed_rpc_methods, perms_dict, ролевые и персональные права)
    из базы данных для всех открытых в данный момент авторизованных WebSocket-сессий.
    Возвращает количество обновленных сессий.
    """
    await reload_guest_permissions_cache()
    active_list = [s for s in list(ACTIVE_SESSIONS_SET) if getattr(s, "authenticated", False) and getattr(s, "user_id", None)]
    if not active_list:
        return 0

    updated_count = 0
    async with system_db_session() as db:
        user_cache: Dict[int, Any] = {}
        for sess in active_list:
            uid = sess.user_id
            if not uid:
                continue
            if uid not in user_cache:
                stmt = select(User).options(
                    selectinload(User.roles).selectinload(Role.permissions),
                    selectinload(User.roles).selectinload(Role.rpc_permissions),
                    selectinload(User.teams),
                    selectinload(User.permissions),
                    selectinload(User.rpc_permissions),
                    selectinload(User.delegations_received),
                ).where(User.id == uid)
                user_cache[uid] = (await db.execute(stmt)).scalar_one_or_none()

            user_obj = user_cache.get(uid)
            if not user_obj or not sess.data:
                continue

            user_ctx = user_obj.get_permissions()
            role_names = [r.name for r in user_obj.roles] if user_obj.roles else ["user"]
            role_name = role_names[0] if role_names else "user"

            if hasattr(sess.data, "user_ctx"):
                sess.data.user_ctx = user_ctx
            if hasattr(sess.data, "allowed_rpc_methods"):
                sess.data.allowed_rpc_methods = set(getattr(user_ctx, "allowed_rpc_methods", set()))
            if hasattr(sess.data, "role"):
                sess.data.role = role_name
            if hasattr(sess.data, "roles"):
                sess.data.roles = role_names
            if hasattr(sess.data, "user_role"):
                sess.data.user_role = role_name
            if hasattr(sess.data, "user_roles"):
                sess.data.user_roles = role_names
            updated_count += 1

    return updated_count


class _InboundWsFrame:
    """Входящий фрейм WebSocket для цикла JsonRpcSession.start()."""

    def __init__(self, data: str):
        self.data = data


class _InboundCloseMessage:
    """Сигнал закрытия WebSocket-соединения."""
    pass


class _LoopbackWsTransport:
    """Двусторонний WebSocket-транспорт для подключения реального клиента к JsonRpcSession."""

    def __init__(self):
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.outbound: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def receive(self):
        if self.closed:
            return _InboundCloseMessage()
        return await self.inbound.get()

    async def send_str(self, payload_str: str):
        await self.outbound.put(payload_str)

    async def send_bytes(self, payload_bytes: bytes):
        await self.outbound.put(payload_bytes.decode("utf-8"))

    async def close(self):
        self.closed = True
        await self.inbound.put(_InboundCloseMessage())


class LiveWsAuditClient:
    """
    Реальный клиент с HTTP Scope (Cookies) и дуплексным WebSocket-соединением,
    работающий поверх боевого цикла `JsonRpcSession.start()`.
    """

    _audit_session_seq = 900000

    def __init__(self, cookies: Optional[Dict[str, str]] = None, ip: str = "127.0.0.1"):
        self.cookies = cookies or {}
        self.ip = ip
        self._transport = _LoopbackWsTransport()
        self._session: Optional[JsonRpcSession] = None
        self._session_task: Optional[asyncio.Task] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._next_id = 1
        self._pending: Dict[int, asyncio.Future] = {}

    async def connect(self) -> "LiveWsAuditClient":
        LiveWsAuditClient._audit_session_seq += 1
        sid = LiveWsAuditClient._audit_session_seq

        headers = []
        if self.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items() if v)
            if cookie_str:
                headers.append(("cookie", cookie_str))

        scope = {
            "proto": "websocket",
            "path": "/ws",
            "headers": headers,
            "client": (self.ip, 0),
        }

        self._session = JsonRpcSession(self._transport, session_id=sid, ip=self.ip, scope=scope)
        # Disable rate limit for rapid batch audit
        self._session.rate_limit_enabled = False

        if self.cookies:
            # Выполняем штатную авто-авторизацию по HTTP Cookie + дозагрузку прав из БД
            from pyferro.app import FerroApp
            dummy_app = object.__new__(FerroApp)
            dummy_app.session_prefix = "ferro"
            FerroApp._auto_authenticate_ws(dummy_app, self._session)
            await FerroApp._hydrate_ws_auth_from_db(dummy_app, self._session)

        self._session_task = asyncio.create_task(self._session.start())
        self._reader_task = asyncio.create_task(self._read_loop())
        return self

    async def _read_loop(self):
        try:
            while not self._transport.closed:
                raw = await self._transport.outbound.get()
                if raw is None:
                    break
                data = orjson.loads(raw)
                req_id = data.get("id")
                if req_id is not None and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(data)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def send_raw_rpc(self, payload: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        payload["id"] = req_id
        payload["jsonrpc"] = "2.0"

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        await self._transport.inbound.put(_InboundWsFrame(orjson.dumps(payload).decode("utf-8")))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(req_id, None)

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Any:
        resp = await self.send_raw_rpc({"method": method, "params": params or {}}, timeout=timeout)
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"RPC Error [{err.get('code')}]: {err.get('message')}")
        return resp.get("result")

    async def check_access(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Проверяет доступ к RPC-методу через флаг `check_access: True` по WebSocket.
        Гарантированно НЕ запускает сам обработчик RPC-метода.
        """
        resp = await self.send_raw_rpc(
            {"method": method, "params": params or {}, "check_access": True},
            timeout=timeout,
        )
        if "error" in resp:
            err = resp["error"]
            return {
                "allowed": False,
                "code": err.get("code", -32003),
                "message": err.get("message", "Denied"),
            }
        res = resp.get("result") or {}
        return {
            "allowed": bool(res.get("allowed", False)),
            "code": 0,
            "message": "OK",
        }

    async def close(self):
        await self._transport.close()
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (Exception, asyncio.CancelledError):
                pass
        if self._session_task:
            try:
                await asyncio.wait_for(self._session_task, timeout=2.0)
            except (Exception, asyncio.CancelledError):
                self._session_task.cancel()
    async def __aenter__(self) -> "LiveWsAuditClient":
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


def _compute_expected_rpc_access(
    method_name: str,
    target_type: str,
    is_superadmin: bool,
    effective_rpc_set: set[str],
    target_roles: Optional[set[str]] = None,
) -> bool:
    """Вычисляет ожидаемый доступ к RPC-методу согласно данным БД CRUD."""
    handler = RPC_REGISTRY.get(method_name)
    method_scopes = getattr(handler, "scopes", None) if handler else None
    if method_scopes:
        if target_type == "guest":
            return False
        if not is_superadmin:
            if not target_roles or not (target_roles & method_scopes):
                return False
    if method_name.startswith("permissions."):
        return bool(is_superadmin)

    if target_type == "guest":
        from pyferro.core.lib.config import settings
        login_rpc = settings.security.get("login_rpc")
        return bool(
            method_name in effective_rpc_set
            or is_guest_rpc_allowed(method_name)
            or (login_rpc is not None and (login_rpc == "" or method_name.startswith(login_rpc)))
            or method_name.startswith("login.")
            or method_name in ("auth.login", "auth.me", "auth.whoami", "auth.submit")
        )

    if is_superadmin or "*" in effective_rpc_set:
        return True

    if method_name in effective_rpc_set:
        return True

    for pattern in effective_rpc_set:
        if pattern.endswith(".*") and method_name.startswith(pattern[:-1]):
            return True

    if (
        is_guest_rpc_allowed(method_name)
        or method_name.startswith("login.")
        or method_name in ("auth.login", "auth.me", "auth.whoami", "auth.submit", "auth.logout")
    ):
        return True

    return False


async def audit_target_permissions(target_type: str, target_id: int) -> Dict[str, Any]:
    """
    Подключается реальным WS-клиентом (через login.refresh без знания пароля и через HTTP Cookie),
    проверяет доступ ко всем RPC-методам и CRUD-моделям в режиме `check_access: True` (без запуска RPC)
    и сравнивает результаты с эталоном в базе данных CRUD.
    """
    await reload_guest_permissions_cache()

    from pyferro.plugins.crud.registry import ModelRegistry
    from pyferro.db import Base
    if not ModelRegistry.all():
        ModelRegistry.auto_discover(Base)

    blacklist_models = {
        "UserRole", "UserTeam", "RoleRpcPermission", "UserRpcPermission",
        "UserPermission", "RolePermission", "RefreshToken", "ActiveSession",
        "OAuthAccount", "CacheTagVersion", "SystemData",
    }
    model_keys = sorted(
        m.key for m in ModelRegistry.all().values() if m.key not in blacklist_models
    )

    rpc_methods = sorted(
        name for name in RPC_REGISTRY.keys()
        if not name.startswith("crud.")
        and not name.startswith("permissions.")
        and name not in ("system.ping", "system.status", "system.ws_status")
    )

    temp_user_id: Optional[int] = None
    temp_rt_id: Optional[int] = None
    temp_token_str: Optional[str] = None
    target_name = ""
    is_superadmin = False
    effective_rpc_set: set[str] = set()
    effective_crud_dict: Dict[str, Dict[str, bool]] = {}
    target_roles: set[str] = set()
    try:
        async with system_db_session() as db:
            if target_type == "guest":
                target_name = "Гости (guest)"
                target_roles = {GUEST_ROLE}
                stmt_guest = select(Role).options(
                    selectinload(Role.permissions),
                    selectinload(Role.rpc_permissions),
                ).where(Role.name == GUEST_ROLE)
                guest_role = (await db.execute(stmt_guest)).scalar_one_or_none()
                if guest_role:
                    effective_rpc_set = {rp.name for rp in guest_role.rpc_permissions}
                    for p in guest_role.permissions:
                        if p.can_read:
                            effective_crud_dict[p.model_name] = {
                                "can_create": False,
                                "can_read": True,
                                "can_update": False,
                                "can_delete": False,
                            }

            elif target_type == "user":
                stmt_u = select(User).options(
                    selectinload(User.roles).selectinload(Role.permissions),
                    selectinload(User.roles).selectinload(Role.rpc_permissions),
                    selectinload(User.teams),
                    selectinload(User.permissions),
                    selectinload(User.rpc_permissions),
                    selectinload(User.delegations_received),
                ).where(User.id == target_id)
                user = (await db.execute(stmt_u)).scalar_one_or_none()
                if not user:
                    raise ValueError(f"Пользователь с ID {target_id} не найден")

                target_name = user.login or user.name
                is_superadmin = bool(user.is_superadmin)
                target_roles = ({r.name for r in user.roles} if user.roles else {"user"}) | user.get_admin_roles()
                if is_superadmin:
                    target_roles.add("admin")
                effective_rpc_set = set(user.get_allowed_rpc_methods())
                effective_crud_dict = user._get_permissions_dict()

                # Выпускаем короткоживущий сервисный RefreshToken для входа БЕЗ пароля
                temp_token_str = f"audit_{secrets.token_urlsafe(32)}"
                rt = RefreshToken(
                    user_id=user.id,
                    token=temp_token_str,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                )
                db.add(rt)
                await db.commit()
                await db.refresh(rt)
                temp_rt_id = rt.id

            elif target_type == "role":
                stmt_r = select(Role).options(
                    selectinload(Role.permissions),
                    selectinload(Role.rpc_permissions),
                ).where(Role.id == target_id)
                role = (await db.execute(stmt_r)).scalar_one_or_none()
                if not role:
                    raise ValueError(f"Роль с ID {target_id} не найдена")

                target_name = role.name
                is_superadmin = False
                target_roles = {role.name}
                effective_rpc_set = {"*"} if is_superadmin else {rp.name for rp in role.rpc_permissions}
                for p in role.permissions:
                    effective_crud_dict[p.model_name] = {
                        "can_create": bool(p.can_create),
                        "can_read": bool(p.can_read),
                        "can_update": bool(p.can_update),
                        "can_delete": bool(p.can_delete),
                    }

                # Создаем изолированного эфемерного пользователя строго с этой ролью (без пароля)
                eph_login = f"__audit_role_{role.id}_{secrets.token_hex(6)}"
                eph_user = User(name=f"Audit Role {role.name}", login=eph_login, roles=[role])
                db.add(eph_user)
                await db.flush()
                temp_user_id = eph_user.id

                temp_token_str = f"audit_{secrets.token_urlsafe(32)}"
                rt = RefreshToken(
                    user_id=eph_user.id,
                    token=temp_token_str,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                )
                db.add(rt)
                await db.commit()
                await db.refresh(rt)
                temp_rt_id = rt.id
            else:
                raise ValueError(f"Неизвестный target_type: {target_type}")

        has_crud_scope = is_superadmin or bool(target_roles & {"admin", "adm_crud"})

        # --- ЗАПУСК РЕАЛЬНЫХ WS И HTTP COOKIE КЛИЕНТОВ ---
        rpc_results: Dict[str, Dict[str, Any]] = {}
        crud_results: Dict[str, Dict[str, Any]] = {}
        mismatches: List[Dict[str, Any]] = []

        if target_type == "guest":
            async with LiveWsAuditClient() as guest_client:
                for m_name in rpc_methods:
                    expected = _compute_expected_rpc_access(m_name, "guest", False, effective_rpc_set, target_roles)
                    ws_res = await guest_client.check_access(m_name)
                    ws_actual = ws_res["allowed"]
                    match = (expected == ws_actual)
                    rpc_results[m_name] = {
                        "expected": expected,
                        "ws_actual": ws_actual,
                        "cookie_actual": ws_actual,
                        "match": match,
                        "code": ws_res["code"],
                    }
                    if not match:
                        mismatches.append({
                            "kind": "rpc",
                            "target": m_name,
                            "expected": expected,
                            "ws_actual": ws_actual,
                            "cookie_actual": ws_actual,
                        })

                for model_key in model_keys:
                    expected_read = bool(effective_crud_dict.get(model_key, {}).get("can_read", False)) if has_crud_scope else False
                    read_res = await guest_client.check_access("crud.list", {"model": model_key})
                    create_res = await guest_client.check_access("crud.create", {"model": model_key})
                    update_res = await guest_client.check_access("crud.update_cell", {"model": model_key})
                    delete_res = await guest_client.check_access("crud.delete", {"model": model_key})

                    actual_map = {
                        "can_create": create_res["allowed"],
                        "can_read": read_res["allowed"],
                        "can_update": update_res["allowed"],
                        "can_delete": delete_res["allowed"],
                    }
                    expected_map = {
                        "can_create": False,
                        "can_read": expected_read,
                        "can_update": False,
                        "can_delete": False,
                    }
                    model_match = (actual_map == expected_map)
                    crud_results[model_key] = {
                        "expected": expected_map,
                        "ws_actual": actual_map,
                        "cookie_actual": actual_map,
                        "match": model_match,
                    }
                    if not model_match:
                        mismatches.append({
                            "kind": "crud",
                            "target": model_key,
                            "expected": expected_map,
                            "ws_actual": actual_map,
                            "cookie_actual": actual_map,
                        })
        else:
            # 1. Клиент №1: Вход по WebSocket через login.refresh (без пароля!)
            # 2. Клиент №2: Вход по HTTP Cookie (ferro_session + rpc_jwt)
            async with LiveWsAuditClient() as ws_client:
                auth_res = await ws_client.call("login.refresh", {
                    "token": temp_token_str,
                    "user_agent": "PyFerroLiveAuditor/1.0",
                })
                jwt_token = auth_res.get("jwt_token", "")

                cookies = {
                    "ferro_session": temp_token_str or "",
                    "rpc_jwt": jwt_token,
                }
                async with LiveWsAuditClient(cookies=cookies) as cookie_client:
                    for m_name in rpc_methods:
                        expected = _compute_expected_rpc_access(
                            m_name, target_type, is_superadmin, effective_rpc_set, target_roles
                        )
                        ws_res = await ws_client.check_access(m_name)
                        ck_res = await cookie_client.check_access(m_name)
                        ws_actual = ws_res["allowed"]
                        ck_actual = ck_res["allowed"]
                        match = (expected == ws_actual == ck_actual)

                        rpc_results[m_name] = {
                            "expected": expected,
                            "ws_actual": ws_actual,
                            "cookie_actual": ck_actual,
                            "match": match,
                            "code": ws_res["code"],
                        }
                        if not match:
                            mismatches.append({
                                "kind": "rpc",
                                "target": m_name,
                                "expected": expected,
                                "ws_actual": ws_actual,
                                "cookie_actual": ck_actual,
                            })

                    for model_key in model_keys:
                        m_cfg = effective_crud_dict.get(model_key, {})
                        expected_map = {
                            "can_create": True if is_superadmin else (bool(m_cfg.get("can_create", False)) if has_crud_scope else False),
                            "can_read": True if is_superadmin else (bool(m_cfg.get("can_read", False)) if has_crud_scope else False),
                            "can_update": True if is_superadmin else (bool(m_cfg.get("can_update", False)) if has_crud_scope else False),
                            "can_delete": True if is_superadmin else (bool(m_cfg.get("can_delete", False)) if has_crud_scope else False),
                        }
                        ws_actual_map = {
                            "can_create": (await ws_client.check_access("crud.create", {"model": model_key}))["allowed"],
                            "can_read": (await ws_client.check_access("crud.list", {"model": model_key}))["allowed"],
                            "can_update": (await ws_client.check_access("crud.update_cell", {"model": model_key}))["allowed"],
                            "can_delete": (await ws_client.check_access("crud.delete", {"model": model_key}))["allowed"],
                        }
                        ck_actual_map = {
                            "can_create": (await cookie_client.check_access("crud.create", {"model": model_key}))["allowed"],
                            "can_read": (await cookie_client.check_access("crud.list", {"model": model_key}))["allowed"],
                            "can_update": (await cookie_client.check_access("crud.update_cell", {"model": model_key}))["allowed"],
                            "can_delete": (await cookie_client.check_access("crud.delete", {"model": model_key}))["allowed"],
                        }

                        model_match = (expected_map == ws_actual_map == ck_actual_map)
                        crud_results[model_key] = {
                            "expected": expected_map,
                            "ws_actual": ws_actual_map,
                            "cookie_actual": ck_actual_map,
                            "match": model_match,
                        }
                        if not model_match:
                            mismatches.append({
                                "kind": "crud",
                                "target": model_key,
                                "expected": expected_map,
                                "ws_actual": ws_actual_map,
                                "cookie_actual": ck_actual_map,
                            })

        matched_rpc = sum(1 for v in rpc_results.values() if v["match"])
        matched_crud = sum(1 for v in crud_results.values() if v["match"])

        return {
            "target_type": target_type,
            "target_id": target_id,
            "target_name": target_name,
            "passed": len(mismatches) == 0,
            "total_rpc": len(rpc_results),
            "matched_rpc": matched_rpc,
            "total_crud": len(crud_results),
            "matched_crud": matched_crud,
            "mismatches": mismatches,
            "rpc_results": rpc_results,
            "crud_results": crud_results,
        }

    finally:
        # Гарантированная очистка сервисных токенов, сессий и временного пользователя роли
        try:
            async with system_db_session() as db:
                if temp_rt_id is not None:
                    await db.execute(delete(ActiveSession).where(ActiveSession.refresh_token_id == temp_rt_id))
                    await db.execute(delete(RefreshToken).where(RefreshToken.id == temp_rt_id))
                if temp_user_id is not None:
                    stmt_del_u = select(User).where(User.id == temp_user_id)
                    u_del = (await db.execute(stmt_del_u)).scalar_one_or_none()
                    if u_del:
                        await db.delete(u_del)
                await db.commit()
        except Exception as cleanup_err:
            logger.debug(f"[AuditCleanup] Ошибка очистки временных данных аудита: {cleanup_err}")
