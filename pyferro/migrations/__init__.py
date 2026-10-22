# -*- coding: utf-8 -*-
"""
Подсистема версионных миграций PyFerro (pyferro.migrations).
Обеспечивает безопасное обновление схемы базы данных, автоматические бэкапы
через нативный VACUUM INTO и учет примененных версий.
"""

from .context import MigrationContext
from .runner import (
    run_migrations,
    rollback_migration,
    get_migration_status,
    stamp_version,
    ensure_migrations_table,
    discover_migrations,
    BASELINE_VERSION,
    MIGRATIONS_TABLE,
)
from .exceptions import (
    MigrationError,
    LegacyDatabaseError,
    MigrationVerificationError,
)

__all__ = [
    "MigrationContext",
    "run_migrations",
    "rollback_migration",
    "get_migration_status",
    "stamp_version",
    "ensure_migrations_table",
    "discover_migrations",
    "BASELINE_VERSION",
    "MIGRATIONS_TABLE",
    "MigrationError",
    "LegacyDatabaseError",
    "MigrationVerificationError",
]