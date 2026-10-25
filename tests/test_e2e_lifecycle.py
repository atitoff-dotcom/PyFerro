"""
Сквозной интеграционный тест полного жизненного цикла приложения на PyFerro 2.0 (Этап 7).

Проверяет работу всех подсистем вместе в едином сценарии:
1. Модель `Book(RowSecureModel)` с `class Crud:` и кастомными методами `Book.transfer` и `Book.live_feed` (`yield`) прямо внутри класса модели (без `name=...`).
2. Подключение Гостя -> отказ доступа -> выдача права `Book.read` роли `guest` -> чтение витрины Гостем.
3. Создание пользователей (`adm_users`), настройка прав роли `user` (`Book.create`, `Book.read_own`, `Book.transfer_own`).
4. Двухфазная потоковая загрузка файла обложки (`files.init_upload` -> `POST /upload` -> `files.commit`).
5. Проверка `session_data.is_own_only("Book.transfer")` для своей и чужой книги.
6. Запуск долгого мультиретурн-стрима (`yield`) по WebSocket и мгновенный корректный дисконнект при смене ролей пользователя.
"""

import asyncio
from collections import deque
from pathlib import Path
from typing import Any

import orjson
import pytest
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.auth import ensure_admin_user, seed_system_roles
from pyferro2.core import Session, SessionData, WsCloseCode, admRole, unpack_tabular
from pyferro2.db import Database, RowSecureModel
from pyferro2.files import FileStorage
from pyferro2.rpc import ForbiddenError, UnauthorizedError, rpc_method
from pyferro2.server import (
    MockRSGIScope,
    MockRSGIWebsocketProtocol,
    PyFerroApp,
    call_rsgi_http,
    make_ws_message,
)


class Book(RowSecureModel):
    """Модель книги с табличным CRUD и собственными бизнес-методами."""

    __tablename__ = "pf_e2e_books"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    cover_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    class Crud:
        title = "Каталог книг"
        searchable = ("title",)

    @rpc_method
    async def transfer(
        book_id: int,
        new_owner_id: int,
        session_data: SessionData,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Кастомный бизнес-метод `Book.transfer` с поддержкой галочки «Только свои»."""
        book = (
            await db.execute(select(Book).where(Book.id == book_id))
        ).scalar_one_or_none()
        if book is None:
            raise ForbiddenError("Книга не найдена")

        if session_data.is_own_only("Book.transfer") and book.creator_id != session_data.user_id:
            raise ForbiddenError("Вы можете передавать только собственные книги")

        book.creator_id = new_owner_id
        await db.commit()
        return {"book_id": book.id, "new_owner_id": book.creator_id}

    @rpc_method
    async def live_feed(limit: int = 2):
        """Мультиретурн-генератор `Book.live_feed` (`yield`)."""
        for step in range(1, limit + 1):
            yield {"event": "book_pulse", "step": step}


@pytest.mark.asyncio
async def test_full_application_lifecycle(tmp_path: Path) -> None:
    db = Database("sqlite+aiosqlite:///:memory:")
    storage = FileStorage(
        storage_dir=tmp_path / "storage",
        tmp_root=tmp_path / "tmp",
        nginx_internal_prefix="/internal_files",
    )
    app = PyFerroApp(
        db=db,
        file_storage=storage,
        secret_key="e2e-full-lifecycle-secret-key-32bytes!",
    )
    # Регистрация модели Book автоматически регистрирует:
    # Book.create, Book.read, Book.update, Book.delete + кастомные Book.transfer и Book.live_feed!
    app.crud.register(Book)
    await app.startup()

    async with db.session() as s:
        await seed_system_roles(s)
        await ensure_admin_user(s, username="root", password="RootPassword1!")

    try:
        # ─── Шаг 1. Гость пытается прочитать каталог до выдачи прав -> Unauthorized ───
        guest_session = Session(session_id="guest-1", data=app.guest_session_data)
        with pytest.raises(UnauthorizedError):
            await app.router.call("Book.read", guest_session, {}, db=app.db)

        # ─── Шаг 2. Главный админ логинится и проверяет матрицу прав ───
        admin_session = Session(session_id="root-1")
        login_res = await app.router.call(
            "auth.login",
            admin_session,
            {"username": "root", "password": "RootPassword1!"},
            db=app.db,
        )
        assert login_res["user"]["is_admin"] is True

        matrix = await app.router.call("admin.get_permissions_matrix", admin_session, db=app.db)
        for expected_method in (
            "Book.create",
            "Book.read",
            "Book.update",
            "Book.delete",
            "Book.transfer",
            "Book.live_feed",
        ):
            assert expected_method in matrix["methods"]

        # Выдаем гостю Book.read, а роли user — создание, чтение/передачу только своих книг и стрим
        await app.router.call(
            "admin.set_role_permissions",
            admin_session,
            {"role_name": "guest", "permissions": ["Book.read"]},
            db=app.db,
        )
        await app.router.call(
            "admin.set_role_permissions",
            admin_session,
            {
                "role_name": "user",
                "permissions": [
                    "Book.create",
                    "Book.read_own",
                    "Book.transfer_own",
                    "Book.live_feed",
                ],
            },
            db=app.db,
        )

        # ─── Шаг 3. Создаются два пользователя: alice и bob ───
        alice_info = await app.router.call(
            "admin.create_user",
            admin_session,
            {"username": "alice", "password": "AlicePass1!"},
            db=app.db,
        )
        bob_info = await app.router.call(
            "admin.create_user",
            admin_session,
            {"username": "bob", "password": "BobPass1!"},
            db=app.db,
        )

        # ─── Шаг 4. Alice входит, загружает файл обложки в 2 фазы и создает книгу ───
        alice_sess = Session(session_id="alice-1")
        alice_login = await app.router.call(
            "auth.login",
            alice_sess,
            {"username": "alice", "password": "AlicePass1!"},
            db=app.db,
        )
        alice_token = alice_login["token"]

        init_up = await app.router.call("files.init_upload", alice_sess)
        folder_hash = init_up["folder_hash"]

        # Потоковая HTTP-загрузка файла обложки
        up_status, _, _, _ = await call_rsgi_http(
            app,
            "POST",
            "/upload",
            query_string=f"folder={folder_hash}&filename=cover.png",
            headers={"authorization": f"Bearer {alice_token}"},
            body_chunks=[b"COVER_IMAGE_BYTES"],
        )
        assert up_status == 200

        committed = await app.router.call(
            "files.commit",
            alice_sess,
            {"folder_hash": folder_hash, "is_public": True},
            db=app.db,
        )
        cover_id = committed["files"][0]["id"]

        book_alice = await app.router.call(
            "Book.create",
            alice_sess,
            {"data": {"title": "Архитектура PyFerro 2", "cover_file_id": cover_id}},
            db=app.db,
        )
        assert book_alice["creator_id"] == alice_info["id"]

        # Bob тоже создает свою книгу
        bob_sess = Session(session_id="bob-1")
        await app.router.call(
            "auth.login",
            bob_sess,
            {"username": "bob", "password": "BobPass1!"},
            db=app.db,
        )
        book_bob = await app.router.call(
            "Book.create",
            bob_sess,
            {"data": {"title": "Книга Боба"}},
            db=app.db,
        )

        # ─── Шаг 5. Гость видит обе книги (включая сжатый режим $tabular), а Alice (по Book.read_own) — только свою ───
        guest_session = Session(session_id="guest-2", data=app.guest_session_data)
        guest_list = await app.router.call("Book.read", guest_session, {}, db=app.db)
        assert guest_list["total"] == 2

        guest_tabular = await app.router.call(
            "Book.read", guest_session, {"tabular": True}, db=app.db
        )
        assert guest_tabular["$tabular"] is True
        assert "title" in guest_tabular["fields"]
        assert len(guest_tabular["rows"]) == 2
        unpacked = unpack_tabular(guest_tabular)
        assert len(unpacked["items"]) == 2
        assert unpacked["items"][0]["title"] == "Книга Боба"

        alice_list = await app.router.call("Book.read", alice_sess, {}, db=app.db)
        assert alice_list["total"] == 1
        assert alice_list["items"][0]["id"] == book_alice["id"]

        # Alice пытается передать чужую книгу Боба -> блокируется через is_own_only("Book.transfer")
        with pytest.raises(ForbiddenError, match="только собственные книги"):
            await app.router.call(
                "Book.transfer",
                alice_sess,
                {"book_id": book_bob["id"], "new_owner_id": alice_info["id"]},
                db=app.db,
            )

        # А свою книгу Alice успешно передает Бобу
        transfer_ok = await app.router.call(
            "Book.transfer",
            alice_sess,
            {"book_id": book_alice["id"], "new_owner_id": bob_info["id"]},
            db=app.db,
        )
        assert transfer_ok["new_owner_id"] == bob_info["id"]

        # ─── Шаг 6. Мультиретурн по WebSocket и дисконнект при смене прав ───
        # ─── Шаг 6. Мультиретурн по WebSocket и дисконнект при смене прав ───
        incoming = [
            make_ws_message(
                orjson.dumps({
                    "jsonrpc": "2.0",
                    "method": "Book.live_feed",
                    "params": {"limit": 2},
                    "id": 500,
                }).decode()
            ),
        ]
        proto = MockRSGIWebsocketProtocol(incoming)
        scope = MockRSGIScope(
            proto="websocket",
            path="/ws",
            headers={"authorization": f"Bearer {alice_token}"},
        )

        async def _admin_change_roles() -> None:
            await asyncio.sleep(0.04)
            # Во время живого WS-соединения админ меняет роли Alice -> должен прилететь close 1008!
            await app.router.call(
                "admin.set_user_roles",
                admin_session,
                {"user_id": alice_info["id"], "roles": ["user", "adm_crud"]},
                db=app.db,
            )

        task = asyncio.create_task(_admin_change_roles())
        await app(scope, proto)
        await task

        text_frames = [
            orjson.loads(m) for m in proto.transport.sent_messages
        ]
        assert text_frames == [
            {"jsonrpc": "2.0", "result": {"event": "book_pulse", "step": 1}, "id": 500},
            {"jsonrpc": "2.0", "result": {"event": "book_pulse", "step": 2}, "id": 500},
        ]
        assert proto.close_code == WsCloseCode.POLICY_VIOLATION

    finally:
        await app.shutdown()
