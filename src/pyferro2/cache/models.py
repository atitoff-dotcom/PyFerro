"""
Модели данных и структуры памяти для подсистемы автоматического кеширования и Offline-First в PyFerro 2.0 (`pyferro2/cache/models.py`).

Хранит глобальную конфигурацию (`pf_cache_config`) и правила для методов (`pf_cache_rules`) в базе данных
с горячим кэшем в оперативной памяти для доступа за O(1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.db.base import Base


class CacheConfigRecord(Base):
    """
    Таблица глобальных настроек подсистемы кеширования и оффлайна (`pf_cache_config`).
    Хранит единственную запись (`id = 1`).
    """

    __tablename__ = "pf_cache_config"

    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    liefi_timeout_ms: Mapped[int] = mapped_column(
        Integer, default=2500, server_default="2500", nullable=False
    )
    max_media_mb: Mapped[int] = mapped_column(
        Integer, default=250, server_default="250", nullable=False
    )
    max_rpc_entries: Mapped[int] = mapped_column(
        Integer, default=2000, server_default="2000", nullable=False
    )
    cache_epoch: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class CacheRuleRecord(Base):
    """
    Таблица правил кеширования и оффлайн-поведения для конкретных RPC-методов (`pf_cache_rules`).
    """

    __tablename__ = "pf_cache_rules"

    method_name: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    cache_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    strategy: Mapped[str] = mapped_column(
        String(16), default="auto", server_default="auto", nullable=False
    )  # "auto" | "ttl"
    ttl_sec: Mapped[int] = mapped_column(
        Integer, default=300, server_default="300", nullable=False
    )
    prefetch_media: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    preload_on_boot: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    offline_outbox: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_name": self.method_name,
            "cache_enabled": bool(self.cache_enabled),
            "strategy": self.strategy or "auto",
            "ttl_sec": int(self.ttl_sec),
            "prefetch_media": bool(self.prefetch_media),
            "preload_on_boot": bool(self.preload_on_boot),
            "offline_outbox": bool(self.offline_outbox),
        }


@dataclass(slots=True)
class CacheRule:
    """Предкомпилированное правило кеширования метода в оперативной памяти."""

    method_name: str
    cache_enabled: bool = False
    strategy: str = "auto"  # "auto" | "ttl"
    ttl_sec: int = 300
    prefetch_media: bool = False
    preload_on_boot: bool = False
    offline_outbox: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_name": self.method_name,
            "cache_enabled": self.cache_enabled,
            "strategy": self.strategy,
            "ttl_sec": self.ttl_sec,
            "prefetch_media": self.prefetch_media,
            "preload_on_boot": self.preload_on_boot,
            "offline_outbox": self.offline_outbox,
        }


@dataclass(slots=True)
class CacheConfig:
    """Глобальная конфигурация кеширования в оперативной памяти."""

    enabled: bool = True
    liefi_timeout_ms: int = 2500
    max_media_mb: int = 250
    max_rpc_entries: int = 2000
    cache_epoch: int = 1
    rules: dict[str, CacheRule] = field(default_factory=dict)

    def to_public_manifest(self) -> dict[str, Any]:
        """Возвращает компактный манифест политики кеширования для клиентского SDK (`IndexedDB`)."""
        active_rules: dict[str, dict[str, Any]] = {}
        for name, rule in self.rules.items():
            if rule.cache_enabled or rule.offline_outbox or rule.preload_on_boot or rule.prefetch_media:
                active_rules[name] = {
                    "c": 1 if rule.cache_enabled else 0,
                    "s": rule.strategy,
                    "t": rule.ttl_sec,
                    "m": 1 if rule.prefetch_media else 0,
                    "p": 1 if rule.preload_on_boot else 0,
                    "o": 1 if rule.offline_outbox else 0,
                }
        return {
            "enabled": self.enabled,
            "liefi_timeout_ms": self.liefi_timeout_ms,
            "max_media_mb": self.max_media_mb,
            "max_rpc_entries": self.max_rpc_entries,
            "cache_epoch": self.cache_epoch,
            "rules": active_rules,
        }
