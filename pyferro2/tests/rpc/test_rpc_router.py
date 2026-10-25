"""
Модульные тесты Этапа 3: диспетчер JSON-RPC 2.0, Smart DI, Lazy DB и авторизация (`pyferro2/rpc/`).
"""

import orjson
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.core import JsonRpcErrorCode, Session, SessionData, USER_ROLE, admRole
from pyferro2.db import Database
from pyferro2.rpc import (
    ForbiddenError,
    InvalidParamsError,
    MethodNotFoundError,
    RpcError,
    RpcRouter,
    UnauthorizedError,
)


@pytest.fixture
def router() -> RpcRouter:
    """Создает чистый экземпляр RpcRouter для каждого теста."""
    return RpcRouter()


class TestRegistrationAndCompilation:
    """Проверка однократной компиляции сигнатур (`RpcMethodSpec`) при старте."""

    def test_auto_module_and_class_method_names(self, router: RpcRouter) -> None:
        @router.rpc_method
        async def calc_tax(amount: int) -> int:
            return amount

        class catalog:
            @router.rpc_method
            async def get_items(session_data: SessionData, limit: int = 10) -> int:
                return limit

        assert "test_rpc_router.calc_tax" in router.methods
        assert "catalog.get_items" in router.methods

        spec = router.methods["catalog.get_items"]
        assert spec.session_data_arg == "session_data"
        assert spec.session_arg is None
        assert spec.db_arg is None
        assert spec.param_names == ("limit",)
        assert spec.required_params == frozenset()

    def test_rejects_sync_function_and_varargs(self, router: RpcRouter) -> None:
        with pytest.raises(TypeError, match="должен быть асинхронной функцией"):
            @router.rpc_method
            def sync_fn() -> int:  # type: ignore[arg-type]
                return 1

        with pytest.raises(TypeError, match="не должен использовать \\*args"):
            @router.rpc_method
            async def varargs_fn(*args: int) -> int:
                return sum(args)


class TestThreeStepAccessControl:
    """Проверка авторизации: публичные, системные (`role=[...]`) и бизнес-методы (`Плашка.метод` / `*_own`)."""

    @pytest.mark.asyncio
    async def test_public_method_accessible_by_everyone(self, router: RpcRouter) -> None:
        class system:
            @router.rpc_method(public=True)
            async def ping() -> str:
                return "pong"

        guest_session = Session(session_id="s-guest")
        assert await router.call("system.ping", guest_session) == "pong"

    @pytest.mark.asyncio
    async def test_system_method_with_adm_roles(self, router: RpcRouter) -> None:
        class crud:
            @router.rpc_method(role=[admRole.adm_crud])
            async def update_schema(session_data: SessionData, table: str) -> str:
                return f"{session_data.username}:{table}"

        # 1. Гость -> UnauthorizedError (-32001)
        guest_session = Session(session_id="s-guest")
        with pytest.raises(UnauthorizedError) as exc_unauth:
            await router.call("crud.update_schema", guest_session, {"table": "users"})
        assert exc_unauth.value.code == JsonRpcErrorCode.UNAUTHORIZED

        # 2. Обычный пользователь без роли adm_crud -> ForbiddenError (-32003)
        regular_user = Session(
            session_id="s-user",
            data=SessionData(user_id=5, username="ivan", roles=frozenset({USER_ROLE})),
        )
        with pytest.raises(ForbiddenError) as exc_forbid:
            await router.call("crud.update_schema", regular_user, {"table": "users"})
        assert exc_forbid.value.code == JsonRpcErrorCode.FORBIDDEN

        # 3. Пользователь с ролью adm_crud -> разрешено!
        crud_manager = Session(
            session_id="s-mgr",
            data=SessionData(
                user_id=6,
                username="olga",
                roles=frozenset({USER_ROLE, admRole.adm_crud.value}),
            ),
        )
        res = await router.call("crud.update_schema", crud_manager, {"table": "users"})
        assert res == "olga:users"

        # 4. Главный администратор (admin) -> разрешено всё!
        admin_session = Session(
            session_id="s-admin",
            data=SessionData(user_id=1, username="root", roles=frozenset({admRole.admin.value})),
        )
        assert await router.call("crud.update_schema", admin_session, {"table": "roles"}) == "root:roles"

    @pytest.mark.asyncio
    async def test_business_method_checked_via_permissions_frozenset(self, router: RpcRouter) -> None:
        class catalog:
            @router.rpc_method
            async def get_items(category: str = "all") -> list[str]:
                return [f"item:{category}"]

        # 1. Гость без прав -> UnauthorizedError
        guest_no_perm = Session(session_id="g1")
        with pytest.raises(UnauthorizedError):
            await router.call("catalog.get_items", guest_no_perm)

        # 2. Гость, которому в БД выдали право на catalog.get_items -> разрешено!
        guest_with_perm = Session(
            session_id="g2",
            data=SessionData.guest(permissions=frozenset({"catalog.get_items"})),
        )
        assert await router.call("catalog.get_items", guest_with_perm, {"category": "books"}) == ["item:books"]

        # 3. Авторизованный пользователь без права -> ForbiddenError
        user_no_perm = Session(
            session_id="u1",
            data=SessionData(user_id=10, username="petr", roles=frozenset({USER_ROLE})),
        )
        with pytest.raises(ForbiddenError):
            await router.call("catalog.get_items", user_no_perm)

        # 4. Авторизованный пользователь с правом в permissions -> разрешено!
        user_with_perm = Session(
            session_id="u2",
            data=SessionData(
                user_id=10,
                username="petr",
                roles=frozenset({USER_ROLE}),
                permissions=frozenset({"catalog.get_items"}),
            ),
        )
        assert await router.call("catalog.get_items", user_with_perm) == ["item:all"]


class TestSmartDIAndLazyDatabase:
    """Проверка умного внедрения зависимостей (`session_data`, `session`, `db`) и ленивой БД."""

    @pytest.mark.asyncio
    async def test_session_notify_and_lazy_db_injection(self, router: RpcRouter) -> None:
        events: list[tuple[str, object]] = []

        async def capture_notify(event: str, payload: object) -> None:
            events.append((event, payload))

        class reports:
            @router.rpc_method(public=True)
            async def generate(session: Session, db: AsyncSession, title: str) -> dict[str, object]:
                await session.notify("report.progress", {"step": 1, "title": title})
                row = (await db.execute(text("SELECT 42"))).scalar_one()
                return {"user": session.data.username, "answer": row}

        database = Database("sqlite+aiosqlite:///:memory:")
        live_session = Session(session_id="s-1", notify=capture_notify)

        try:
            result = await router.call(
                "reports.generate",
                live_session,
                ["Q4 Report"],
                db=database,
            )
            assert result == {"user": "guest", "answer": 42}
            assert events == [("report.progress", {"step": 1, "title": "Q4 Report"})]
        finally:
            await database.close()

    @pytest.mark.asyncio
    async def test_missing_db_raises_clear_error_only_when_db_requested(self, router: RpcRouter) -> None:
        class db:
            @router.rpc_method(public=True)
            async def query(db: AsyncSession) -> int:
                return 1

        session = Session(session_id="s-1")
        with pytest.raises(RpcError, match="требует базу данных"):
            await router.call("db.query", session, db=None)


class TestParamsValidationAndRawWireProtocol:
    """Проверка валидации параметров и пакетного JSON-RPC 2.0 обработчика `handle_raw` (orjson)."""

    @pytest.mark.asyncio
    async def test_invalid_params_and_method_not_found(self, router: RpcRouter) -> None:
        class math:
            @router.rpc_method(public=True)
            async def divide(a: int, b: int = 2) -> float:
                return a / b

        session = Session(session_id="s-1")

        # Несуществующий метод
        with pytest.raises(MethodNotFoundError):
            await router.call("math.unknown", session)

        # Пропущен обязательный параметр 'a'
        with pytest.raises(InvalidParamsError, match="Пропущены обязательные параметры"):
            await router.call("math.divide", session, {})

        # Передан лишний неизвестный параметр
        with pytest.raises(InvalidParamsError, match="Неизвестные параметры"):
            await router.call("math.divide", session, {"a": 10, "unknown": 1})

        # Передано слишком много позиционных аргументов
        with pytest.raises(InvalidParamsError, match="принимает максимум 2 аргументов"):
            await router.call("math.divide", session, [10, 2, 999])

    @pytest.mark.asyncio
    async def test_handle_raw_orjson_protocol(self, router: RpcRouter) -> None:
        class math:
            @router.rpc_method(public=True)
            async def add(a: int, b: int) -> int:
                return a + b

        session = Session(session_id="s-wire")

        # 1. Успешный запрос
        req_bytes = orjson.dumps({"jsonrpc": "2.0", "method": "math.add", "params": {"a": 7, "b": 8}, "id": 101})
        resp_bytes = await router.handle_raw(req_bytes, session)
        assert resp_bytes is not None
        assert orjson.loads(resp_bytes) == {"jsonrpc": "2.0", "result": 15, "id": 101}

        # 2. JSON-RPC Notification (без поля 'id') — возвращает None
        notif_bytes = orjson.dumps({"jsonrpc": "2.0", "method": "math.add", "params": [1, 2]})
        assert await router.handle_raw(notif_bytes, session) is None

        # 3. Битый JSON -> PARSE_ERROR (-32700)
        bad_json_resp = await router.handle_raw(b"{broken_json", session)
        assert bad_json_resp is not None
        assert orjson.loads(bad_json_resp)["error"]["code"] == JsonRpcErrorCode.PARSE_ERROR

        # 4. Некорректный конверт JSON-RPC -> INVALID_REQUEST (-32600)
        bad_env_resp = await router.handle_raw(b'{"jsonrpc": "1.0", "id": 5}', session)
        assert bad_env_resp is not None
        parsed_err = orjson.loads(bad_env_resp)
        assert parsed_err["id"] == 5
        assert parsed_err["error"]["code"] == JsonRpcErrorCode.INVALID_REQUEST
