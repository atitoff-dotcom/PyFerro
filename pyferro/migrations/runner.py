# -*- coding: utf-8 -*-
"""
Движок управления миграциями PyFerro (MigrationRunner).
Обеспечивает обнаружение шагов, учет ревизий, авто-бэкап и выполнение DDL/DML.

Архитектурный инвариант SemVer:
Субминорные обновления (Patch: 0.33.12 -> 0.33.16) физически гарантируют
отсутствие изменений схемы БД. Изменения схемы допускаются строго в минорных
или мажорных релизах (0.33 -> 0.34).
"""

from __future__ import annotations
import os
import re
import time
import importlib
import importlib.util
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy import text

from pyferro.core.logger import logger
from pyferro.db import engine as global_engine
from pyferro.migrations.context import MigrationContext
from pyferro.migrations.exceptions import (
    MigrationError,
    LegacyDatabaseError,
    MigrationVerificationError,
)

try:
    from pyferro import __version__ as FRAMEWORK_VERSION
except Exception:
    FRAMEWORK_VERSION = "0.7.0"

MIGRATIONS_TABLE = "pf_schema_migrations"
BASELINE_VERSION = "0001_baseline_v0.7.0"

LEGACY_FRAMEWORK_TABLES = {
    "auth_user",
    "auth_role",
    "auth_rpc_permission",
    "auth_role_permission",
    "auth_user_permission",
    "auth_team",
}


def parse_version_tuple(ver_str: str) -> tuple[int, int, int]:
    """
    Разбирает строку версии (например '0.7.0', 'v0.34.12', '0.33.16-dev') в кортеж (major, minor, patch).
    """
    if not ver_str:
        return (0, 0, 0)
    clean = re.sub(r"^[^\d]*", "", str(ver_str)).split("-")[0].split("+")[0]
    parts = clean.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return (0, 0, 0)


def is_patch_update(current_ver: str, target_ver: str) -> bool:
    """
    Проверяет, является ли обновление чисто субминорным (patch).
    Субминорные обновления (например, 0.33.12 -> 0.33.16) физически гарантируют
    отсутствие изменений схемы БД и не требуют миграции.
    """
    cur_maj, cur_min, _ = parse_version_tuple(current_ver)
    tgt_maj, tgt_min, _ = parse_version_tuple(target_ver)
    return (cur_maj, cur_min) == (tgt_maj, tgt_min)


def discover_migrations() -> List[ModuleType]:
    """
    Обнаруживает и упорядочивает все файлы версий из pyferro/migrations/versions.
    Использует importlib.util.spec_from_file_location для поддержки версий с точками
    в имени файла (например, 0001_baseline_v0.7.0.py).
    """
    versions_dir = os.path.join(os.path.dirname(__file__), "versions")
    if not os.path.exists(versions_dir):
        return []

    migration_modules: List[ModuleType] = []
    pattern = re.compile(r"^\d{4}_.*\.py$")

    files = sorted([f for f in os.listdir(versions_dir) if pattern.match(f)])
    for fname in files:
        fpath = os.path.join(versions_dir, fname)
        safe_mod_name = f"pyferro_mig_{fname[:-3].replace('.', '_')}"
        try:
            spec = importlib.util.spec_from_file_location(safe_mod_name, fpath)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "VERSION") and hasattr(mod, "upgrade"):
                    migration_modules.append(mod)
        except Exception as e:
            logger.error(f"[Migration] Ошибка импорта шага {fname}: {e}")
            raise MigrationError(f"Не удалось загрузить миграцию {fname}: {e}") from e

    return migration_modules


async def ensure_migrations_table(ctx: MigrationContext) -> None:
    """
    Гарантирует существование таблицы pf_schema_migrations.
    Если таблица создается впервые:
    - Проверяет схему на наличие устаревших pre-v0.7.0 таблиц (auth_user без pf_).
    - Если обнаружено легаси — прерывает работу с инструкцией для пользователя.
    - Если база пустая или уже в формате v0.7.0 — фиксирует baseline ревизию.
    """
    has_table = await ctx.has_table(MIGRATIONS_TABLE)
    if not has_table:
        sql = f"""
        CREATE TABLE {MIGRATIONS_TABLE} (
            version VARCHAR(64) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            execution_time_ms INTEGER,
            checksum VARCHAR(64),
            backup_path VARCHAR(255),
            app_version VARCHAR(32)
        )
        """
        await ctx.execute_raw(sql)
        logger.info(f"[Migration] Создана таблица учета миграций: {MIGRATIONS_TABLE}")

        # Проверяем существующие таблицы
        existing_tables = await ctx.get_table_names()
        user_tables = [t for t in existing_tables if t != MIGRATIONS_TABLE and not t.startswith("sqlite_")]

        if not user_tables:
            # 1. База полностью пустая -> фиксируем базовый baseline
            await ctx.execute_raw(
                f"INSERT INTO {MIGRATIONS_TABLE} (version, execution_time_ms, app_version) VALUES (:ver, 0, :app_ver)",
                {"ver": BASELINE_VERSION, "app_ver": FRAMEWORK_VERSION},
            )
            logger.info(f"[Migration] Чистая база данных. Зафиксирован baseline: {BASELINE_VERSION} (PyFerro v{FRAMEWORK_VERSION})")
            return

        # 2. Проверяем наличие префиксов pf_
        has_pf_tables = any(t.startswith("pf_") for t in user_tables)
        if has_pf_tables:
            await ctx.execute_raw(
                f"INSERT INTO {MIGRATIONS_TABLE} (version, execution_time_ms, app_version) VALUES (:ver, 0, :app_ver)",
                {"ver": BASELINE_VERSION, "app_ver": FRAMEWORK_VERSION},
            )
            logger.info(f"[Migration] Обнаружена база стандарта v0.7.0+. Зафиксирован baseline: {BASELINE_VERSION}")
            return

        # 3. Проверяем легаси-таблицы (до v0.7.0)
        has_legacy = any(t in LEGACY_FRAMEWORK_TABLES for t in user_tables)
        if has_legacy:
            raise LegacyDatabaseError(
                "❌ Обнаружена база данных устаревшей структуры (до v0.7.0 без префиксов pf_).\n"
                "Автоматический апгрейд с доисторических версий не поддерживается.\n"
                "👉 Используйте миграционный промпт docs/upgrades/ для ИИ-ассистента, "
                "чтобы привести схему к стандарту v0.7.0, либо начните с чистой базы."
            )

        # 4. В базе только пользовательские таблицы без системных таблиц фреймворка
        await ctx.execute_raw(
            f"INSERT INTO {MIGRATIONS_TABLE} (version, execution_time_ms, app_version) VALUES (:ver, 0, :app_ver)",
            {"ver": BASELINE_VERSION, "app_ver": FRAMEWORK_VERSION},
        )
    else:
        # Убеждаемся, что в существующей таблице есть колонка app_version
        if not await ctx.has_column(MIGRATIONS_TABLE, "app_version"):
            await ctx.add_column(MIGRATIONS_TABLE, "app_version", "VARCHAR(32)", nullable=True)

        # Бесшовная нормализация старого формата записи 0001_baseline_v070 -> 0001_baseline_v0.7.0
        try:
            await ctx.execute_raw(
                f"UPDATE {MIGRATIONS_TABLE} SET version = :new_ver WHERE version = :old_ver",
                {"new_ver": BASELINE_VERSION, "old_ver": "0001_baseline_v070"},
            )
        except Exception:
            pass

async def get_applied_migrations(ctx: MigrationContext) -> List[Dict[str, Any]]:
    """Возвращает список уже примененных миграций из БД."""
    if not await ctx.has_table(MIGRATIONS_TABLE):
        return []
    has_app_col = await ctx.has_column(MIGRATIONS_TABLE, "app_version")
    query = (
        f"SELECT version, applied_at, execution_time_ms, backup_path, app_version FROM {MIGRATIONS_TABLE} ORDER BY applied_at ASC"
        if has_app_col
        else f"SELECT version, applied_at, execution_time_ms, backup_path, NULL FROM {MIGRATIONS_TABLE} ORDER BY applied_at ASC"
    )
    res = await ctx.execute_raw(query)
    rows = res.fetchall()
    return [
        {
            "version": r[0],
            "applied_at": str(r[1]),
            "execution_time_ms": r[2],
            "backup_path": r[3],
            "app_version": r[4],
        }
        for r in rows
    ]


async def get_migration_status(engine: Optional[Any] = None) -> Dict[str, Any]:
    """
    Возвращает статус миграций: примененные, ожидающие, версии приложения и флаг актуальности.
    """
    target_engine = engine or global_engine
    async with target_engine.begin() as conn:
        ctx = MigrationContext(conn)
        await ensure_migrations_table(ctx)

        applied = await get_applied_migrations(ctx)
        applied_versions = {a["version"] for a in applied}

        all_modules = discover_migrations()
        pending = [
            {"version": m.VERSION, "description": getattr(m, "DESCRIPTION", "")}
            for m in all_modules
            if m.VERSION not in applied_versions
        ]

        latest_applied = applied[-1]["version"] if applied else None
        db_app_ver = applied[-1].get("app_version") if applied else None
        patch_compatible = is_patch_update(db_app_ver or FRAMEWORK_VERSION, FRAMEWORK_VERSION)

        return {
            "applied": applied,
            "pending": pending,
            "latest_applied": latest_applied,
            "framework_version": FRAMEWORK_VERSION,
            "db_app_version": db_app_ver,
            "is_patch_compatible": patch_compatible,
            "is_up_to_date": len(pending) == 0,
        }


async def run_migrations(
    engine: Optional[Any] = None,
    target_version: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], Any]] = None,
    create_backup: bool = True,
) -> List[str]:
    """
    Выполняет накат всех ожидающих миграций (или до target_version).
    Перед выполнением изменений автоматически создает резервный снимок (SQLite).
    Возвращает список успешно примененных версий.
    """
    target_engine = engine or global_engine
    applied_versions: List[str] = []

    async with target_engine.begin() as conn:
        ctx = MigrationContext(conn, progress_callback=progress_callback)
        await ensure_migrations_table(ctx)

        applied_records = await get_applied_migrations(ctx)
        applied_set = {r["version"] for r in applied_records}

        all_modules = discover_migrations()
        pending_modules = [m for m in all_modules if m.VERSION not in applied_set]

        if not pending_modules:
            db_app_ver = applied_records[-1].get("app_version") if applied_records else None
            if db_app_ver and is_patch_update(db_app_ver, FRAMEWORK_VERSION):
                logger.debug(
                    f"[Migration] Субминорный релиз ({db_app_ver} -> {FRAMEWORK_VERSION}): "
                    "схема БД инвариантна, миграции пропущены."
                )
            else:
                logger.info("[Migration] База данных уже находится в актуальном состоянии.")
            return []

        # Фильтр по target_version при необходимости
        if target_version:
            target_idx = None
            for idx, m in enumerate(pending_modules):
                if m.VERSION == target_version:
                    target_idx = idx
                    break
            if target_idx is None:
                raise MigrationError(f"Целевая миграция '{target_version}' не найдена в списке ожидающих.")
            pending_modules = pending_modules[: target_idx + 1]

        # 1. Автоматический снимок перед первой миграцией
        backup_path = None
        if create_backup:
            backup_path = await ctx.create_sqlite_snapshot()

        total = len(pending_modules)
        for i, mod in enumerate(pending_modules):
            pct_start = int((i / total) * 100)
            await ctx.report_progress(pct_start, f"Применение миграции {mod.VERSION}...")

            # Вызов предварительной проверки pre_check
            if hasattr(mod, "pre_check"):
                ok = await mod.pre_check(ctx)
                if not ok:
                    raise MigrationVerificationError(
                        f"Предварительная проверка (pre_check) миграции {mod.VERSION} завершилась неудачей."
                    )

            # Выполнение наката
            start_time = time.perf_counter()
            await mod.upgrade(ctx)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Запись в таблицу учета
            await ctx.execute_raw(
                f"""
                INSERT INTO {MIGRATIONS_TABLE} (version, execution_time_ms, backup_path, app_version)
                VALUES (:ver, :dur, :bpath, :app_ver)
                """,
                {
                    "ver": mod.VERSION,
                    "dur": duration_ms,
                    "bpath": backup_path,
                    "app_ver": FRAMEWORK_VERSION,
                },
            )

            applied_versions.append(mod.VERSION)
            pct_end = int(((i + 1) / total) * 100)
            await ctx.report_progress(pct_end, f"Миграция {mod.VERSION} успешно применена за {duration_ms} мс.")

    return applied_versions


async def rollback_migration(
    engine: Optional[Any] = None,
    steps: int = 1,
    progress_callback: Optional[Callable[[int, str], Any]] = None,
) -> List[str]:
    """
    Откатывает последние N примененных миграций (кроме базовой ревизии baseline).
    Возвращает список откатанных версий.
    """
    target_engine = engine or global_engine
    rolled_back: List[str] = []

    async with target_engine.begin() as conn:
        ctx = MigrationContext(conn, progress_callback=progress_callback)
        await ensure_migrations_table(ctx)

        applied = await get_applied_migrations(ctx)
        reversable = [r for r in applied if r["version"] != BASELINE_VERSION]
        if not reversable:
            logger.warning("[Migration] Нет миграций, доступных для отката.")
            return []

        to_rollback = list(reversed(reversable))[:steps]
        all_modules = {m.VERSION: m for m in discover_migrations()}

        for item in to_rollback:
            ver = item["version"]
            mod = all_modules.get(ver)
            if not mod or not hasattr(mod, "downgrade"):
                raise MigrationError(f"Миграция {ver} не имеет метода downgrade() для отката.")

            await ctx.report_progress(50, f"Откат миграции {ver}...")
            await mod.downgrade(ctx)

            await ctx.execute_raw(
                f"DELETE FROM {MIGRATIONS_TABLE} WHERE version = :ver",
                {"ver": ver},
            )
            rolled_back.append(ver)
            await ctx.report_progress(100, f"Миграция {ver} успешно откатана.")

    return rolled_back


async def stamp_version(version: str, engine: Optional[Any] = None) -> None:
    """Маркирует версию как примененную в БД без вызова upgrade()."""
    target_engine = engine or global_engine
    async with target_engine.begin() as conn:
        ctx = MigrationContext(conn)
        await ensure_migrations_table(ctx)
        await ctx.execute_raw(
            f"""
            INSERT INTO {MIGRATIONS_TABLE} (version, execution_time_ms, app_version)
            VALUES (:ver, 0, :app_ver)
            ON CONFLICT (version) DO NOTHING
            """,
            {"ver": version, "app_ver": FRAMEWORK_VERSION},
        )
