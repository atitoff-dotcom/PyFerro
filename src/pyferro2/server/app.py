"""
Чистый RSGI-сервер PyFerro 2.0 (`PyFerroApp`).

Обслуживает нативные интерфейсы Granian RSGI (Rust Server-Gateway Interface):
1. `WebSocket /ws` — полнодуплексный JSON-RPC 2.0 канал, мультиретурн (`yield`),
   `session.notify(...)`, `auth.login` на лету и мгновенный дисконнект при смене прав.
2. `HTTP POST /rpc` — JSON-RPC 2.0 поверх HTTP в один вызов `proto.response_bytes(...)`.
3. `HTTP POST /upload` — потоковый прием файлов чанками на диск (`O(1)` RAM).
4. `HTTP GET /files/<folder>/<filename>` — zero-copy отдача файлов через Rust (`proto.response_file`)
   или Nginx `X-Accel-Redirect` (`proto.response_empty`).
5. `HTTP GET /pyferro_admin` — zero-copy раздача статической SPA панели управления через Rust.
6. `HTTP GET /sitemap.xml` (`/sitemap-N.xml`), `/<indexnow_key>.txt` и Dynamic Rendering для ботов (`?bot=1`).
"""

import asyncio
from collections.abc import AsyncIterator
import mimetypes
from pathlib import Path
import secrets
import sys
from typing import Any
from urllib.parse import parse_qs, unquote

from granian.rsgi import (
    ProtocolClosed as RSGIProtocolClosed,
    WebsocketMessageType,
)
import orjson
from sqlalchemy import select

from pyferro2.auth.seeder import ensure_admin_user, load_guest_session_data, seed_system_roles
from pyferro2.core.constants import JsonRpcErrorCode, WsCloseCode
from pyferro2.core.session import Session
from pyferro2.core.session_data import GUEST_SESSION_DATA, SessionData
from pyferro2.crud.engine import CrudEngine
from pyferro2.crud.rpc import register_crud_rpc
from pyferro2.db.engine import Database
from pyferro2.files.models import StoredFile
from pyferro2.files.rpc import register_file_rpc
from pyferro2.files.storage import FileMaxSizeExceededError, FileStorage
from pyferro2.help.rpc import register_help_rpc
from pyferro2.rpc.errors import RpcError
from pyferro2.rpc.router import RpcRouter, default_router, encode_error
from pyferro2.seo.models import get_seo_config
from pyferro2.seo.router import handle_bot_http
from pyferro2.seo.rpc import register_seo_rpc
from pyferro2.seo.site_tree import load_seo_from_db
from pyferro2.seo.sitemap import handle_sitemap_http
from pyferro2.server.auth_rpc import register_auth_rpc
from pyferro2.server.tokens import TokenManager, extract_token_from_scope
_JSON_CONTENT_TYPE: tuple[str, str] = ("content-type", "application/json; charset=utf-8")
_FILE_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("content-security-policy", "default-src 'none'; sandbox"),
    ("referrer-policy", "no-referrer"),
)


def _granian_target_loader(target: Any) -> Any:
    """Позволяет Granian запускать уже созданный экземпляр PyFerroApp через app.run()."""
    if isinstance(target, str):
        from granian._internal import load_target

        return load_target(target)
    return target


def _set_scope_session_data(scope: Any, session_data: SessionData) -> None:
    """Безопасно сохраняет актуальный SessionData в scope."""
    if isinstance(scope, dict):
        scope["session_data"] = session_data
    else:
        try:
            setattr(scope, "session_data", session_data)
        except Exception:
            pass
        if hasattr(scope, "__setitem__"):
            try:
                scope["session_data"] = session_data
            except Exception:
                pass


class PyFerroApp:
    """
    Главное RSGI-приложение фреймворка PyFerro 2.0.
    """

    __slots__ = (
        "db",
        "router",
        "token_manager",
        "file_storage",
        "crud",
        "guest_session_data",
        "admin_path",
        "frontend_dist",
        "docs_help_dir",
        "_sessions",
    )
    def __init__(
        self,
        db: Database | None = None,
        router: RpcRouter | None = None,
        token_manager: TokenManager | None = None,
        file_storage: FileStorage | None = None,
        crud: CrudEngine | None = None,
        secret_key: str = "pyferro2-dev-secret-key-change-in-prod-32b",
        admin_path: str = "/pyferro_admin",
        frontend_dist: Path | None = None,
        docs_help_dir: Path | str = "docs/help",
    ) -> None:
        self.db: Database = db if db is not None else Database()
        self.router: RpcRouter = router if router is not None else RpcRouter()
        self.router.include(default_router)
        self.token_manager: TokenManager = (
            token_manager if token_manager is not None else TokenManager(secret_key=secret_key)
        )
        self.file_storage: FileStorage = (
            file_storage if file_storage is not None else FileStorage()
        )
        self.guest_session_data: SessionData = GUEST_SESSION_DATA
        self.admin_path: str = admin_path.rstrip("/") or "/pyferro_admin"
        if frontend_dist is not None:
            self.frontend_dist = frontend_dist
        else:
            pkg_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
            repo_dist = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
            self.frontend_dist = repo_dist if repo_dist.exists() else pkg_dist
        self.docs_help_dir: Path = Path(docs_help_dir)
        self._sessions: set[Session] = set()

        self.crud: CrudEngine = (
            crud
            if crud is not None
            else CrudEngine(
                on_disconnect_user=self.disconnect_user,
                on_guest_permissions_updated=self._update_guest_permissions,
            )
        )

        # Регистрируем встроенные системные, файловые, CRUD и SEO RPC-методы
        register_auth_rpc(self.router, self.token_manager)
        register_file_rpc(self.router, self.file_storage, self.token_manager)
        register_crud_rpc(self.router, self.crud)
        register_seo_rpc(
            self.router,
            self.db,
            self.crud,
            lambda: self.guest_session_data.permissions,
        )
        register_help_rpc(self.router, self.docs_help_dir)

    def _update_guest_permissions(self, permissions: frozenset[str]) -> None:
        """Обновляет in-memory кэш прав роли `guest` при изменении матрицы прав."""
        self.guest_session_data = SessionData.guest(permissions)
        for sess in list(self._sessions):
            sess._guest_permissions = permissions
            if sess.data.is_guest:
                sess.reset_to_guest(permissions)

    async def disconnect_user(
        self,
        user_id: int,
        code: int = WsCloseCode.POLICY_VIOLATION,
    ) -> None:
        """
        Отзывает JWT-токены пользователя и запрашивает корректный дисконнект
        всех его открытых WebSocket-сессий (после завершения текущих атомарных RPC).
        """
        self.token_manager.revoke_user(user_id)
        for sess in list(self._sessions):
            if sess.data.user_id == user_id:
                await sess.request_disconnect(code)

    async def startup(self) -> None:
        """Инициализирует таблицы БД, системные роли, кэш разрешений гостя и дерево SEO."""
        self.router.include(default_router)
        await self.db.create_tables()
        async with self.db.session() as session:
            await seed_system_roles(session)
            self.guest_session_data = await load_guest_session_data(session)
            await load_seo_from_db(session)

    async def shutdown(self) -> None:
        """Корректно закрывает активные сессии и соединения с БД."""
        for sess in list(self._sessions):
            await sess.request_disconnect(WsCloseCode.GOING_AWAY)
        self._sessions.clear()
        await self.db.close()

    def handle_cli(self, argv: list[str] | None = None) -> bool:
        """
        Обрабатывает служебные CLI-флаги (например, --add-admin).
        Возвращает True, если команда была обработана и сервер запускать не требуется.
        """
        args = argv if argv is not None else sys.argv[1:]
        if not args:
            return False

        if "--add-admin" in args:
            username = "admin"
            password = "admin"
            for i, arg in enumerate(args):
                if arg in ("--username", "-u") and i + 1 < len(args):
                    username = args[i + 1]
                elif arg in ("--password", "-p") and i + 1 < len(args):
                    password = args[i + 1]

            async def _run() -> None:
                await self.db.create_tables()
                async with self.db.session() as session:
                    user = await ensure_admin_user(session, username=username, password=password)
                print("=" * 60)
                print(" 🛡️  PyFerro 2.0: Администратор успешно создан / обновлен!")
                print(f" 👤 Логин:  {user.username}")
                print(f" 🔑 Пароль: {password}")
                print(f" 👑 Роли:   {', '.join(r.name for r in user.roles)}")
                print("=" * 60)

            asyncio.run(_run())
            return True

        return False

    def __rsgi_init__(self, loop: Any) -> None:
        """Хук инициализации Granian RSGI воркера."""
        loop.run_until_complete(self.startup())

    def __rsgi_del__(self, loop: Any) -> None:
        """Хук завершения работы Granian RSGI воркера."""
        loop.run_until_complete(self.shutdown())

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        workers: int = 1,
        **granian_kwargs: Any,
    ) -> None:
        """
        Запускает приложение на нативном RSGI-сервере Granian.
        Перед стартом проверяет наличие CLI-команд (например, --add-admin).
        """
        if self.handle_cli():
            return

        try:
            from granian import Granian
        except ImportError as exc:
            raise RuntimeError(
                "Для запуска сервера через app.run() установите granian: pip install granian"
            ) from exc

        target_loader = granian_kwargs.pop("target_loader", _granian_target_loader)
        interface = granian_kwargs.pop("interface", "rsgi")
        server = Granian(
            target=self,
            address=host,
            port=port,
            interface=interface,
            workers=workers,
            **granian_kwargs,
        )
        server.serve(target_loader=target_loader)

    def authenticate_scope(self, scope: Any) -> SessionData:
        """
        Извлекает токен (`Bearer` -> кука `ferro_session` -> `?token=`),
        проверяет его в `TokenManager` за O(1) и записывает `session_data` в scope.
        """
        token = extract_token_from_scope(scope)
        session_data = self.token_manager.resolve_token(token)
        if session_data is None:
            session_data = self.guest_session_data
        _set_scope_session_data(scope, session_data)
        return session_data

    async def __call__(self, scope: Any, proto: Any) -> None:
        """
        Нативная точка входа RSGI (`async def (scope, proto)`).
        """
        proto_type = getattr(scope, "proto", "")
        if not proto_type and isinstance(scope, dict):
            proto_type = scope.get("type", "")

        session_data = self.authenticate_scope(scope)

        if proto_type in ("websocket", "ws"):
            await self._handle_websocket(scope, proto, session_data)
        elif proto_type in ("http", "https"):
            await self._handle_http(scope, proto, session_data)

    async def _handle_websocket(
        self,
        scope: Any,
        proto: Any,
        initial_data: SessionData,
    ) -> None:
        path = getattr(scope, "path", "")
        if path not in ("/ws", "/ws/"):
            # Отклоняем WebSocket-подключение на неизвестный маршрут до accept()
            try:
                proto.close(WsCloseCode.POLICY_VIOLATION)
            except Exception:
                pass
            return

        try:
            transport = await proto.accept()
        except Exception:
            return

        ws_closed = False

        async def ws_notify(event: str, payload: Any) -> None:
            if ws_closed:
                return
            frame_bytes = orjson.dumps({
                "jsonrpc": "2.0",
                "method": event,
                "params": payload,
            })
            await transport.send_str(frame_bytes.decode("utf-8"))

        async def ws_close(code: int) -> None:
            nonlocal ws_closed
            if not ws_closed:
                ws_closed = True
                try:
                    proto.close(int(code))
                except Exception:
                    pass

        session = Session(
            session_id=f"ws-{secrets.token_hex(8)}",
            data=initial_data,
            notify=ws_notify,
            close=ws_close,
            guest_permissions=self.guest_session_data.permissions,
        )
        self._sessions.add(session)

        try:
            while not ws_closed and not session.is_closing:
                try:
                    msg = await transport.receive()
                except (RSGIProtocolClosed, ConnectionResetError, asyncio.CancelledError):
                    ws_closed = True
                    break
                except Exception as exc:
                    if "RSGI transport is closed" in str(exc) or "ProtocolClosed" in type(exc).__name__:
                        ws_closed = True
                        break
                    raise

                cls_name = getattr(getattr(msg, "__class__", None), "__name__", "") or type(msg).__name__
                if not msg or "CloseMessage" in cls_name or getattr(msg, "kind", None) == WebsocketMessageType.close:
                    ws_closed = True
                    break

                raw = getattr(msg, "data", None)
                if not raw or session.is_closing:
                    continue

                # Легковесный текстовый Heartbeat без парсинга JSON
                if raw in ("ping", b"ping"):
                    await transport.send_str("pong")
                    continue

                await self._dispatch_ws_frame(raw, session, scope, transport)
        finally:
            self._sessions.discard(session)
            for task in list(session._stream_tasks):
                if not task.done():
                    task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _dispatch_ws_frame(
        self,
        raw: bytes | str,
        session: Session,
        scope: Any,
        transport: Any,
    ) -> None:
        """
        Обрабатывает входящий JSON-RPC фрейм по WebSocket:
        - Если вызван мультиретурн-метод (`yield`), запускает потоковую передачу чанков с тем же `id`.
        - Если вызван обычный `return`-метод, выполняет его, гарантированно отправляет ответ,
          и только после этого завершает RPC-цикл (применяя отложенный дисконнект, если он был запрошен).
        """
        try:
            packet = orjson.loads(raw)
        except Exception:
            err_bytes = encode_error(None, JsonRpcErrorCode.PARSE_ERROR, "Ошибка разбора JSON")
            await transport.send_str(err_bytes.decode("utf-8"))
            return

        if type(packet) is not dict or packet.get("jsonrpc") != "2.0":
            req_id = packet.get("id") if type(packet) is dict else None
            err_bytes = encode_error(
                req_id, JsonRpcErrorCode.INVALID_REQUEST, "Некорректный пакет JSON-RPC 2.0"
            )
            await transport.send_str(err_bytes.decode("utf-8"))
            return

        method_name = packet.get("method")
        spec = self.router.get_spec(method_name) if type(method_name) is str else None

        # Если метод — мультиретурн (`async def ... yield`), стримим каждый yield с тем же id
        if spec is not None and spec.is_stream:
            req_id = packet.get("id")
            raw_params = packet.get("params")

            async def _run_stream() -> None:
                try:
                    async for item in self.router.stream(
                        method_name, session, raw_params, db=self.db
                    ):
                        if session._closed:
                            break
                        chunk_bytes = orjson.dumps({
                            "jsonrpc": "2.0",
                            "result": item,
                            "id": req_id,
                        })
                        await transport.send_str(chunk_bytes.decode("utf-8"))
                except RpcError as rpc_err:
                    if req_id is not None and not session._closed:
                        eb = encode_error(req_id, rpc_err.code, rpc_err.message, rpc_err.data)
                        await transport.send_str(eb.decode("utf-8"))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if req_id is not None and not session._closed:
                        eb = encode_error(
                            req_id,
                            JsonRpcErrorCode.INTERNAL_ERROR,
                            "Внутренняя ошибка сервера",
                        )
                        await transport.send_str(eb.decode("utf-8"))

            task = asyncio.create_task(_run_stream())
            session.register_stream_task(task)
            await asyncio.sleep(0)
            return

        # Обычный атомарный `return`-вызов: удерживаем счетчик активных RPC до отправки ответа в сокет
        session.begin_rpc()
        try:
            resp_bytes = await self.router.handle_packet(packet, session, db=self.db)
            _set_scope_session_data(scope, session.data)

            if resp_bytes is not None and not session._closed:
                await transport.send_str(resp_bytes.decode("utf-8"))
        finally:
            await session.end_rpc()

    async def _handle_http(
        self,
        scope: Any,
        proto: Any,
        session_data: SessionData,
    ) -> None:
        method = getattr(scope, "method", "GET").upper()
        path = getattr(scope, "path", "/")

        if (path == "/rpc" or path == "/rpc/") and method == "POST":
            body = await proto()
            session = Session(
                session_id=f"http-{secrets.token_hex(6)}",
                data=session_data,
                guest_permissions=self.guest_session_data.permissions,
            )
            resp_bytes = await self.router.handle_raw(body, session, db=self.db)
            _set_scope_session_data(scope, session.data)
            proto.response_bytes(200, [_JSON_CONTENT_TYPE], resp_bytes or b"")
            return

        if path == "/upload" and method == "POST":
            await self._handle_http_upload(scope, proto, session_data)
            return

        if path.startswith("/files/") and method == "GET":
            await self._handle_http_file_download(scope, proto, session_data)
            return

        if method == "GET" and (
            path == self.admin_path or path.startswith(f"{self.admin_path}/")
        ):
            await self._handle_http_admin_spa(path, proto)
            return

        if method in ("GET", "HEAD"):
            # 1. Карта сайта (/sitemap.xml, /sitemap-N.xml)
            if await handle_sitemap_http(
                scope,
                proto,
                db=self.db,
                crud_engine=self.crud,
                guest_permissions=self.guest_session_data.permissions,
            ):
                return

            # 2. Верификационный ключ IndexNow (/<indexnow_key>.txt)
            seo_cfg = get_seo_config()
            if seo_cfg.indexnow_key and path == f"/{seo_cfg.indexnow_key}.txt":
                if hasattr(proto, "response_str"):
                    proto.response_str(
                        200,
                        [("content-type", "text/plain; charset=utf-8")],
                        seo_cfg.indexnow_key,
                    )
                else:
                    proto.response_bytes(
                        200,
                        [("content-type", "text/plain; charset=utf-8")],
                        seo_cfg.indexnow_key.encode("utf-8"),
                    )
                return

            # 3. Dynamic Rendering для поисковых ботов и режима эмуляции (?bot=1)
            if await handle_bot_http(
                scope,
                proto,
                db=self.db,
                crud_engine=self.crud,
                guest_permissions=self.guest_session_data.permissions,
                admin_path=self.admin_path,
            ):
                return

        proto.response_bytes(
            404,
            [_JSON_CONTENT_TYPE],
            orjson.dumps({"error": "Not Found", "path": path}),
        )

    async def _handle_http_admin_spa(self, path: str, proto: Any) -> None:
        """Раздает статическую сборку SPA панели управления `/pyferro_admin` zero-copy через Rust."""
        rel_part = path[len(self.admin_path) :].lstrip("/")
        dist_root = self.frontend_dist.resolve()
        target_file = (dist_root / rel_part).resolve() if rel_part else (dist_root / "index.html")

        if not target_file.is_relative_to(dist_root) or not target_file.is_file():
            target_file = dist_root / "index.html"

        if not target_file.is_file():
            proto.response_bytes(
                404,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Сборка панели /pyferro_admin не найдена"}),
            )
            return

        mime_type, _ = mimetypes.guess_type(target_file.name)
        content_type = mime_type or "application/octet-stream"
        proto.response_file(
            200,
            [("content-type", content_type)],
            str(target_file),
        )

    async def _handle_http_upload(
        self,
        scope: Any,
        proto: Any,
        session_data: SessionData,
    ) -> None:
        if session_data.is_guest:
            proto.response_bytes(
                401,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Требуется авторизация"}),
            )
            return

        query_str = getattr(scope, "query_string", "")
        if isinstance(query_str, bytes):
            query_str = query_str.decode("latin-1")
        query = parse_qs(query_str)
        folder_hash = (query.get("folder") or [""])[0].strip()
        filename = (query.get("filename") or [""])[0].strip()

        headers = getattr(scope, "headers", None)
        if headers is None and isinstance(scope, dict):
            headers = scope.get("headers")

        if not filename:
            filename = (
                headers.get("x-file-name", "uploaded_file")
                if hasattr(headers, "get")
                else "uploaded_file"
            )
        mime_type = (
            headers.get("content-type", "application/octet-stream")
            if hasattr(headers, "get")
            else "application/octet-stream"
        )

        tx = self.file_storage.get_transaction(folder_hash)
        if tx is None:
            proto.response_bytes(
                404,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Транзакция загрузки не найдена"}),
            )
            return
        if not session_data.is_admin and tx.creator_id != session_data.user_id:
            proto.response_bytes(
                403,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Доступ к транзакции запрещен"}),
            )
            return

        # Fail-Fast проверка заголовка Content-Length ДО чтения потока из RSGI proto
        raw_content_length = (
            headers.get("content-length") if hasattr(headers, "get") else None
        )
        if raw_content_length is not None:
            try:
                declared_size = int(raw_content_length)
            except (TypeError, ValueError):
                proto.response_bytes(
                    400,
                    [_JSON_CONTENT_TYPE],
                    orjson.dumps({"error": "Некорректный заголовок Content-Length"}),
                )
                return
            if declared_size < 0:
                proto.response_bytes(
                    400,
                    [_JSON_CONTENT_TYPE],
                    orjson.dumps({"error": "Некорректный заголовок Content-Length"}),
                )
                return
            if declared_size > self.file_storage.max_file_size:
                proto.response_bytes(
                    413,
                    [_JSON_CONTENT_TYPE],
                    orjson.dumps(
                        {
                            "error": (
                                f"Превышен максимальный размер файла "
                                f"({self.file_storage.max_file_size} байт)"
                            )
                        }
                    ),
                )
                return

        try:
            file_info = await self.file_storage.receive_stream(
                folder_hash=folder_hash,
                raw_filename=filename,
                mime_type=mime_type,
                chunks=_iter_rsgi_chunks(proto),
            )
        except FileMaxSizeExceededError as exc:
            proto.response_bytes(
                413,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": str(exc)}),
            )
            return
        except TimeoutError as exc:
            proto.response_bytes(
                408,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": str(exc)}),
            )
            return
        except ValueError as exc:
            proto.response_bytes(
                400,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": str(exc)}),
            )
            return

        proto.response_bytes(
            200,
            [_JSON_CONTENT_TYPE],
            orjson.dumps({"status": "uploaded", "file": file_info}),
        )

    async def _handle_http_file_download(
        self,
        scope: Any,
        proto: Any,
        session_data: SessionData,
    ) -> None:
        path = getattr(scope, "path", "")
        parts = [unquote(p) for p in path.split("/") if p]
        if len(parts) != 3 or parts[0] != "files":
            proto.response_bytes(
                404,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Некорректный путь к файлу"}),
            )
            return

        _, folder_hash, filename = parts

        async with self.db.session() as db_session:
            stmt = select(StoredFile).where(
                StoredFile.folder_hash == folder_hash,
                StoredFile.filename == filename,
            )
            record = (await db_session.execute(stmt)).scalar_one_or_none()

        if record is None:
            proto.response_bytes(
                404,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Файл не найден в реестре"}),
            )
            return

        if not record.is_public:
            has_user_access = (
                not session_data.is_guest
                and (session_data.is_admin or record.creator_id == session_data.user_id)
            )
            if not has_user_access:
                token = extract_token_from_scope(scope)
                allowed_file_id = self.token_manager.verify_file_token(token)
                if allowed_file_id != record.id:
                    proto.response_bytes(
                        403,
                        [_JSON_CONTENT_TYPE],
                        orjson.dumps({"error": "Нет прав на скачивание приватного файла"}),
                    )
                    return

        file_path = self.file_storage.resolve_file_path(folder_hash, filename)
        if file_path is None:
            proto.response_bytes(
                404,
                [_JSON_CONTENT_TYPE],
                orjson.dumps({"error": "Физический файл отсутствует"}),
            )
            return

        content_type = record.mime_type
        response_headers: list[tuple[str, str]] = [
            ("content-type", content_type),
            *_FILE_SECURITY_HEADERS,
        ]

        if self.file_storage.nginx_internal_prefix:
            internal_uri = f"{self.file_storage.nginx_internal_prefix}/{folder_hash}/{filename}"
            proto.response_empty(
                200,
                [
                    *response_headers,
                    ("x-accel-redirect", internal_uri),
                ],
            )
            return

        proto.response_file(
            200,
            response_headers,
            str(file_path),
        )


async def _iter_rsgi_chunks(proto: Any) -> AsyncIterator[bytes]:
    """Асинхронный генератор чанков тела HTTP-запроса из RSGI протокола."""
    if hasattr(proto, "__aiter__"):
        async for chunk in proto:
            if chunk:
                yield chunk
    else:
        body = await proto()
        if body:
            yield body
