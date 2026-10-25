"""
Диспетчер JSON-RPC 2.0, компилятор сигнатур, мультиретурн (`yield`) и проверка прав (`pyferro2/rpc/router.py`).

Ключевые принципы:
1. **Zero-Reflection в рантайме**: `inspect.signature` вызывается ровно 1 раз в момент
   регистрации функции декоратором `@rpc_method`. Создается неизменяемый `RpcMethodSpec`.
2. **Единое имя метода из кода (без параметра `name=...`)**:
   имя `Плашка.метод` берется напрямую из объявления функции (`class Book: async def transfer` -> `Book.transfer`,
   либо `<модуль>.<функция>`).
3. **Поддержка и `return`, и мультиретурна `yield`**:
   - Обычная `async def ... return` функция возвращает единичный ответ.
   - Генератор `async def ... yield` (мультиретурн) отправляет поток ответов с тем же `id` запроса!
4. **Smart Dependency Injection**: обработчик запрашивает только нужные ему аргументы:
   - `session_data: SessionData` (паспорт пользователя),
   - `session: Session` (канал связи),
   - `db: AsyncSession` (сессия БД — открывается из пула **только** если объявлена в аргументах!).
5. **Единая O(1) авторизация в памяти (`Плашка.метод` и `Плашка.метод_own`)**:
   проверка ролей и разрешений выполняется мгновенно через `frozenset.isdisjoint`.
"""

from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
import inspect
from typing import Any, get_type_hints

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.core.constants import JsonRpcErrorCode
from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro2.core.tabular import apply_tabular_result
from pyferro2.db.engine import Database
from pyferro2.rpc.errors import (
    ForbiddenError,
    InvalidParamsError,
    MethodNotFoundError,
    RpcError,
    UnauthorizedError,
)

RpcHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RpcMethodSpec:
    """
    Предкомпилированная спецификация RPC-метода.
    Создается один раз при старте сервера и используется для мгновенного вызова без рефлексии.
    """

    name: str
    handler: RpcHandler
    public: bool
    required_roles: frozenset[str] | None
    allowed_permissions: frozenset[str]
    is_stream: bool  # True, если функция использует мультиретурн (`yield`)
    tabular: bool  # True, если списки словарей автоматически сжимаются в $tabular

    # Имена аргументов для автоматического внедрения зависимостей (Smart DI)
    session_data_arg: str | None
    session_arg: str | None
    db_arg: str | None

    # Метаданные пользовательских аргументов (для валидации за O(1) без inspect)
    param_names: tuple[str, ...]
    allowed_params: frozenset[str]
    required_params: frozenset[str]
    accepts_kwargs: bool


def check_rpc_access(spec: RpcMethodSpec, session_data: SessionData) -> bool:
    """
    Прозрачная проверка прав доступа к RPC-методу (100% в оперативной памяти за O(1)):

    1. Публичный метод (`public=True`) или Главный администратор (`is_admin`) -> доступ открыт.
    2. Если указан `required_roles` и есть пересечение с `session_data.roles` -> доступ открыт.
    3. Если метод допускает проверку по матрице прав (`allowed_permissions`: `X.y` или `X.y_own`) ->
       проверяется пересечение с `session_data.permissions`.
    """
    if spec.public or session_data.is_admin:
        return True

    if spec.required_roles is not None and not session_data.roles.isdisjoint(spec.required_roles):
        return True

    if spec.allowed_permissions:
        return not session_data.permissions.isdisjoint(spec.allowed_permissions)

    return False


def _resolve_method_name(fn: RpcHandler) -> str:
    """
    Вычисляет имя метода `Плашка.метод` напрямую из структуры кода Python:
    - Если функция объявлена внутри класса (`class Book: async def transfer`): -> `Book.transfer`.
    - Если функция объявлена на уровне модуля (`catalog.py` -> `async def get_items`): -> `catalog.get_items`.
    """
    qual_parts = fn.__qualname__.split(".")
    if len(qual_parts) >= 2 and qual_parts[-2] != "<locals>":
        return f"{qual_parts[-2]}.{qual_parts[-1]}"
    module_short = fn.__module__.rsplit(".", 1)[-1]
    return f"{module_short}.{fn.__name__}"


def _compile_method_spec(
    fn: RpcHandler,
    *,
    role: Iterable[str] | str | None = None,
    public: bool = False,
    allow_permissions: bool | None = None,
    tabular: bool = False,
) -> RpcMethodSpec:
    """
    Инспектирует сигнатуру функции ровно 1 раз при регистрации и компилирует `RpcMethodSpec`.
    Поддерживает как обычные корутины (`return`), так и асинхронные генераторы (`yield` мультиретурн).
    """
    is_coro = inspect.iscoroutinefunction(fn)
    is_async_gen = inspect.isasyncgenfunction(fn)
    if not (is_coro or is_async_gen):
        raise TypeError(
            f"RPC-метод '{fn.__name__}' должен быть асинхронной функцией (async def с return или yield)"
        )

    method_name = _resolve_method_name(fn)

    if role is not None:
        if isinstance(role, str):
            req_roles: frozenset[str] | None = frozenset({role})
        else:
            req_roles = frozenset(str(r) for r in role)
    else:
        req_roles = None

    has_perms = (
        allow_permissions
        if allow_permissions is not None
        else (not public and req_roles is None)
    )
    allowed_perms: frozenset[str] = (
        frozenset({method_name, f"{method_name}_own"}) if has_perms else frozenset()
    )

    sig = inspect.signature(fn)
    try:
        type_hints = get_type_hints(fn)
    except Exception:
        type_hints = {}

    session_data_arg: str | None = None
    session_arg: str | None = None
    db_arg: str | None = None

    param_names: list[str] = []
    required_params: set[str] = set()
    accepts_kwargs = False

    for param_name, param in sig.parameters.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_kwargs = True
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            raise TypeError(
                f"RPC-метод '{method_name}' не должен использовать *args, объявите явные аргументы"
            )

        hint = type_hints.get(param_name, param.annotation)

        # Распознаем зависимости фреймворка по типу или каноническому имени аргумента
        if hint is SessionData or param_name == "session_data":
            session_data_arg = param_name
        elif hint is Session or param_name == "session":
            session_arg = param_name
        elif hint is AsyncSession or param_name == "db":
            db_arg = param_name
        else:
            param_names.append(param_name)
            if param.default is inspect.Parameter.empty:
                required_params.add(param_name)

    return RpcMethodSpec(
        name=method_name,
        handler=fn,
        public=bool(public),
        required_roles=req_roles,
        allowed_permissions=allowed_perms,
        is_stream=is_async_gen,
        tabular=bool(tabular),
        session_data_arg=session_data_arg,
        session_arg=session_arg,
        db_arg=db_arg,
        param_names=tuple(param_names),
        allowed_params=frozenset(param_names),
        required_params=frozenset(required_params),
        accepts_kwargs=accepts_kwargs,
    )


def _bind_user_params(
    spec: RpcMethodSpec,
    raw_params: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    """
    Быстро связывает входные параметры JSON-RPC (`dict`, `list` или `None`)
    с аргументами функции по предкомпилированному `RpcMethodSpec`.
    """
    if raw_params is None:
        bound: dict[str, Any] = {}
    elif type(raw_params) is dict:
        if not spec.accepts_kwargs:
            extra_keys = raw_params.keys() - spec.allowed_params
            if extra_keys:
                raise InvalidParamsError(
                    f"Неизвестные параметры для '{spec.name}': {', '.join(sorted(extra_keys))}"
                )
        bound = dict(raw_params)
    elif type(raw_params) is list:
        if len(raw_params) > len(spec.param_names):
            raise InvalidParamsError(
                f"Метод '{spec.name}' принимает максимум {len(spec.param_names)} аргументов, "
                f"передано: {len(raw_params)}"
            )
        bound = dict(zip(spec.param_names, raw_params))
    else:
        raise InvalidParamsError("Поле 'params' должно быть объектом (dict) или массивом (list)")

    missing = spec.required_params - bound.keys()
    if missing:
        raise InvalidParamsError(
            f"Пропущены обязательные параметры для '{spec.name}': {', '.join(sorted(missing))}"
        )

    return bound


class RpcRouter:
    """
    Скоростной реестр и диспетчер методов JSON-RPC 2.0.
    Хранит методы в плоском C-хеш-словаре для мгновенного поиска O(1).
    """

    __slots__ = ("_methods",)

    def __init__(self) -> None:
        self._methods: dict[str, RpcMethodSpec] = {}

    @property
    def methods(self) -> dict[str, RpcMethodSpec]:
        """Возвращает словарь всех зарегистрированных спецификаций методов."""
        return self._methods

    def business_methods(self) -> list[str]:
        """
        Возвращает отсортированный список всех прикладных методов (`Плашка.метод`),
        которые отображаются в матрице прав `/pyferro_admin`.
        """
        return sorted(
            spec.name for spec in self._methods.values() if spec.allowed_permissions
        )

    def get_spec(self, method_name: str) -> RpcMethodSpec | None:
        """Мгновенно возвращает спецификацию метода по имени за O(1)."""
        return self._methods.get(method_name)

    def rpc_method(
        self,
        fn: RpcHandler | None = None,
        *,
        role: Iterable[str] | str | None = None,
        public: bool = False,
        allow_permissions: bool | None = None,
        tabular: bool = False,
    ) -> Any:
        """
        Универсальный декоратор регистрации RPC-метода (поддерживает `return`, мультиретурн `yield` и `tabular=True`).
        Имя метода (`Плашка.метод`) определяется автоматически из имени класса/модуля и функции.
        """
        def _decorator(func: RpcHandler) -> RpcHandler:
            spec = _compile_method_spec(
                func,
                role=role,
                public=public,
                allow_permissions=allow_permissions,
                tabular=tabular,
            )
            func.__rpc_spec__ = spec  # type: ignore[attr-defined]
            self._methods[spec.name] = spec
            return func

        if fn is not None:
            return _decorator(fn)
        return _decorator

    def _prepare_call(
        self,
        method_name: str,
        session: Session,
        params: dict[str, Any] | list[Any] | None,
    ) -> tuple[RpcMethodSpec, dict[str, Any]]:
        """Проверяет существование метода, права доступа и связывает аргументы."""
        spec = self._methods.get(method_name)
        if spec is None:
            raise MethodNotFoundError(f"Метод '{method_name}' не зарегистрирован")

        if not check_rpc_access(spec, session.data):
            if session.data.is_guest:
                raise UnauthorizedError()
            raise ForbiddenError()

        call_kwargs = _bind_user_params(spec, params)
        if spec.session_data_arg is not None:
            call_kwargs[spec.session_data_arg] = session.data
        if spec.session_arg is not None:
            call_kwargs[spec.session_arg] = session

        return spec, call_kwargs

    async def stream(
        self,
        method_name: str,
        session: Session,
        params: dict[str, Any] | list[Any] | None = None,
        *,
        db: Database | AsyncSession | None = None,
    ) -> AsyncIterator[Any]:
        """
        Выполняет мультиретурн-метод (`async def ... yield`) и отдает поток значений.
        Если в процессе работы у сессии запрошен дисконнект (`session.is_closing`),
        аккуратно закрывает генератор через `await gen.aclose()`.
        """
        spec, call_kwargs = self._prepare_call(method_name, session, params)

        if not spec.is_stream:
            yield await self.call(method_name, session, params, db=db)
            return

        if spec.db_arg is not None:
            if isinstance(db, AsyncSession):
                call_kwargs[spec.db_arg] = db
                gen = spec.handler(**call_kwargs)
                try:
                    async for item in gen:
                        yield item
                        if session.is_closing:
                            break
                finally:
                    await gen.aclose()
                return

            if isinstance(db, Database):
                async with db.session() as db_session:
                    call_kwargs[spec.db_arg] = db_session
                    gen = spec.handler(**call_kwargs)
                    try:
                        async for item in gen:
                            yield item
                            if session.is_closing:
                                break
                    finally:
                        await gen.aclose()
                return

            raise RpcError(
                f"Метод '{method_name}' требует базу данных ('{spec.db_arg}: AsyncSession'), "
                "но объект Database не был передан в диспетчер"
            )

        gen = spec.handler(**call_kwargs)
        try:
            async for item in gen:
                yield item
                if session.is_closing:
                    break
        finally:
            await gen.aclose()

    async def call(
        self,
        method_name: str,
        session: Session,
        params: dict[str, Any] | list[Any] | None = None,
        *,
        db: Database | AsyncSession | None = None,
    ) -> Any:
        """
        Выполняет проверку прав, внедряет зависимости и вызывает обработчик RPC-метода.
        Сессия БД открывается лениво — только если обработчик явно запросил аргумент `db`.
        """
        spec, call_kwargs = self._prepare_call(method_name, session, params)

        if spec.is_stream:
            return [item async for item in self.stream(method_name, session, params, db=db)]

        session.begin_rpc()
        try:
            if spec.db_arg is not None:
                if isinstance(db, AsyncSession):
                    call_kwargs[spec.db_arg] = db
                    res = await spec.handler(**call_kwargs)
                elif isinstance(db, Database):
                    async with db.session() as db_session:
                        call_kwargs[spec.db_arg] = db_session
                        res = await spec.handler(**call_kwargs)
                else:
                    raise RpcError(
                        f"Метод '{method_name}' требует базу данных ('{spec.db_arg}: AsyncSession'), "
                        "но объект Database не был передан в диспетчер"
                    )
            else:
                res = await spec.handler(**call_kwargs)

            if spec.tabular:
                res = apply_tabular_result(res)
            return res
        finally:
            await session.end_rpc()

    async def handle_raw(
        self,
        raw_payload: bytes | str,
        session: Session,
        *,
        db: Database | AsyncSession | None = None,
    ) -> bytes | None:
        """
        Принимает сырой JSON-RPC 2.0 пакет (`bytes` или `str`), парсит через `orjson`,
        вызывает метод и возвращает готовые `bytes` ответа (или `None` для уведомлений без `id`).
        """
        try:
            packet = orjson.loads(raw_payload)
        except Exception:
            return encode_error(None, JsonRpcErrorCode.PARSE_ERROR, "Ошибка разбора JSON")

        if type(packet) is not dict or packet.get("jsonrpc") != "2.0":
            req_id = packet.get("id") if type(packet) is dict else None
            return encode_error(req_id, JsonRpcErrorCode.INVALID_REQUEST, "Некорректный пакет JSON-RPC 2.0")

        method_name = packet.get("method")
        is_notification = "id" not in packet
        req_id = packet.get("id")

        if type(method_name) is not str or not method_name:
            return encode_error(req_id, JsonRpcErrorCode.INVALID_REQUEST, "Отсутствует строковое поле 'method'")

        raw_params = packet.get("params")

        try:
            result = await self.call(method_name, session, raw_params, db=db)
        except RpcError as rpc_err:
            if is_notification:
                return None
            return encode_error(req_id, rpc_err.code, rpc_err.message, rpc_err.data)
        except Exception:
            if is_notification:
                return None
            return encode_error(req_id, JsonRpcErrorCode.INTERNAL_ERROR, "Внутренняя ошибка сервера")

        if is_notification:
            return None

        return orjson.dumps({
            "jsonrpc": "2.0",
            "result": result,
            "id": req_id,
        })


def encode_error(
    req_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> bytes:
    """Сериализует ошибку JSON-RPC 2.0 в `bytes` через `orjson`."""
    err_obj: dict[str, Any] = {
        "code": int(code),
        "message": message,
    }
    if data is not None:
        err_obj["data"] = data
    return orjson.dumps({
        "jsonrpc": "2.0",
        "error": err_obj,
        "id": req_id,
    })


# Глобальный роутер по умолчанию и удобный алиас декоратора
default_router = RpcRouter()
rpc_method = default_router.rpc_method
