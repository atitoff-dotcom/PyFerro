# -*- coding: utf-8 -*-
"""
Официальный плагин авторизации и пользователей PyFerro (plugins/auth).
Предоставляет модели User/Role, сессии, токены, Row-Level Security и RPC-методы авторизации.
"""

from .core import (
    current_user_ctx,
    system_bypass_ctx,
    AuthSession,
    BasicSecureModel,
    RowSecureModel,
)
from .models import (
    User,
    Role,
    RolePermission,
    UserPermission,
    RpcPermission,
    UserRole,
    RoleRpcPermission,
    UserRpcPermission,
    UserTeam,
    RefreshToken,
    ActiveSession,
    OAuthAccount,
    Team,
    SystemData,
    UserDelegation,
)
from .discovery import (
    sync_rpc_permissions,
    reload_guest_permissions_cache,
    ensure_system_roles,
)
from .permissions import (
    check_permissions,
    prefill_ownership,
)
from .config import (
    get_session_lifetime_days,
    get_max_active_sessions,
)
from .handlers import (
    issue_refresh_token,
    notify_session_change,
    cleanup_app_session,
    handle_ws_disconnect,
)
from . import permission_handlers
from .auditor import (
    LiveWsAuditClient,
    audit_target_permissions,
    reload_active_sessions_permissions,
)

__all__ = [
    # Контексты и базовые классы RLS
    "current_user_ctx",
    "system_bypass_ctx",
    "AuthSession",
    "BasicSecureModel",
    "RowSecureModel",
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
    "UserDelegation",
    # Service Discovery
    "sync_rpc_permissions",
    "reload_guest_permissions_cache",
    "reload_active_sessions_permissions",
    "ensure_system_roles",
    "LiveWsAuditClient",
    "audit_target_permissions",
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
