"""
Модульные и интеграционные тесты Этапа 4:
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
from pyferro2.core import SESSION_COOKIE_NAME, Session, SessionData, USER_ROLE, admRole
from pyferro2.db import Database
from pyferro2.files import FileStorage
from pyferro2.server import PyFerroApp, TokenManager, extract_token_from_scope


async def call_asgi_http(
    app: PyFerroApp,
    method: str,
    path: str,
    *,
    query_string: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
    body_chunks: list[bytes] | None = None,
) -> tuple[int, dict[str, str], bytes, dict[str, Any]]:
    """Вспомогательный клиент для вызова HTTP-маршрутов напрямую через ASGI-интерфейс."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string.encode("latin-1"),
        "headers": headers or [],
    }
    chunks = list(body_chunks or [b""])
    idx = 0

    async def receive() -> dict[str, Any]:
        nonlocal idx
        if idx < len(chunks):
            chunk = chunks[idx]
            idx += 1
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": idx < len(chunks),
            }
        return {"type": "http.disconnect"}

    status_code = 500
    resp_headers: dict[str, str] = {}
    resp_body: list[bytes] = []

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = message["status"]
            for k, v in message.get("headers", []):
                resp_headers[k.decode("latin-1").lower()] = v.decode("latin-1")
        elif message["type"] == "http.response.body":
            resp_body.append(message.get("body", b""))

    await app(scope, receive, send)
    return status_code, resp_headers, b"".join(resp_body), scope


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
        scope = {
            "headers": [
                (b"cookie", f"{SESSION_COOKIE_NAME}=cookie_tok".encode("latin-1")),
                (b"authorization", b"Bearer bearer_tok"),
            ],
            "query_string": b"token=query_tok",
        }
        # Приоритет 1: Authorization Bearer
        assert extract_token_from_scope(scope) == "bearer_tok"

        # Приоритет 2: Кука ferro_session
        scope["headers"] = [(b"cookie", f"{SESSION_COOKIE_NAME}=cookie_tok".encode("latin-1"))]
        assert extract_token_from_scope(scope) == "cookie_tok"

        # Приоритет 3: Query ?token=
        scope["headers"] = []
        assert extract_token_from_scope(scope) == "query_tok"


class TestHttpAndWebSocketTransport:
    """Проверка авторизации по куке, по Bearer и живого WebSocket-соединения."""

    @pytest.mark.asyncio
    async def test_http_rpc_login_bearer_and_cookie(self, app: PyFerroApp) -> None:
        # 1. Вход через HTTP POST /rpc -> получаем JWT токен
        login_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "auth.login",
            "params": {"username": "alex", "password": "Pass123!"},
            "id": 1,
        })
        status, _, body, _ = await call_asgi_http(app, "POST", "/rpc", body_chunks=[login_req])
        assert status == 200
        login_res = orjson.loads(body)["result"]
        token = login_res["token"]
        assert login_res["user"]["username"] == "alex"

        # 2. Запрос auth.me по заголовку Authorization: Bearer <token>
        me_req = orjson.dumps({"jsonrpc": "2.0", "method": "auth.me", "id": 2})
        _, _, me_body, scope_bearer = await call_asgi_http(
            app,
            "POST",
            "/rpc",
            headers=[(b"authorization", f"Bearer {token}".encode("latin-1"))],
            body_chunks=[me_req],
        )
        assert orjson.loads(me_body)["result"]["username"] == "alex"
        assert scope_bearer["session_data"].username == "alex"

        # 3. Запрос auth.me по куке ferro_session
        _, _, cookie_body, scope_cookie = await call_asgi_http(
            app,
            "POST",
            "/rpc",
            headers=[(b"cookie", f"{SESSION_COOKIE_NAME}={token}".encode("latin-1"))],
            body_chunks=[me_req],
        )
        assert orjson.loads(cookie_body)["result"]["username"] == "alex"
        assert scope_cookie["session_data"].user_id == 1

        # 4. Невалидный токен отсекается до гостя
        _, _, bad_body, scope_bad = await call_asgi_http(
            app,
            "POST",
            "/rpc",
            headers=[(b"authorization", b"Bearer invalid_token_xyz")],
            body_chunks=[me_req],
        )
        assert orjson.loads(bad_body)["result"]["is_guest"] is True
        assert scope_bad["session_data"].is_guest is True

    @pytest.mark.asyncio
    async def test_websocket_live_login_notify_and_logout(self, app: PyFerroApp) -> None:
        # Регистрируем бизнес-метод, который пушит уведомление клиенту и требует право 'orders.list'
        class orders:
            @app.router.rpc_method
            async def list(session: Session) -> list[str]:
                await session.notify("orders.loading", {"progress": 100})
                return [f"order_for_{session.data.username}"]

        incoming: deque[dict[str, Any]] = deque([
            {"type": "websocket.connect"},
            # Шаг 1: Heartbeat ping
            {"type": "websocket.receive", "text": "ping"},
            # Шаг 2: Попытка вызвать orders.list гостем -> ошибка -32001
            {
                "type": "websocket.receive",
                "text": orjson.dumps({"jsonrpc": "2.0", "method": "orders.list", "id": 1}).decode(),
            },
            # Шаг 3: Вход через auth.login прямо в живом соединении
            {
                "type": "websocket.receive",
                "text": orjson.dumps({
                    "jsonrpc": "2.0",
                    "method": "auth.login",
                    "params": {"username": "alex", "password": "Pass123!"},
                    "id": 2,
                }).decode(),
            },
            # Шаг 4: Повторный вызов orders.list в том же сокете -> теперь успешно + пуш notify!
            {
                "type": "websocket.receive",
                "text": orjson.dumps({"jsonrpc": "2.0", "method": "orders.list", "id": 3}).decode(),
            },
            # Шаг 5: Выход auth.logout и закрытие сокета
            {
                "type": "websocket.receive",
                "text": orjson.dumps({"jsonrpc": "2.0", "method": "auth.logout", "id": 4}).decode(),
            },
            {"type": "websocket.disconnect"},
        ])

        sent_frames: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return incoming.popleft()

        async def send(msg: dict[str, Any]) -> None:
            sent_frames.append(msg)

        scope: dict[str, Any] = {"type": "websocket", "path": "/ws", "headers": []}
        await app(scope, receive, send)

        assert sent_frames[0] == {"type": "websocket.accept"}
        assert sent_frames[1] == {"type": "websocket.send", "text": "pong"}

        # Ответ на шаг 2: гость получил Unauthorized (-32001)
        err_frame = orjson.loads(sent_frames[2]["text"])
        assert err_frame["id"] == 1
        assert err_frame["error"]["code"] == -32001

        # Ответ на шаг 3: успешный логин
        login_frame = orjson.loads(sent_frames[3]["text"])
        assert login_frame["id"] == 2
        assert login_frame["result"]["user"]["username"] == "alex"

        # Ответы на шаг 4: сначала пришло push-уведомление orders.loading, затем результат orders.list
        notif_frame = orjson.loads(sent_frames[4]["text"])
        assert notif_frame == {"jsonrpc": "2.0", "method": "orders.loading", "params": {"progress": 100}}

        orders_frame = orjson.loads(sent_frames[5]["text"])
        assert orders_frame == {"jsonrpc": "2.0", "result": ["order_for_alex"], "id": 3}

        # Ответ на шаг 5: выход вернул сессию в состояние гостя
        logout_frame = orjson.loads(sent_frames[6]["text"])
        assert logout_frame["result"]["user"]["is_guest"] is True
        assert scope["session_data"].is_guest is True


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
        _, _, login_body, _ = await call_asgi_http(app, "POST", "/rpc", body_chunks=[login_req])
        token = orjson.loads(login_body)["result"]["token"]
        auth_headers = [(b"authorization", f"Bearer {token}".encode("latin-1"))]

        # 2. Фаза 1: files.init_upload
        init_req = orjson.dumps({"jsonrpc": "2.0", "method": "files.init_upload", "id": 2})
        _, _, init_body, _ = await call_asgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[init_req]
        )
        folder_hash = orjson.loads(init_body)["result"]["folder_hash"]

        # 3. Потоковая закачка файла чанками через POST /upload
        file_content = b"Hello PyFerro 2.0 Streaming File Content!"
        up_status, _, up_body, _ = await call_asgi_http(
            app,
            "POST",
            "/upload",
            query_string=f"folder={folder_hash}&filename=report.txt",
            headers=auth_headers + [(b"content-type", b"text/plain")],
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
        _, _, commit_body, _ = await call_asgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[commit_req]
        )
        committed_file = orjson.loads(commit_body)["result"]["files"][0]
        file_id = committed_file["id"]
        file_url = committed_file["url"]

        # 5. Гость без токена получает 403 при попытке скачать приватный файл
        dl_status_guest, _, _, _ = await call_asgi_http(app, "GET", file_url)
        assert dl_status_guest == 403

        # 6. Получаем целевой JWT-токен скачивания через files.get_download_token
        tok_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "files.get_download_token",
            "params": {"file_id": file_id},
            "id": 4,
        })
        _, _, tok_body, _ = await call_asgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[tok_req]
        )
        dl_token = orjson.loads(tok_body)["result"]["token"]

        # 7. Гость с целевым файловым JWT-токеном успешно скачивает файл
        dl_status_ok, _, dl_bytes, _ = await call_asgi_http(
            app, "GET", file_url, query_string=f"token={dl_token}"
        )
        assert dl_status_ok == 200
        assert dl_bytes == file_content

        # 8. Проверка режима Nginx X-Accel-Redirect
        app.file_storage.nginx_internal_prefix = "/_internal_storage"
        accel_status, accel_headers, accel_body, _ = await call_asgi_http(
            app, "GET", file_url, query_string=f"token={dl_token}"
        )
        assert accel_status == 200
        assert accel_headers["x-accel-redirect"] == f"/_internal_storage/{folder_hash}/report.txt"
        assert accel_body == b""

        # 9. Удаление файла через files.delete
        del_req = orjson.dumps({
            "jsonrpc": "2.0",
            "method": "files.delete",
            "params": {"file_id": file_id},
            "id": 5,
        })
        _, _, del_body, _ = await call_asgi_http(
            app, "POST", "/rpc", headers=auth_headers, body_chunks=[del_req]
        )
        assert orjson.loads(del_body)["result"] == {"deleted": True, "id": file_id}
