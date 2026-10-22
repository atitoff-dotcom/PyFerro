# -*- coding: utf-8 -*-
"""
Базовая ревизия PyFerro v0.7.0.
Архитектурный базис:
- Префикс системных таблиц pf_ (17 системных таблиц).
- Роль guest и Default Deny CQRS.
- Гранулярные права read_global/update_global/delete_global, делегирование и owner_id в RowSecureModel.
"""

from pyferro.migrations.context import MigrationContext

VERSION = "0001_baseline_v0.7.0"
DESCRIPTION = "PyFerro v0.7.0 Baseline: pf_ system tables, guest CQRS and granular RLS"
DEPENDS_ON = None


async def pre_check(ctx: MigrationContext) -> bool:
    """Базовая ревизия всегда готова к наложению."""
    return True


async def upgrade(ctx: MigrationContext) -> None:
    """
    Базовый срез схемы. На чистой базе таблицы создаются через Base.metadata.create_all(),
    поэтому шаг является маркерным (no-op baseline).
    """
    await ctx.report_progress(100, "Базовая схема v0.7.0 зафиксирована.")


async def downgrade(ctx: MigrationContext) -> None:
    """Откат базовой схемы не предусмотрен (pre-v0.7.0 не поддерживается)."""
    pass