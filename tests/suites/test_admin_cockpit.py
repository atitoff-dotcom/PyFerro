# -*- coding: utf-8 -*-
"""
Тест-сьют: Mission Control Cockpit (/admin/system RPC Handlers).
Проверяет системные методы управления:
1. admin.sessions_list и admin.session_kill (Kick/Kill)
2. system.cache_stats и system.cache_invalidate (RFC 0001)
3. system.broadcast (Zero-copy broadcast)
4. system.recent_logs (Live Log Streamer из оперативной памяти)
5. system.get_config (Runtime Config с маскированием секретов)
6. Защиту прав доступа (доступ только администратору)
"""

import time
import pytest
from unittest.mock import MagicMock, AsyncMock

from pyferro.core.session import (
    JsonRpcSession,
    ACTIVE_SESSIONS_SET,
    RPC_REGISTRY,
    RPCError,
)
from pyferro.core.logger import logger, get_recent_logs
from pyferro.plugins.crud.admin_handlers import (
    list_active_sessions,
    kill_session,
    get_cache_stats,
    invalidate_cache_tags,
    send_system_broadcast,
    stream_recent_logs,
    get_system_config,
    get_plugin_matrix,
    update_hot_config,
    list_delegations_admin,
    toggle_delegation_admin,
    create_delegation_admin,
    delete_delegation_admin,
    delegation_options_admin,
    seo_get_config_admin,
    seo_update_config_admin,
    seo_ping_indexnow_admin,
)

class MockAdminSession:
    session_id = 999
    ip = "127.0.0.1"
    data = {"username": "admin", "role": "admin"}


class MockUserSession:
    session_id = 111
    ip = "192.168.1.50"
    data = {"username": "vasya", "role": "user"}


@pytest.mark.asyncio
async def test_admin_handlers_access_control():
    """Проверяет строгую защиту системных методов от не-администраторов."""
    guest_session = None
    user_session = MockUserSession()

    # 1. Гость не может вызывать системные методы
    with pytest.raises(RPCError) as exc:
        await list_active_sessions(guest_session)
    assert exc.value.code == -32003

    # 2. Обычный пользователь (не admin) получает ошибку доступа
    with pytest.raises(RPCError) as exc:
        await list_active_sessions(user_session)
    assert exc.value.code == -32003

    with pytest.raises(RPCError) as exc:
        await get_cache_stats(user_session)
    assert exc.value.code == -32003

    with pytest.raises(RPCError) as exc:
        await send_system_broadcast(user_session, message="Hello")
    assert exc.value.code == -32003

    # 3. Суперадминистратор (is_superadmin=True) успешно получает метрики
    class MockSuperuserSession:
        session_id = 888
        ip = "127.0.0.1"
        is_superadmin = True

    superuser_session = MockSuperuserSession()
    stats = await get_cache_stats(superuser_session)
    assert isinstance(stats, list)
@pytest.mark.asyncio
async def test_admin_sessions_list_and_kill():
    """Проверяет мониторинг активных сессий и kick/kill."""
    admin = MockAdminSession()
    
    # Создаем фейковую клиентскую сессию
    ws_mock = MagicMock()
    ws_mock.receive = AsyncMock()
    client_session = JsonRpcSession(ws_mock, session_id=777, ip="10.0.0.1")
    client_session.data = {"username": "client_test", "role": "user"}
    
    try:
        # Список сессий
        sessions = await list_active_sessions(admin)
        assert isinstance(sessions, list)
        found = next((s for s in sessions if s["session_id"] == 777), None)
        assert found is not None
        assert found["username"] == "client_test"
        assert found["ip"] == "10.0.0.1"

        # Попытка кикнуть самого себя (администратора) должна завершиться ошибкой
        with pytest.raises(RPCError) as exc:
            await kill_session(admin, session_id=admin.session_id)
        assert exc.value.code == -32602

        # Успешный kick клиентской сессии
        res = await kill_session(admin, session_id=777)
        assert res["status"] == "ok"
        assert res["session_id"] == 777
        assert client_session._closed is True
    finally:
        ACTIVE_SESSIONS_SET.discard(client_session)


@pytest.mark.asyncio
async def test_system_cache_stats_and_invalidate():
    """Проверяет инспекцию и сброс тегов Smart Cache."""
    admin = MockAdminSession()

    # Инспекция тегов
    stats = await get_cache_stats(admin)
    assert isinstance(stats, list)

    # Инвалидация
    res = await invalidate_cache_tags(admin, tags=["admin_test_tag"])
    assert res["status"] == "ok"
    assert "admin_test_tag" in res["invalidated_tags"]
    assert res["invalidated_tags"]["admin_test_tag"] >= 2


@pytest.mark.asyncio
async def test_system_broadcast():
    """Проверяет отправку системного оповещения."""
    admin = MockAdminSession()

    res = await send_system_broadcast(admin, message="Внимание! Рестарт через 5 минут", level="warning")
    assert res["status"] == "ok"
    assert "delivered_count" in res


@pytest.mark.asyncio
async def test_system_recent_logs():
    """Проверяет чтение логов из оперативной памяти сервера."""
    admin = MockAdminSession()

    unique_msg = f"Test admin log entry unique {time.time()}"
    logger.info(unique_msg)
    logs = await stream_recent_logs(admin, limit=50)
    assert isinstance(logs, list)
    assert len(logs) > 0

    matching = [l for l in logs if l.get("message") == unique_msg]
    assert len(matching) == 1, "Лог не должен дублироваться в буфере памяти!"
    
    last = logs[-1]
    assert "message" in last
    assert "timestamp" in last
    assert "level" in last


@pytest.mark.asyncio
async def test_system_get_config_masks_secrets():
    """Проверяет получение настроек ядра и маскирование секретов."""
    admin = MockAdminSession()

    conf = await get_system_config(admin)
    assert isinstance(conf, dict)
    assert "security" in conf
    secret_key = conf["security"].get("secret_key", "")
    assert "••••••••" in secret_key, "Secret key must be masked!"


@pytest.mark.asyncio
async def test_system_plugin_matrix():
    """Проверяет получение сводной матрицы состояния плагинов платформы."""
    admin = MockAdminSession()
    user = MockUserSession()

    # 1. Защита доступа
    with pytest.raises(RPCError) as exc:
        await get_plugin_matrix(user)
    assert exc.value.code == -32003

    # 2. Успешный вызов администратором
    matrix = await get_plugin_matrix(admin)
    assert isinstance(matrix, dict)
    assert "plugins" in matrix
    assert "runtime" in matrix

    plugins = matrix["plugins"]
    for key in ("db", "smart_cache", "crud", "files", "seo", "broadcast", "auth"):
        assert key in plugins
        assert plugins[key]["active"] is True

    # Проверка ключевых полей плагинов
    assert "dialect" in plugins["db"]
    assert "tag_count" in plugins["smart_cache"]
    assert "models_count" in plugins["crud"]

    runtime = matrix["runtime"]
    assert "log_level" in runtime
    assert "db_echo" in runtime
    assert "python_version" in runtime


@pytest.mark.asyncio
async def test_system_update_hot_config():
    """Проверяет безопасное горячее обновление параметров ядра в рантайме."""
    admin = MockAdminSession()
    user = MockUserSession()

    # 1. Защита доступа
    with pytest.raises(RPCError) as exc:
        await update_hot_config(user, log_level="DEBUG")
    assert exc.value.code == -32003

    # 2. Невалидные аргументы (защита от ошибок)
    with pytest.raises(RPCError) as exc:
        await update_hot_config(admin, log_level="INVALID_LEVEL")
    assert exc.value.code == -32602

    with pytest.raises(RPCError) as exc:
        await update_hot_config(admin, guest_idle_timeout=-10)
    assert exc.value.code == -32602

    # 3. Успешное применение настроек
    res = await update_hot_config(
        admin,
        log_level="DEBUG",
        db_echo=True,
        guest_idle_timeout=600,
        user_idle_timeout=1200,
        allow_guests=True,
    )
    assert res["status"] == "ok"
    assert res["applied"]["log_level"] == "DEBUG"
    assert res["applied"]["db_echo"] is True
    assert res["applied"]["guest_idle_timeout"] == 600
    assert res["applied"]["user_idle_timeout"] == 1200

    # Проверяем, что runtime обновился
    assert res["runtime"]["log_level"] == "DEBUG"
    assert res["runtime"]["db_echo"] is True

    # Возвращаем дефолты
    await update_hot_config(admin, log_level="INFO", db_echo=False)


@pytest.mark.asyncio
async def test_admin_delegations_lifecycle():
    """Проверяет управление замещениями полномочий в админке (UserDelegation CRUD & Toggle)."""
    admin = MockAdminSession()
    user = MockUserSession()

    # 1. Защита доступа (только admin)
    with pytest.raises(RPCError) as exc:
        await list_delegations_admin(user)
    assert exc.value.code == -32003

    # 2. Получение опций для формы
    options = await delegation_options_admin(admin)
    assert "users" in options
    assert "models" in options

    # 3. Валидация: нельзя делегировать самому себе
    with pytest.raises(RPCError) as exc:
        await create_delegation_admin(admin, from_user_id=1, to_user_id=1)
    assert exc.value.code == -32602

    from pyferro.db import system_db_session, engine, Base
    from pyferro.auth.models import User
    from sqlalchemy import select

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        u1 = (await db.execute(select(User).where(User.id == 1001))).scalar_one_or_none()
        if not u1:
            u1 = User(id=1001, login="del_user1", name="Del User 1")
            db.add(u1)
        u2 = (await db.execute(select(User).where(User.id == 1002))).scalar_one_or_none()
        if not u2:
            u2 = User(id=1002, login="del_user2", name="Del User 2")
            db.add(u2)
        await db.commit()

    # 4. Успешное создание замещения
    created = await create_delegation_admin(
        admin,
        from_user_id=1001,
        to_user_id=1002,
        model_name="Task",
        is_active=True,
    )
    del_id = created["id"]
    assert del_id > 0

    # 5. Проверка в общем списке
    dels = await list_delegations_admin(admin)
    found = next((d for d in dels if d["id"] == del_id), None)
    assert found is not None
    assert found["from_user_id"] == 1001
    assert found["to_user_id"] == 1002
    assert found["model_name"] == "Task"
    assert found["is_active"] is True
    assert found["status"] == "active"

    # 6. Переключение активности (toggle)
    toggled = await toggle_delegation_admin(admin, id=del_id)
    assert toggled["is_active"] is False

    # 7. Удаление
    deleted = await delete_delegation_admin(admin, id=del_id)
    assert deleted["deleted"] is True
    assert deleted["id"] == del_id


@pytest.mark.asyncio
async def test_admin_seo_handlers():
    admin = MockAdminSession()
    user = MockUserSession()

    # 1. Non-admin is blocked
    with pytest.raises(RPCError):
        await seo_get_config_admin(user)

    with pytest.raises(RPCError):
        await seo_update_config_admin(user, site_name="Hacked")

    # 2. Get SEO config
    cfg = await seo_get_config_admin(admin)
    assert "site_url" in cfg
    assert "default_title" in cfg
    assert "default_description" in cfg
    assert "available_models" in cfg

    # 3. Update SEO config online
    updated = await seo_update_config_admin(
        admin,
        site_name="PyFerro Super Store",
        default_title="Купить всё онлайн",
        default_description="Лучший магазин на PyFerro",
        enable_sitemap=True,
    )
    assert updated["status"] == "ok"
    assert updated["config"]["site_name"] == "PyFerro Super Store"
    assert updated["config"]["default_title"] == "Купить всё онлайн"

    # 4. Verify config reflects update
    cfg_after = await seo_get_config_admin(admin)
    assert cfg_after["site_name"] == "PyFerro Super Store"
    assert cfg_after["default_title"] == "Купить всё онлайн"

    # 5. User with adm-seo role is allowed access to SEO methods
    class MockSeoSession:
        is_superadmin = False
        user = type("MockUser", (), {"is_superadmin": False, "roles": [type("R", (), {"name": "adm-seo"})()]})()

    seo_user = MockSeoSession()
    seo_cfg = await seo_get_config_admin(seo_user)
    assert seo_cfg["site_name"] == "PyFerro Super Store"
