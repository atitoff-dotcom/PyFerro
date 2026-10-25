"""
Чистый ASGI-сервер PyFerro 2.0 (`PyFerroApp`).

Обслуживает:
1. `WebSocket /ws` — полнодуплексный JSON-RPC 2.0 канал, мультиретурн (`yield`),
   `session.notify(...)`, `auth.login` на лету и корректный дисконнект при смене прав.
2. `HTTP POST /rpc` — синхронный JSON-RPC 2.0 поверх HTTP.
3. `HTTP POST /upload` — потоковый прием файлов чанками на диск (потребление памяти O(1) RAM).
4. `HTTP GET /files/<folder>/<filename>` — защищенная раздача файлов (поддерживает `X-Accel-Redirect` для Nginx и JWT-токены).
"""

import asyncio
from collections.abc import AsyncIterator
import mimetypes
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import parse_qs, unquote

import orjson
from sqlalchemy import select

from pyferro2.auth.seeder import load_guest_session_data, seed_system_roles
from pyferro2.core.constants import JsonRpcErrorCode, WsCloseCode
from pyferro2.core.session import Session
from pyferro2.core.session_data import GUEST_SESSION_DATA, SessionData
from pyferro2.crud.engine import CrudEngine
from pyferro2.crud.rpc import register_crud_rpc
from pyferro2.db.engine import Database
from pyferro2.files.models import StoredFile
from pyferro2.files.rpc import register_file_rpc
from pyferro2.files.storage import FileStorage
from pyferro2.rpc.errors import RpcError
from pyferro2.rpc.router import RpcRouter, encode_error
from pyferro2.server.auth_rpc import register_auth_rpc
from pyferro2.server.tokens import TokenManager, extract_token_from_scope

_CHUNK_SIZE = 64 * 1024  # 64 КБ


def _granian_target_loader(target: Any) -> Any:
    """Позволяет Granian запускать уже созданный экземпляр PyFerroApp через app.run()."""
    if isinstance(target, str):
        from granian._internal import load_target

        return load_target(target)
    return target


class PyFerroApp:
    """
    Главное ASGI-приложение фреймворка PyFerro 2.0.
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
    ) -> None:
        self.db: Database = db if db is not None else Database()
        self.router: RpcRouter = router if router is not None else RpcRouter()
        self.token_manager: TokenManager = (
            token_manager if token_manager is not None else TokenManager(secret_key=secret_key)
        )
        self.file_storage: FileStorage = (
            file_storage if file_storage is not None else FileStorage()
        )
        self.guest_session_data: SessionData = GUEST_SESSION_DATA
        self.admin_path: str = admin_path.rstrip("/") or "/pyferro_admin"
        self.frontend_dist: Path = (
            frontend_dist
            if frontend_dist is not None
            else Path(__file__).resolve().parent.parent / "frontend" / "dist"
        )
        self._sessions: set[Session] = set()

        self.crud: CrudEngine = (
            crud
            if crud is not None
            else CrudEngine(
                on_disconnect_user=self.disconnect_user,
                on_guest_permissions_updated=self._update_guest_permissions,
            )
        )

        # Регистрируем встроенные системные, файловые и CRUD RPC-методы
        register_auth_rpc(self.router, self.token_manager)
        register_file_rpc(self.router, self.file_storage, self.token_manager)
        register_crud_rpc(self.router, self.crud)

    def _update_guest_permissions(self, permissions: frozenset[str]) -> None:
        """Обновляет in-memory кэш прав роли `guest` при изменении матрицы прав."""
        self.guest_session_data = SessionData.guest(permissions)
        for sess in list(self._sessions):
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
        """Инициализирует таблицы БД, системные роли и кэш разрешений гостя."""
        await self.db.create_tables()
        async with self.db.session() as session:
            await seed_system_roles(session)
            self.guest_session_data = await load_guest_session_data(session)

    async def shutdown(self) -> None:
        """Корректно закрывает активные сессии и соединения с БД."""
        for sess in list(self._sessions):
            await sess.request_disconnect(WsCloseCode.GOING_AWAY)
        self._sessions.clear()
        await self.db.close()

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        workers: int = 1,
        **granian_kwargs: Any,
    ) -> None:
        """
        Запускает приложение на Rust-сервере Granian (поэтому фреймворк и называется PyFerro: Python + Rust).
        """
        try:
            from granian import Granian
        except ImportError as exc:
            raise RuntimeError(
                "Для запуска сервера через app.run() установите granian: pip install granian"
            ) from exc

        target_loader = granian_kwargs.pop("target_loader", _granian_target_loader)
        interface = granian_kwargs.pop("interface", "asgi")
        server = Granian(
            target=self,
            address=host,
            port=port,
            interface=interface,
            workers=workers,
            **granian_kwargs,
        )
        server.serve(target_loader=target_loader)

    def authenticate_scope(self, scope: dict[str, Any]) -> SessionData:
        """
        Извлекает токен (`Bearer` -> кука `ferro_session` -> `?token=`),
        проверяет его в `TokenManager` за O(1) и записывает `scope['session_data']`.
        """
        token = extract_token_from_scope(scope)
        session_data = self.token_manager.resolve_token(token)
        if session_data is None:
            session_data = self.guest_session_data
        scope["session_data"] = session_data
        return session_data

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope["type"]

        if scope_type == "lifespan":
            await self._handle_lifespan(receive, send)
            return

        session_data = self.authenticate_scope(scope)

        if scope_type == "websocket":
            await self._handle_websocket(scope, receive, send, session_data)
        elif scope_type == "http":
            await self._handle_http(scope, receive, send, session_data)

    async def _handle_lifespan(self, receive: Any, send: Any) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self.startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
            elif message["type"] == "lifespan.shutdown":
                await self.shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        initial_data: SessionData,
    ) -> None:
        path = scope.get("path", "")
        if path != "/ws":
            await send({"type": "websocket.close", "code": WsCloseCode.POLICY_VIOLATION})
            return

        msg = await receive()
        if msg["type"] != "websocket.connect":
            return

        await send({"type": "websocket.accept"})

        ws_closed = False

        async def ws_notify(event: str, payload: Any) -> None:
            if ws_closed:
                return
            frame_bytes = orjson.dumps({
                "jsonrpc": "2.0",
                "method": event,
                "params": payload,
            })
            await send({"type": "websocket.send", "text": frame_bytes.decode("utf-8")})

        async def ws_close(code: int) -> None:
            nonlocal ws_closed
            if not ws_closed:
                ws_closed = True
                await send({"type": "websocket.close", "code": int(code)})

        session = Session(
            session_id=f"ws-{secrets.token_hex(8)}",
            data=initial_data,
            notify=ws_notify,
            close=ws_close,
        )
        self._sessions.add(session)

        try:
            while not ws_closed and not session.is_closing:
                event = await receive()
                event_type = event["type"]

                if event_type == "websocket.disconnect":
                    ws_closed = True
                    break

                if event_type == "websocket.receive":
                    raw = event.get("bytes") or event.get("text")
                    if not raw or session.is_closing:
                        continue

                    # Легковесный текстовый Heartbeat без парсинга JSON
                    if raw in ("ping", b"ping"):
                        await send({"type": "websocket.send", "text": "pong"})
                        continue

                    await self._dispatch_ws_frame(raw, session, scope, send)
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
        scope: dict[str, Any],
        send: Any,
    ) -> None:
        """
        Обрабатывает входящий JSON-RPC фрейм по WebSocket:
        - Если вызван мультиретурн-метод (`yield`), запускает потоковую передачу чанков с тем же `id`.
        - Если вызван обычный `return`-метод, выполняет его и отправляет единичный ответ.
        """
        try:
            packet = orjson.loads(raw)
        except Exception:
            err_bytes = encode_error(None, JsonRpcErrorCode.PARSE_ERROR, "Ошибка разбора JSON")
            await send({"type": "websocket.send", "text": err_bytes.decode("utf-8")})
            return

        if type(packet) is not dict or packet.get("jsonrpc") != "2.0":
            req_id = packet.get("id") if type(packet) is dict else None
            err_bytes = encode_error(req_id, JsonRpcErrorCode.INVALID_REQUEST, "Некорректный пакет JSON-RPC 2.0")
            await send({"type": "websocket.send", "text": err_bytes.decode("utf-8")})
            return

        method_name = packet.get("method")
        spec = self.router.get_spec(method_name) if type(method_name) is str else None

        # Если метод — мультиретурн (`async def ... yield`), стримим каждый yield с тем же id
        if spec is not None and spec.is_stream:
            req_id = packet.get("id")
            raw_params = packet.get("params")

            async def _run_stream() -> None:
                try:
                    async for item in self.router.stream(method_name, session, raw_params, db=self.db):
                        if session._closed:
                            break
                        chunk_bytes = orjson.dumps({
                            "jsonrpc": "2.0",
                            "result": item,
                            "id": req_id,
                        })
                        await send({"type": "websocket.send", "text": chunk_bytes.decode("utf-8")})
                except RpcError as rpc_err:
                    if req_id is not None and not session._closed:
                        eb = encode_error(req_id, rpc_err.code, rpc_err.message, rpc_err.data)
                        await send({"type": "websocket.send", "text": eb.decode("utf-8")})
                except asyncio.CancelledError:
                    raise

            task = asyncio.create_task(_run_stream())
            session.register_stream_task(task)
            await asyncio.sleep(0)
            return

        # Обычный атомарный `return`-вызов
        resp_bytes = await self.router.handle_raw(raw, session, db=self.db)
        scope["session_data"] = session.data

        if resp_bytes is not None:
            await send({"type": "websocket.send", "text": resp_bytes.decode("utf-8")})

    async def _handle_http(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        session_data: SessionData,
    ) -> None:
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")

        if path == "/rpc" and method == "POST":
            body = await _read_full_body(receive)
            session = Session(session_id=f"http-{secrets.token_hex(6)}", data=session_data)
            resp_bytes = await self.router.handle_raw(body, session, db=self.db)
            scope["session_data"] = session.data
            await _send_json_bytes(send, 200, resp_bytes or b"")
            return

        if path == "/upload" and method == "POST":
            await self._handle_http_upload(scope, receive, send, session_data)
            return

        if path.startswith("/files/") and method == "GET":
            await self._handle_http_file_download(scope, send, session_data)
            return

        if method == "GET" and (
            path == self.admin_path or path.startswith(f"{self.admin_path}/")
        ):
            await self._handle_http_admin_spa(path, send)
            return

        await _send_json_bytes(
            send,
            404,
            orjson.dumps({"error": "Not Found", "path": path}),
        )

    async def _handle_http_admin_spa(self, path: str, send: Any) -> None:
        """Раздает статическую сборку SPA панели управления `/pyferro_admin`."""
        rel_part = path[len(self.admin_path) :].lstrip("/")
        dist_root = self.frontend_dist.resolve()
        target_file = (dist_root / rel_part).resolve() if rel_part else (dist_root / "index.html")

        if not target_file.is_relative_to(dist_root) or not target_file.is_file():
            target_file = dist_root / "index.html"

        if not target_file.is_file():
            await _send_json_bytes(
                send,
                404,
                orjson.dumps({"error": "Сборка панели /pyferro_admin не найдена"}),
            )
            return

        mime_type, _ = mimetypes.guess_type(target_file.name)
        content_type = (mime_type or "application/octet-stream").encode("latin-1")
        body = target_file.read_bytes()
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", content_type),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def _handle_http_upload(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        session_data: SessionData,
    ) -> None:
        if session_data.is_guest:
            await _send_json_bytes(send, 401, orjson.dumps({"error": "Требуется авторизация"}))
            return

        query = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
        folder_hash = (query.get("folder") or [""])[0].strip()
        filename = (query.get("filename") or [""])[0].strip()

        headers_dict = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in (scope.get("headers") or [])
        }
        if not filename:
            filename = headers_dict.get("x-file-name", "uploaded_file")
        mime_type = headers_dict.get("content-type", "application/octet-stream")

        tx = self.file_storage.get_transaction(folder_hash)
        if tx is None:
            await _send_json_bytes(send, 404, orjson.dumps({"error": "Транзакция загрузки не найдена"}))
            return
        if not session_data.is_admin and tx.creator_id != session_data.user_id:
            await _send_json_bytes(send, 403, orjson.dumps({"error": "Доступ к транзакции запрещен"}))
            return

        try:
            file_info = await self.file_storage.receive_stream(
                folder_hash=folder_hash,
                raw_filename=filename,
                mime_type=mime_type,
                chunks=_iter_request_chunks(receive),
            )
        except ValueError as exc:
            await _send_json_bytes(send, 400, orjson.dumps({"error": str(exc)}))
            return

        await _send_json_bytes(send, 200, orjson.dumps({"status": "uploaded", "file": file_info}))

    async def _handle_http_file_download(
        self,
        scope: dict[str, Any],
        send: Any,
        session_data: SessionData,
    ) -> None:
        parts = [unquote(p) for p in scope.get("path", "").split("/") if p]
        if len(parts) != 3 or parts[0] != "files":
            await _send_json_bytes(send, 404, orjson.dumps({"error": "Некорректный путь к файлу"}))
            return

        _, folder_hash, filename = parts

        async with self.db.session() as db_session:
            stmt = select(StoredFile).where(
                StoredFile.folder_hash == folder_hash,
                StoredFile.filename == filename,
            )
            record = (await db_session.execute(stmt)).scalar_one_or_none()

        if record is None:
            await _send_json_bytes(send, 404, orjson.dumps({"error": "Файл не найден в реестре"}))
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
                    await _send_json_bytes(
                        send, 403, orjson.dumps({"error": "Нет прав на скачивание приватного файла"})
                    )
                    return

        file_path = self.file_storage.resolve_file_path(folder_hash, filename)
        if file_path is None:
            await _send_json_bytes(send, 404, orjson.dumps({"error": "Физический файл отсутствует"}))
            return

        content_type = record.mime_type.encode("latin-1")

        if self.file_storage.nginx_internal_prefix:
            internal_uri = f"{self.file_storage.nginx_internal_prefix}/{folder_hash}/{filename}"
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", content_type),
                    (b"x-accel-redirect", internal_uri.encode("latin-1")),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", content_type),
                (b"content-length", str(record.size).encode("latin-1")),
            ],
        })
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(_CHUNK_SIZE)
                if not chunk:
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    break
                await send({"type": "http.response.body", "body": chunk, "more_body": True})


async def _read_full_body(receive: Any) -> bytes:
    """Считывает тело короткого HTTP-запроса (для `/rpc`)."""
    chunks: list[bytes] = []
    async for chunk in _iter_request_chunks(receive):
        chunks.append(chunk)
    return b"".join(chunks)


async def _iter_request_chunks(receive: Any) -> AsyncIterator[bytes]:
    """Асинхронный генератор чанков тела HTTP-запроса из ASGI `receive`."""
    while True:
        message = await receive()
        if message["type"] == "http.request":
            body = message.get("body", b"")
            if body:
                yield body
            if not message.get("more_body", False):
                break
        elif message["type"] == "http.disconnect":
            break


async def _send_json_bytes(send: Any, status: int, body: bytes) -> None:
    """Отправляет HTTP JSON-ответ с готовыми `bytes` от `orjson`."""
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("latin-1")),
        ],
    })
    await send({"type": "http.response.body", "body": body})
