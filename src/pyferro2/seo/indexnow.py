"""
Асинхронная отправка уведомлений в поисковики (Яндекс, Bing) по протоколу IndexNow,
файловый буфер-пакетировщик и верификация ключа (`GET /<key>.txt`) в PyFerro 2.0.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse
import urllib.request

import orjson

from pyferro2.seo.models import get_seo_config

logger = logging.getLogger("pyferro2.seo.indexnow")

INDEXNOW_ENDPOINTS: tuple[str, ...] = (
    "https://api.indexnow.org/indexnow",
    "https://yandex.com/indexnow",
)


def _post_indexnow_sync(endpoint: str, payload_bytes: bytes, timeout: float = 10.0) -> int:
    """Синхронный POST-запрос с использованием `urllib.request` (без сторонних библиотек)."""
    req = urllib.request.Request(
        url=endpoint,
        data=payload_bytes,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status)


async def _send_indexnow_background(
    urls: list[str],
    host: str,
    key: str,
    key_location: str | None = None,
) -> None:
    """Фоновая корутина для отправки уведомлений по всем эндпоинтам IndexNow."""
    if not urls:
        return

    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location or f"https://{host}/{key}.txt",
        "urlList": urls,
    }
    payload_bytes = orjson.dumps(payload)

    for endpoint in INDEXNOW_ENDPOINTS:
        try:
            status = await asyncio.to_thread(_post_indexnow_sync, endpoint, payload_bytes)
            if status in (200, 202):
                logger.info("[INDEXNOW] Отправлено %d URL в %s (HTTP %d).", len(urls), endpoint, status)
            elif status == 429:
                logger.warning("[INDEXNOW] Лимит запросов превышен (HTTP 429) на %s.", endpoint)
            else:
                logger.warning("[INDEXNOW] Эндпоинт %s вернул HTTP %d.", endpoint, status)
        except Exception as exc:
            logger.warning("[INDEXNOW] Сбой при отправке в %s: %s", endpoint, exc)


def enqueue_indexnow_urls(urls: list[str], queue_file: str | None = None) -> int:
    """Добавляет URL в файловую очередь IndexNow в режиме append."""
    cfg = get_seo_config()
    target_file = queue_file or cfg.indexnow_queue_file
    if not target_file or not urls:
        return 0

    dir_name = os.path.dirname(target_file)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    count = 0
    with open(target_file, "a", encoding="utf-8") as f:
        for u in urls:
            u_clean = u.strip()
            if u_clean:
                f.write(u_clean + "\n")
                count += 1
    return count


async def flush_indexnow_queue(
    queue_file: str | None = None,
    host: str | None = None,
    key: str | None = None,
) -> int:
    """
    Атомарно забирает накопленную файловую очередь, дедуплицирует ссылки
    и отправляет пачками по 10 000 URL в IndexNow.
    """
    cfg = get_seo_config()
    actual_key = key or cfg.indexnow_key
    if not actual_key:
        return 0

    target_file = queue_file or cfg.indexnow_queue_file
    if not target_file or not os.path.exists(target_file):
        return 0

    processing_file = f"{target_file}.processing.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        os.replace(target_file, processing_file)
    except FileNotFoundError:
        return 0
    except OSError:
        return 0

    unique_urls: list[str] = []
    seen: set[str] = set()
    try:
        with open(processing_file, "r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if u and u not in seen:
                    seen.add(u)
                    unique_urls.append(u)
    finally:
        try:
            os.remove(processing_file)
        except OSError:
            pass

    if not unique_urls:
        return 0

    if not host:
        parsed = urlparse(cfg.site_url)
        actual_host = parsed.netloc or cfg.site_url
    else:
        actual_host = host

    for i in range(0, len(unique_urls), 10_000):
        batch = unique_urls[i : i + 10_000]
        await _send_indexnow_background(batch, actual_host, actual_key)

    return len(unique_urls)


def notify_indexnow(
    urls: str | list[str],
    host: str | None = None,
    key: str | None = None,
) -> Any:
    """
    Отправляет список добавленных или измененных URL в Яндекс и Bing по протоколу IndexNow.
    """
    if isinstance(urls, str):
        url_list = [urls]
    else:
        url_list = list(urls)

    cfg = get_seo_config()
    actual_key = key or cfg.indexnow_key
    if not actual_key or not url_list:
        try:
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            fut.set_result(0)
            return fut
        except RuntimeError:
            return 0

    if cfg.indexnow_queue_file is not None:
        enqueue_indexnow_urls(url_list, cfg.indexnow_queue_file)
        try:
            if os.path.exists(cfg.indexnow_queue_file):
                if os.path.getsize(cfg.indexnow_queue_file) > cfg.indexnow_max_queue_size * 50:
                    loop = asyncio.get_running_loop()
                    return loop.create_task(flush_indexnow_queue(host=host, key=actual_key))
        except Exception:
            pass

        try:
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            fut.set_result(len(url_list))
            return fut
        except RuntimeError:
            return len(url_list)

    if not host:
        parsed = urlparse(cfg.site_url)
        actual_host = parsed.netloc or cfg.site_url
    else:
        actual_host = host

    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(_send_indexnow_background(url_list, actual_host, actual_key))
    except RuntimeError:
        return None
