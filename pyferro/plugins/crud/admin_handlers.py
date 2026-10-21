# -*- coding: utf-8 -*-
"""
RPC-обработчики системного пульта управления (Mission Control Cockpit /admin/system).
Предоставляют инспекцию и управление активными сессиями, Smart Cache, рассылками,
системными логами и конфигурацией фреймворка.
"""

import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional

from pyferro.core.session import (
    rpc_method,
    RPCError,
    require_admin,
    ACTIVE_SESSIONS_SET,
    current_transport_ctx,
)
from pyferro.core.logger import (
    get_recent_logs,
    _extract_username_safe,
    logger,
    get_runtime_log_level,
    set_runtime_log_level,
)
from pyferro.core.lib.config import settings
from pyferro.core.backplane import get_backplane
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pyferro.db import system_db_session
from pyferro.auth.models import User, UserDelegation
from pyferro.broadcast import broadcast_notification
from pyferro.smart_cache.engine import version_registry, invalidate_tags
from pyferro.db.session import get_db_echo, set_db_echo
from pyferro.plugins.crud.registry import ModelRegistry
@rpc_method("admin.sessions_list")
async def list_active_sessions(session) -> List[Dict[str, Any]]:
    """Мониторинг активных WebSocket-подключений и сессий пользователей.

    Возвращает список подключенных клиентов с IP-адресами, именами пользователей,
    ролями и временем бездействия.
    """
    require_admin(session)
    now = time.time()
    transport = current_transport_ctx.get()
    current_id = getattr(transport, "session_id", None) or getattr(session, "session_id", None)
    sessions = []
    for s in list(ACTIVE_SESSIONS_SET):
        s_id = getattr(s, "session_id", None)
        ip = getattr(s, "ip", "0.0.0.0")
        username = _extract_username_safe(s)
        role = "guest"
        if getattr(s, "data", None):
            if isinstance(s.data, dict):
                role = s.data.get("role") or s.data.get("user_role") or s.data.get("role_name") or "user"
            else:
                role = (
                    getattr(s.data, "role", None)
                    or getattr(s.data, "user_role", None)
                    or getattr(s.data, "role_name", None)
                    or "user"
                )
        last_act = getattr(s, "last_activity", now)
        idle_sec = max(0, int(now - last_act))
        sessions.append({
            "session_id": s_id,
            "ip": ip,
            "username": username,
            "role": str(role),
            "idle_seconds": idle_sec,
            "rate_limit_enabled": getattr(s, "rate_limit_enabled", True),
            "is_current": s_id == current_id,
        })
    # Сортируем: текущая сессия первой, затем по ID
    sessions.sort(key=lambda x: (not x["is_current"], x["session_id"]))
    return sessions


@rpc_method("admin.session_kill")
async def kill_session(session, session_id: int) -> Dict[str, Any]:
    """Принудительное завершение активной WebSocket-сессии (Kick/Disconnect).

    Разрывает WebSocket-соединение указанного клиента и очищает его контекст.
    Нельзя принудительно разорвать свою собственную текущую сессию.

    :param session_id: Идентификатор активной сессии.
    """
    require_admin(session)
    transport = current_transport_ctx.get()
    current_sid = getattr(transport, "session_id", None) or getattr(session, "session_id", None)
    if session_id == current_sid:
        raise RPCError(-32602, "Нельзя принудительно отключить свою собственную сессию")

    target = None
    for s in list(ACTIVE_SESSIONS_SET):
        if getattr(s, "session_id", None) == session_id:
            target = s
            break

    if not target:
        raise RPCError(-32602, f"Сессия {session_id} не найдена или уже завершена")

    username = _extract_username_safe(target)
    await target.close()
    logger.info(f"[Admin] Сессия {session_id} ({username}) принудительно отключена администратором")
    return {"status": "ok", "session_id": session_id, "username": username}


@rpc_method("system.cache_stats")
async def get_cache_stats(session) -> List[Dict[str, Any]]:
    """Инспекция версий тегов Smart Cache (RFC 0001).

    Возвращает актуальный список тегов кэша в оперативной памяти и БД
    с их текущими монотонными версиями.
    """
    require_admin(session)
    versions_map = version_registry.get_all_versions()
    stats = [{"tag": tag, "version": ver} for tag, ver in sorted(versions_map.items())]
    return stats


@rpc_method("system.cache_invalidate")
async def invalidate_cache_tags(session, tags: List[str]) -> Dict[str, Any]:
    """Принудительная реактивная инвалидация тегов кэша.

    Инкрементирует монотонные версии тегов и отправляет клиентам
    WSRPC-нотификацию cache.invalidate в реальном времени.

    :param tags: Список тегов для инвалидации (например, ['items', 'users']).
    """
    require_admin(session)
    if not tags or not isinstance(tags, list):
        raise RPCError(-32602, "Параметр 'tags' должен быть непустым списком строк")
    clean_tags = [str(t).strip() for t in tags if str(t).strip()]
    if not clean_tags:
        raise RPCError(-32602, "Список тегов пуст")

    new_versions = await invalidate_tags(clean_tags, reason="admin_manual_invalidate")
    return {"status": "ok", "invalidated_tags": new_versions}


@rpc_method("system.broadcast")
async def send_system_broadcast(
    session,
    message: str,
    level: str = "info",
    title: Optional[str] = None
) -> Dict[str, Any]:
    """Отправка системного всплывающего оповещения всем подключенным клиентам.

    Мгновенно рассылает JSON-RPC нотификацию system.alert по открытым сокетам.

    :param message: Текст сообщения.
    :param level: Уровень важности ('info', 'warning', 'error', 'success').
    :param title: Заголовок уведомления (опционально).
    """
    require_admin(session)
    if not message or not message.strip():
        raise RPCError(-32602, "Текст сообщения не может быть пустым")

    admin_name = _extract_username_safe(session)
    payload = {
        "title": title or "Системное оповещение",
        "message": message.strip(),
        "level": level if level in ("info", "warning", "error", "success") else "info",
        "sender": admin_name,
        "timestamp": time.time(),
    }
    delivered = await broadcast_notification("system.alert", payload)
    logger.info(f"[Admin] Системная рассылка '{payload['title']}' отправлена {delivered} клиентам")
    return {"status": "ok", "delivered_count": delivered}


@rpc_method("system.recent_logs")
async def stream_recent_logs(session, limit: int = 100) -> List[Dict[str, Any]]:
    """Просмотр системного журнала событий сервера из оперативной памяти.

    Возвращает последние записи логов сервера с временными метками, уровнями
    логирования и контекстом сессий.

    :param limit: Количество последних записей (максимум 200).
    """
    require_admin(session)
    safe_limit = min(max(1, limit), 200)
    return get_recent_logs(safe_limit)


@rpc_method("system.config")
async def get_system_config(session) -> Dict[str, Any]:
    """Просмотр системной конфигурации и параметров ядра платформы.

    Возвращает текущие настройки безопасности, таймаутов и путей.
    Секретные ключи экранируются в целях безопасности.
    """
    require_admin(session)
    conf = settings.to_dict()
    # Маскируем чувствительные данные
    if "security" in conf and isinstance(conf["security"], dict):
        sec = conf["security"].copy()
        if "secret_key" in sec and sec["secret_key"]:
            sec["secret_key"] = sec["secret_key"][:4] + "••••••••" + sec["secret_key"][-4:]
        conf["security"] = sec
    return conf


@rpc_method("system.plugin_matrix")
async def get_plugin_matrix(session) -> Dict[str, Any]:
    """Сводный статус и параметры подключенных плагинов фреймворка.

    Возвращает матрицу состояния всех плагинов платформы (Smart Cache,
    хранилище файлов, SEO, база данных, безопасность, бродкаст, CRUD),
    а также текущие динамические параметры ядра.
    """
    require_admin(session)

    # 1. Database Plugin
    db_url = getattr(settings, "database_url", "") or ""
    masked_db = db_url
    if "@" in masked_db:
        try:
            proto_user, host_db = masked_db.split("@", 1)
            if ":" in proto_user:
                proto, rest = proto_user.split("://", 1)
                user = rest.split(":", 1)[0]
                masked_db = f"{proto}://{user}:••••••••@{host_db}"
        except Exception:
            masked_db = "configured_database"
    dialect = "sqlite"
    if "postgres" in db_url:
        dialect = "postgresql"
    elif "mysql" in db_url:
        dialect = "mysql"

    db_info = {
        "active": True,
        "name": "Database (SQLAlchemy 2.0)",
        "dialect": dialect,
        "url_masked": masked_db,
        "echo": get_db_echo(),
    }

    # 2. Smart Cache Plugin
    all_versions = version_registry.get_all_versions()
    cache_info = {
        "active": True,
        "name": "Smart Cache (RFC 0001)",
        "tag_count": len(all_versions),
        "tags": sorted(list(all_versions.keys())),
    }

    # 3. CRUD Plugin
    all_models = ModelRegistry.all()
    crud_info = {
        "active": True,
        "name": "Reactive CRUD & Admin",
        "models_count": len(all_models),
        "models": [
            {
                "key": m.key,
                "label": m.verbose_name_plural or m.key,
                "is_internal": getattr(m, "is_internal", False),
            }
            for m in all_models.values()
        ],
    }

    # 4. Files Storage (2PC)
    files_dir = getattr(settings, "files_path", "./files")
    files_active = os.path.exists(files_dir) if files_dir else False
    files_info = {
        "active": True,
        "name": "2PC File Storage (RFC 0005)",
        "storage_dir": files_dir,
        "storage_exists": files_active,
        "max_upload_size": getattr(settings, "max_upload_size", "100MB"),
    }

    # 5. SEO & Dynamic Rendering
    try:
        from pyferro.plugins.seo.router import BOT_ROUTES
        bot_routes_count = len(BOT_ROUTES)
    except Exception:
        bot_routes_count = 0
    seo_info = {
        "active": True,
        "name": "SEO & Dynamic Rendering",
        "bot_routes_count": bot_routes_count,
    }

    # 6. Broadcast Plugin
    backplane = get_backplane()
    broadcast_info = {
        "active": True,
        "name": "Zero-Copy Broadcast",
        "backplane_type": backplane.__class__.__name__,
        "connected_sessions": len(ACTIVE_SESSIONS_SET),
    }

    # 7. Auth & Security
    sec = settings.to_dict().get("security", {})
    auth_info = {
        "active": True,
        "name": "Auth & RBAC",
        "allow_guests": bool(sec.get("allow_guests", True)),
        "guest_idle_timeout": int(sec.get("guest_idle_timeout", 900)),
        "user_idle_timeout": int(sec.get("user_idle_timeout", 1800)),
        "token_expire_hours": int(sec.get("token_expire_hours", 24)),
        "login_rpc": str(sec.get("login_rpc", "login.")),
    }

    # 8. Runtime & Infrastructure Stats
    runtime_info = {
        "log_level": get_runtime_log_level(),
        "db_echo": get_db_echo(),
        "python_version": sys.version.split()[0],
        "platform": platform.system(),
        "platform_release": platform.release(),
        "allow_guests": bool(sec.get("allow_guests", True)),
        "guest_idle_timeout": int(sec.get("guest_idle_timeout", 900)),
        "user_idle_timeout": int(sec.get("user_idle_timeout", 1800)),
    }

    return {
        "plugins": {
            "db": db_info,
            "smart_cache": cache_info,
            "crud": crud_info,
            "files": files_info,
            "seo": seo_info,
            "broadcast": broadcast_info,
            "auth": auth_info,
        },
        "runtime": runtime_info,
    }


@rpc_method("system.update_hot_config")
async def update_hot_config(
    session,
    log_level: Optional[str] = None,
    db_echo: Optional[bool] = None,
    guest_idle_timeout: Optional[int] = None,
    user_idle_timeout: Optional[int] = None,
    allow_guests: Optional[bool] = None,
) -> Dict[str, Any]:
    """Горячее обновление оперативных параметров фреймворка в рантайме.

    Применяет настройки мгновенно без перезапуска сервера и без
    разрыва открытых WebSocket-соединений.

    :param log_level: Уровень логирования ('DEBUG', 'INFO', 'WARNING', 'ERROR').
    :param db_echo: Включение/выключение вывода SQL-запросов (True/False).
    :param guest_idle_timeout: Таймаут неактивности гостей в секундах (> 0).
    :param user_idle_timeout: Таймаут неактивности авторизованных пользователей (> 0).
    :param allow_guests: Разрешить или запретить гостевой доступ (True/False).
    """
    require_admin(session)
    applied: Dict[str, Any] = {}

    if log_level is not None:
        try:
            new_lvl = set_runtime_log_level(str(log_level))
            applied["log_level"] = new_lvl
        except ValueError as e:
            raise RPCError(-32602, str(e))

    if db_echo is not None:
        new_echo = set_db_echo(bool(db_echo))
        applied["db_echo"] = new_echo

    sec_updates: Dict[str, Any] = {}
    if allow_guests is not None:
        sec_updates["allow_guests"] = bool(allow_guests)
        applied["allow_guests"] = bool(allow_guests)

    if guest_idle_timeout is not None:
        val = int(guest_idle_timeout)
        if val <= 0:
            raise RPCError(-32602, "Таймаут гостей должен быть больше нуля")
        sec_updates["guest_idle_timeout"] = val
        applied["guest_idle_timeout"] = val

    if user_idle_timeout is not None:
        val = int(user_idle_timeout)
        if val <= 0:
            raise RPCError(-32602, "Таймаут пользователей должен быть больше нуля")
        sec_updates["user_idle_timeout"] = val
        applied["user_idle_timeout"] = val

    if sec_updates:
        settings.update({"security": sec_updates})

    admin_name = _extract_username_safe(session)
    logger.info(f"[Admin] Администратор '{admin_name}' обновил горячие настройки: {applied}")

    sec = settings.to_dict().get("security", {})
    return {
        "status": "ok",
        "applied": applied,
        "runtime": {
            "log_level": get_runtime_log_level(),
            "db_echo": get_db_echo(),
            "allow_guests": bool(sec.get("allow_guests", True)),
            "guest_idle_timeout": int(sec.get("guest_idle_timeout", 900)),
            "user_idle_timeout": int(sec.get("user_idle_timeout", 1800)),
        },
    }


# --- УПРАВЛЕНИЕ ЗАМЕЩЕНИЯМИ И ДЕЛЕГИРОВАНИЕМ (USER DELEGATIONS) ---

@rpc_method("admin.delegations_list")
async def list_delegations_admin(session) -> List[Dict[str, Any]]:
    """Возвращает сквозной реестр всех замещений полномочий (UserDelegation) в системе."""
    require_admin(session)
    now = datetime.now(timezone.utc)
    async with system_db_session() as db:
        stmt = (
            select(UserDelegation)
            .options(
                selectinload(UserDelegation.from_user),
                selectinload(UserDelegation.to_user)
            )
            .order_by(UserDelegation.id.desc())
        )
        delegations = (await db.execute(stmt)).scalars().all()
        result = []
        for d in delegations:
            v_from = d.valid_from.replace(tzinfo=timezone.utc) if (d.valid_from and d.valid_from.tzinfo is None) else d.valid_from
            v_to = d.valid_to.replace(tzinfo=timezone.utc) if (d.valid_to and d.valid_to.tzinfo is None) else d.valid_to
            status = "active"
            if not d.is_active:
                status = "disabled"
            elif v_from and v_from > now:
                status = "scheduled"
            elif v_to and v_to < now:
                status = "expired"

            from_u = d.from_user
            to_u = d.to_user
            result.append({
                "id": d.id,
                "from_user_id": d.from_user_id,
                "from_user_name": (from_u.name if from_u else None) or (from_u.login if from_u else None) or f"User #{d.from_user_id}",
                "from_user_login": from_u.login if from_u else "",
                "to_user_id": d.to_user_id,
                "to_user_name": (to_u.name if to_u else None) or (to_u.login if to_u else None) or f"User #{d.to_user_id}",
                "to_user_login": to_u.login if to_u else "",
                "model_name": d.model_name or None,
                "valid_from": d.valid_from.isoformat() if d.valid_from else None,
                "valid_to": d.valid_to.isoformat() if d.valid_to else None,
                "is_active": d.is_active,
                "status": status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })
        return result


@rpc_method("admin.delegation_toggle")
async def toggle_delegation_admin(session, id: int = None, **kwargs) -> Dict[str, Any]:
    """Переключает статус активности замещения (вкл/выкл)."""
    require_admin(session)
    target_id = id or kwargs.get("id")
    if not target_id:
        raise RPCError(-32602, "ID замещения обязателен")
    async with system_db_session() as db:
        stmt = select(UserDelegation).where(UserDelegation.id == int(target_id))
        delegation = (await db.execute(stmt)).scalar_one_or_none()
        if not delegation:
            raise RPCError(404, f"Замещение #{target_id} не найдено")
        delegation.is_active = not delegation.is_active
        await db.commit()
        await db.refresh(delegation)
        res = {
            "id": delegation.id,
            "is_active": delegation.is_active,
        }
    await broadcast_notification("delegations.changed", res)
    return res


@rpc_method("admin.delegation_create")
async def create_delegation_admin(
    session,
    from_user_id: int,
    to_user_id: int,
    model_name: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_to: Optional[str] = None,
    is_active: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """Создает новое замещение полномочий между сотрудниками."""
    require_admin(session)
    if not from_user_id or not to_user_id:
        raise RPCError(-32602, "Параметры from_user_id и to_user_id обязательны")
    if int(from_user_id) == int(to_user_id):
        raise RPCError(-32602, "Сотрудник не может назначить заместителем самого себя")

    parsed_from = None
    parsed_to = None
    if valid_from:
        try:
            parsed_from = datetime.fromisoformat(str(valid_from).replace("Z", "+00:00"))
        except Exception:
            pass
    if valid_to:
        try:
            parsed_to = datetime.fromisoformat(str(valid_to).replace("Z", "+00:00"))
        except Exception:
            pass

    clean_model = (model_name or "").strip() or None

    async with system_db_session() as db:
        u_from = (await db.execute(select(User).where(User.id == int(from_user_id)))).scalar_one_or_none()
        u_to = (await db.execute(select(User).where(User.id == int(to_user_id)))).scalar_one_or_none()
        if not u_from:
            raise RPCError(404, f"Пользователь #{from_user_id} не найден")
        if not u_to:
            raise RPCError(404, f"Пользователь #{to_user_id} не найден")

        delegation = UserDelegation(
            from_user_id=int(from_user_id),
            to_user_id=int(to_user_id),
            model_name=clean_model,
            valid_from=parsed_from,
            valid_to=parsed_to,
            is_active=bool(is_active),
        )
        db.add(delegation)
        await db.commit()
        await db.refresh(delegation)
        res = {"id": delegation.id, "created": True}

    await broadcast_notification("delegations.changed", res)
    return res


@rpc_method("admin.delegation_delete")
async def delete_delegation_admin(session, id: int = None, **kwargs) -> Dict[str, Any]:
    """Удаляет запись замещения полномочий."""
    require_admin(session)
    target_id = id or kwargs.get("id")
    if not target_id:
        raise RPCError(-32602, "ID обязателен")
    async with system_db_session() as db:
        stmt = select(UserDelegation).where(UserDelegation.id == int(target_id))
        delegation = (await db.execute(stmt)).scalar_one_or_none()
        if not delegation:
            raise RPCError(404, f"Замещение #{target_id} не найдено")
        await db.delete(delegation)
        await db.commit()
        res = {"id": int(target_id), "deleted": True}

    await broadcast_notification("delegations.changed", res)
    return res


@rpc_method("admin.delegation_options")
async def delegation_options_admin(session) -> Dict[str, Any]:
    """Возвращает список пользователей и бизнес-моделей для модального окна создания замещения."""
    require_admin(session)
    async with system_db_session() as db:
        stmt = select(User).order_by(User.id.asc())
        users = (await db.execute(stmt)).scalars().all()
        users_list = [
            {
                "id": u.id,
                "login": u.login,
                "name": u.name or u.login,
            }
            for u in users
        ]

    models_list = [
        {"key": meta.key, "verbose_name": meta.verbose_name or meta.key}
        for meta in ModelRegistry.all().values()
        if not getattr(meta, "internal", False)
    ]
    return {
        "users": users_list,
        "models": models_list,
    }
