# -*- coding: utf-8 -*-
import os
import pytest
import tempfile
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pyferro.migrations.context import MigrationContext
from pyferro.migrations.runner import (
    ensure_migrations_table,
    get_applied_migrations,
    get_migration_status,
    run_migrations,
    rollback_migration,
    stamp_version,
    BASELINE_VERSION,
    MIGRATIONS_TABLE,
)
from pyferro.migrations.exceptions import LegacyDatabaseError, MigrationError


@pytest.fixture
def tmp_sqlite():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite+aiosqlite:///{path}"
    test_engine = create_async_engine(db_url)
    yield test_engine, path
    # Cleanup
    asyncio.run(test_engine.dispose())
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_ensure_migrations_table_fresh_db(tmp_sqlite):
    test_engine, _ = tmp_sqlite
    async with test_engine.begin() as conn:
        ctx = MigrationContext(conn)
        assert not await ctx.has_table(MIGRATIONS_TABLE)
        await ensure_migrations_table(ctx)
        assert await ctx.has_table(MIGRATIONS_TABLE)

        applied = await get_applied_migrations(ctx)
        assert len(applied) == 1
        assert applied[0]["version"] == BASELINE_VERSION


@pytest.mark.asyncio
async def test_ensure_migrations_table_existing_pf_db(tmp_sqlite):
    test_engine, _ = tmp_sqlite
    async with test_engine.begin() as conn:
        ctx = MigrationContext(conn)
        # Симулируем существующую базу v0.7.0 с таблицей pf_auth_user
        await ctx.execute_raw("CREATE TABLE pf_auth_user (id INTEGER PRIMARY KEY, login VARCHAR(64))")
        await ensure_migrations_table(ctx)

        applied = await get_applied_migrations(ctx)
        assert len(applied) == 1
        assert applied[0]["version"] == BASELINE_VERSION


@pytest.mark.asyncio
async def test_legacy_database_detection_raises_error(tmp_sqlite):
    test_engine, _ = tmp_sqlite
    async with test_engine.begin() as conn:
        ctx = MigrationContext(conn)
        # Симулируем легаси базу (до v0.7.0) с таблицей auth_user без префикса pf_
        await ctx.execute_raw("CREATE TABLE auth_user (id INTEGER PRIMARY KEY, login VARCHAR(64))")

        with pytest.raises(LegacyDatabaseError) as exc_info:
            await ensure_migrations_table(ctx)
        assert "до v0.7.0" in str(exc_info.value)


@pytest.mark.asyncio
async def test_migration_context_ddl_helpers(tmp_sqlite):
    test_engine, _ = tmp_sqlite
    async with test_engine.begin() as conn:
        ctx = MigrationContext(conn)
        await ctx.execute_raw("CREATE TABLE test_items (id INTEGER PRIMARY KEY, title VARCHAR(100))")

        assert await ctx.has_table("test_items")
        assert not await ctx.has_table("non_existent")

        assert await ctx.has_column("test_items", "title")
        assert not await ctx.has_column("test_items", "description")

        # add_column
        await ctx.add_column("test_items", "description", "TEXT", default="none", nullable=True)
        assert await ctx.has_column("test_items", "description")

        # create_index
        await ctx.create_index("ix_items_title", "test_items", ["title"])
        assert await ctx.has_index("ix_items_title", "test_items")

        # drop_index
        await ctx.drop_index("ix_items_title")
        assert not await ctx.has_index("ix_items_title", "test_items")

        # rename_table
        await ctx.rename_table("test_items", "renamed_items")
        assert not await ctx.has_table("test_items")
        assert await ctx.has_table("renamed_items")


@pytest.mark.asyncio
async def test_migration_sqlite_snapshot_and_rotation(tmp_sqlite):
    test_engine, db_path = tmp_sqlite
    async with test_engine.begin() as conn:
        ctx = MigrationContext(conn)
        await ctx.execute_raw("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

        with tempfile.TemporaryDirectory() as bdir:
            snap1 = await ctx.create_sqlite_snapshot(backup_dir=bdir, max_backups=2)
            assert snap1 is not None and os.path.exists(snap1)

            # Создаем еще снимки для проверки ротации
            snap2 = await ctx.create_sqlite_snapshot(backup_dir=bdir, max_backups=2)
            snap3 = await ctx.create_sqlite_snapshot(backup_dir=bdir, max_backups=2)

            remaining = os.listdir(bdir)
            assert len(remaining) <= 2


@pytest.mark.asyncio
async def test_get_migration_status(tmp_sqlite):
    test_engine, _ = tmp_sqlite
    status = await get_migration_status(test_engine)
    assert "applied" in status
    assert "pending" in status
    assert status["is_up_to_date"] is True
    assert status["latest_applied"] == BASELINE_VERSION


@pytest.mark.asyncio
async def test_stamp_version(tmp_sqlite):
    test_engine, _ = tmp_sqlite
    await stamp_version("0002_custom_test", engine=test_engine)
    status = await get_migration_status(test_engine)
    versions = [a["version"] for a in status["applied"]]
    assert "0002_custom_test" in versions


def test_semver_patch_update_invariants():
    from pyferro.migrations.runner import parse_version_tuple, is_patch_update

    assert parse_version_tuple("0.7.0") == (0, 7, 0)
    assert parse_version_tuple("v0.33.16") == (0, 33, 16)
    assert parse_version_tuple("0.34.1-alpha") == (0, 34, 1)

    # Субминорные обновления (patch) внутри одной ветки не требуют миграции
    assert is_patch_update("0.33.12", "0.33.16") is True
    assert is_patch_update("0.7.0", "0.7.4") is True

    # Переход между минорными ветками требует миграции
    assert is_patch_update("0.33.12", "0.34.1") is False
    assert is_patch_update("0.7.0", "0.8.0") is False
    assert is_patch_update("0.7.0", "1.0.0") is False