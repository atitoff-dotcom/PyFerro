"""
Легковесный асинхронный HTTP-клиент без сторонних библиотек.

Использует встроенный в Python `urllib.request` поверх `asyncio.to_thread`
и сверхбыструю сериализацию `orjson`.
"""

import asyncio
from typing import Any
import urllib.parse
import urllib.request
import orjson


def _sync_http_request(
    url: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    req_headers = {
        "User-Agent": "PyFerro2-Auth/1.0",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)

    target_url = url
    if params:
        query_str = urllib.parse.urlencode(params)
        target_url = f"{url}?{query_str}" if "?" not in url else f"{url}&{query_str}"

    encoded_data: bytes | None = None
    if data is not None:
        if req_headers.get("Content-Type") == "application/x-www-form-urlencoded":
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        else:
            req_headers.setdefault("Content-Type", "application/json; charset=utf-8")
            encoded_data = orjson.dumps(data)

    request = urllib.request.Request(
        target_url,
        data=encoded_data,
        headers=req_headers,
        method=method.upper(),
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as err:
        body = err.read()

    if not body:
        return {}
    try:
        return orjson.loads(body)
    except Exception:
        return {"raw": body.decode("utf-8", errors="replace")}

async def async_http_json(
    url: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Выполняет неблокирующий HTTP-запрос к внешнему API в пуле потоков."""
    return await asyncio.to_thread(
        _sync_http_request,
        url=url,
        method=method,
        params=params,
        data=data,
        headers=headers,
        timeout=timeout,
    )
