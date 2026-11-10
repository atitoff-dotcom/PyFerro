"""
Менеджер серверного L1-кеша, авто-трекинга таблиц SQLAlchemy, ETag и идемпотентности мутаций (`pyferro2/cache/manager.py`).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextvars import ContextVar, Token
from dataclasses import dataclass
import hashlib
import time
from typing import Any, Callable, Coroutine

import orjson
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.cache.models import (
    CacheConfig,
    CacheConfigRecord,
    CacheRule,
    CacheRuleRecord,
)

# Контекстная переменная для отслеживания таблиц БД, прочитанных в рамках текущего RPC-вызова
_active_table_tracker: ContextVar[set[str] | None] = ContextVar(
    "_active_table_tracker", default=None
)


def start_table_tracking() -> tuple[set[str], Token[set[str] | None]]:
    """Включает сбор имен таблиц, к которым обращаются SELECT-запросы в текущем контексте."""
    tracked: set[str] = set()
    token = _active_table_tracker.set(tracked)
    return tracked, token


def stop_table_tracking(token: Token[set[str] | None]) -> None:
    """Завершает сбор имен таблиц в текущем контексте."""
    _active_table_tracker.reset(token)


def record_read_table(table_name: str) -> None:
    """Фиксирует чтение из таблицы `table_name`, если трекинг активен."""
    tracker = _active_table_tracker.get()
    if tracker is not None and table_name and not table_name.startswith("pf_"):
        tracker.add(table_name)


def compute_etag(data: Any) -> str:
    """Вычисляет быстрый 64-битный ETag (16 hex-символов) через BLAKE2b от сериализованного JSON."""
    try:
        raw = orjson.dumps(data, option=orjson.OPT_SORT_KEYS)
    except Exception:
        raw = str(data).encode("utf-8", errors="ignore")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()


def make_canonical_params(params: dict[str, Any] | list[Any] | None) -> str:
    """Возвращает каноническое строковое представление параметров вызова для ключа кеша."""
    if not params:
        return "{}"
    try:
        return orjson.dumps(params, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    except Exception:
        return str(params)


@dataclass(slots=True)
class ServerCacheEntry:
    """Запись в серверном L1-кеше (RAM)."""

    cache_key: str
    method_name: str
    scope: str  # "public" | "user"
    user_id: int | None
    result: Any
    etag: str
    tables: frozenset[str]
    created_at: float
    expires_at: float


BroadcastCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class CacheManager:
    """
    Высокоскоростной in-memory движок кеширования, ETag-валидации и реактивной инвалидации.
    """

    def __init__(self, max_l1_entries: int = 4096) -> None:
        self.config: CacheConfig = CacheConfig()
        self.max_l1_entries: int = max_l1_entries
        self._l1: OrderedDict[str, ServerCacheEntry] = OrderedDict()
        self._table_to_keys: dict[str, set[str]] = {}
        self._table_to_methods: dict[str, set[str]] = {}
        self._method_to_keys: dict[str, set[str]] = {}
        self._idempotency: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_idempotency: int = 2048
        self._idempotency_ttl: float = 900.0  # 15 минут
        self.hits: int = 0
        self.misses: int = 0
        self.not_modified_hits: int = 0
        self.invalidations: int = 0
        self._broadcast_cb: BroadcastCallback | None = None

    def set_broadcast_callback(self, cb: BroadcastCallback | None) -> None:
        """Устанавливает функцию широковещательной рассылки событий всем WebSocket-сессиям."""
        self._broadcast_cb = cb

    def get_rule(self, method_name: str) -> CacheRule | None:
        """Мгновенно возвращает правило для метода за O(1)."""
        if not self.config.enabled:
            return None
        return self.config.rules.get(method_name)

    def build_cache_key(
        self,
        method_name: str,
        scope: str,
        user_id: int | None,
        params: dict[str, Any] | list[Any] | None,
    ) -> str:
        uid_part = str(user_id or 0) if scope == "user" else "0"
        return f"{scope}:{uid_part}:{method_name}:{make_canonical_params(params)}"

    def get_entry(self, cache_key: str) -> ServerCacheEntry | None:
        """Возвращает запись из L1-кеша (проверяя срок действия для стратегии 'ttl')."""
        if not self.config.enabled:
            return None
        entry = self._l1.get(cache_key)
        if entry is None:
            self.misses += 1
            return None
        now = time.monotonic()
        rule = self.config.rules.get(entry.method_name)
        if rule is not None and rule.strategy == "ttl" and now > entry.expires_at:
            self._remove_key(cache_key)
            self.misses += 1
            return None
        self._l1.move_to_end(cache_key)
        self.hits += 1
        return entry

    def put_entry(
        self,
        cache_key: str,
        method_name: str,
        scope: str,
        user_id: int | None,
        result: Any,
        tables: set[str],
        ttl_sec: int = 300,
    ) -> ServerCacheEntry:
        """Сохраняет результат выполнения RPC-метода в серверный L1-кеш и связывает его с таблицами БД."""
        now = time.monotonic()
        etag = compute_etag(result)
        frozen_tables = frozenset(tables)
        entry = ServerCacheEntry(
            cache_key=cache_key,
            method_name=method_name,
            scope=scope,
            user_id=user_id,
            result=result,
            etag=etag,
            tables=frozen_tables,
            created_at=now,
            expires_at=now + max(1, ttl_sec),
        )
        if cache_key in self._l1:
            self._remove_key(cache_key)

        self._l1[cache_key] = entry
        self._method_to_keys.setdefault(method_name, set()).add(cache_key)
        for tbl in frozen_tables:
            self._table_to_keys.setdefault(tbl, set()).add(cache_key)
            self._table_to_methods.setdefault(tbl, set()).add(method_name)

        while len(self._l1) > self.max_l1_entries:
            oldest_key, _ = next(iter(self._l1.items()))
            self._remove_key(oldest_key)

        return entry

    def _remove_key(self, cache_key: str) -> None:
        entry = self._l1.pop(cache_key, None)
        if entry is None:
            return
        m_keys = self._method_to_keys.get(entry.method_name)
        if m_keys is not None:
            m_keys.discard(cache_key)
        for tbl in entry.tables:
            t_keys = self._table_to_keys.get(tbl)
            if t_keys is not None:
                t_keys.discard(cache_key)

    def invalidate_tables(self, mutated_tables: set[str] | frozenset[str]) -> list[str]:
        """
        Сбрасывает все записи L1-кеша, которые читали из измененных таблиц `mutated_tables`.
        Возвращает список затронутых RPC-методов и инициирует WebSocket-рассылку `$cache.invalidate`.
        """
        if not mutated_tables:
            return []

        affected_methods: set[str] = set()
        keys_to_remove: set[str] = set()

        for tbl in mutated_tables:
            if tbl.startswith("pf_"):
                continue
            t_keys = self._table_to_keys.get(tbl)
            if t_keys:
                keys_to_remove.update(t_keys)
            t_methods = self._table_to_methods.get(tbl)
            if t_methods:
                affected_methods.update(t_methods)

        for k in keys_to_remove:
            self._remove_key(k)

        if keys_to_remove or affected_methods:
            self.invalidations += 1

        methods_list = sorted(affected_methods)
        if methods_list and self._broadcast_cb is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._broadcast_cb(
                        "$cache.invalidate",
                        {
                            "methods": methods_list,
                            "tables": sorted(t for t in mutated_tables if not t.startswith("pf_")),
                            "epoch": self.config.cache_epoch,
                        },
                    )
                )
            except RuntimeError:
                pass

        return methods_list

    def invalidate_methods(self, method_names: list[str] | set[str]) -> None:
        """Принудительно очищает L1-кеш для указанных методов."""
        keys_to_remove: set[str] = set()
        for m in method_names:
            m_keys = self._method_to_keys.get(m)
            if m_keys:
                keys_to_remove.update(m_keys)
        for k in keys_to_remove:
            self._remove_key(k)

    def clear_l1(self) -> None:
        """Полная очистка серверного L1-кеша."""
        self._l1.clear()
        self._table_to_keys.clear()
        self._method_to_keys.clear()

    def check_idempotency(self, key: str) -> tuple[bool, Any]:
        """Проверяет, выполнялась ли уже мутация с данным `$idempotency_key`."""
        if not key:
            return False, None
        now = time.monotonic()
        item = self._idempotency.get(key)
        if item is None:
            return False, None
        expires_at, saved_result = item
        if now > expires_at:
            self._idempotency.pop(key, None)
            return False, None
        self._idempotency.move_to_end(key)
        return True, saved_result

    def save_idempotency(self, key: str, result: Any) -> None:
        """Сохраняет результат успешной мутации по `$idempotency_key`."""
        if not key:
            return
        now = time.monotonic()
        self._idempotency[key] = (now + self._idempotency_ttl, result)
        self._idempotency.move_to_end(key)
        while len(self._idempotency) > self._max_idempotency:
            self._idempotency.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        """Возвращает статистику работы серверного L1-кеша для панели управления."""
        total = self.hits + self.misses
        hit_rate = round((self.hits / total) * 100, 1) if total > 0 else 0.0
        return {
            "l1_entries": len(self._l1),
            "tracked_tables": sorted(self._table_to_methods.keys()),
            "hits": self.hits,
            "misses": self.misses,
            "not_modified_hits": self.not_modified_hits,
            "invalidations": self.invalidations,
            "hit_rate_pct": hit_rate,
            "cache_epoch": self.config.cache_epoch,
        }


# Глобальный синглтон менеджера кеша
cache_manager = CacheManager()


async def load_cache_from_db(session: AsyncSession) -> CacheConfig:
    """
    Загружает глобальные настройки (`pf_cache_config`) и правила методов (`pf_cache_rules`)
    из БД в оперативную память `cache_manager`.
    """
    cfg_row = (await session.execute(select(CacheConfigRecord).where(CacheConfigRecord.id == 1))).scalar_one_or_none()
    if cfg_row is None:
        cfg_row = CacheConfigRecord(
            id=1,
            enabled=True,
            liefi_timeout_ms=2500,
            max_media_mb=250,
            max_rpc_entries=2000,
            cache_epoch=1,
        )
        session.add(cfg_row)
        await session.commit()

    rule_rows = (await session.execute(select(CacheRuleRecord))).scalars().all()
    rules_map: dict[str, CacheRule] = {}
    for r in rule_rows:
        rules_map[r.method_name] = CacheRule(
            method_name=r.method_name,
            cache_enabled=bool(r.cache_enabled),
            strategy=r.strategy or "auto",
            ttl_sec=int(r.ttl_sec),
            prefetch_media=bool(r.prefetch_media),
            preload_on_boot=bool(r.preload_on_boot),
            offline_outbox=bool(r.offline_outbox),
        )

    cache_manager.config = CacheConfig(
        enabled=bool(cfg_row.enabled),
        liefi_timeout_ms=int(cfg_row.liefi_timeout_ms),
        max_media_mb=int(cfg_row.max_media_mb),
        max_rpc_entries=int(cfg_row.max_rpc_entries),
        cache_epoch=int(cfg_row.cache_epoch),
        rules=rules_map,
    )
    return cache_manager.config


async def save_cache_to_db(
    session: AsyncSession,
    config_data: dict[str, Any],
    rules_list: list[dict[str, Any]],
) -> CacheConfig:
    """
    Атомарно сохраняет глобальные настройки и правила методов в БД,
    обновляет in-memory конфигурацию и рассылает обновленный манифест клиентам.
    """
    cfg_row = (await session.execute(select(CacheConfigRecord).where(CacheConfigRecord.id == 1))).scalar_one_or_none()
    if cfg_row is None:
        cfg_row = CacheConfigRecord(id=1)
        session.add(cfg_row)

    cfg_row.enabled = bool(config_data.get("enabled", True))
    cfg_row.liefi_timeout_ms = max(500, min(30000, int(config_data.get("liefi_timeout_ms", 2500))))
    cfg_row.max_media_mb = max(10, min(2048, int(config_data.get("max_media_mb", 250))))
    cfg_row.max_rpc_entries = max(100, min(50000, int(config_data.get("max_rpc_entries", 2000))))

    await session.execute(delete(CacheRuleRecord))

    new_rules_map: dict[str, CacheRule] = {}
    for item in rules_list:
        m_name = str(item.get("method_name", "")).strip()
        if not m_name:
            continue
        c_enabled = bool(item.get("cache_enabled", False))
        strategy = str(item.get("strategy", "auto")).strip().lower()
        if strategy not in ("auto", "ttl"):
            strategy = "auto"
        ttl_sec = max(1, min(604800, int(item.get("ttl_sec", 300))))
        prefetch_media = bool(item.get("prefetch_media", False))
        preload_on_boot = bool(item.get("preload_on_boot", False))
        offline_outbox = bool(item.get("offline_outbox", False))

        if c_enabled or prefetch_media or preload_on_boot or offline_outbox:
            rec = CacheRuleRecord(
                method_name=m_name,
                cache_enabled=c_enabled,
                strategy=strategy,
                ttl_sec=ttl_sec,
                prefetch_media=prefetch_media,
                preload_on_boot=preload_on_boot,
                offline_outbox=offline_outbox,
            )
            session.add(rec)
            new_rules_map[m_name] = CacheRule(
                method_name=m_name,
                cache_enabled=c_enabled,
                strategy=strategy,
                ttl_sec=ttl_sec,
                prefetch_media=prefetch_media,
                preload_on_boot=preload_on_boot,
                offline_outbox=offline_outbox,
            )

    await session.commit()

    cache_manager.config = CacheConfig(
        enabled=bool(cfg_row.enabled),
        liefi_timeout_ms=int(cfg_row.liefi_timeout_ms),
        max_media_mb=int(cfg_row.max_media_mb),
        max_rpc_entries=int(cfg_row.max_rpc_entries),
        cache_epoch=int(cfg_row.cache_epoch),
        rules=new_rules_map,
    )
    cache_manager.clear_l1()

    if cache_manager._broadcast_cb is not None:
        await cache_manager._broadcast_cb(
            "$cache.config_updated",
            cache_manager.config.to_public_manifest(),
        )

    return cache_manager.config


async def purge_all_cache(session: AsyncSession) -> int:
    """
    Очищает серверный L1-кеш, увеличивает `cache_epoch` в БД и рассылает сигнал `$cache.purge` всем клиентам.
    """
    cfg_row = (await session.execute(select(CacheConfigRecord).where(CacheConfigRecord.id == 1))).scalar_one_or_none()
    if cfg_row is None:
        cfg_row = CacheConfigRecord(id=1, cache_epoch=2)
        session.add(cfg_row)
    else:
        cfg_row.cache_epoch = int(cfg_row.cache_epoch) + 1

    await session.commit()
    cache_manager.config.cache_epoch = int(cfg_row.cache_epoch)
    cache_manager.clear_l1()

    if cache_manager._broadcast_cb is not None:
        await cache_manager._broadcast_cb(
            "$cache.purge",
            {"cache_epoch": cache_manager.config.cache_epoch},
        )

    return cache_manager.config.cache_epoch
