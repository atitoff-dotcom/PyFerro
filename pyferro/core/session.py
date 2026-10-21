import asyncio
import inspect
import time
from contextvars import ContextVar
from itertools import count
from typing import Optional, Any

import orjson
from .logger import logger
from .lib.config import settings
from .tabular import pack_tabular, unpack_tabular, is_tabular, tabular_response

# Контекстные переменные для доступа к сессиям из любой точки кода
current_transport_ctx: ContextVar = ContextVar("current_transport", default=None)
current_session_ctx: ContextVar = ContextVar("current_session", default=None)
current_rpc_id_ctx: ContextVar = ContextVar("current_rpc_id", default=None)
current_user_ctx: ContextVar = ContextVar("current_user", default=None)

ACTIVE_SESSIONS_SET = set()
RPC_REGISTRY = {}
GUEST_ALLOWED_RPC_METHODS: set = set()
GUEST_ALLOWED_CRUD_MODELS: set = set()

def is_guest_rpc_allowed(method_name: str) -> bool:
    """Проверяет O(1) доступность RPC-метода для системной роли guest."""
    if method_name in GUEST_ALLOWED_RPC_METHODS:
        return True
    for p in GUEST_ALLOWED_RPC_METHODS:
        if p.endswith(".*") and method_name.startswith(p[:-1]):
            return True
    return False


def is_framework_handler(handler: Any) -> bool:
    """
    Определяет, относится ли RPC-обработчик к ядру или встроенным плагинам pyferro.
    """
    if handler is None:
        return False
    explicit = getattr(handler, "is_framework", None)
    if explicit is not None:
        return bool(explicit)

    try:
        unwrapped = inspect.unwrap(handler)
    except Exception:
        unwrapped = handler

    mod = getattr(unwrapped, "__module__", "") or ""
    if mod == "pyferro" or mod.startswith("pyferro."):
        return True

    try:
        from pathlib import Path
        import pyferro
        fn_file = Path(inspect.getfile(unwrapped)).resolve()
        pyferro_dir = Path(pyferro.__file__).resolve().parent
        if pyferro_dir in fn_file.parents or fn_file == pyferro_dir:
            return True
    except (TypeError, OSError):
        pass

    return False
def _is_session_admin(session: Any) -> bool:
    """Производит проверку прав администратора для сессии, включая токены или Cookie."""
    if not session:
        return False
    if getattr(session, "is_superadmin", False) is True or getattr(session, "is_admin", False) is True:
        return True
    data = getattr(session, "data", None)
    if data:
        if getattr(data, "is_superadmin", False) is True or getattr(data, "is_admin", False) is True:
            return True
        if isinstance(data, dict):
            if data.get("is_superadmin"):
                return True
            role = data.get("role") or data.get("user_role")
            roles = data.get("roles") or data.get("user_roles") or []
            return role in ("admin", "ADMIN", "superadmin") or any(r in ("admin", "ADMIN", "superadmin") for r in roles)
    if isinstance(session, dict):
        if session.get("is_superadmin"):
            return True
        role = session.get("role") or session.get("user_role")
        roles = session.get("roles") or session.get("user_roles") or []
        return role in ("admin", "ADMIN", "superadmin") or any(r in ("admin", "ADMIN", "superadmin") for r in roles)
    role = getattr(session, "user_role", None) or getattr(session, "role", None)
    if isinstance(role, str) and role.lower() in ("admin", "superadmin", "administrator"):
        return True
    roles = getattr(session, "user_roles", None) or getattr(session, "roles", None)
    if isinstance(roles, (list, tuple, set)) and any(isinstance(r, str) and r.lower() in ("admin", "superadmin", "administrator") for r in roles):
        return True
    cookies = getattr(session, "cookies", None)
    if cookies and isinstance(cookies, dict):
        from .http import extract_session_token
        token = extract_session_token(cookies)
        if token:
            try:
                from pyferro.plugins.crud.auth import get_crud_session
                sdata = get_crud_session(token)
                if sdata and (sdata.get("is_superadmin") or str(sdata.get("role") or "").lower() in ("admin", "superadmin", "administrator")):
                    return True
            except Exception:
                pass
    return False


def require_admin(session: Any) -> None:
    """Проверяет наличие прав администратора у сессии (session.is_superadmin).

    Выбрасывает стандартизированную ошибку RPCError(-32003) при недостатке прав.
    """
    if getattr(session, "is_superadmin", False) is True:
        return
    if not _is_session_admin(session):
        raise RPCError(-32003, "Доступ запрещен: требуются права администратора.")

class RPCError(Exception):
    """
    Исключение для RPC-ошибок, сообщения которых возвращаются клиенту.
    Поддерживает как передачу (message), так и (code, message).
    """
    def __init__(self, code_or_message: Any, message: Optional[str] = None):
        if message is not None:
            self.code = int(code_or_message)
            self.message = str(message)
        elif isinstance(code_or_message, int):
            self.code = code_or_message
            self.message = "RPC Error"
        else:
            self.code = -32000
            self.message = str(code_or_message)
        super().__init__(self.message)



def rpc_method(
    name: str,
    description: Optional[str] = None,
    http: bool = False,
    is_framework: Optional[bool] = None,
):
    """
    Декоратор для регистрации JSON-RPC 2.0 методов.
    Все права доступа настраиваются динамически в базе данных (роли guest, user, admin).

    :param name: Обязательное сетевое имя метода (например, "orders.create", "system.ping").
    :param description: Описание метода для документации и матрицы прав (по умолчанию извлекается из docstring).
    :param http: Разрешить прямой вызов метода через HTTP POST /rpc.
    :param is_framework: Явный признак системного метода фреймворка (по умолчанию определяется автоматически).
    """
    if not isinstance(name, str) or not name.strip():
        raise TypeError("Декоратор @rpc_method требует явное строковое имя метода: @rpc_method(\"namespace.method\")")

    def decorator(func):
        try:
            unwrapped = inspect.unwrap(func)
        except Exception:
            unwrapped = func

        method_name = name.strip()
        fw_flag = is_framework if is_framework is not None else is_framework_handler(unwrapped)

        sig = inspect.signature(unwrapped)
        param_names = list(sig.parameters.keys())
        has_var_pos = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        is_generic_wrapper = has_var_pos and has_var_kw
        expects_session_and_params = len(param_names) == 2 and param_names[0] in ("session", "self", "s") and param_names[1] in ("params", "args", "data", "p")

        # Извлекаем оригинальный docstring функции или явное описание
        full_doc = description or inspect.getdoc(unwrapped) or inspect.getdoc(func) or getattr(func, "__doc__", None)

        async def wrapper(session, params):
            if expects_session_and_params or is_generic_wrapper:
                return await func(session, params)

            # Если первый аргумент явно session/self
            if param_names and param_names[0] in ("session", "self", "s"):
                if isinstance(params, dict):
                    # Отфильтруем только те аргументы, которые ожидает функция (или передадим все, если есть **kwargs)
                    kw = params if has_var_kw else {k: v for k, v in params.items() if k in sig.parameters}
                    return await func(session, **kw)
                return await func(session, params)

            # Если сигнатура ожидает только именованные параметры без явного session
            if isinstance(params, dict):
                kw = params if has_var_kw else {k: v for k, v in params.items() if k in sig.parameters}
                return await func(**kw)

            if len(param_names) == 1:
                return await func(params)

            return await func()

        wrapper.__doc__ = full_doc
        wrapper.__name__ = getattr(unwrapped, "__name__", "wrapper")
        wrapper.__wrapped__ = unwrapped
        RPC_REGISTRY[method_name] = wrapper
        wrapper.http = http
        wrapper.description = description
        wrapper.is_framework = fw_flag
        return func
    return decorator


@rpc_method("system.ping", description="Штатный сетевой пинг для измерения Round Trip Time (RTT).", is_framework=True)
async def _builtin_system_ping(session=None, params=None):
    return {
        "status": "pong",
        "server_time": time.time(),
        "granian": "rsgi",
    }


@rpc_method("system.info", description="Системная информация, активные сессии и метрики окружения.", is_framework=True)
async def _builtin_system_info(session=None, params=None):
    import sys
    import platform
    transport = current_transport_ctx.get() or session
    sid = getattr(transport, "session_id", getattr(session, "session_id", 1))
    return {
        "framework": "PyFerro",
        "rsgi_server": "Granian (Rust)",
        "python_version": sys.version.split()[0],
        "os_platform": platform.platform(),
        "active_sessions_count": len(ACTIVE_SESSIONS_SET),
        "your_session_id": sid,
    }
# --- СЕССИЯ RSGI ---

class JsonRpcSession:
    __slots__ = (
        "ws", "user_data", "session_id", "scope",
        "_id_generator", "_pending_requests", "_auth_timeout_task", "_idle_timeout_task",
        "_is_alive", "_handler_tasks", "tokens", "rate_limit_enabled", "_closed",
        "_reset_timer_handle", "_main_task", "last_activity",
        "ip", "data", "_on_close_callbacks", "_close_tasks"
    )

    def __init__(self, ws, session_id: int, ip: str = "0.0.0.0", scope: Any = None):
        self.ws = ws
        self.session_id = session_id
        self.scope = scope
        self.user_data = {}
        self.ip = ip
        self.data = None
        self._on_close_callbacks = []
        self._close_tasks = set()
        ACTIVE_SESSIONS_SET.add(self)

        self._id_generator = count()
        self._pending_requests = {}
        self._handler_tasks = set()
        self._auth_timeout_task = None
        self._idle_timeout_task = None
        self._is_alive = True
        self._closed = False
        self._reset_timer_handle = None
        self._main_task = None
        self.last_activity = time.time()

        # --- НАСТРОЙКИ ЗАЩИТЫ ---
        self.rate_limit_enabled = True  # True - включено, False - выключено
        self.tokens = 0                 # Текущий счетчик запросов в текущем окне

    def register_on_close(self, callback):
        """Регистрирует колбэк, который будет вызван при закрытии сессии."""
        self._on_close_callbacks.append(callback)

    @property
    def authenticated(self) -> bool:
        return self.data is not None

    @property
    def user_role(self):
        if not self.data:
            return 'guest'
        if isinstance(self.data, dict):
            return self.data.get('role') or self.data.get('user_role') or 'guest'
        return getattr(self.data, 'user_role', None) or getattr(self.data, 'role', 'guest')

    @property
    def user_roles(self):
        if not self.data:
            return ['guest']
        if isinstance(self.data, dict):
            roles = self.data.get('roles') or self.data.get('user_roles')
            if roles:
                return list(roles)
            role = self.data.get('role') or self.data.get('user_role')
            return [role] if role else ['guest']
        if hasattr(self.data, 'user_roles') and self.data.user_roles:
            return list(self.data.user_roles)
        role = getattr(self.data, 'user_role', None) or getattr(self.data, 'role', None)
        return [role] if role else ['guest']
    @property
    def user_id(self) -> Optional[int]:
        if not self.data:
            return None
        if isinstance(self.data, dict):
            val = self.data.get("user_id") or self.data.get("uid") or self.data.get("id")
            try:
                return int(val) if val is not None else None
            except (ValueError, TypeError):
                return None
        val = getattr(self.data, "user_id", None) or getattr(self.data, "uid", None)
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def username(self) -> str:
        if not self.data:
            return "guest"
        if isinstance(self.data, dict):
            return str(self.data.get("username") or self.data.get("user_name") or "guest")
        return str(getattr(self.data, "username", None) or getattr(self.data, "user_name", "guest"))

    @property
    def is_superadmin(self) -> bool:
        if not self.data:
            return False
        if isinstance(self.data, dict):
            if self.data.get("is_superadmin"):
                return True
            role = self.data.get("role") or self.data.get("user_role")
            roles = self.data.get("roles") or self.data.get("user_roles") or []
            return role in ("admin", "ADMIN", "superadmin") or any(r in ("admin", "ADMIN", "superadmin") for r in roles)
        return bool(getattr(self.data, "is_superadmin", False))

    @property
    def is_admin(self) -> bool:
        return self.is_superadmin

    @property
    def cookies(self) -> Dict[str, str]:
        """Возвращает распарсенные HTTP-куки из handshake текущего WebSocket-соединения."""
        if not self.scope:
            return {}
        from .http import extract_header
        raw = extract_header(self.scope, "cookie", "")
        if not raw:
            return {}
        res = {}
        for item in raw.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                res[k.strip()] = v.strip()
        return res

    async def send_str(self, payload_str: str) -> bool:
        """
        Безопасная неблокирующая отправка текстового payload в WebSocket.
        Изолирует ошибки закрытого сокета и обходит несовместимость Future.cancelled в Python 3.13+/Granian.
        """
        if self._closed or not self.ws:
            return False
        try:
            awaitable = self.ws.send_str(payload_str)
            if not hasattr(awaitable, "cancelled"):
                try:
                    awaitable.cancelled = lambda: False
                except AttributeError:
                    pass
            await awaitable
            return True
        except Exception as e:
            logger.debug(f"[Сессия {self.session_id}] Ошибка отправки в сокет: {e}")
            return False

    def _reset_tokens_loop(self):
        """Быстрый таймер сброса лимитов без создания тяжелых asyncio.Task"""
        if self._closed:
            return
        self.tokens = 0  # Обнуляем счетчик каждую секунду
        self._reset_timer_handle = asyncio.get_running_loop().call_later(1.0, self._reset_tokens_loop)

    async def start(self):
        self._main_task = asyncio.current_task()
        self._auth_timeout_task = asyncio.create_task(self._auth_timeout_loop())
        self._idle_timeout_task = asyncio.create_task(self._idle_timeout_loop())
        
        # Запускаем ежесекундный сброс лимитов
        self._reset_tokens_loop()
        
        max_message_size = settings.security.get("max_message_size", 10 * 1024 * 1024)

        try:
            while True:
                msg = await self.ws.receive()
                self.last_activity = time.time()
                logger.debug(f"[Сессия {self.session_id}] Получено сообщение")

                # --- ПРОВЕРКА НА ДИСКОННЕКТ ПО ТИПУ ОБЪЕКТА ---
                cls_name = getattr(getattr(msg, "__class__", None), "__name__", "") or type(msg).__name__
                if not msg or "CloseMessage" in cls_name or "CloseMessage" in type(msg).__name__:
                    logger.info(f"disconnect: session_id {self.session_id}")
                    break 
                # ---------------------------------------------

                    
                self._is_alive = True              

                # --- УЛЬТРАБЫСТРАЯ ПРОВЕРКА ЛИМИТА ---
                if self.rate_limit_enabled:
                    self.tokens += 1
                    if self.tokens > 30:  # Максимум 30 запросов в секунду
                        logger.warning(f"[Защита] Сессия {self.session_id} заблокирована за RPC-флуд!")
                        await self._send_error(None, -32005, "Too many requests. Connection closing.")
                        break 
                # -------------------------------------

                raw_data = getattr(msg, "data", None)
                if raw_data is None:
                    continue

                if len(raw_data) > max_message_size:
                    logger.warning(f"[Защита] Сессия {self.session_id}: превышен лимит размера сообщения ({len(raw_data)} > {max_message_size})")
                    await self._send_error(None, -32600, "Message too large")
                    continue

                try:
                    data = orjson.loads(raw_data)
                except Exception as e:
                    logger.warning(f"[Сессия {self.session_id}] Ошибка парсинга orjson: {e}")
                    await self._send_error(None, -32700, "Parse error")
                    continue

                if not isinstance(data, dict):
                    await self._send_error(None, -32600, "Invalid Request: root must be a JSON object")
                    continue

                rpc_id = data.get("id")
                if rpc_id is not None and not isinstance(rpc_id, (str, int)):
                    await self._send_error(None, -32600, "Invalid Request: id must be integer, string or null")
                    continue

                if rpc_id is not None and ("result" in data or "error" in data):
                    fut = self._pending_requests.pop(rpc_id, None)
                    if fut and not fut.done():
                        fut.set_result(data)
                    continue

                if data.get("jsonrpc") != "2.0" or "method" not in data:
                    await self._send_error(rpc_id, -32600, "Invalid Request")
                    continue

                method_name = data.get("method")
                if not isinstance(method_name, str):
                    await self._send_error(rpc_id, -32600, "Invalid Request: method must be string")
                    continue

                params = data.get("params", {})
                if not isinstance(params, (dict, list)):
                    await self._send_error(rpc_id, -32602, "Invalid params: must be object or array")
                    continue

                handler = RPC_REGISTRY.get(method_name)
                if not handler:
                    await self._send_error(rpc_id, -32601, f"Method '{method_name}' not found")
                    continue

                is_preflight = bool(data.get("check_access") is True)
                if is_preflight and self.rate_limit_enabled and self.tokens > 0:
                    self.tokens -= 1

                allowed, err_code, err_msg = self.check_rpc_access(method_name, params, is_preflight=is_preflight)
                if not allowed:
                    await self._send_error(rpc_id, err_code, err_msg)
                    continue

                if is_preflight:
                    payload_str = orjson.dumps({
                        "jsonrpc": "2.0",
                        "result": {"allowed": True, "method": method_name},
                        "id": rpc_id,
                    }).decode("utf-8")
                    await self.send_str(payload_str)
                    continue

                task = asyncio.create_task(
                    self._run_rpc_handler(handler, method_name, rpc_id, params)
                )
                self._handler_tasks.add(task)
                task.add_done_callback(self._handler_tasks.discard)

        finally:
            # Гарантированная очистка ресурсов в одной точке
            await self.close()

    def check_rpc_access(self, method_name: str, params: Any = None, is_preflight: bool = False) -> tuple[bool, int, str]:
        """
        Проверяет права доступа текущей сессии к указанному RPC-методу без запуска его обработчика.
        Возвращает кортеж (allowed, error_code, error_message).
        """
        if method_name not in RPC_REGISTRY:
            return False, -32601, f"Method '{method_name}' not found"

        # 1. Проверка для методов CRUD
        if method_name.startswith("crud."):
            if not self.authenticated:
                if method_name not in ("crud.list", "crud.get", "crud.schema"):
                    return (
                        False,
                        -32003,
                        "Мутации в CRUD запрещены для роли Гость. Используйте специализированные RPC-методы.",
                    )
                if is_preflight and method_name in ("crud.list", "crud.get") and isinstance(params, dict) and params.get("model"):
                    model_name = str(params["model"])
                    if model_name not in GUEST_ALLOWED_CRUD_MODELS:
                        return False, -32003, f"Чтение модели '{model_name}' запрещено для роли Гость."
            elif is_preflight and isinstance(params, dict) and params.get("model"):
                if not (self.is_admin or self.is_superadmin):
                    model_name = str(params["model"])
                    action_map = {
                        "crud.list": "can_read",
                        "crud.get": "can_read",
                        "crud.lookup": "can_read",
                        "crud.create": "can_create",
                        "crud.update_cell": "can_update",
                        "crud.bulk_update": "can_update",
                        "crud.delete": "can_delete",
                    }
                    perm_key = action_map.get(method_name)
                    if perm_key:
                        user_ctx = getattr(self.data, "user_ctx", None) if self.data else None
                        perms_dict = getattr(user_ctx, "perms_dict", {}) if user_ctx else {}
                        if not perms_dict and isinstance(self.data, dict):
                            perms_dict = self.data.get("perms_dict") or self.data.get("permissions") or {}
                        model_perms = perms_dict.get(model_name, {}) if isinstance(perms_dict, dict) else {}
                        if not model_perms.get(perm_key, False):
                            return False, -32003, f"Доступ к операции '{method_name}' для модели '{model_name}' запрещен."
            return True, 0, ""

        # 2. Системные методы управления правами требуют прав администратора
        if method_name.startswith("permissions."):
            if not (self.is_admin or self.is_superadmin):
                return False, -32003, "Доступ запрещен: требуются права администратора"
            return True, 0, ""

        # 3. Проверка обычных RPC-методов для роли guest
        if not self.authenticated:
            login_rpc = settings.security.get("login_rpc")
            is_allowed_guest = (
                is_guest_rpc_allowed(method_name)
                or (login_rpc is not None and (login_rpc == "" or method_name.startswith(login_rpc)))
                or method_name.startswith("login.")
                or method_name in ("auth.login", "auth.me", "auth.whoami", "auth.submit")
            )
            if not is_allowed_guest:
                return False, -32001, "Unauthorized: доступ запрещен для роли Гость."
            return True, 0, ""

        # 4. Проверка прав авторизованного пользователя (O(1) in-memory)
        has_perm = False
        session_data = self.data
        if session_data:
            if hasattr(session_data, "has_rpc_permission"):
                has_perm = session_data.has_rpc_permission(method_name)
            else:
                role = getattr(session_data, "user_role", None) or getattr(self, "user_role", None)
                roles = getattr(session_data, "user_roles", None) or getattr(self, "user_roles", [])
                if role in ("admin", "ADMIN") or "admin" in roles or "ADMIN" in roles or self.is_superadmin:
                    has_perm = True
                elif hasattr(session_data, "allowed_rpc_methods"):
                    allowed = session_data.allowed_rpc_methods
                    has_perm = "*" in allowed or method_name in allowed
                    if not has_perm:
                        for m in allowed:
                            if m.endswith(".*") and method_name.startswith(m[:-1]):
                                has_perm = True
                                break

        # Если метод открыт роли guest или это системный выход из сессии, авторизованный пользователь тоже имеет к нему доступ
        if not has_perm and (
            is_guest_rpc_allowed(method_name)
            or method_name.startswith("login.")
            or method_name in ("auth.login", "auth.me", "auth.whoami", "auth.submit", "auth.logout")
        ):
            has_perm = True

        if not has_perm:
            return False, -32003, f"Доступ к методу '{method_name}' запрещен."

        return True, 0, ""
    async def _run_rpc_handler(self, handler, method_name: str, rpc_id, params):
        transport_token = current_transport_ctx.set(self)
        session_token = current_session_ctx.set(self.data)
        rpc_token = current_rpc_id_ctx.set(rpc_id)
        user_token = None
        if self.data:
            u_ctx = getattr(self.data, "user_ctx", None) or self.data
            user_token = current_user_ctx.set(u_ctx)
        try:
            session_arg = self.data if self.data else self
            result = await handler(session_arg, params)
            
            if self._closed or not self.ws:
                return

            payload_str = orjson.dumps({
                "jsonrpc": "2.0", "result": result, "id": rpc_id
            }).decode("utf-8")
            
            await self.send_str(payload_str)
            
        except RPCError as e:
            # Возвращаем ожидаемую ошибку RPC клиенту с указанным кодом
            err_code = getattr(e, "code", -32000)
            await self._send_error(rpc_id, err_code, e.message)
        except Exception as e:
            logger.error(f"[RPC Error] Ошибка в хендлере {method_name}: {e}")
            await self._send_error(rpc_id, -32603, "Internal server error")
        finally:
            if user_token is not None:
                current_user_ctx.reset(user_token)
            current_transport_ctx.reset(transport_token)
            current_session_ctx.reset(session_token)
            current_rpc_id_ctx.reset(rpc_token)

    async def send_request(self, method: str, params: dict = None, timeout: float = 5.0) -> dict:
        if self._closed or not self.ws:
            raise ConnectionError("WebSocket connection is not active")
            
        rpc_id = next(self._id_generator)
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": rpc_id}
        
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_requests[rpc_id] = fut
        
        payload_str = orjson.dumps(payload).decode("utf-8")
        await self.send_str(payload_str)
        
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending_requests.pop(rpc_id, None)

    async def _auth_timeout_loop(self):
        try:
            from .lib.config import settings
            timeout = settings.security.get("auth_timeout", 0)
            if not timeout or timeout <= 0:
                return

            await asyncio.sleep(timeout)
            if not self.authenticated:
                logger.warning(f"[Защита] Таймаут авторизации ({int(timeout)}с) для сессии {self.session_id}. Закрываем.")
                if self._main_task and not self._main_task.done():
                    self._main_task.cancel()
        except asyncio.CancelledError:
            pass

    async def _idle_timeout_loop(self):
        try:
            from .lib.config import settings

            while not self._closed:
                await asyncio.sleep(10.0)
                elapsed = time.time() - self.last_activity

                # Разделение таймаутов неактивности: для гостей и для зарегистрированных пользователей
                if self.authenticated:
                    timeout = settings.security.get("user_idle_timeout") or settings.security.get("session_idle_timeout", 1800)
                    role_desc = "пользователя"
                else:
                    timeout = settings.security.get("guest_idle_timeout") or settings.security.get("session_idle_timeout", 900)
                    role_desc = "гостя"

                if timeout and timeout > 0 and elapsed >= timeout:
                    logger.info(f"[Защита] Сессия {self.session_id} ({role_desc}) закрыта по неактивности ({int(elapsed)}с).")
                    try:
                        payload_str = orjson.dumps({
                            "jsonrpc": "2.0", "method": "session.expired", "params": {"reason": "idle_timeout"}
                        }).decode("utf-8")
                        await self.send_str(payload_str)
                    except Exception:
                        pass
                    
                    if self._main_task and not self._main_task.done():
                        self._main_task.cancel()
                    break
        except asyncio.CancelledError:
            pass

    async def send_stream_chunk(self, rpc_id, chunk_data):
        if self._closed or not self.ws:
            return
        payload_str = orjson.dumps({
            "jsonrpc": "2.0", "result": {"stream": True, "data": chunk_data}, "id": rpc_id
        }).decode("utf-8")
        await self.send_str(payload_str)

    async def _send_error(self, rpc_id, code: int, message: str):
        if self._closed or not self.ws:
            return
        payload_str = orjson.dumps({
            "jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": rpc_id
        }).decode("utf-8")
        await self.send_str(payload_str)

    async def close(self):
        if self._closed:
            return
        self._closed = True

        current_task = asyncio.current_task()

        # Безопасно завершаем таски таймаутов без риска рекурсии
        if self._auth_timeout_task and self._auth_timeout_task != current_task and not self._auth_timeout_task.done():
            self._auth_timeout_task.cancel()
            
        if self._idle_timeout_task and self._idle_timeout_task != current_task and not self._idle_timeout_task.done():
            self._idle_timeout_task.cancel()
            
        for task in self._handler_tasks:
            if task != current_task and not task.done():
                task.cancel()
            
        self._handler_tasks.clear()
        
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Session closed"))
        self._pending_requests.clear()
        
        if self._reset_timer_handle:
            self._reset_timer_handle.cancel()
            self._reset_timer_handle = None

        if self._main_task and self._main_task != current_task and not self._main_task.done():
            self._main_task.cancel()

        # Вызов зарегистрированных колбэков закрытия сессии
        for callback in self._on_close_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    task = asyncio.create_task(callback(self))
                    self._close_tasks.add(task)
                    task.add_done_callback(self._close_tasks.discard)
                else:
                    callback(self)
            except Exception as e:
                logger.error(f"[Сессия] Ошибка выполнения close-колбэка: {e}")

        ACTIVE_SESSIONS_SET.discard(self)
        self.ws = None

    def __del__(self):
        try:
            logger.debug(f"[Сессия] Уничтожена: ID {self.session_id}")
        except Exception:
            pass
