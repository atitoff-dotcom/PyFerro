# -*- coding: utf-8 -*-
"""
Тесты изоляции системных таблиц фреймворка с префиксом pf_ (FerroApp(table_prefix="pf_")).
"""

import pytest
from pyferro import FerroApp, get_table_prefix
from pyferro.db import (
    Base,
    DEFAULT_TABLE_PREFIX,
    get_system_table_prefix,
    set_system_table_prefix,
    is_system_table_name,
)
from pyferro.auth import User, Role, RpcPermission, RolePermission, UserPermission, UserDelegation
from pyferro.auth.models import (
    UserRole, UserTeam, RoleRpcPermission, UserRpcPermission,
    Team, RefreshToken, ActiveSession, SystemData, OAuthAccount
)
from pyferro.smart_cache.engine import CacheTagVersion
from pyferro.plugins.files.models import StoredFile
from pyferro.plugins.crud import ModelRegistry


def test_default_system_table_names_prefix():
    """Проверка, что все таблицы фреймворка имеют префикс pf_ по умолчанию."""
    assert User.__tablename__ == "pf_auth_user"
    assert Role.__tablename__ == "pf_auth_role"
    assert Team.__tablename__ == "pf_auth_team"
    assert RpcPermission.__tablename__ == "pf_auth_rpc_permission"
    assert RolePermission.__tablename__ == "pf_auth_role_permission"
    assert UserPermission.__tablename__ == "pf_auth_user_permission"
    assert UserDelegation.__tablename__ == "pf_auth_user_delegation"
    assert UserRole.__tablename__ == "pf_auth_user_auth_role"
    assert UserTeam.__tablename__ == "pf_auth_user_auth_team"
    assert RoleRpcPermission.__tablename__ == "pf_auth_role_auth_rpc_permission"
    assert UserRpcPermission.__tablename__ == "pf_auth_user_auth_rpc_permission"
    assert RefreshToken.__tablename__ == "pf_refresh_tokens"
    assert ActiveSession.__tablename__ == "pf_active_sessions"
    assert SystemData.__tablename__ == "pf_system_data"
    assert OAuthAccount.__tablename__ == "pf_oauth_accounts"
    assert CacheTagVersion.__tablename__ == "pf_cache_tag_versions"
    assert StoredFile.__tablename__ == "pf_file_metadata"

    assert get_table_prefix() == "pf_"
    assert get_system_table_prefix() == "pf_"


def test_is_system_table_name_helper():
    """Проверка функции распознавания системных таблиц фреймворка."""
    assert is_system_table_name("pf_auth_user") is True
    assert is_system_table_name("pf_auth_role") is True
    assert is_system_table_name("pf_cache_tag_versions") is True
    assert is_system_table_name("pf_file_metadata") is True
    
    # Обратная совместимость с историческими именами без префикса
    assert is_system_table_name("auth_user") is True
    assert is_system_table_name("auth_role") is True
    assert is_system_table_name("file_metadata") is True

    # Пользовательские таблицы приложения
    assert is_system_table_name("tasks") is False
    assert is_system_table_name("documents") is False
    assert is_system_table_name("orders") is False


def test_crud_model_registry_lookup_with_prefix():
    """Проверка поиска моделей в ModelRegistry по ключевому имени, имени таблицы с pf_ и без него."""
    ModelRegistry.register(User)
    ModelRegistry.register(Role)

    # По имени класса
    assert ModelRegistry.get("User") is not None
    assert ModelRegistry.get("Role") is not None

    # По полному имени таблицы с префиксом pf_
    assert ModelRegistry.get("pf_auth_user") is not None
    assert ModelRegistry.get("pf_auth_role") is not None

    # По историческому имени без префикса
    assert ModelRegistry.get("auth_user") is not None
    assert ModelRegistry.get("auth_role") is not None


def test_ferroapp_table_prefix_configuration():
    """Проверка конфигурации FerroApp(table_prefix='...')."""
    app = FerroApp(secret_key="test-key-prefix-12345678901234567890", table_prefix="pf_")
    assert app is not None
    assert get_table_prefix() == "pf_"


def test_dynamic_table_prefix_switch():
    """Проверка динамического изменения префикса системных таблиц."""
    try:
        set_system_table_prefix("custom_")
        assert get_system_table_prefix() == "custom_"
        assert "custom_auth_user" in Base.metadata.tables
        assert Base.metadata.tables["custom_auth_user"].name == "custom_auth_user"
        assert is_system_table_name("custom_auth_user") is True
    finally:
        # Всегда возвращаем к стандарту pf_
        set_system_table_prefix("pf_")
        assert get_system_table_prefix() == "pf_"
        assert "pf_auth_user" in Base.metadata.tables
        assert Base.metadata.tables["pf_auth_user"].name == "pf_auth_user"
