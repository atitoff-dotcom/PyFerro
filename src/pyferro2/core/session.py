"""
Контракт сессии (`Session`) для WebSocket и HTTP-контекста.

Предоставляет высокоуровневый канал взаимодействия с клиентом:
- Хранит паспортные данные пользователя (`session.data: SessionData`).
- Позволяет отправлять уведомления на фронтенд (`await session.notify(...)`).
- Управляет корректным отключением (`request_disconnect`) при смене прав пользователя:
  - дожидается завершения текущих атомарных (`return`) RPC-вызовов,
  - мгновенно и чисто закрывает долгоживущие потоковые (`yield`) генераторы.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from pyferro2.core.constants import WsCloseCode
from pyferro2.core.session_data import GUEST_SESSION_DATA, SessionData

# Сигнатура функции обратной связи для отправки событий клиенту (имя события, полезная нагрузка)
NotifyCallback = Callable[[str, Any], Awaitable[None]]
# Сигнатура функции закрытия транспортного соединения с кодом закрытия WS
CloseCallback = Callable[[int], Awaitable[None]]


class Session:
    """
    Контекст активной сессии клиента.
    """

    __slots__ = (
        "session_id",
        "data",
        "_guest_permissions",
        "_notify",
        "_close",
        "_active_rpcs",
        "_stream_tasks",
        "_closing_code",
        "_closed",
    )

    def __init__(
        self,
        session_id: str,
        data: SessionData = GUEST_SESSION_DATA,
        notify: NotifyCallback | None = None,
        close: CloseCallback | None = None,
        guest_permissions: frozenset[str] | None = None,
    ) -> None:
        if type(session_id) is not str or not session_id:
            raise ValueError("session_id должен быть непустой строкой")
        if type(data) is not SessionData:
            raise TypeError(f"data должен быть экземпляром SessionData, получено: {type(data).__name__}")
        if notify is not None and not callable(notify):
            raise TypeError("notify должен быть вызываемым объектом (async callback) или None")
        if close is not None and not callable(close):
            raise TypeError("close должен быть вызываемым объектом (async callback) или None")

        self.session_id: str = session_id
        self.data: SessionData = data
        if guest_permissions is not None:
            self._guest_permissions: frozenset[str] = frozenset(guest_permissions)
        elif data.is_guest:
            self._guest_permissions = data.permissions
        else:
            self._guest_permissions = GUEST_SESSION_DATA.permissions
        self._notify: NotifyCallback | None = notify
        self._close: CloseCallback | None = close
        self._active_rpcs: int = 0
        self._stream_tasks: set[asyncio.Task[Any]] = set()
        self._closing_code: int | None = None
        self._closed: bool = False

    @property
    def is_closing(self) -> bool:
        """Возвращает True, если сессии запрошен дисконнект (например, после смены прав)."""
        return self._closing_code is not None or self._closed

    def authenticate(self, new_data: SessionData) -> None:
        """
        Атомарно обновляет данные пользователя в живой сессии (после вызова `auth.login`).
        """
        if type(new_data) is not SessionData:
            raise TypeError(f"new_data должен быть экземпляром SessionData, получено: {type(new_data).__name__}")
        self.data = new_data

    def reset_to_guest(self, guest_permissions: frozenset[str] | None = None) -> None:
        """
        Сбрасывает сессию обратно в гостевое состояние (при вызове `auth.logout`),
        сохраняя актуальные разрешения роли `guest`.
        """
        if guest_permissions is not None:
            self._guest_permissions = frozenset(guest_permissions)
        self.data = SessionData.guest(self._guest_permissions)

    async def notify(self, event: str, payload: Any = None) -> None:
        """
        Отправляет асинхронное уведомление (JSON-RPC notification) на фронтенд.
        """
        if type(event) is not str or not event:
            raise ValueError("event должен быть непустой строкой")
        if not self._closed and self._notify is not None:
            await self._notify(event, payload)

    def begin_rpc(self) -> None:
        """Увеличивает счетчик активных атомарных (`return`) RPC-запросов."""
        self._active_rpcs += 1

    async def end_rpc(self) -> None:
        """
        Уменьшает счетчик активных атомарных RPC-запросов.
        Если был запрошен отложенный дисконнект и это был последний активный запрос —
        закрывает соединение.
        """
        if self._active_rpcs > 0:
            self._active_rpcs -= 1
        if self._active_rpcs == 0 and self._closing_code is not None and not self._closed:
            await self._execute_close(self._closing_code)

    def register_stream_task(self, task: asyncio.Task[Any]) -> None:
        """Регистрирует задачу мультиретурн-стрима (`yield`), чтобы прервать её при дисконнекте."""
        self._stream_tasks.add(task)
        task.add_done_callback(self._stream_tasks.discard)

    async def request_disconnect(self, code: int = WsCloseCode.POLICY_VIOLATION) -> None:
        """
        Запрашивает корректное отключение сессии (например, при смене ролей/прав пользователя):
        1. Останавливает все долгоживущие потоковые (`yield`) RPC.
        2. Если сейчас нет выполняющихся атомарных (`return`) RPC — закрывает сокет сразу.
        3. Если выполняется атомарный RPC — сокет закроется автоматически в `end_rpc()`,
           как только текущий вызов отправит свой ответ.
        """
        if self._closed:
            return
        self._closing_code = int(code)

        # Отменяем долгоживущие генераторы (мультиретурны), чтобы они не держали сокет
        for task in list(self._stream_tasks):
            if not task.done():
                task.cancel()

        if self._active_rpcs == 0:
            await self._execute_close(self._closing_code)

    async def _execute_close(self, code: int) -> None:
        if self._closed:
            return
        self._closed = True
        if self._close is not None:
            await self._close(code)
