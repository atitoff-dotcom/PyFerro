"""
Модульные и интеграционные тесты RSGI-транспорта и файлов:
- Гибридный `TokenManager` (JWT для Nginx + O(1) кэш в памяти)
- HTTP `/rpc` (авторизация по `Bearer` и куке `ferro_session`)
- WebSocket `/ws` (живой `auth.login`, `session.notify`, Heartbeat, `auth.logout`)
- Файловая подсистема ядра (`pyferro2/files/`: двухфазная загрузка, раздача, приватные JWT и `X-Accel-Redirect`).
"""

from collections import deque
from pathlib import Path
from typing import Any

import jwt
import orjson
import pytest

from pyferro2.auth import User, hash_password, seed_system_roles
from pyferro2.core import SESSION_COOKIE_NAME, Session, SessionData, USER_ROLE, WsCloseCode, admRole
from pyferro2.db import Database
from pyferro2.files import FileStorage
from pyferro2.server import (
    MockRSGIScope,
    MockRSGIWebsocketProtocol,
    PyFerroApp,
    TokenManager,
    call_rsgi_http,
    extract_token_from_scope,
    make_ws_close,
    make_ws_message,
)


@pytest.fixture
async def app(tmp_path: Path) -> PyFerroApp:
    """Создает изолированное приложение PyFerroApp с in-memory БД и временным хранилищем файлов."""
    db = Database("sqlite+aiosqlite:///:memory:")
    storage = FileStorage(
        storage_dir=tmp_path / "storage",
        tmp_root=tmp_path / "tmp_uploads",
    )
    ferro_app = PyFerroApp(
        db=db,
        file_storage=storage,
        secret_key="test-nginx-shared-jwt-secret-key-32bytes",
    )
    await ferro_app.startup()

    # Создадим тестового пользователя 'alex' с ролью 'user' и правом 'orders.list'
    async with db.session() as session:
        roles = await seed_system_roles(session)
        user_role = roles[USER_ROLE]
        user_role.add_permission("orders.list")

        user = User(
            username="alex",
            password_hash=hash_password("Pass123!"),
            full_name="Alex Dev",
            roles=[user_role],
        )
        session.add(user)
        await session.commit()

    yield ferro_app
    await ferro_app.shutdown()


class TestHybridTokenManager:
    """Проверка гибридного `TokenManager`: совместимость с JWT (Nginx) и O(1) кэш в памяти."""

    def test_jwt_format_and_in_memory_cache(self) -> None:
        tm = TokenManager(secret_key="nginx-secret-key-for-jwt-validation")
        sd = SessionData(
            user_id=7,
            username="alex",
            roles=frozenset({USER_ROLE}),
            permissions=frozenset({"orders.list"}),
        )
        token = tm.issue_token(sd)

        # 1. Nginx может декодировать токен стандартным HS256 по общему secret_key
        decoded = jwt.decode(token, "nginx-secret-key-for-jwt-validation", algorithms=["HS256"])
        assert decoded["user_id"] == 7
        assert decoded["username"] == "alex"
        assert decoded["roles"] == ["user"]

        # 2. Быстрый путь в Python: возвращает тот же самый объект SessionData из RAM
        resolved_fast = tm.resolve_token(token)
        assert resolved_fast is sd

        # 3. Холодный путь (имитируем перезапуск воркера очисткой кэша) — восстанавливает из JWT
        tm._cache.clear()
        resolved_cold = tm.resolve_token(token)
        assert resolved_cold == sd

        # 4. Отзыв токена мгновенно блокирует и кэш, и повторный декод по jti
        tm.revoke_token(token)
        assert tm.resolve_token(token) is None

    def test_revoke_user_blocks_cold_jwt_decode(self) -> None:
        tm = TokenManager(secret_key="nginx-secret-key-for-jwt-validation")
        sd = SessionData(user_id=42, username="bob", roles=frozenset({USER_ROLE}))
        token = tm.issue_token(sd)

        # Имитируем очистку кэша, когда токен еще не был проверен в текущем воркере, но пользователь отозван
        tm._cache.clear()
        tm.revoke_user(42)
        assert tm.resolve_token(token) is None

        # Новый токен, выпущенный после разблокировки/перелогина, снова валиден
        new_token = tm.issue_token(sd)
        tm._cache.clear()
        assert tm.resolve_token(new_token) == sd

    def test_rejects_invalid_and_expired_tokens(self) -> None:
        tm = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
        sd = SessionData(user_id=1, username="u", roles=frozenset({USER_ROLE}))

        expired_token = tm.issue_token(sd, ttl_seconds=-10)
        assert tm.resolve_token(expired_token) is None
        assert tm.resolve_token("not.a.jwt") is None
        assert tm.resolve_token(None) is None

        # Токен скачивания файла не может использоваться как сессионный access-токен
        file_tok = tm.issue_file_token(file_id=55)
        assert tm.resolve_token(file_tok) is None
        assert tm.verify_file_token(file_tok) == 55
        assert tm.verify_file_token("invalid") is None

    def test_token_extraction_priority(self) -> None:
        scope = MockRSGIScope(
            proto="http",
            path="/",
            headers={
                "cookie": f"{SESSION_COOKIE_NAME}=cookie_tok",
                "authorization": "Bearer bearer_tok",
            },
            query_string="token=query_tok",
        )
        # Приоритет 1: Authorization Bearer
        assert extract_token_from_scope(scope) == "bearer_tok"

        # Приоритет 2: Кука ferro_session
        scope.headers = {"cookie": f"{SESSION_COOKIE_NAME}=cookie_tok"}
        assert extract_token_from_scope(scope) == "cookie_tok"

        # Приоритет 3: Query ?token=
        scope.headers = {}
        assert extract_token_from_scope(scope) == "query_tok"


class TestHttpAndWebSocketTransport:
    """Проверка авторизации по куке, по Bearer и живого RSGI WebSocket-соединения."""

    @pytest.mark.asyncio
    async def test_http_rpc_login_bearer_and_cookie(self, app: PyFerroApp) -> None:
        # 1. Вход через HTTP POST /rpc -> получаем JWT токен
        login_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "auth.login",
            "params": {"username": "alex", "password": "Pass123!"},
            "id": 1,
        })
        status, _, body, _ = await call_rsgi_http(app, "POST", "/rpc", body_chunks=[login_req])
        assert status == 200
        login_res = orjson.loads(body)["result"]
        token = login_res["token"]
        assert login_res["user"]["username"] == "alex"

        # 2. Запрос auth.me по заголовку Authorization: Bearer <token>
        me_req = orjson.dumps({"jsonrpc": "2.0", "method": "auth.me", "id": 2})
        _, _, me_body, scope_bearer = await call_rsgi_http(
            app,
            "POST",
            "/rpc",
            headers={"authorization": f"Bearer {token}"},
            body_chunks=[me_req],
        )
        assert orjson.loads(me_body)["result"]["username"] == "alex"
        assert scope_bearer["session_data"].username == "alex"

        # 3. Запрос auth.me по куке ferro_session
        _, _, cookie_body, scope_cookie = await call_rsgi_http(
            app,
            "POST",
            "/rpc",
            headers={"cookie": f"{SESSION_COOKIE_NAME}={token}"},
            body_chunks=[me_req],
        )
        assert orjson.loads(cookie_body)["result"]["username"] == "alex"
        assert scope_cookie["session_data"].user_id > 0

        # 4. Невалидный токен отсекается до гостя
        _, _, bad_body, scope_bad = await call_rsgi_http(
            app,
            "POST",
            "/rpc",
            headers={"authorization": "Bearer invalid_token_xyz"},
            body_chunks=[me_req],
        )
        assert orjson.loads(bad_body)["result"]["is_guest"] is True
        assert scope_bad["session_data"].is_guest is True

    @pytest.mark.asyncio
    async def test_websocket_live_login_notify_and_logout(self, app: PyFerroApp) -> None:
        # Выдадим гостю право 'public.catalog', чтобы убедиться, что auth.logout сохраняет права гостя
        app._update_guest_permissions(frozenset({"public.catalog"}))

        # Регистрируем бизнес-метод, который пушит уведомление клиенту и требует право 'orders.list'
        class orders:
            @app.router.rpc_method
            async def list(session: Session) -> list[str]:
                await session.notify("orders.loading", {"progress": 100})
                return [f"order_for_{session.data.username}"]

        incoming = [
            # Шаг 1: Heartbeat ping
            make_ws_message("ping"),
            # Шаг 2: Попытка вызвать orders.list гостем -> ошибка -32001
            make_ws_message(
                orjson.dumps({"jsonrpc": "2.0", "method": "orders.list", "id": 1}).decode()
            ),
            # Шаг 3: Вход через auth.login прямо в живом соединении
            make_ws_message(
                orjson.dumps({
                    "jsonrpc": "2.0",
                    "method": "auth.login",
                    "params": {"username": "alex", "password": "Pass123!"},
                    "id": 2,
                }).decode()
            ),
            # Шаг 4: Повторный вызов orders.list в том же сокете -> теперь успешно + пуш notify!
            make_ws_message(
                orjson.dumps({"jsonrpc": "2.0", "method": "orders.list", "id": 3}).decode()
            ),
            # Шаг 5: Выход auth.logout и закрытие сокета
            make_ws_message(
                orjson.dumps({"jsonrpc": "2.0", "method": "auth.logout", "id": 4}).decode()
            ),
            make_ws_close(),
        ]

        proto = MockRSGIWebsocketProtocol(incoming)
        scope = MockRSGIScope(proto="websocket", path="/ws")
        await app(scope, proto)

        assert proto.accepted is True
        sent_frames = proto.transport.sent_messages
        assert sent_frames[0] == "pong"

        # Ответ на шаг 2: гость получил Unauthorized (-32001)
        err_frame = orjson.loads(sent_frames[1])
        assert err_frame["id"] == 1
        assert err_frame["error"]["code"] == -32001

        # Ответ на шаг 3: успешный логин
        login_frame = orjson.loads(sent_frames[2])
        assert login_frame["id"] == 2
        assert login_frame["result"]["user"]["username"] == "alex"

        # Ответы на шаг 4: сначала пришло push-уведомление orders.loading, затем результат orders.list
        notif_frame = orjson.loads(sent_frames[3])
        assert notif_frame == {
            "jsonrpc": "2.0",
            "method": "orders.loading",
            "params": {"progress": 100},
        }

        orders_frame = orjson.loads(sent_frames[4])
        assert orders_frame == {"jsonrpc": "2.0", "result": ["order_for_alex"], "id": 3}

        # Ответ на шаг 5: выход вернул сессию в состояние гостя с сохранением прав гостя
        logout_frame = orjson.loads(sent_frames[5])
        assert logout_frame["result"]["user"]["is_guest"] is True
        assert logout_frame["result"]["user"]["permissions"] == ["public.catalog"]
        assert scope["session_data"].is_guest is True
        assert scope["session_data"].permissions == frozenset({"public.catalog"})

    @pytest.mark.asyncio
    async def test_websocket_invalid_path_rejected_before_accept(self, app: PyFerroApp) -> None:
        proto = MockRSGIWebsocketProtocol([])
        scope = MockRSGIScope(proto="websocket", path="/wrong_ws_path")
        await app(scope, proto)

        assert proto.accepted is False
        assert proto.close_code == WsCloseCode.POLICY_VIOLATION

    @pytest.mark.asyncio
    async def test_websocket_atomic_rpc_sends_response_before_disconnect_and_stream_catches_errors(
        self, app: PyFerroApp
    ) -> None:
        class stream_test:
            @app.router.rpc_method(public=True)
            async def boom_stream():
                yield {"step": 1}
                raise RuntimeError("Неожиданная авария в генераторе")

            @app.router.rpc_method(public=True)
            async def self_disconnect(session: Session) -> dict[str, str]:
                # Имитируем ситуацию, когда прямо во время выполнения атомарного RPC запрошен дисконнект
                await session.request_disconnect(WsCloseCode.POLICY_VIOLATION)
                return {"status": "completed_before_close"}

        incoming = [
            make_ws_message(
                orjson.dumps({"jsonrpc": "2.0", "method": "stream_test.boom_stream", "id": 10}).decode()
            ),
            make_ws_message(
                orjson.dumps({"jsonrpc": "2.0", "method": "stream_test.self_disconnect", "id": 11}).decode()
            ),
        ]

        proto = MockRSGIWebsocketProtocol(incoming)
        scope = MockRSGIScope(proto="websocket", path="/ws")
        await app(scope, proto)

        frames = [orjson.loads(m) for m in proto.transport.sent_messages]
        assert frames == [
            {"jsonrpc": "2.0", "result": {"step": 1}, "id": 10},
            {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": "Внутренняя ошибка сервера"},
                "id": 10,
            },
            {"jsonrpc": "2.0", "result": {"status": "completed_before_close"}, "id": 11},
        ]
        assert proto.close_code == WsCloseCode.POLICY_VIOLATION


class TestCoreFileSubsystem:
    """Проверка двухфазной загрузки файлов, приватных JWT-токенов и заголовка Nginx `X-Accel-Redirect`."""

    @pytest.mark.asyncio
    async def test_two_phase_upload_download_and_nginx_accel(self, app: PyFerroApp) -> None:
        # 1. Логинимся и получаем JWT токен
        login_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "auth.login",
            "params": {"username": "alex", "password": "Pass123!"},
            "id": 1,
        })
        _, _, login_body, _ = await call_rsgi_http(app, "POST", "/rpc", body_chunks=[login_req])
        token = orjson.loads(login_body)["result"]["token"]
        auth_headers = {"authorization": f"Bearer {token}"}

        # 2. Фаза 1: files.init_upload
        init_req = orjson.dumps({"jsonrpc": "2.0", "method": "files.init_upload", "id": 2})
        _, _, init_body, _ = await call_rsgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[init_req]
        )
        folder_hash = orjson.loads(init_body)["result"]["folder_hash"]

        # 3. Потоковая закачка файла чанками через POST /upload
        file_content = b"Hello PyFerro 2.0 Streaming File Content!"
        upload_headers = dict(auth_headers)
        upload_headers["content-type"] = "text/plain"
        up_status, _, up_body, _ = await call_rsgi_http(
            app,
            "POST",
            "/upload",
            query_string=f"folder={folder_hash}&filename=report.txt",
            headers=upload_headers,
            body_chunks=[file_content[:15], file_content[15:]],
        )
        assert up_status == 200
        assert orjson.loads(up_body)["file"]["size"] == len(file_content)

        # 4. Фаза 2: files.commit (делаем файл приватным is_public=False)
        commit_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "files.commit",
            "params": {"folder_hash": folder_hash, "is_public": False},
            "id": 3,
        })
        _, _, commit_body, _ = await call_rsgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[commit_req]
        )
        committed_file = orjson.loads(commit_body)["result"]["files"][0]
        file_id = committed_file["id"]
        file_url = committed_file["url"]

        # 5. Гость без токена получает 403 при попытке скачать приватный файл
        dl_status_guest, _, _, _ = await call_rsgi_http(app, "GET", file_url)
        assert dl_status_guest == 403

        # 6. Получаем целевой JWT-токен скачивания через files.get_download_token
        tok_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "files.get_download_token",
            "params": {"file_id": file_id},
            "id": 4,
        })
        _, _, tok_body, _ = await call_rsgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[tok_req]
        )
        dl_token = orjson.loads(tok_body)["result"]["token"]

        # 7. Гость с целевым файловым JWT-токеном успешно скачивает файл (с заголовками защиты от XSS)
        dl_status_ok, dl_headers_ok, dl_bytes, _ = await call_rsgi_http(
            app, "GET", file_url, query_string=f"token={dl_token}"
        )
        assert dl_status_ok == 200
        assert dl_bytes == file_content
        assert dl_headers_ok["x-content-type-options"] == "nosniff"
        assert dl_headers_ok["content-security-policy"] == "default-src 'none'; sandbox"
        assert dl_headers_ok["referrer-policy"] == "no-referrer"

        # 8. Проверка режима Nginx X-Accel-Redirect
        app.file_storage.nginx_internal_prefix = "/_internal_storage"
        accel_status, accel_headers, accel_body, _ = await call_rsgi_http(
            app, "GET", file_url, query_string=f"token={dl_token}"
        )
        assert accel_status == 200
        assert accel_headers["x-accel-redirect"] == f"/_internal_storage/{folder_hash}/report.txt"
        assert accel_headers["x-content-type-options"] == "nosniff"
        assert accel_headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert accel_headers["referrer-policy"] == "no-referrer"
        assert accel_body == b""

        # 9. Удаление файла через files.delete
        del_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "files.delete",
            "params": {"file_id": file_id},
            "id": 5,
        })
        _, _, del_body, _ = await call_rsgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[del_req]
        )
        assert orjson.loads(del_body)["result"] == {"deleted": True, "id": file_id}

    @pytest.mark.asyncio
    async def test_upload_fail_fast_content_length_and_slowloris_protection(
        self, app: PyFerroApp
    ) -> None:
        import asyncio

        # Логинимся и создаем транзакцию загрузки
        login_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "auth.login",
            "params": {"username": "alex", "password": "Pass123!"},
            "id": 1,
        })
        _, _, login_body, _ = await call_rsgi_http(app, "POST", "/rpc", body_chunks=[login_req])
        token = orjson.loads(login_body)["result"]["token"]
        auth_headers = {"authorization": f"Bearer {token}"}

        init_req = orjson.dumps({"jsonrpc": "2.0", "method": "files.init_upload", "id": 2})
        _, _, init_body, _ = await call_rsgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[init_req]
        )
        folder_hash = orjson.loads(init_body)["result"]["folder_hash"]
        tx = app.file_storage.get_transaction(folder_hash)
        assert tx is not None

        # Протокол-ловушка: если сервер попытается прочитать хотя бы 1 байт тела — тест упадет
        class PoisonHTTPProtocol:
            def __init__(self) -> None:
                self.status: int | None = None
                self.body: bytes = b""

            def __aiter__(self) -> Any:
                raise AssertionError("Fail-Fast нарушен: начато чтение потока тела!")

            def response_bytes(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
                self.status = status
                self.body = body

        # 1. Fail-Fast 401: гость отсекается ДО чтения потока тела
        poison_guest = PoisonHTTPProtocol()
        await app(
            MockRSGIScope(
                proto="http",
                method="POST",
                path="/upload",
                query_string=f"folder={folder_hash}&filename=hack.bin",
            ),
            poison_guest,
        )
        assert poison_guest.status == 401
        assert list(tx.tmp_dir.iterdir()) == []

        # 2. Fail-Fast 413 по Content-Length: отсекается на стадии заголовков ДО чтения потока
        app.file_storage.max_file_size = 100
        poison_oversize = PoisonHTTPProtocol()
        await app(
            MockRSGIScope(
                proto="http",
                method="POST",
                path="/upload",
                query_string=f"folder={folder_hash}&filename=huge.bin",
                headers={**auth_headers, "content-length": "500"},
            ),
            poison_oversize,
        )
        assert poison_oversize.status == 413
        assert list(tx.tmp_dir.iterdir()) == []

        # 3. Превышение лимита во время стриминга без Content-Length -> 413 и очистка временного файла
        stream_status, _, _, _ = await call_rsgi_http(
            app,
            "POST",
            "/upload",
            query_string=f"folder={folder_hash}&filename=stream_too_big.bin",
            headers=auth_headers,
            body_chunks=[b"x" * 60, b"y" * 60],
        )
        assert stream_status == 413
        assert list(tx.tmp_dir.iterdir()) == []

        # 4. Защита от Slowloris: зависание между чанками дольше chunk_timeout -> 408 и очистка файла
        app.file_storage.chunk_timeout = 0.03

        class SlowlorisHTTPProtocol:
            def __init__(self) -> None:
                self.status: int | None = None
                self.body: bytes = b""

            async def __aiter__(self) -> Any:
                yield b"first_chunk"
                await asyncio.sleep(0.15)
                yield b"second_chunk_too_late"

            def response_bytes(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
                self.status = status
                self.body = body

        slow_proto = SlowlorisHTTPProtocol()
        await app(
            MockRSGIScope(
                proto="http",
                method="POST",
                path="/upload",
                query_string=f"folder={folder_hash}&filename=slow.bin",
                headers=auth_headers,
            ),
            slow_proto,
        )
        assert slow_proto.status == 408
        assert list(tx.tmp_dir.iterdir()) == []
