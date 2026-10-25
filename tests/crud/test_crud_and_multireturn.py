"""
Модульные и интеграционные тесты Этапа 5:
- Мультиретурн (`async def ... yield`) по WebSocket и в роутере
- Корректный дисконнект (`request_disconnect`) при смене прав: ожидание атомарного `return` и мгновенное закрытие `yield`-стримов
- Единая точечная модель CRUD и RPC (`Article.create`, `Article.read`, `Article.update`, `Article.delete`, `Book.transfer`, `Book.archive`)
- Глобальные (`Плашка.метод`) и построчные (`Плашка.метод_own`) права (включая безопасное поведение `*_own` там, где нет `creator_id`)
- Защита системных ролей (`is_system=True`) от удаления и переименования
- Разграничение разделов админки (`adm_crud`, `adm_users`, `adm_roles`) и матрица прав (включая `guest`).
"""

import asyncio
from collections import deque
from pathlib import Path
from typing import Any

import orjson
import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.auth import ensure_admin_user, seed_system_roles
from pyferro2.core import Session, SessionData, USER_ROLE, WsCloseCode, admRole
from pyferro2.db import Database, RowSecureModel
from pyferro2.files import FileStorage
from pyferro2.rpc import ForbiddenError, UnauthorizedError
from pyferro2.server import (
    MockRSGIScope,
    MockRSGIWebsocketProtocol,
    PyFerroApp,
    call_rsgi_http,
    make_ws_close,
    make_ws_message,
)


class Article(RowSecureModel):
    """Тестовая модель для проверки декларативного CRUD и построчных прав (RLS)."""

    __tablename__ = "pf_test_crud_article"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    internal_secret: Mapped[str] = mapped_column(String(200), default="top-secret", nullable=False)
    status_code_label: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)

    class Crud:
        title = "Статьи блога"
        searchable = ("title",)
        readonly = ("status_code_label",)
        hidden = ("internal_secret",)


@pytest.fixture
async def app(tmp_path: Path) -> PyFerroApp:
    """Создает приложение PyFerroApp с зарегистрированной моделью Article и кастомными Book.* методами."""
    db = Database("sqlite+aiosqlite:///:memory:")
    storage = FileStorage(storage_dir=tmp_path / "storage", tmp_root=tmp_path / "tmp")
    ferro_app = PyFerroApp(
        db=db,
        file_storage=storage,
        secret_key="crud-and-stream-test-secret-key-32b!",
    )
    ferro_app.crud.register(Article)

    class Book:
        @ferro_app.router.rpc_method
        async def transfer(book_id: int) -> dict[str, Any]:
            return {"transferred": book_id}

        @ferro_app.router.rpc_method
        async def archive(book_id: int) -> dict[str, Any]:
            return {"archived": book_id}

    await ferro_app.startup()

    async with db.session() as session:
        await seed_system_roles(session)
        await ensure_admin_user(session, username="root", password="RootPass1!")

    yield ferro_app
    await ferro_app.shutdown()


class TestMultiReturnAndGracefulDisconnect:
    """Проверка мультиретурна (`yield`) и умного дисконнекта сессии при смене прав."""

    @pytest.mark.asyncio
    async def test_multireturn_yield_over_websocket(self, app: PyFerroApp) -> None:
        class feed:
            @app.router.rpc_method(public=True)
            async def countdown(start: int):
                for val in range(start, 0, -1):
                    yield {"tick": val}

        incoming = [
            make_ws_message(
                orjson.dumps({
                    "jsonrpc": "2.0",
                    "method": "feed.countdown",
                    "params": {"start": 3},
                    "id": 77,
                }).decode()
            ),
            make_ws_close(),
        ]
        proto = MockRSGIWebsocketProtocol(incoming)
        scope = MockRSGIScope(proto="websocket", path="/ws")
        await app(scope, proto)

        assert proto.accepted is True
        rpc_payloads = [
            orjson.loads(f) for f in proto.transport.sent_messages
        ]
        assert rpc_payloads == [
            {"jsonrpc": "2.0", "result": {"tick": 3}, "id": 77},
            {"jsonrpc": "2.0", "result": {"tick": 2}, "id": 77},
            {"jsonrpc": "2.0", "result": {"tick": 1}, "id": 77},
        ]

    @pytest.mark.asyncio
    async def test_graceful_disconnect_waits_for_return_rpc_and_cancels_infinite_yield(self) -> None:
        closed_codes: list[int] = []

        async def on_close(code: int) -> None:
            closed_codes.append(code)

        session = Session(
            session_id="sess-graceful",
            data=SessionData(user_id=10, username="ivan", roles=frozenset({USER_ROLE})),
            close=on_close,
        )

        cleanup_called = False

        async def infinite_notification_stream() -> None:
            nonlocal cleanup_called
            try:
                while True:
                    await asyncio.sleep(10)
            finally:
                cleanup_called = True

        stream_task = asyncio.create_task(infinite_notification_stream())
        session.register_stream_task(stream_task)
        await asyncio.sleep(0)

        session.begin_rpc()
        await session.request_disconnect(WsCloseCode.POLICY_VIOLATION)

        await asyncio.sleep(0)
        assert cleanup_called is True
        assert closed_codes == []

        await session.end_rpc()
        assert closed_codes == [WsCloseCode.POLICY_VIOLATION]


class TestCrudEngineAndPermissionsMatrix:
    """Проверка единых точечных методов (`Article.create/read/update/delete`), RLS (`*_own`) и матрицы прав."""

    @pytest.mark.asyncio
    async def test_crud_operations_hidden_readonly_and_system_role_protection(
        self, app: PyFerroApp
    ) -> None:
        admin_session = Session(
            session_id="s-admin",
            data=SessionData(user_id=1, username="root", roles=frozenset({admRole.admin.value})),
        )

        # 1. Создание статьи через прямой точечный метод Article.create
        created = await app.router.call(
            "Article.create",
            admin_session,
            {"data": {"title": "PyFerro 2 Release", "internal_secret": "hack"}},
            db=app.db,
        )
        assert created["id"] == 1
        assert created["title"] == "PyFerro 2 Release"
        assert created["creator_id"] == 1
        assert "internal_secret" not in created

        # 2. Попытка изменить readonly-поле 'status_code_label' блокируется
        with pytest.raises(ForbiddenError, match="Поля только для чтения"):
            await app.router.call(
                "Article.update",
                admin_session,
                {"id": 1, "data": {"status_code_label": "published"}},
                db=app.db,
            )

        # 3. Защита системных ролей (is_system=True): нельзя удалить или переименовать роль 'admin'
        roles_list = await app.router.call(
            "Role.read",
            admin_session,
            {"search": "admin"},
            db=app.db,
        )
        admin_role_id = next(r["id"] for r in roles_list["items"] if r["name"] == "admin")

        with pytest.raises(ForbiddenError, match="Запрещено переименовывать системную роль"):
            await app.router.call(
                "Role.update",
                admin_session,
                {"id": admin_role_id, "data": {"name": "super_root"}},
                db=app.db,
            )

        with pytest.raises(ForbiddenError, match="Запрещено удалять системную роль"):
            await app.router.call(
                "Role.delete",
                admin_session,
                {"id": admin_role_id},
                db=app.db,
            )

    @pytest.mark.asyncio
    async def test_row_level_security_own_vs_global_and_custom_rpc(
        self, app: PyFerroApp
    ) -> None:
        # 1. Пользователь с ролью adm_users создает двух авторов: user_a и user_b
        users_mgr = Session(
            session_id="s-umgr",
            data=SessionData(
                user_id=2,
                username="hr_admin",
                roles=frozenset({admRole.adm_users.value}),
            ),
        )
        await app.router.call(
            "admin.create_user",
            users_mgr,
            {"username": "author_a", "password": "PassA!"},
            db=app.db,
        )
        await app.router.call(
            "admin.create_user",
            users_mgr,
            {"username": "author_b", "password": "PassB!"},
            db=app.db,
        )

        # Менеджер пользователей не имеет доступа к разделу ролей (adm_roles)
        with pytest.raises(ForbiddenError):
            await app.router.call(
                "admin.set_role_permissions",
                users_mgr,
                {"role_name": "user", "permissions": ["Article.read"]},
                db=app.db,
            )

        # 2. Администратор ролей (adm_roles) проверяет единый каталог методов и настраивает матрицу прав:
        roles_mgr = Session(
            session_id="s-rmgr",
            data=SessionData(
                user_id=3,
                username="sec_admin",
                roles=frozenset({admRole.adm_roles.value}),
            ),
        )
        matrix = await app.router.call("admin.get_permissions_matrix", roles_mgr, db=app.db)
        assert "Article.create" in matrix["methods"]
        assert "Article.read" in matrix["methods"]
        assert "Book.transfer" in matrix["methods"]
        assert "Book.archive" in matrix["methods"]
        # Системные таблицы User и Role не засоряют матрицу бизнес-прав
        assert "User.read" not in matrix["methods"]
        assert "Role.read" not in matrix["methods"]

        # Даже если админ включил галочку "только свои" на Article.create_own и Book.transfer_own —
        # всё работает без ошибок!
        await app.router.call(
            "admin.set_role_permissions",
            roles_mgr,
            {
                "role_name": "user",
                "permissions": [
                    "Article.create_own",
                    "Article.read_own",
                    "Article.update_own",
                    "Article.delete_own",
                    "Book.transfer_own",
                ],
            },
            db=app.db,
        )
        await app.router.call(
            "admin.set_role_permissions",
            roles_mgr,
            {"role_name": "guest", "permissions": ["Article.read"]},
            db=app.db,
        )

        # 3. Логинимся за author_a и author_b и создаем по статье
        sess_a = Session(session_id="sa")
        await app.router.call(
            "auth.login", sess_a, {"username": "author_a", "password": "PassA!"}, db=app.db
        )
        art_a = await app.router.call(
            "Article.create", sess_a, {"data": {"title": "Статья Автора А"}}, db=app.db
        )
        # Кастомный Book.transfer проходит по праву Book.transfer_own без ошибок
        transfer_res = await app.router.call("Book.transfer", sess_a, {"book_id": 42})
        assert transfer_res == {"transferred": 42}
        # А на Book.archive права нет
        with pytest.raises(ForbiddenError):
            await app.router.call("Book.archive", sess_a, {"book_id": 42})

        sess_b = Session(session_id="sb")
        await app.router.call(
            "auth.login", sess_b, {"username": "author_b", "password": "PassB!"}, db=app.db
        )
        art_b = await app.router.call(
            "Article.create", sess_b, {"data": {"title": "Статья Автора Б"}}, db=app.db
        )

        # 4. Проверка RLS: author_a в списке видит ТОЛЬКО свою статью и не может менять статью author_b
        list_for_a = await app.router.call("Article.read", sess_a, {}, db=app.db)
        assert list_for_a["total"] == 1
        assert list_for_a["items"][0]["id"] == art_a["id"]

        with pytest.raises(ForbiddenError, match="Нет прав на редактирование чужой записи"):
            await app.router.call(
                "Article.update",
                sess_a,
                {"id": art_b["id"], "data": {"title": "Взлом"}},
                db=app.db,
            )

        # Свою статью author_a редактирует успешно
        updated_a = await app.router.call(
            "Article.update",
            sess_a,
            {"id": art_a["id"], "data": {"title": "Обновленная Статья А"}},
            db=app.db,
        )
        assert updated_a["title"] == "Обновленная Статья А"

        # 5. Проверка гостя: благодаря обновленному кэшу guest_session_data гость может читать статьи, но не удалять
        guest_sess = Session(session_id="s-guest", data=app.guest_session_data)
        guest_list = await app.router.call("Article.read", guest_sess, {}, db=app.db)
        assert guest_list["total"] == 2

        with pytest.raises(UnauthorizedError):
            await app.router.call(
                "Article.delete", guest_sess, {"id": art_a["id"]}, db=app.db
            )

    @pytest.mark.asyncio
    async def test_pyferro_admin_spa_route_and_free_app_admin(
        self, app: PyFerroApp
    ) -> None:
        """Проверяет, что панель раздается строго на /pyferro_admin, а /admin свободен для приложения."""
        status, _, body, _ = await call_rsgi_http(app, "GET", "/pyferro_admin")
        assert status == 200
        html_body = body.decode("utf-8")
        assert "/pyferro_admin/assets/" in html_body

        # При этом маршрут /admin свободен (404 у ядра, не перехватывается фреймворком)
        app_status, _, _, _ = await call_rsgi_http(app, "GET", "/admin")
        assert app_status == 404
