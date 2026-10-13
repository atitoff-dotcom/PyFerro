# -*- coding: utf-8 -*-
"""
Официальный плагин авторизации и пользователей PyFerro (pyferro.plugins.auth).
Для обратной совместимости реэкспортирует подсистему ядра pyferro.auth.
"""

from pyferro.auth import *
from pyferro.auth import (
    models,
    core,
    config,
    discovery,
    permissions,
    handlers,
    permission_handlers,
    oauth,
    security,
)

__all__ = [
    # Контексты и базовые классы RLS
    "current_user_ctx",
    "system_bypass_ctx",
    "AuthSession",
    "BasicSecureModel",
    "RowSecureModel",
    "SecureModelBase",
    # Модели ORM
    "User",
    "Role",
    "RolePermission",
    "UserPermission",
    "RpcPermission",
    "UserRole",
    "RoleRpcPermission",
    "UserRpcPermission",
    "UserTeam",
    "RefreshToken",
    "ActiveSession",
    "OAuthAccount",
    "Team",
    "SystemData",
    # Service Discovery
    "sync_rpc_permissions",
    "reload_public_rpc_cache",
    # Проверки прав
    "check_permissions",
    "prefill_ownership",
    # Настройки
    "get_session_lifetime_days",
    "get_max_active_sessions",
    # Хендлеры и сессии
    "issue_refresh_token",
    "notify_session_change",
    "cleanup_app_session",
    "handle_ws_disconnect",
]
