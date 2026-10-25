# -*- coding: utf-8 -*-
"""
pyferro.plugins.seo.page_cache: LRU TTL-кэш для SEO-страниц и отрицательный кэш промахов.
"""

from __future__ import annotations
from collections import OrderedDict
import os
import time
from typing import Any, Tuple, Optional


class TTLCache:
    """
    Ограниченный по размеру LRU-кэш с поддержкой индивидуального TTL.
    Потокобезопасность не требуется (один event loop).
    Поддерживает отрицательный кэш (сохранение None).
    """

    def __init__(self, max_entries: int = 5000):
        self.max_entries = max_entries
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Tuple[bool, Any]:
        """
        Возвращает (found: bool, value: Any).
        Если записи нет или она просрочена: (False, None).
        Если в кэше сохранён None (отрицательный кэш): (True, None).
        При попадании обновляет позицию в LRU (перемещает в конец).
        """
        if key not in self._cache:
            return False, None

        expires_at, value = self._cache[key]
        now = time.monotonic()
        if now >= expires_at:
            del self._cache[key]
            return False, None

        self._cache.move_to_end(key)
        return True, value

    def set(self, key: str, value: Any, ttl: float) -> None:
        """
        Сохраняет значение с заданным TTL (в секундах).
        Ключи длиннее 512 символов игнорируются для защиты памяти.
        При превышении max_entries вытесняет самую старую запись (LRU).
        """
        if ttl <= 0 or len(key) > 512:
            return

        if key in self._cache:
            del self._cache[key]

        while len(self._cache) >= self.max_entries:
            self._cache.popitem(last=False)

        self._cache[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        """Очищает кэш."""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# Чтение настроек из окружения
SEO_CACHE_TTL = float(os.getenv("SEO_CACHE_TTL", "60"))
SEO_CACHE_NEGATIVE_TTL = float(os.getenv("SEO_CACHE_NEGATIVE_TTL", "30"))
SEO_CACHE_MAX_ENTRIES = int(os.getenv("SEO_CACHE_MAX_ENTRIES", "5000"))

_GLOBAL_CACHE = TTLCache(max_entries=SEO_CACHE_MAX_ENTRIES)


def get_cached(path: str) -> Tuple[bool, Any]:
    """Получить закэшированные данные для пути."""
    if SEO_CACHE_TTL <= 0:
        return False, None
    return _GLOBAL_CACHE.get(path)


def set_cached(path: str, value: Any) -> None:
    """
    Сохранить данные страницы или промах (None) в кэш.
    Автоматически выбирает TTL: SEO_CACHE_NEGATIVE_TTL для None, SEO_CACHE_TTL для объекта.
    """
    if SEO_CACHE_TTL <= 0:
        return
    ttl = SEO_CACHE_NEGATIVE_TTL if value is None else SEO_CACHE_TTL
    _GLOBAL_CACHE.set(path, value, ttl)


def clear_seo_cache() -> None:
    """Полная очистка SEO-кэша."""
    _GLOBAL_CACHE.clear()


__all__ = [
    "TTLCache",
    "SEO_CACHE_TTL",
    "SEO_CACHE_NEGATIVE_TTL",
    "SEO_CACHE_MAX_ENTRIES",
    "get_cached",
    "set_cached",
    "clear_seo_cache",
]
