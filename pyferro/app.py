# -*- coding: utf-8 -*-
"""
Главный класс приложения FerroApp.
Предоставляет готовую точку входа для Granian RSGI, инкапсулирует конфигурацию,
маршрутизацию HTTP/WebSocket, раздачу статики, CORS и управление жизненным циклом.
"""

import os
import sys
import asyncio
import inspect
import mimetypes
from typing import Optional, List, Dict, Any, Union, Callable

from .core.lib.config import configure, settings, Settings
from .core.session import JsonRpcSession, rpc_method, RPC_REGISTRY, ACTIVE_SESSIONS_SET
from .core.router import http_route, HTTP_ROUTES
from .core.lifecycle import on_startup, on_shutdown, run_startup_callbacks, run_shutdown_callbacks
from .core.logger import logger, setup_logging

_CURRENT_APP: Optional["FerroApp"] = None


def get_current_app() -> Optional["FerroApp"]:
    """Возвращает текущий активный экземпляр FerroApp."""
    return _CURRENT_APP


class _SessionCounter:
    """Сериализуемый счетчик сессий (совместим с multiprocessing spawn / pickle в Python 3.14)."""

    def __init__(self, start: int = 0):
        self._val = start

    def __iter__(self):
        return self

    def __next__(self) -> int:
        val = self._val
        self._val += 1
        return val


def _granian_target_loader(target: Any) -> Any:
    """Загрузчик целевого приложения для воркеров Granian.
    
    Позволяет Granian безопасно передавать уже созданный экземпляр FerroApp
    в дочерние процессы воркеров без падения load_target(re.split).
    """
    if isinstance(target, str):
        from granian._internal import load_target
        return load_target(target)
    return target


class FerroApp:
    """
    Полнофункциональное RSGI-приложение PyFerro.
    """

    def __init__(
        self,
        *,
        # Безопасность и ядро
        secret_key: Optional[str] = None,
        database_url: Optional[str] = None,
        db_echo: bool = False,
        files_path: Optional[str] = None,
        max_upload_size: Optional[int] = None,
        login_rpc: Optional[str] = None,
        auth_timeout: Optional[int] = None,
        guest_idle_timeout: Optional[int] = None,
        user_idle_timeout: Optional[int] = None,
        session_idle_timeout: Optional[int] = None,
        allow_guests: Optional[bool] = None,
        password_iterations: Optional[int] = None,
        token_expire_hours: Optional[int] = None,
        session_prefix: str = "ferro",
        table_prefix: str = "pf_",
        max_message_size: Optional[int] = None,
        # HTTP и CORS
        cors: bool = True,
        cors_origins: Union[str, List[str]] = "*",
        cors_headers: str = "content-type, authorization",
        cors_methods: str = "GET, POST, PUT, DELETE, OPTIONS",
        # Статика и UI
        static_dir: Optional[str] = None,
        static_prefix: str = "/static",
        index_file: Optional[str] = None,
        public_help: Optional[bool] = None,
        # Внешняя авторизация и плагины
        oauth: Optional[Union[List[Any], Dict[str, Any]]] = None,
        backplane_url: Optional[str] = None,
        enable_seo: bool = False,
        sitemap_host: Optional[str] = None,
        auto_auth_ws: bool = True,
        auto_auth_models: bool = True,
        auto_migrate: bool = True,
        custom_settings: Optional[Dict[str, Any]] = None,
        **extra_settings: Any
    ):
        # 1. Применяем конфигурацию к ядру
        config_kwargs: Dict[str, Any] = {}
        if table_prefix is not None:
            config_kwargs["table_prefix"] = table_prefix
        if secret_key is not None:
            config_kwargs["secret_key"] = secret_key
        if database_url is not None:
            config_kwargs["database_url"] = database_url
        if db_echo:
            config_kwargs["db_echo"] = db_echo
        if files_path is not None:
            config_kwargs["files_path"] = files_path
        if max_upload_size is not None:
            config_kwargs["max_upload_size"] = max_upload_size
        if backplane_url is not None:
            config_kwargs["backplane_url"] = backplane_url
        if sitemap_host is not None:
            config_kwargs["sitemap_host"] = sitemap_host
        if login_rpc is not None:
            config_kwargs["login_rpc"] = login_rpc
        if auth_timeout is not None:
            config_kwargs["auth_timeout"] = auth_timeout
        if guest_idle_timeout is not None:
            config_kwargs["guest_idle_timeout"] = guest_idle_timeout
        if user_idle_timeout is not None:
            config_kwargs["user_idle_timeout"] = user_idle_timeout
        if session_idle_timeout is not None:
            config_kwargs["session_idle_timeout"] = session_idle_timeout
        if allow_guests is not None:
            config_kwargs["allow_guests"] = allow_guests
        if password_iterations is not None:
            config_kwargs["password_iterations"] = password_iterations
        if token_expire_hours is not None:
            config_kwargs["token_expire_hours"] = token_expire_hours
        if max_message_size is not None:
            config_kwargs.setdefault("custom", {})["max_message_size"] = max_message_size

        if session_prefix is not None:
            config_kwargs["session_prefix"] = session_prefix

        if oauth:
            oauth_dict: Dict[str, Any] = {}
            if isinstance(oauth, list):
                for prov in oauth:
                    p_name = getattr(prov, "provider_name", None) or prov.__class__.__name__.lower().replace("oauth", "")
                    oauth_dict[p_name] = {
                        k: v for k, v in prov.__dict__.items() if not k.startswith("_")
                    }
            elif isinstance(oauth, dict):
                oauth_dict = oauth
            config_kwargs["oauth"] = oauth_dict

        if custom_settings:
            config_kwargs.setdefault("custom", {}).update(custom_settings)
        if extra_settings:
            config_kwargs.setdefault("custom", {}).update(extra_settings)

        self.settings: Settings = configure(**config_kwargs)
        self.session_prefix: str = session_prefix or "ferro"

        # 2. Настройки HTTP / CORS
        self.cors_enabled = cors
        self.cors_origins = cors_origins if isinstance(cors_origins, str) else ", ".join(cors_origins)
        self.cors_headers = cors_headers
        self.cors_methods = cors_methods

        # 3. Настройки статических файлов
        self.static_dir = os.path.abspath(static_dir) if static_dir else None
        self.static_prefix = "/" + static_prefix.strip("/") if static_prefix else "/static"
        self.index_file = None
        if index_file:
            if os.path.isabs(index_file):
                self.index_file = index_file
            elif self.static_dir:
                self.index_file = os.path.join(self.static_dir, index_file)
            else:
                self.index_file = os.path.abspath(index_file)
        elif self.static_dir:
            candidate = os.path.join(self.static_dir, "index.html")
            if os.path.exists(candidate):
                self.index_file = candidate

        self.public_help = public_help
        global _CURRENT_APP
        _CURRENT_APP = self
        self.enable_seo = enable_seo
        self._session_counter = _SessionCounter()
        self._on_connect_callbacks: List[Callable] = []

        self.auto_auth_ws = auto_auth_ws
        self.auto_migrate = auto_migrate

        # Автоматическая регистрация стандартных моделей в CRUD
        if auto_auth_models:
            try:
                from pyferro.plugins.crud.registry import ModelRegistry
                ModelRegistry.register_auth_models()
            except Exception:
                pass

        # Граниан связывает __rsgi_init__ и __rsgi_del__ на самом объекте приложения
        self.__rsgi_init__ = self._rsgi_init_handler
        self.__rsgi_del__ = self._rsgi_del_handler

    async def set_admin_password(self, login: str = "admin", password: Optional[str] = None) -> str:
        """
        Устанавливает или генерирует новый пароль для указанного пользователя в БД.
        Строго DML (не создает таблицы или схему БД во избежание версионных проблем).
        """
        import secrets
        import string
        from sqlalchemy import select
        from pyferro.db import system_db_session
        from pyferro.auth import User

        if not password:
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
            password = "".join(secrets.choice(chars) for _ in range(16))

        async with system_db_session() as db:
            user = (await db.execute(select(User).where(User.login == login))).scalar_one_or_none()
            if not user:
                raise ValueError(
                    f"Пользователь с логином '{login}' не найден в базе данных. "
                    f"Схема данных и пользователи должны быть предварительно инициализированы приложением."
                )
            user.password_hash = User._hash_password(password)
            await db.commit()
            return password

    def handle_cli(self, argv: Optional[List[str]] = None) -> bool:
        """
        Обрабатывает служебные CLI-флаги, такие как --set-admin-password.
        Возвращает True, если была выполнена служебная команда (сервер запускать не нужно).
        """
        import sys
        args = argv if argv is not None else sys.argv[1:]
        if not args:
            return False

        for i, arg in enumerate(args):
            if arg in ("--migrate", "migrate"):
                try:
                    from pyferro.migrations import run_migrations
                    applied = asyncio.run(run_migrations())
                    if applied:
                        print(f"✅ PyFerro: Успешно применены миграции: {', '.join(applied)}")
                    else:
                        print("✨ PyFerro: Все миграции уже применены, схема базы актуальна.")
                    return True
                except Exception as e:
                    print(f"❌ Ошибка миграции: {e}", file=sys.stderr)
                    sys.exit(1)

            if arg in ("--set-admin-password", "--set-password"):
                custom_password = None
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    custom_password = args[i + 1]

                login = "admin"
                for j, a in enumerate(args):
                    if a == "--login" and j + 1 < len(args):
                        login = args[j + 1]

                db_url = self.settings.get("database_url", "sqlite+aiosqlite:///app.db")
                try:
                    new_pwd = asyncio.run(self.set_admin_password(login=login, password=custom_password))
                    print("=" * 64)
                    print(" 🛡️  PyFerro: Пароль успешно обновлен в базе данных!")
                    print(f" 🗄️  База данных: {db_url}")
                    print(f" 👤 Логин:       {login}")
                    print(f" 🔑 Пароль:      {new_pwd}")
                    print("=" * 64)
                    print(" 👉 Войдите через форму авторизации вашего приложения.")
                    return True
                except Exception as e:
                    print("=" * 64, file=sys.stderr)
                    print(f" ❌ Ошибка смены пароля: {e}", file=sys.stderr)
                    print("=" * 64, file=sys.stderr)
                    sys.exit(1)
        return False

    @property
    def has_user_frontend(self) -> bool:
        """
        Проверяет, подключен ли пользовательский фронтенд:
        - Задан существующий index_file
        - Или задана существующая директория static_dir с файлами
        - Или зарегистрирован пользовательский HTTP маршрут для корня '/'
        """
        if self.index_file and os.path.exists(self.index_file):
            return True
        if self.static_dir and os.path.isdir(self.static_dir):
            try:
                if any(os.scandir(self.static_dir)):
                    return True
            except Exception:
                pass
        for route_path, methods, handler in HTTP_ROUTES:
            if not route_path.startswith("/admin") and not route_path.startswith("/upload") and not route_path.startswith("/sitemap"):
                if route_path in ("/", "/*"):
                    return True
        return False

    def _auto_authenticate_ws(self, session: JsonRpcSession) -> None:
        """Автоматически авторизует WebSocket по Cookie (сконфигурированный префикс + fallback)."""
        if session.data is not None:
            return
        cookies = session.cookies
        if not cookies:
            return
        from pyferro.core.http import get_session_cookie_names

        candidate_tokens = []
        for name in get_session_cookie_names(self.session_prefix):
            val = cookies.get(name)
            if val and val not in candidate_tokens:
                candidate_tokens.append(val)
        if not candidate_tokens:
            return

        user_info = None
        for token in candidate_tokens:
            try:
                from pyferro.plugins.crud.auth import get_crud_session
                user_info = get_crud_session(token)
                if user_info:
                    break
            except Exception:
                pass

            try:
                from pyferro.core.security import decode_access_token
                payload = decode_access_token(token)
                if payload:
                    roles = payload.get("roles", [])
                    role = payload.get("role") or (roles[0] if roles else "user")
                    is_admin = bool("admin" in roles or "ADMIN" in roles or "superadmin" in roles or payload.get("is_superadmin") or role in ("admin", "ADMIN", "superadmin"))
                    raw_sub = payload.get("sub", "1")
                    uid = int(raw_sub) if str(raw_sub).isdigit() else 1
                    user_info = {
                        "uid": uid,
                        "user_id": uid,
                        "username": payload.get("username", "admin" if is_admin else "user"),
                        "role": "admin" if is_admin else role,
                        "roles": roles if roles else [role],
                        "is_superadmin": is_admin,
                        "perms_dict": payload.get("permissions") or payload.get("perms_dict") or {},
                        "allowed_rpc_methods": {"*"} if is_admin else set(payload.get("allowed_rpc_methods", [])),
                    }
                    break
            except Exception:
                pass

        if user_info:
            uid = user_info.get("uid") or user_info.get("user_id", 1)
            role = user_info.get("role", "user")
            roles = user_info.get("roles") or [role]
            is_superadmin = bool(
                role in ("admin", "ADMIN", "superadmin")
                or "admin" in roles
                or "ADMIN" in roles
                or "superadmin" in roles
                or user_info.get("is_superadmin")
            )
            user_ctx = type("UserCtx", (), {
                "is_superadmin": is_superadmin,
                "user_id": uid,
                "team_ids": user_info.get("team_ids", []),
                "delegated_user_ids": user_info.get("delegated_user_ids", []),
                "perms_dict": user_info.get("perms_dict", {}),
                "allowed_rpc_methods": {"*"} if is_superadmin else set(user_info.get("allowed_rpc_methods", [])),
            })()

            from pyferro.auth import AuthSession
            session.data = AuthSession(
                uid=uid,
                user=None,
                user_name=user_info.get("username", "user"),
                user_role=role,
                user_roles=roles,
                session_db_id=0,
                user_ctx=user_ctx,
                allowed_rpc_methods={"*"} if is_superadmin else set(user_info.get("allowed_rpc_methods", [])),
                send_request_cb=getattr(session, "send_request", None),
                send_stream_cb=getattr(session, "send_stream_chunk", None),
                close_cb=getattr(session, "close", None),
            )
            logger.info(f"[AutoAuth] WebSocket #{session.session_id} автоматически авторизован по Cookie как {user_info.get('username')} ({role})")

    async def _hydrate_ws_auth_from_db(self, session: JsonRpcSession) -> None:
        """
        Дозагружает актуальные права пользователя (роли, RPC, CRUD, замещения) из БД при авто-авторизации по Cookie,
        а также разрешает сессию по RefreshToken (ferro_session), если JWT не был передан.
        """
        cookies = session.cookies
        if not cookies and session.data is None:
            return
        if session.data is not None and session.is_superadmin:
            return
        try:
            from datetime import datetime, timezone
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            from pyferro.db import system_db_session
            from pyferro.auth.models import User, Role, RefreshToken
            from pyferro.auth import AuthSession
            from pyferro.core.http import get_session_cookie_names

            async with system_db_session() as db:
                target_uid = None
                if session.data is not None:
                    target_uid = session.user_id
                else:
                    # Попытка найти активный RefreshToken из cookie (например, ferro_session)
                    for name in get_session_cookie_names(self.session_prefix):
                        token_val = cookies.get(name)
                        if not token_val:
                            continue
                        stmt_rt = select(RefreshToken).where(
                            RefreshToken.token == token_val,
                            RefreshToken.expires_at > datetime.now(timezone.utc)
                        )
                        rt_obj = (await db.execute(stmt_rt)).scalar_one_or_none()
                        if rt_obj:
                            target_uid = rt_obj.user_id
                            break

                if not target_uid:
                    return

                stmt_user = select(User).options(
                    selectinload(User.roles).selectinload(Role.permissions),
                    selectinload(User.roles).selectinload(Role.rpc_permissions),
                    selectinload(User.teams),
                    selectinload(User.permissions),
                    selectinload(User.rpc_permissions),
                    selectinload(User.delegations_received),
                ).where(User.id == target_uid)
                user = (await db.execute(stmt_user)).scalar_one_or_none()
                if not user:
                    return

                user_ctx = user.get_permissions()
                role_names = [r.name for r in user.roles] if user.roles else ["user"]
                role_name = role_names[0] if role_names else "user"

                session.data = AuthSession(
                    uid=user.id,
                    user=user,
                    user_name=user.login or user.name,
                    user_role=role_name,
                    user_roles=role_names,
                    session_db_id=getattr(session.data, "session_db_id", 0) if session.data else 0,
                    user_ctx=user_ctx,
                    allowed_rpc_methods=getattr(user_ctx, "allowed_rpc_methods", set()),
                    send_request_cb=getattr(session, "send_request", None),
                    send_stream_cb=getattr(session, "send_stream_chunk", None),
                    close_cb=getattr(session, "close", None),
                )
        except Exception as e:
            logger.debug(f"[AutoAuth] Не удалось дозагрузить права из БД для сессии #{session.session_id}: {e}")
    # --- ДЕКОРАТОРЫ ---

    def rpc(self, name: str, description: Optional[str] = None, http: bool = False):
        """Декоратор для регистрации JSON-RPC 2.0 метода."""
        return rpc_method(name=name, description=description, http=http)

    def route(self, path: str, methods: Optional[List[str]] = None):
        """Декоратор для регистрации HTTP-обработчика."""
        return http_route(path=path, methods=methods)

    def on_startup(self, func: Callable):
        """Регистрирует хук запуска приложения."""
        return on_startup(func)

    def on_shutdown(self, func: Callable):
        """Регистрирует хук завершения приложения."""
        return on_shutdown(func)

    def on_connect(self, func: Callable):
        """Регистрирует асинхронный хук при подключении новой WebSocket-сессии (session: JsonRpcSession)."""
        self._on_connect_callbacks.append(func)
        return func

    # --- ЖИЗНЕННЫЙ ЦИКЛ RSGI ---

    def _rsgi_init_handler(self, loop):
        """Инициализация при старте воркера Granian."""
        try:
            if self.auto_migrate:
                from pyferro.migrations import run_migrations
                loop.run_until_complete(run_migrations())
            loop.run_until_complete(run_startup_callbacks())
        except Exception as e:
            logger.critical(f"[FerroApp] Сбой при startup: {e}", exc_info=True)
            sys.exit(1)

    def _rsgi_del_handler(self, loop):
        """Очистка при завершении воркера Granian."""
        try:
            # Закрываем оставшиеся WebSocket-сессии
            async def _cleanup():
                await run_shutdown_callbacks()
                close_tasks = [s.close() for s in list(ACTIVE_SESSIONS_SET)]
                if close_tasks:
                    await asyncio.gather(*close_tasks, return_exceptions=True)

            loop.run_until_complete(_cleanup())
            logger.info("[FerroApp] Корректно завершен (graceful shutdown).")
        except Exception as e:
            logger.error(f"[FerroApp] Ошибка при shutdown: {e}", exc_info=True)

    # --- ОБРАБОТКА RSGI ВХОДЯЩИХ ЗАПРОСОВ ---

    async def __call__(self, scope, proto):
        """
        Главный диспетчер Granian RSGI: разделение HTTP и WebSocket.
        """
        proto_type = getattr(scope, "proto", "")

        if proto_type == "http":
            await self._handle_http(scope, proto)
            return

        if proto_type in ("websocket", "ws"):
            await self._handle_websocket(scope, proto)
            return

        # Неизвестный протокол
        logger.warning(f"[FerroApp] Неизвестный тип протокола: {proto_type}")

    async def _handle_http(self, scope, proto):
        method = getattr(scope, "method", None) or (scope.get("method", "GET") if isinstance(scope, dict) else "GET")
        path = getattr(scope, "path", None) or (scope.get("path", "/") if isinstance(scope, dict) else "/")

        # 1. CORS Preflight (OPTIONS)
        if self.cors_enabled and method == "OPTIONS":
            proto.response_str(
                status=204,
                headers=[
                    ("access-control-allow-origin", self.cors_origins),
                    ("access-control-allow-methods", self.cors_methods),
                    ("access-control-allow-headers", self.cors_headers),
                    ("access-control-max-age", "86400"),
                ],
                body=""
            )
            return

        # 2. Опциональный перехват SEO-ботов
        if self.enable_seo:
            try:
                from .plugins.seo.router import handle_bot_http
                if await handle_bot_http(scope, proto):
                    return
            except ImportError:
                pass
            except Exception as e:
                logger.error(f"[FerroApp] Ошибка SEO перехвата: {e}", exc_info=True)

        # 3. Маршрутизация по зарегистрированным HTTP_ROUTES (от более специфичных к общим)
        # 3.1. Сначала точные совпадения
        for route_path, methods, handler in HTTP_ROUTES:
            if method in methods and (path == route_path or path.rstrip("/") == route_path.rstrip("/")):
                if not route_path.endswith("/*"):
                    await handler(scope, proto)
                    return

        # 3.2. Затем префиксные wildcard-маршруты (/*) от более длинных к более коротким
        wildcard_routes = [
            (rp, m, h) for rp, m, h in HTTP_ROUTES
            if rp.endswith("/*") and method in m
        ]
        wildcard_routes.sort(key=lambda r: len(r[0]), reverse=True)
        for route_path, methods, handler in wildcard_routes:
            prefix = route_path[:-1]  # e.g. "/admin/help/"
            if path.startswith(prefix) or path == route_path[:-2]:
                await handler(scope, proto)
                return
        # 4. Отдача index.html на корневой GET /
        if method == "GET" and path == "/" and self.index_file and os.path.exists(self.index_file):
            self._serve_static_file(proto, self.index_file)
            return

        # 5. Раздача статики из static_dir
        if method == "GET" and self.static_dir:
            # 1. Попытка с префиксом static_prefix (если он задан)
            if self.static_prefix and path.startswith(self.static_prefix):
                rel_path = path[len(self.static_prefix):].lstrip("/")
                if rel_path:
                    safe_full_path = os.path.abspath(os.path.join(self.static_dir, rel_path))
                    # Защита от Path Traversal
                    if (safe_full_path == self.static_dir or safe_full_path.startswith(self.static_dir + os.sep)) and os.path.isfile(safe_full_path):
                        self._serve_static_file(proto, safe_full_path)
                        return

            # 2. Прямая раздача из static_dir (например, /assets/..., /favicon.ico)
            rel_path = path.lstrip("/")
            if rel_path:
                safe_full_path = os.path.abspath(os.path.join(self.static_dir, rel_path))
                # Защита от Path Traversal
                if (safe_full_path == self.static_dir or safe_full_path.startswith(self.static_dir + os.sep)) and os.path.isfile(safe_full_path):
                    self._serve_static_file(proto, safe_full_path)
                    return

        # 6. Если пользовательского фронтенда нет и запрос к корню GET / — авто-редирект на /admin/help/
        if method == "GET" and path == "/" and not self.has_user_frontend:
            proto.response_str(
                status=307,
                headers=[
                    ("location", "/admin/help/"),
                    ("content-length", "0"),
                ],
                body=""
            )
            return

        # 7. 404 Not Found
        proto.response_str(
            status=404,
            headers=[("content-type", "text/plain; charset=utf-8")],
            body="404 Not Found"
        )

    def _serve_static_file(self, proto, file_path: str):
        """Отдает статический файл через нативный proto.response_file (Zero-Copy)."""
        content_type, _ = mimetypes.guess_type(file_path)
        content_type = content_type or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        
        headers = [
            ("content-type", content_type),
            ("cache-control", "public, max-age=3600"),
        ]
        if self.cors_enabled:
            headers.append(("access-control-allow-origin", self.cors_origins))

        if hasattr(proto, "response_file"):
            proto.response_file(status=200, headers=headers, file=file_path)
        else:
            # Fallback для тестовых моков
            with open(file_path, "rb") as f:
                data = f.read()
            if hasattr(proto, "response_bytes"):
                proto.response_bytes(status=200, headers=headers, body=data)
            else:
                proto.response_str(status=200, headers=headers, body=data.decode("utf-8", errors="replace"))

    async def _handle_websocket(self, scope, proto):
        """Принимает входящее WebSocket-соединение и запускает WSRPC JsonRpcSession (или raw_ws при совпадении маршрута)."""
        # Проверяем специализированные маршруты raw_ws
        try:
            from .plugins.raw_ws.manager import dispatch_raw_ws, RAW_WS_ROUTES
            if RAW_WS_ROUTES and await dispatch_raw_ws(scope, proto):
                return
        except ImportError:
            pass

        session = None
        try:
            ws = await proto.accept()
            session_id = next(self._session_counter)
            
            # Извлекаем IP адрес клиента из scope
            client_ip = "0.0.0.0"
            client = getattr(scope, "client", None)
            if client and isinstance(client, (list, tuple)) and len(client) > 0:
                client_ip = str(client[0])

            session = JsonRpcSession(ws, session_id, ip=client_ip, scope=scope)
            if self.auto_auth_ws:
                self._auto_authenticate_ws(session)
                await self._hydrate_ws_auth_from_db(session)
            for cb in self._on_connect_callbacks:
                try:
                    if inspect.iscoroutinefunction(cb):
                        await cb(session)
                    else:
                        cb(session)
                except Exception as e:
                    logger.error(f"[FerroApp on_connect] Ошибка в хуке подключения: {e}", exc_info=True)
            await session.start()
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception as e:
            sid_str = f" #{session.session_id}" if session else ""
            if "RSGI transport is closed" in str(e) or "ProtocolClosed" in type(e).__name__:
                logger.debug(f"[FerroApp WS] Клиент отключился (сессия{sid_str})")
            else:
                logger.error(f"[FerroApp WS] Ошибка сокет-сессии: {e}", exc_info=True)
        finally:
            if session:
                await session.close()

    async def broadcast(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        exclude_current: bool = False,
    ) -> int:
        """
        Рассылает JSON-RPC нотификацию всем активным WebSocket-клиентам.
        """
        from pyferro.broadcast import broadcast_notification
        return await broadcast_notification(method, params=params, exclude_current=exclude_current)

    def run(self, host: str = "127.0.0.1", port: int = 8080, workers: int = 1, **granian_kwargs: Any):
        """
        Удобный запуск сервера через Granian в коде.
        """
        if self.handle_cli():
            return
        if workers > 1:
            from .core.backplane import get_backplane, MemoryBackplane
            if isinstance(get_backplane(), MemoryBackplane):
                logger.warning(
                    f"[Multi-Worker] Внимание: сервер запускается с workers={workers}, "
                    "но используется локальный MemoryBackplane. "
                    "WebSocket-сессии и Smart Cache изолированы внутри каждого процесса воркера! "
                    "Для синхронизации подключите распределенный Backplane (Redis/PG) или используйте workers=1."
                )

        try:
            from granian import Granian
        except ImportError:
            raise RuntimeError("Для запуска через app.run() установите granian: pip install granian")

        target_loader = granian_kwargs.pop("target_loader", _granian_target_loader)
        server = Granian(
            target=self,
            address=host,
            port=port,
            interface="rsgi",
            workers=workers,
            **granian_kwargs
        )
        server.serve(target_loader=target_loader)
