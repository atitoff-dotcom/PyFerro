# -*- coding: utf-8 -*-
"""
Официальный плагин интерактивной документации и справки PyFerro (plugins/help).
Включает WSRPC-обработчики справки, тесты API и веб-интерфейс /admin/help.
"""

from .handlers import (
    help_ping,
    help_echo,
    help_multi_output,
    help_tabular_demo,
    help_reverse_call,
    help_migration_status,
    help_migration_dry_run,
)
from .static_handler import serve_help_static
from .models import ForumCategory, ForumTopic, ForumPost

# Автоматическая регистрация моделей форума в CRUD
try:
    from pyferro.plugins.crud import ModelRegistry
    ModelRegistry.register(ForumCategory)
    ModelRegistry.register(ForumTopic)
    ModelRegistry.register(ForumPost)
except Exception:
    pass

__all__ = [
    "help_ping",
    "help_echo",
    "help_multi_output",
    "help_tabular_demo",
    "help_reverse_call",
    "help_migration_status",
    "help_migration_dry_run",
    "serve_help_static",
    "ForumCategory",
    "ForumTopic",
    "ForumPost",
]