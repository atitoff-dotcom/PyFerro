"""
Утилиты и мок-протоколы для тестирования RSGI-приложений (`PyFerroApp`).

Предоставляет in-memory реализацию спецификации RSGI (Rust Server-Gateway Interface):
- `MockRSGIScope` — имитирует RSGI scope (HTTP и WebSocket).
- `MockRSGIHTTPProtocol` — реализует нативные методы RSGIHTTPProtocol (`response_bytes`, `response_file`, `response_empty`).
- `MockRSGIWebsocketProtocol` и `MockRSGIWebsocketTransport` — реализуют полнодуплексный обмен WS-сообщениями.
- `call_rsgi_http` — лаконичный тестовый хелпер для вызова HTTP-маршрутов.
"""

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from granian.rsgi import WebsocketMessage, WebsocketMessageType

from pyferro2.core.session_data import SessionData


class MockRSGIScope:
    """Имитирует RSGI Scope для HTTP и WebSocket запросов."""

    __slots__ = (
        "proto",
        "method",
        "path",
        "query_string",
        "headers",
        "client",
        "server",
        "scheme",
        "http_version",
        "rsgi_version",
        "session_data",
        "_dict",
    )

    def __init__(
        self,
        proto: str,
        path: str,
        *,
        method: str = "GET",
        query_string: str = "",
        headers: dict[str, str] | list[tuple[str, str]] | list[tuple[bytes, bytes]] | None = None,
        client: str = "127.0.0.1:50000",
        server: str = "127.0.0.1:8080",
        scheme: str = "http",
        http_version: str = "1.1",
        rsgi_version: str = "1.4",
        session_data: SessionData | None = None,
    ) -> None:
        self.proto: str = proto
        self.method: str = method
        self.path: str = path
        self.query_string: str = query_string
        self.client: str = client
        self.server: str = server
        self.scheme: str = scheme
        self.http_version: str = http_version
        self.rsgi_version: str = rsgi_version
        self.session_data: SessionData | None = session_data
        self._dict: dict[str, Any] = {}

        norm_headers: dict[str, str] = {}
        if isinstance(headers, dict):
            norm_headers = {k.lower(): v for k, v in headers.items()}
        elif isinstance(headers, list):
            for k, v in headers:
                k_str = k.decode("latin-1").lower() if isinstance(k, bytes) else str(k).lower()
                v_str = v.decode("latin-1") if isinstance(v, bytes) else str(v)
                norm_headers[k_str] = v_str
        self.headers: dict[str, str] = norm_headers

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        return self._dict[item]

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self._dict[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self._dict.get(key, default)


class MockRSGIHTTPProtocol:
    """Мок RSGIHTTPProtocol для in-memory выполнения HTTP-запросов."""

    __slots__ = ("body_chunks", "status", "headers", "body", "file_path")

    def __init__(self, body_chunks: list[bytes] | None = None) -> None:
        self.body_chunks: list[bytes] = list(body_chunks or [b""])
        self.status: int = 200
        self.headers: list[tuple[str, str]] = []
        self.body: bytes = b""
        self.file_path: str | None = None

    async def __call__(self) -> bytes:
        return b"".join(self.body_chunks)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.body_chunks:
            if chunk:
                yield chunk

    async def client_disconnect(self) -> None:
        pass

    def response_empty(self, status: int, headers: list[tuple[str, str]]) -> None:
        self.status = status
        self.headers = list(headers)
        self.body = b""

    def response_bytes(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
        self.status = status
        self.headers = list(headers)
        self.body = body

    def response_str(self, status: int, headers: list[tuple[str, str]], body: str) -> None:
        self.status = status
        self.headers = list(headers)
        self.body = body.encode("utf-8")

    def response_file(self, status: int, headers: list[tuple[str, str]], file: str) -> None:
        self.status = status
        self.headers = list(headers)
        self.file_path = file
        with open(file, "rb") as f:
            self.body = f.read()

    def response_file_range(
        self, status: int, headers: list[tuple[str, str]], file: str, start: int, end: int
    ) -> None:
        self.status = status
        self.headers = list(headers)
        self.file_path = file
        with open(file, "rb") as f:
            f.seek(start)
            self.body = f.read(end - start)


class MockRSGIWebsocketTransport:
    """Имитирует RSGIWebsocketTransport."""

    __slots__ = ("incoming", "sent_messages", "closed", "_event")

    def __init__(self, incoming: list[WebsocketMessage] | deque[WebsocketMessage]) -> None:
        self.incoming: deque[WebsocketMessage] = deque(incoming)
        self.sent_messages: list[str | bytes] = []
        self.closed: bool = False
        self._event: asyncio.Event = asyncio.Event()

    async def receive(self) -> WebsocketMessage:
        while not self.incoming and not self.closed:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=0.02)
            except asyncio.TimeoutError:
                pass
        if self.incoming:
            return self.incoming.popleft()
        msg = WebsocketMessage()
        msg.kind = WebsocketMessageType.close
        msg.data = ""
        return msg

    async def send_str(self, data: str) -> None:
        self.sent_messages.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.sent_messages.append(data)


class MockRSGIWebsocketProtocol:
    """Имитирует RSGIWebsocketProtocol."""

    __slots__ = ("transport", "accepted", "close_code")

    def __init__(self, incoming_messages: list[WebsocketMessage] | deque[WebsocketMessage]) -> None:
        self.transport = MockRSGIWebsocketTransport(incoming_messages)
        self.accepted: bool = False
        self.close_code: int | None = None

    async def accept(self) -> MockRSGIWebsocketTransport:
        self.accepted = True
        return self.transport

    def close(self, status: int | None) -> tuple[int, bool]:
        self.close_code = status
        self.transport.closed = True
        self.transport._event.set()
        return (status or 1000, True)


def make_ws_message(data: str | bytes) -> WebsocketMessage:
    """Создает WebsocketMessage для текстовых или бинарных фреймов."""
    msg = WebsocketMessage()
    if isinstance(data, bytes):
        msg.kind = WebsocketMessageType.bytes
    else:
        msg.kind = WebsocketMessageType.string
    msg.data = data
    return msg


def make_ws_close() -> WebsocketMessage:
    """Создает WebsocketMessage с событием закрытия соединения."""
    msg = WebsocketMessage()
    msg.kind = WebsocketMessageType.close
    msg.data = ""
    return msg


async def call_rsgi_http(
    app: Any,
    method: str,
    path: str,
    *,
    query_string: str = "",
    headers: dict[str, str] | list[tuple[str, str]] | list[tuple[bytes, bytes]] | None = None,
    body_chunks: list[bytes] | None = None,
) -> tuple[int, dict[str, str], bytes, MockRSGIScope]:
    """Вспомогательный клиент для прямого вызова HTTP-маршрутов RSGI-сервера."""
    scope = MockRSGIScope(
        proto="http",
        path=path,
        method=method,
        query_string=query_string,
        headers=headers,
    )
    proto = MockRSGIHTTPProtocol(body_chunks=body_chunks)
    await app(scope, proto)
    resp_headers_dict: dict[str, str] = {k.lower(): v for k, v in proto.headers}
    return proto.status, resp_headers_dict, proto.body, scope
