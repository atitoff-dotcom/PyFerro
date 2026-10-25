# -*- coding: utf-8 -*-
"""
Тест-сьют: Проверка находок независимого архитектурного аудита.

Каждый тест либо ПОДТВЕРЖДАЕТ, либо ОПРОВЕРГАЕТ конкретный тезис аудита.

Соглашение:
  * обычный тест  — тезис аудита опровергнут (защита работает) или зафиксировано текущее поведение;
  * xfail(strict) — тезис ПОДТВЕРЖДЁН: тест описывает ЖЕЛАЕМОЕ безопасное поведение и пока падает.
                    Когда проблему исправят, strict-xfail «загорится» (XPASS -> FAIL), и метку
                    нужно будет снять — так находка не потеряется и не регрессирует.
"""

import asyncio
import contextlib

import pytest
from sqlalchemy import Integer, String, event, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from pyferro.core.session import RPCError
from pyferro.db import Base, async_session
import pyferro.plugins.help.models  # noqa: F401  (регистрирует таблицы форума в Base.metadata до create_all)
from pyferro.plugins.crud import (
    AccessPolicy,
    DefaultAccessPolicy,
    DefaultIdentityProvider,
    ModelRegistry,
    handle_crud_create,
    handle_crud_list,
    handle_crud_update_cell,
    set_access_policy,
    set_identity_provider,
)


# ---------------------------------------------------------------------------
# Тестовые модели
# ---------------------------------------------------------------------------

class AuditNote(Base):
    """Модель с owner_id: row-secure определяется автоматически по имени колонки."""
    __tablename__ = "test_audit_notes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=True)
    secret_token: Mapped[str] = mapped_column(String(100), default="")


class AuditPost(Base):
    """Модель с «нестандартной» колонкой владельца user_id (объявлена в owner_columns)."""
    __tablename__ = "test_audit_posts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True)

    class Crud:
        owner_columns = {"user_id"}


class AuditComment(Base):
    """Модель без class Crud, но с колонкой author_id — должна вызывать warning при регистрации."""
    __tablename__ = "test_audit_comments"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(String(100), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, nullable=True)

class _Session:
    """Минимальная авторизованная не-админская сессия."""

    def __init__(self, user_id):
        self.session_id = 1000 + user_id
        self.user = {"id": user_id, "username": f"user{user_id}", "role": "user", "is_superuser": False}
        self.ws = None
        self.authenticated = True
        self.data = self.user
        self.user_role = "user"
        self.user_roles = ["user"]


class _Provider:
    def __init__(self, user_id, permissions):
        self.uid = user_id
        self.perms = set(permissions)

    def user_id(self, session):
        return self.uid

    def user_name(self, session):
        return f"user{self.uid}"

    def is_superuser(self, user_id):
        return False

    def has_permission(self, user_id, perm):
        return perm in self.perms

    async def effective_user_ids(self, user_id, model_name, db):
        return {user_id}

    async def user_team_ids(self, user_id, db):
        return set()

    async def primary_team_id(self, user_id, db):
        return None


@contextlib.asynccontextmanager
async def _memory_db():
    """Изолированная in-memory БД с восстановлением глобального состояния после теста."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session.configure(bind=engine)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        set_identity_provider(DefaultIdentityProvider())
        set_access_policy(DefaultAccessPolicy())
        await engine.dispose()
        from pyferro.db import engine as orig_engine
        async_session.configure(bind=orig_engine)


def _register_models():
    ModelRegistry.register(AuditNote)
    ModelRegistry.register(AuditPost)


async def _seed(rows):
    async with async_session() as db:
        db.add_all(rows)
        await db.commit()


# ===========================================================================
# ТЕЗИС 3 АУДИТА: «Скрытые уязвимости RLS»
# ===========================================================================

@pytest.mark.asyncio
async def test_rls_owner_id_is_autodetected_and_foreign_rows_hidden():
    """
    Тезис аудита: «Забыл флаг is_row_secure — данные открыты».
    ОПРОВЕРГНУТ для owner_id/creator_id/team_id: флаг выводится из колонок автоматически.
    """
    async with _memory_db():
        _register_models()
        await _seed([
            AuditNote(title="mine", owner_id=1),
            AuditNote(title="foreign", owner_id=2),
        ])
        set_identity_provider(_Provider(1, {"AuditNote:read"}))
        set_access_policy(DefaultAccessPolicy())

        meta = ModelRegistry.get("AuditNote")
        assert meta.is_row_secure is True

        res = await handle_crud_list(_Session(1), {"model": "AuditNote"})
        assert res["total"] == 1, "total (count) обязан считаться ПОСЛЕ применения RLS-предиката"
        assert len(res["rows"]) == 1


@pytest.mark.asyncio
async def test_rls_declared_owner_column_hides_foreign_rows():
    """Модель с объявленной owner_columns={'user_id'} изолирует чужие строки для пользователя без view_all."""
    async with _memory_db():
        _register_models()
        await _seed([
            AuditPost(title="mine", user_id=1),
            AuditPost(title="foreign", user_id=2),
        ])
        set_identity_provider(_Provider(1, {"AuditPost:read"}))
        set_access_policy(DefaultAccessPolicy())

        res = await handle_crud_list(_Session(1), {"model": "AuditPost"})
        assert res["total"] == 1
        assert len(res["rows"]) == 1


def test_rls_unregistered_suspicious_owner_column_emits_warning(caplog):
    """Модель с author_id без явного class Crud: owner_columns должна выдавать warning в лог."""
    import logging
    with caplog.at_level(logging.WARNING):
        ModelRegistry.register(AuditComment)

    found_warning = any(
        "AuditComment" in r.message and "author_id" in r.message and "owner_columns" in r.message
        for r in caplog.records
    )
    assert found_warning, "Ожидалось предупреждение о незадекларированной колонке владельца"


@pytest.mark.asyncio
async def test_rls_declared_owner_column_create_protects_foreign_owner():
    """При создании записи в модели с owner_columns={'user_id'} попытка подсунуть чужой user_id игнорируется."""
    async with _memory_db():
        _register_models()
        set_identity_provider(_Provider(1, {"AuditPost:create", "AuditPost:read"}))
        set_access_policy(DefaultAccessPolicy())

        res = await handle_crud_create(_Session(1), {
            "model": "AuditPost",
            "data": {"title": "safe_post", "user_id": 999}
        })
        assert "id" in res
        async with async_session() as db:
            row = (await db.execute(select(AuditPost).where(AuditPost.id == res["id"]))).scalar_one()
        assert row.title == "safe_post"
        assert row.user_id == 1, "user_id обязан принадлежать текущему пользователю, а не подсунутому 999"
@pytest.mark.asyncio
async def test_rls_create_cannot_assign_foreign_owner():
    """
    Тезис аудита: «create с чужим owner_id проходит».
    ОПРОВЕРГНУТ: owner_id защищён (protected) и без права :transfer отбрасывается, owner = текущий пользователь.
    """
    async with _memory_db():
        _register_models()
        set_identity_provider(_Provider(1, {"AuditNote:create", "AuditNote:read"}))
        set_access_policy(DefaultAccessPolicy())

        res = await handle_crud_create(_Session(1), {
            "model": "AuditNote",
            "data": {"title": "hack", "owner_id": 999},
        })
        async with async_session() as db:
            row = (await db.execute(select(AuditNote).where(AuditNote.id == res["id"]))).scalar_one()
        assert row.owner_id == 1, "owner_id из payload обязан игнорироваться без права transfer"


@pytest.mark.asyncio
async def test_rls_create_on_behalf_of_other_user_denied():
    """acting_for_user_id без полномочия замещения/transfer должен отклоняться."""
    async with _memory_db():
        _register_models()
        set_identity_provider(_Provider(1, {"AuditNote:create"}))
        set_access_policy(DefaultAccessPolicy())

        with pytest.raises(RPCError) as exc:
            await handle_crud_create(_Session(1), {
                "model": "AuditNote",
                "data": {"title": "x"},
                "acting_for_user_id": 999,
            })
        assert exc.value.code == -32003 if hasattr(exc.value, "code") else True


@pytest.mark.asyncio
async def test_rls_update_cannot_transfer_ownership_via_cell():
    """Смена owner_id через update_cell без права transfer должна блокироваться."""
    async with _memory_db():
        _register_models()
        await _seed([AuditNote(title="mine", owner_id=1)])
        set_identity_provider(_Provider(1, {"AuditNote:read", "AuditNote:update"}))
        set_access_policy(DefaultAccessPolicy())

        with pytest.raises(RPCError):
            await handle_crud_update_cell(_Session(1), {
                "model": "AuditNote", "id": 1, "field": "owner_id", "value": 999,
            })
        async with async_session() as db:
            row = (await db.execute(select(AuditNote).where(AuditNote.id == 1))).scalar_one()
        assert row.owner_id == 1


@pytest.mark.asyncio
async def test_rls_hidden_field_is_not_an_oracle_via_filter_or_search():
    """
    Тезис аудита: «side-channel через фильтры/поиск по полям, недоступным для чтения».
    ОПРОВЕРГНУТ: filters/sort принимают только публичные поля, hidden-поля не searchable.
    """
    async with _memory_db():
        _register_models()
        await _seed([
            AuditNote(title="a", owner_id=1, secret_token="alpha-secret"),
            AuditNote(title="b", owner_id=1, secret_token="beta-secret"),
        ])
        set_identity_provider(_Provider(1, {"AuditNote:read"}))
        set_access_policy(DefaultAccessPolicy())
        sess = _Session(1)

        by_filter = await handle_crud_list(sess, {"model": "AuditNote", "filters": {"secret_token": "alpha-secret"}})
        assert by_filter["total"] == 2, "фильтр по скрытому полю должен игнорироваться, а не сужать выдачу"
        assert "secret_token" not in by_filter["fields"]

        by_search = await handle_crud_list(sess, {"model": "AuditNote", "search": "alpha"})
        assert by_search["total"] == 0, "поиск не должен заглядывать в скрытые поля"

        by_sort = await handle_crud_list(sess, {"model": "AuditNote", "sort_field": "secret_token"})
        assert by_sort["total"] == 2


# ===========================================================================
# ТЕЗИС 2 АУДИТА: «DoS через Dynamic Rendering»
# ===========================================================================

class _MockProto:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = ""

    def response_str(self, status=200, headers=None, body=""):
        self.status = status
        self.headers = dict(headers or [])
        self.body = body


def _bot_scope(path):
    return {
        "method": "GET",
        "path": path,
        "headers": [
            (b"user-agent", b"Mozilla/5.0 (compatible; Googlebot/2.1)"),
            (b"host", b"localhost:8080"),
        ],
        "query_string": b"",
    }


@contextlib.contextmanager
def _count_queries(engine):
    counter = {"n": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before)


async def _seo_setup():
    from pyferro.plugins.help.models import ForumCategory, ForumTopic
    ModelRegistry.register(ForumCategory)
    ModelRegistry.register(ForumTopic)
    async with async_session() as db:
        dev = ForumCategory(name="Разработка", slug="development", description="d")
        db.add(dev)
        await db.commit()
        await db.refresh(dev)
        db.add(ForumTopic(category_id=dev.id, title="Тема", slug="real-topic", first_post_text="t"))
        await db.commit()


@pytest.mark.asyncio
async def test_seo_miss_cost_is_bounded_and_reported():
    """
    Измеряет усиление «1 HTTP-запрос -> N SQL-запросов» на несуществующих URL (ботнет-перебор).
    Это измерение, а не защита: тест фиксирует верхнюю границу и печатает фактическое значение (pytest -s).
    """
    from pyferro.plugins.seo.router import handle_bot_http

    async with _memory_db() as engine:
        await _seo_setup()
        n = 20
        with _count_queries(engine) as counter:
            for i in range(n):
                proto = _MockProto()
                # Промах: перехватчик возвращает False и отдаёт запрос дальше (404 формирует приложение).
                handled = await handle_bot_http(_bot_scope(f"/forum/nope{i}/miss{i}"), proto)
                assert handled is False
        per_miss = counter["n"] / n
        print(f"\n[AUDIT] SQL-запросов на один несуществующий URL: {per_miss:.1f}")
        assert per_miss <= 20, "усиление запросов вышло за разумные рамки"


@pytest.mark.asyncio
async def test_seo_repeated_404_should_be_served_from_negative_cache():
    from pyferro.plugins.seo.router import handle_bot_http

    async with _memory_db() as engine:
        await _seo_setup()
        await handle_bot_http(_bot_scope("/forum/ghost/ghost-topic"), _MockProto())
        with _count_queries(engine) as counter:
            handled = await handle_bot_http(_bot_scope("/forum/ghost/ghost-topic"), _MockProto())
        assert handled is False
        assert counter["n"] == 0, f"повторный промах выполнил {counter['n']} SQL-запросов, ожидалось 0 (отрицательный кэш)"


@pytest.mark.asyncio
async def test_seo_repeated_valid_page_should_be_served_from_cache():
    from pyferro.plugins.seo.router import handle_bot_http

    async with _memory_db() as engine:
        await _seo_setup()
        first = _MockProto()
        await handle_bot_http(_bot_scope("/forum/development/real-topic"), first)
        assert first.status == 200
        with _count_queries(engine) as counter:
            second = _MockProto()
            await handle_bot_http(_bot_scope("/forum/development/real-topic"), second)
        assert second.status == 200
        assert counter["n"] == 0


def test_seo_cache_max_entries_bounded():
    from pyferro.plugins.seo.page_cache import TTLCache

    cache = TTLCache(max_entries=10)
    for i in range(25):
        cache.set(f"/path/{i}", f"data_{i}", ttl=60)
    assert len(cache) == 10
    # Самые первые ключи должны быть вытеснены
    found_0, _ = cache.get("/path/0")
    assert not found_0
    # Самые последние должны остаться
    found_24, val_24 = cache.get("/path/24")
    assert found_24 and val_24 == "data_24"


def test_seo_cache_ttl_expiration(monkeypatch):
    import time
    from pyferro.plugins.seo.page_cache import TTLCache

    cache = TTLCache(max_entries=100)
    fake_time = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: fake_time)

    cache.set("/valid", "content", ttl=10)
    cache.set("/missing", None, ttl=5)

    assert cache.get("/valid") == (True, "content")
    assert cache.get("/missing") == (True, None)

    # Прошло 6 секунд: /missing истек, /valid еще жив
    fake_time = 1006.0
    assert cache.get("/missing") == (False, None)
    assert cache.get("/valid") == (True, "content")

    # Прошло 11 секунд: /valid тоже истек
    fake_time = 1011.0
    assert cache.get("/valid") == (False, None)


def test_seo_cache_long_key_ignored():
    from pyferro.plugins.seo.page_cache import TTLCache

    cache = TTLCache(max_entries=100)
    long_key = "/" + "a" * 550
    cache.set(long_key, "data", ttl=60)
    assert len(cache) == 0
    found, _ = cache.get(long_key)
    assert not found


# ===========================================================================
# ТЕЗИС 1 АУДИТА: «Горизонтальное масштабирование / broadcast»
# ===========================================================================

class _FakeWsSession:
    def __init__(self, sid):
        self.session_id = sid
        self._closed = False
        self.received = []

    async def send_str(self, payload):
        self.received.append(payload)
        return True


@contextlib.contextmanager
def _recording_backplane():
    from pyferro.core.backplane import BaseBackplane, get_backplane, set_backplane

    class _Recording(BaseBackplane):
        def __init__(self):
            self.published = []

        async def publish(self, channel, message):
            self.published.append((channel, message))

        async def subscribe(self, channel, callback):
            return None

        async def unsubscribe(self, channel, callback):
            return None

    previous = get_backplane()
    rec = _Recording()
    set_backplane(rec)
    try:
        yield rec
    finally:
        set_backplane(previous)


@pytest.mark.asyncio
async def test_broadcast_delivers_to_local_sessions():
    """Базовое поведение: рассылка достигает сессий своего процесса."""
    from pyferro.broadcast import broadcast_notification
    from pyferro.core.session import ACTIVE_SESSIONS_SET

    s = _FakeWsSession(777001)
    ACTIVE_SESSIONS_SET.add(s)
    try:
        sent = await broadcast_notification("audit.ping", {"x": 1})
        assert sent >= 1
        assert any("audit.ping" in p for p in s.received)
    finally:
        ACTIVE_SESSIONS_SET.discard(s)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="АУДИТ ПОДТВЕРЖДЁН: broadcast_notification не публикует в backplane — "
           "при нескольких воркерах/подах сообщение достигнет только клиентов своего процесса.",
)
async def test_broadcast_must_be_published_to_backplane_for_other_workers():
    from pyferro.broadcast import broadcast_notification
    from pyferro.core.session import ACTIVE_SESSIONS_SET

    s = _FakeWsSession(777002)
    ACTIVE_SESSIONS_SET.add(s)
    try:
        with _recording_backplane() as backplane:
            await broadcast_notification("audit.cluster", {"x": 1})
            await asyncio.sleep(0)
        assert backplane.published, "событие обязано уйти в backplane, чтобы дойти до других процессов"
    finally:
        ACTIVE_SESSIONS_SET.discard(s)


# ---------------------------------------------------------------------------
# CRIT-01: Предотвращение захвата аккаунта суперадмина через нечисловой sub в JWT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crit_01_file_download_token_cannot_authenticate_as_superadmin():
    """
    CRIT-01: Проверяет, что Capability-токен скачивания файла не может быть
    использован как Access-токен суперадминистратора (uid = 1) ни через WebSocket,
    ни через CRUD SSO / get_crud_session, ни через decode_access_token.
    """
    import jwt
    from unittest.mock import AsyncMock, MagicMock
    from pyferro.app import FerroApp
    from pyferro.plugins.files.service import FileStorageService
    from pyferro.plugins.crud.auth import get_crud_session
    from pyferro.core.security import decode_access_token

    # 1. Генерируем Capability-токен на скачивание файла
    dl_token = FileStorageService.generate_download_token(file_id=123)

    # 2. decode_access_token должен отклонить токен
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(dl_token)

    # 3. get_crud_session не должен возвращать сессию суперадмина
    assert get_crud_session(dl_token) is None

    # 4. WebSocket auto-auth не должен авторизовать сессию по этому токену
    app = FerroApp(auto_auth_ws=True)
    scope = {
        "proto": "websocket",
        "client": ("127.0.0.1", 54321),
        "headers": [
            (b"cookie", f"rpc_jwt={dl_token}; ferro_session={dl_token}".encode("latin1"))
        ]
    }
    proto = MagicMock()
    ws_mock = AsyncMock()
    ws_mock.receive = AsyncMock(side_effect=Exception("RSGI transport is closed"))
    proto.accept = AsyncMock(return_value=ws_mock)

    connected_session = None

    @app.on_connect
    def hook(session):
        nonlocal connected_session
        connected_session = session

    await app._handle_websocket(scope, proto)

    assert connected_session is not None
    # Сессия НЕ должна быть авторизована, data должна быть None, user_id не должен быть 1
    assert connected_session.data is None
    assert connected_session.is_superadmin is False
    assert connected_session.user_id is None
    await connected_session.close()


def test_crit_01_non_numeric_and_invalid_sub_rejected():
    """
    CRIT-01: Любые нечисловые, пустые или отрицательные sub в подписанных JWT
    должны отклоняться decode_access_token и get_crud_session (без фоллбэка на uid=1).
    """
    import jwt
    from pyferro.core.security import get_secret_key, ALGORITHM, decode_access_token
    from pyferro.plugins.crud.auth import get_crud_session

    invalid_subs = ["file_download", "admin", "root", "", "-1", "0", None]
    sec = get_secret_key()

    for bad_sub in invalid_subs:
        payload = {"username": "hacker"}
        if bad_sub is not None:
            payload["sub"] = bad_sub
        token = jwt.encode(payload, sec, algorithm=ALGORITHM)

        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

        assert get_crud_session(token) is None


def test_crit_01_token_isolation():
    """
    CRIT-01: Проверяет взаимную изоляцию пользовательских токенов и токенов файлов.
    """
    from pyferro.core.security import create_access_token, decode_access_token
    from pyferro.plugins.files.service import FileStorageService

    # Access-токен валиден для доступа, но не для скачивания файла
    user_token, _, _ = create_access_token(user_id=42, username="alice", roles=["user"])
    payload = decode_access_token(user_token)
    assert payload["sub"] == "42"
    assert payload["typ"] == "access"
    assert FileStorageService.verify_download_token(user_token) is None

    # Download-токен валиден для скачивания файла, но не для доступа
    dl_token = FileStorageService.generate_download_token(file_id=777)
    assert FileStorageService.verify_download_token(dl_token) == 777


# ---------------------------------------------------------------------------
# CRIT-02: Предотвращение обхода матрицы прав в CRUD и эскалации через системные модели
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crit_02_system_models_crud_forbidden_for_regular_user():
    """
    CRIT-02: Проверяет, что обычный пользователь не может создать UserDelegation
    или прочитать RefreshToken/ActiveSession через CRUD даже в боевом вызове
    (без флага check_access / is_preflight=False).
    """
    from unittest.mock import MagicMock
    from pyferro.core.session import JsonRpcSession, ACTIVE_SESSIONS_SET
    from pyferro.plugins.crud.identity import DefaultIdentityProvider

    # 1. Сессия обычного пользователя (user_id = 5, не админ)
    session = JsonRpcSession(MagicMock(), session_id=105)
    try:
        user_ctx = type("UserCtx", (), {
            "user_id": 5,
            "is_superadmin": False,
            "team_ids": [],
            "delegated_user_ids": [],
            "perms_dict": {},
        })()
        auth_data = type("AuthSession", (), {
            "user_id": 5,
            "user_role": "user",
            "user_roles": ["user"],
            "is_superadmin": False,
            "user_ctx": user_ctx,
            "perms_dict": {},
            "allowed_rpc_methods": {"crud.*"},
        })()
        session.data = auth_data

        # Вектор 1: попытка создать UserDelegation от суперадмина (from_user_id=1 к to_user_id=5)
        allowed, err_code, err_msg = session.check_rpc_access(
            "crud.create",
            {"model": "UserDelegation", "data": {"from_user_id": 1, "to_user_id": 5, "is_active": True}},
            is_preflight=False,
        )
        assert allowed is False
        assert err_code == -32003

        # Вектор 2: попытка прочитать RefreshToken или ActiveSession
        allowed_rf, err_code_rf, _ = session.check_rpc_access(
            "crud.list",
            {"model": "RefreshToken"},
            is_preflight=False,
        )
        assert allowed_rf is False
        assert err_code_rf == -32003

        allowed_as, err_code_as, _ = session.check_rpc_access(
            "crud.list",
            {"model": "ActiveSession"},
            is_preflight=False,
        )
        assert allowed_as is False
        assert err_code_as == -32003

        # Проверка через DefaultIdentityProvider.has_permission с контекстом сессии
        from pyferro.core.session import current_transport_ctx
        token = current_transport_ctx.set(session)
        try:
            provider = DefaultIdentityProvider()
            assert provider.has_permission(5, "UserDelegation:create") is False
            assert provider.has_permission(5, "UserDelegation:read") is False
            assert provider.has_permission(5, "RefreshToken:read") is False
            assert provider.has_permission(5, "ActiveSession:read") is False
            assert provider.has_permission(5, "Role:delete") is False
        finally:
            current_transport_ctx.reset(token)
    finally:
        ACTIVE_SESSIONS_SET.discard(session)


@pytest.mark.asyncio
async def test_crit_02_perms_dict_enforced_in_real_calls():
    """
    CRIT-02: Проверяет, что доступ к CRUD шлюзу требует роли adm_crud,
    а матрица perms_dict соблюдается провайдером прав при вызовах.
    """
    from unittest.mock import MagicMock
    from pyferro.core.session import JsonRpcSession, ACTIVE_SESSIONS_SET
    from pyferro.plugins.crud.identity import DefaultIdentityProvider
    from pyferro.core.session import current_transport_ctx
    from pyferro.core.constants import admRole

    # Пользователь с матрицей прав: Чтение разрешено, создание запрещено
    user_ctx = type("UserCtx", (), {
        "user_id": 10,
        "is_superadmin": False,
        "team_ids": [],
        "delegated_user_ids": [],
        "perms_dict": {
            "Article": {
                "can_read": True,
                "read_global": False,
                "can_create": False,
                "can_update": True,
                "update_global": False,
                "can_delete": False,
                "delete_global": False,
            }
        },
    })()

    # 1. Пользователь без роли adm_crud блокируется на уровне RPC gateway
    regular_auth = type("AuthSession", (), {
        "user_id": 10,
        "user_role": "editor",
        "user_roles": ["editor"],
        "is_superadmin": False,
        "user_ctx": user_ctx,
        "perms_dict": user_ctx.perms_dict,
        "allowed_rpc_methods": {"crud.*"},
    })()
    session = JsonRpcSession(MagicMock(), session_id=110)
    try:
        session.data = regular_auth
        can_list, code_reg, _ = session.check_rpc_access("crud.list", {"model": "Article"}, is_preflight=False)
        assert can_list is False
        assert code_reg == -32003

        # 2. Пользователь с ролью adm_crud проходит gateway-проверку скоупа
        crud_auth = type("AuthSession", (), {
            "user_id": 10,
            "user_role": "editor",
            "user_roles": ["editor", admRole.adm_crud.value],
            "is_superadmin": False,
            "user_ctx": user_ctx,
            "perms_dict": user_ctx.perms_dict,
            "allowed_rpc_methods": {"crud.*"},
        })()
        session.data = crud_auth
        can_list_crud, _, _ = session.check_rpc_access("crud.list", {"model": "Article"}, is_preflight=False)
        assert can_list_crud is True

        # 3. Проверка соблюдения матрицы perms_dict через DefaultIdentityProvider
        provider = DefaultIdentityProvider()
        token = current_transport_ctx.set(session)
        try:
            assert provider.has_permission(10, "Article:read") is True
            assert provider.has_permission(10, "Article:create") is False
            assert provider.has_permission(10, "Article:delete") is False
            assert provider.has_permission(10, "Article:update") is True
        finally:
            current_transport_ctx.reset(token)
    finally:
        ACTIVE_SESSIONS_SET.discard(session)


@pytest.mark.asyncio
async def test_crit_02_guest_crud_restrictions_in_real_calls():
    """
    CRIT-02: Гостевой доступ к административным CRUD RPC блокируется
    как неавторизованный (код -32001).
    """
    from unittest.mock import MagicMock
    from pyferro.core.session import JsonRpcSession, ACTIVE_SESSIONS_SET

    guest_session = JsonRpcSession(MagicMock(), session_id=999)
    try:
        guest_session.data = None

        # Попытка чтения произвольной модели гостем
        allowed, code, _ = guest_session.check_rpc_access(
            "crud.list",
            {"model": "SecretProject"},
            is_preflight=False,
        )
        assert allowed is False
        assert code == -32001
    finally:
        ACTIVE_SESSIONS_SET.discard(guest_session)


@pytest.mark.asyncio
async def test_guest_hard_blocked_from_all_admin_scopes_in_code():
    """
    Проверяет, что роль guest на уровне кода ядра физически не может выполнить
    ни одного административного RPC (со скоупами adm_*, crud.*, permissions.*),
    даже если эти методы попытались принудительно добавить в кэш гостя.
    """
    from unittest.mock import MagicMock
    from pyferro.core.session import (
        JsonRpcSession,
        ACTIVE_SESSIONS_SET,
        is_guest_rpc_allowed,
        GUEST_ALLOWED_RPC_METHODS,
        RPC_REGISTRY,
    )

    guest_session = JsonRpcSession(MagicMock(), session_id=888)
    try:
        guest_session.data = None

        # 1. Попытка внедрения административных методов в кэш гостя
        GUEST_ALLOWED_RPC_METHODS.add("crud.list")
        GUEST_ALLOWED_RPC_METHODS.add("crud.create")
        GUEST_ALLOWED_RPC_METHODS.add("permissions.save")
        try:
            # is_guest_rpc_allowed блокирует их безусловно
            assert is_guest_rpc_allowed("crud.list") is False
            assert is_guest_rpc_allowed("crud.create") is False
            assert is_guest_rpc_allowed("permissions.save") is False

            # check_rpc_access блокирует их с кодом -32001
            for adm_method in ("crud.list", "crud.create", "permissions.save"):
                allowed, code, _ = guest_session.check_rpc_access(adm_method, {}, is_preflight=False)
                assert allowed is False
                assert code == -32001
        finally:
            GUEST_ALLOWED_RPC_METHODS.discard("crud.list")
            GUEST_ALLOWED_RPC_METHODS.discard("crud.create")
            GUEST_ALLOWED_RPC_METHODS.discard("permissions.save")

        # 2. Проверяем все зарегистрированные методы со скоупами: ни один не доступен гостю
        for m_name, handler in RPC_REGISTRY.items():
            if getattr(handler, "scopes", None) or m_name.startswith("crud.") or m_name.startswith("permissions."):
                allowed, code, _ = guest_session.check_rpc_access(m_name, {}, is_preflight=False)
                assert allowed is False, f"Метод {m_name} был ошибочно разрешен гостю!"
                assert code == -32001
    finally:
        ACTIVE_SESSIONS_SET.discard(guest_session)


@pytest.mark.asyncio
async def test_crit_03_jinja_cannot_access_auth_and_system_models():
    """
    CRIT-03 Penetration Test:
    Проверяет, что системные и auth-модели (RefreshToken, User, ActiveSession и др.)
    полностью исключены из контекста Jinja2 шаблонизатора SEO.
    Попытка эксплойта вида {% for t in RefreshToken %}{{ t.token }}{% endfor %}
    не приводит к извлечению токенов.
    """
    from pyferro.plugins.seo.jinja_engine import (
        build_template_context,
        render_jinja_template,
        is_model_allowed_for_seo,
        ModelQueryWrapper,
        SYSTEM_SECURITY_MODELS,
    )
    from pyferro.plugins.crud import ModelRegistry

    # 1. Проверяем, что ни одна служебная модель не попала в контекст
    ctx = build_template_context(extra={"title": "Тест"})
    for sec_model in SYSTEM_SECURITY_MODELS:
        assert sec_model not in ctx, f"Модель безопасности {sec_model} попала в контекст Jinja2!"

    # 2. Проверяем, что функция is_model_allowed_for_seo запрещает служебные модели
    for m_key in ("User", "RefreshToken", "ActiveSession", "SystemData", "OAuthAccount"):
        meta = ModelRegistry.get(m_key)
        if meta:
            assert is_model_allowed_for_seo(meta) is False, f"Модель {m_key} разрешена для SEO!"

    # 3. Симуляция атаки через шаблон
    exploit_template = """
    {% for t in RefreshToken %}
      TOKEN:{{ t.token }}
    {% endfor %}
    {% for u in User %}
      USER:{{ u.login }}:{{ u.password_hash }}
    {% endfor %}
    """
    rendered = await render_jinja_template(exploit_template, ctx)
    assert "TOKEN:" not in rendered
    assert "USER:" not in rendered


@pytest.mark.asyncio
async def test_crit_03_model_query_wrapper_defense_in_depth():
    """
    CRIT-03: Проверяет, что даже при прямой инициализации ModelQueryWrapper
    системной моделью (User или RefreshToken), генератор блокирует запрос
    и не возвращает записей.
    """
    from pyferro.plugins.seo.jinja_engine import ModelQueryWrapper
    from pyferro.plugins.crud import ModelRegistry

    user_meta = ModelRegistry.get("User")
    if user_meta:
        wrapper = ModelQueryWrapper(user_meta)
        count = await wrapper.count()
        assert count == 0

        rows = [r async for r in wrapper]
        assert len(rows) == 0

    token_meta = ModelRegistry.get("RefreshToken")
    if token_meta:
        wrapper = ModelQueryWrapper(token_meta)
        count = await wrapper.count()
        assert count == 0

        rows = [r async for r in wrapper]
        assert len(rows) == 0


def test_crit_03_serialize_safe_record_and_record_wrapper():
    """
    CRIT-03: Проверяет, что serialize_safe_record и RecordWrapper надежно
    вырезают конфиденциальные поля (password_hash, token, secret, salt, private_key).
    """
    from pyferro.plugins.seo.jinja_engine import serialize_safe_record, RecordWrapper

    raw_data = {
        "id": 1,
        "title": "Безопасная статья",
        "slug": "safe-article",
        "password_hash": "argon2$sensitive_hash",
        "token": "super_secret_refresh_token",
        "api_key": "sec_12345",
        "secret": "top_secret_salt",
    }

    safe = serialize_safe_record(raw_data)
    assert safe["id"] == 1
    assert safe["title"] == "Безопасная статья"
    assert safe["slug"] == "safe-article"
    assert "password_hash" not in safe
    assert "token" not in safe
    assert "api_key" not in safe
    assert "secret" not in safe

    # Проверка RecordWrapper
    wrapper = RecordWrapper(raw_data)
    assert wrapper.title == "Безопасная статья"
    assert wrapper.password_hash is None
    assert wrapper.token is None
    assert wrapper["token"] is None
    assert "token" not in wrapper

    dict_repr = wrapper.to_dict()
    assert "password_hash" not in dict_repr
    assert "token" not in dict_repr


@pytest.mark.asyncio
async def test_crit_03_admin_seo_endpoints_block_system_models():
    """
    CRIT-03: Проверяет, что RPC-эндпоинты admin.seo_preview_tree_node,
    admin.seo_save_tree и admin.seo_toggle_model_permission отклоняют
    попытки привязать системные модели безопасности.
    """
    from pyferro.plugins.crud.admin_handlers import (
        seo_preview_tree_node_admin,
        seo_save_tree_admin,
        seo_toggle_model_permission_admin,
    )
    from pyferro.core.session import RPCError

    class MockSeoAdminSession:
        is_superadmin = False
        roles = ["adm_seo"]
        user = type("MockUser", (), {"is_superadmin": False, "id": 10, "login": "seo_admin", "roles": [type("R", (), {"name": "adm_seo"})()]})()

    session = MockSeoAdminSession()

    # 1. Попытка превью системной модели RefreshToken
    malicious_node = {
        "node_type": "detail",
        "model_key": "RefreshToken",
        "url_pattern": "/tokens/{id}",
        "template": "{% for t in RefreshToken %}{{ t.token }}{% endfor %}",
    }
    with pytest.raises(RPCError) as exc_info:
        await seo_preview_tree_node_admin(session, node=malicious_node)
    assert exc_info.value.code == -32003
    assert "RefreshToken" in exc_info.value.message

    # 2. Попытка сохранения дерева с моделью User
    malicious_tree = {
        "id": "root",
        "node_type": "static",
        "children": [
            {
                "id": "steal_users",
                "model_key": "User",
                "node_type": "collection",
            }
        ]
    }
    with pytest.raises(RPCError) as exc_info:
        await seo_save_tree_admin(session, tree=malicious_tree)
    assert exc_info.value.code == -32003
    assert "User" in exc_info.value.message

    # 3. Попытка выдать право роли 'seo' на модель RefreshToken
    with pytest.raises(RPCError) as exc_info:
        await seo_toggle_model_permission_admin(session, model_key="RefreshToken", allowed=True)
    assert exc_info.value.code == -32003
    assert "RefreshToken" in exc_info.value.message


@pytest.mark.asyncio
async def test_crit_04_registration_and_login_assigns_default_user_role():
    """
    CRIT-04 Test:
    Проверяет, что при вызове login.register новому пользователю автоматически
    назначается базовая роль по умолчанию ('user'), и последующий вход через
    login.submit проходит успешно без отказа -32003.
    """
    import uuid
    from unittest.mock import MagicMock
    from pyferro.core.session import JsonRpcSession
    from pyferro.auth.handlers import handle_register, handle_login
    from pyferro.db import system_db_session
    from pyferro.auth.models import User
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    test_login = f"user_{uuid.uuid4().hex[:8]}"
    test_email = f"{test_login}@example.com"
    test_password = "SecretPassword123!"

    mock_ws = MagicMock()
    mock_ws.client = ("127.0.0.1", 12345)
    mock_ws.scope = {"type": "websocket", "client": ("127.0.0.1", 12345)}
    session = JsonRpcSession(mock_ws, session_id=9001)

    # 1. Регистрация нового пользователя
    reg_result = await handle_register(session, {
        "username": test_login,
        "email": test_email,
        "password": test_password,
    })
    assert reg_result["success"] is True

    # 2. Проверяем в БД, что роль 'user' назначена
    async with system_db_session() as db:
        stmt = select(User).options(selectinload(User.roles)).where(User.login == test_login)
        user_db = (await db.execute(stmt)).scalar_one()
        assert len(user_db.roles) > 0
        role_names = [r.name for r in user_db.roles]
        assert "user" in role_names

    # 3. Вход пользователя через login.submit
    login_result = await handle_login(session, {
        "username": test_login,
        "password": test_password,
    })
    assert login_result["authenticated"] is True
    assert "user" in login_result["roles"]
    assert login_result["username"] == test_login


@pytest.mark.asyncio
async def test_crit_04_existing_user_without_roles_auto_assigned_user_role():
    """
    CRIT-04 Test:
    Проверяет, что если существующий пользователь без ролей пытается войти в систему,
    _create_authenticated_session не блокирует вход с ошибкой -32003, а автоматически
    привязывает ему базовую роль 'user' и успешно выпускает сессию.
    """
    import uuid
    from unittest.mock import MagicMock
    from pyferro.core.session import JsonRpcSession
    from pyferro.auth.handlers import _create_authenticated_session
    from pyferro.db import system_db_session
    from pyferro.auth.models import User
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    test_login = f"orphan_{uuid.uuid4().hex[:8]}"
    mock_ws = MagicMock()
    mock_ws.client = ("127.0.0.1", 12345)
    mock_ws.scope = {"type": "websocket", "client": ("127.0.0.1", 12345)}
    session = JsonRpcSession(mock_ws, session_id=9002)

    # Создаем пользователя без ролей
    async with system_db_session() as db:
        user = User(
            login=test_login,
            name="Orphan User",
            email=f"{test_login}@example.com",
            password_hash=User._hash_password("DummyPass123!"),
            is_superadmin=False,
            admin_roles="",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Вход через _create_authenticated_session
    async with system_db_session() as db:
        stmt = select(User).options(selectinload(User.roles)).where(User.login == test_login)
        user_db = (await db.execute(stmt)).scalar_one()
        assert len(user_db.roles) == 0

        res = await _create_authenticated_session(db, user_db, session, "test-agent")
        assert res["authenticated"] is True
        assert "user" in res["roles"]

    # Проверяем, что роль зафиксирована в БД
    async with system_db_session() as db:
        stmt = select(User).options(selectinload(User.roles)).where(User.login == test_login)
        user_reloaded = (await db.execute(stmt)).scalar_one()
        assert len(user_reloaded.roles) > 0
        assert any(r.name == "user" for r in user_reloaded.roles)
