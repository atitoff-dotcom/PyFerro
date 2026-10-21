# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pyferro.core.session import (
    JsonRpcSession, rpc_method, RPC_REGISTRY, RPCError,
    GUEST_ALLOWED_RPC_METHODS, is_guest_rpc_allowed
)
from pyferro.core.constants import ADMIN_ROLE, GUEST_ROLE, SYSTEM_ROLES
from pyferro.auth.models import Role, RpcPermission, User
from pyferro.auth.core import AuthSession
from pyferro.auth.discovery import sync_rpc_permissions, reload_guest_permissions_cache
from pyferro.plugins.crud.handlers import handle_crud_delete, handle_crud_update_cell
from pyferro.db import async_session, Base, engine


class MockTransport:
    def __init__(self, data=None):
        self.data = data
        self.sent = []
        self._closed = False
        self.ws = MagicMock()

    async def _send_error(self, rpc_id, code, message):
        self.sent.append({"id": rpc_id, "error": {"code": code, "message": message}})

    @property
    def authenticated(self) -> bool:
        return self.data is not None

    @property
    def user_role(self):
        if self.data and hasattr(self.data, "user_role"):
            return self.data.user_role
        return None

    @property
    def user_roles(self):
        if self.data and hasattr(self.data, "user_roles"):
            return self.data.user_roles
        return []


@pytest.mark.asyncio
async def test_guest_allowed_rpc_methods_cache():
    GUEST_ALLOWED_RPC_METHODS.add("catalog.list")
    GUEST_ALLOWED_RPC_METHODS.add("public_api.*")

    assert is_guest_rpc_allowed("catalog.list") is True
    assert is_guest_rpc_allowed("public_api.items") is True
    assert is_guest_rpc_allowed("public_api.details") is True
    assert is_guest_rpc_allowed("secret.data") is False

    GUEST_ALLOWED_RPC_METHODS.discard("catalog.list")
    assert is_guest_rpc_allowed("catalog.list") is False


@pytest.mark.asyncio
async def test_auth_session_rpc_permissions():
    # 1. Admin has bypass to everything
    admin_sess = AuthSession(
        uid=1, user=None, user_name="admin", user_role="admin", user_roles=["admin"],
        session_db_id=1, allowed_rpc_methods=set()
    )
    assert admin_sess.has_rpc_permission("orders.dispatch") is True
    assert admin_sess.has_rpc_permission("any.random.method") is True

    # 2. Regular user with wildcard and specific permissions
    user_sess = AuthSession(
        uid=2, user=None, user_name="operator", user_role="user", user_roles=["user"],
        session_db_id=2, allowed_rpc_methods={"orders.*", "reports.view"}
    )
    assert user_sess.has_rpc_permission("orders.list") is True
    assert user_sess.has_rpc_permission("orders.dispatch") is True
    assert user_sess.has_rpc_permission("reports.view") is True
    assert user_sess.has_rpc_permission("reports.export") is False
    assert user_sess.has_rpc_permission("admin.cleanup") is False


@pytest.mark.asyncio
async def test_crud_immutable_roles_protection():
    from pyferro.plugins.crud import ModelRegistry
    from pyferro.auth.core import system_bypass_ctx
    ModelRegistry.register(Role)
    token = system_bypass_ctx.set(True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session() as db:
            # Убеждаемся в наличии ролей
            # Убеждаемся в наличии ролей
            for r_name in (ADMIN_ROLE, GUEST_ROLE):
                stmt = select(Role).where(Role.name == r_name)
                if not (await db.execute(stmt)).scalar_one_or_none():
                    db.add(Role(name=r_name, description=f"Builtin {r_name}"))

            # Создаем кастомную роль
            stmt_custom = select(Role).where(Role.name == "manager")
            if not (await db.execute(stmt_custom)).scalar_one_or_none():
                db.add(Role(name="manager", description="Custom manager"))

            await db.commit()

            # Получаем id
            admin_id = (await db.execute(select(Role.id).where(Role.name == ADMIN_ROLE))).scalar_one()
            guest_id = (await db.execute(select(Role.id).where(Role.name == GUEST_ROLE))).scalar_one()
            manager_id = (await db.execute(select(Role.id).where(Role.name == "manager"))).scalar_one()
    finally:
        system_bypass_ctx.reset(token)

    # Сессия администратора
    admin_session = MagicMock()
    admin_session.user_role = "admin"
    admin_session.user_roles = ["admin"]
    admin_session.cookies = {}
    admin_session.data = None

    # Попытка удалить admin -> RPCError
    with pytest.raises(RPCError) as exc_admin:
        await handle_crud_delete(admin_session, {"model": "auth_role", "id": admin_id})
    assert "не может быть удалена" in str(exc_admin.value)

    # Попытка удалить guest -> RPCError
    with pytest.raises(RPCError) as exc_guest:
        await handle_crud_delete(admin_session, {"model": "auth_role", "id": guest_id})
    assert "не может быть удалена" in str(exc_guest.value)
    # Попытка переименовать admin -> RPCError
    with pytest.raises(RPCError) as exc_rename:
        await handle_crud_update_cell(admin_session, {
            "model": "auth_role", "id": admin_id, "field": "name", "value": "super_admin"
        })
    assert "не может быть переименована" in str(exc_rename.value)

    # Кастомная роль manager удаляется успешно
    res = await handle_crud_delete(admin_session, {"model": "auth_role", "id": manager_id})
    assert res == {"success": True, "id": manager_id}


@pytest.mark.asyncio
async def test_user_personal_permissions_merging():
    from pyferro.auth.models import RolePermission, UserPermission, UserRpcPermission

    # 1. Роль с базовыми правами: чтение Task (только свои) и RPC reports.view
    role = Role(id=10, name="operator", description="Operator role")
    role_perm = RolePermission(
        model_name="Task",
        can_read=True,
        can_create=False,
        can_update=False,
        can_delete=False,
        read_global=False,
        update_global=False,
        delete_global=False,
    )
    role.permissions = [role_perm]
    rpc_view = RpcPermission(id=101, name="reports.view", description="View reports")
    role.rpc_permissions = [rpc_view]

    # 2. Пользователь с ролью
    user = User(id=5, name="John Doe", login="johnd")
    user.roles = [role]
    user.permissions = []
    user.rpc_permissions = []

    # Проверка базовых ролевых прав
    perms = user._get_permissions_dict()
    assert perms["Task"]["can_read"] is True
    assert perms["Task"]["read_global"] is False
    assert perms["Task"]["can_delete"] is False
    assert user.get_allowed_rpc_methods() == {"reports.view"}

    # 3. Добавляем персональные права пользователю:
    # - CRUD надбавка: удаление Task глобально
    user_perm = UserPermission(
        model_name="Task",
        can_read=False,
        can_create=False,
        can_update=False,
        can_delete=True,
        delete_global=True,
    )
    user.permissions = [user_perm]

    # - Персональное RPC право: orders.dispatch
    rpc_dispatch = RpcPermission(id=102, name="orders.dispatch", description="Dispatch orders")
    user.rpc_permissions = [rpc_dispatch]

    # Проверяем итоговое объединение
    merged_perms = user._get_permissions_dict()
    assert merged_perms["Task"]["can_read"] is True  # из роли
    assert merged_perms["Task"]["read_global"] is False  # из роли
    assert merged_perms["Task"]["can_delete"] is True  # персональная надбавка
    assert merged_perms["Task"]["delete_global"] is True  # персональная надбавка

    allowed_rpcs = user.get_allowed_rpc_methods()
    assert allowed_rpcs == {"reports.view", "orders.dispatch"}


@pytest.mark.asyncio
async def test_permissions_api_flow():
    from pyferro.auth.permission_handlers import (
        handle_permissions_get_schema,
        handle_permissions_get,
        handle_permissions_save
    )
    from pyferro.auth.core import system_bypass_ctx

    admin_session = MagicMock()
    admin_session.user_role = "admin"
    admin_session.user_roles = ["admin"]
    admin_session.cookies = {}

    guest_session = MagicMock()
    guest_session.user_role = "user"
    guest_session.user_roles = ["user"]
    guest_session.data = None
    guest_session.cookies = {}

    # 1. Non-admin is rejected
    with pytest.raises(RPCError) as exc:
        await handle_permissions_get_schema(guest_session)
    assert exc.value.code == -32003
    assert "требуются права администратора" in str(exc.value)

    # 2. Superadmin (is_superadmin=True) gets schema
    superadmin_session = MagicMock()
    superadmin_session.is_superadmin = True
    schema_super = await handle_permissions_get_schema(superadmin_session)
    assert "models" in schema_super

    # 3. Admin gets schema
    schema = await handle_permissions_get_schema(admin_session)
    assert "models" in schema
    assert "rpc_methods" in schema
    assert isinstance(schema["models"], list)

    token = system_bypass_ctx.set(True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session() as db:
            # Создаем или находим тестовую роль и пользователя
            role = (await db.execute(select(Role).where(Role.name == "tester_role"))).scalar_one_or_none()
            if not role:
                role = Role(name="tester_role", description="Test Role")
                db.add(role)
                await db.commit()
                await db.refresh(role)

            stmt_user = select(User).options(selectinload(User.roles)).where(User.login == "test_user_perm")
            user = (await db.execute(stmt_user)).scalar_one_or_none()
            if not user:
                user = User(name="Test User", login="test_user_perm", roles=[role])
                db.add(user)
            else:
                user.roles = [role]
            await db.commit()
            await db.refresh(user)

            role_id = role.id
            user_id = user.id
    finally:
        system_bypass_ctx.reset(token)

    # 3. Save permissions for role
    crud_cfg = {
        "Task": {
            "can_read": True,
            "can_create": True,
            "can_update": False,
            "can_delete": False,
            "read_global": False,
        }
    }
    save_res = await handle_permissions_save(
        admin_session,
        target_type="role",
        target_id=role_id,
        crud_permissions=crud_cfg,
        rpc_permissions=[]
    )
    assert save_res["success"] is True

    # 4. Get permissions for role
    role_perms = await handle_permissions_get(admin_session, target_type="role", target_id=role_id)
    assert role_perms["target_name"] == "tester_role"
    assert role_perms["crud_permissions"]["Task"]["can_read"] is True
    assert role_perms["crud_permissions"]["Task"]["can_create"] is True
    assert role_perms["crud_permissions"]["Task"]["read_global"] is False

    # 5. Save personal permissions for user
    user_crud_cfg = {
        "Task": {
            "can_delete": True,
            "delete_global": True,
        }
    }
    user_save_res = await handle_permissions_save(
        admin_session,
        target_type="user",
        target_id=user_id,
        crud_permissions=user_crud_cfg,
        rpc_permissions=[]
    )
    assert user_save_res["success"] is True

    # 6. Get permissions for user
    user_perms = await handle_permissions_get(admin_session, target_type="user", target_id=user_id)
    assert user_perms["target_name"] == "test_user_perm"
    # Inherited from role:
    assert user_perms["inherited_crud"]["Task"]["can_read"] is True
    # Personal override:
    assert user_perms["personal_crud"]["Task"]["can_delete"] is True
    # Effective merged:
    assert user_perms["effective_crud"]["Task"]["can_read"] is True
    assert user_perms["effective_crud"]["Task"]["can_delete"] is True
    assert user_perms["effective_crud"]["Task"]["delete_global"] is True

    # 7. Save and get permissions for guest
    guest_save_res = await handle_permissions_save(
        admin_session,
        target_type="guest",
        target_id=0,
        crud_permissions={},
        rpc_permissions=["system.ping", "catalog.items"]
    )
    assert guest_save_res["success"] is True

    guest_perms = await handle_permissions_get(admin_session, target_type="guest", target_id=0)
    assert guest_perms["target_name"] == "Гости"
    assert "catalog.items" in guest_perms["rpc_permissions"]
    assert is_guest_rpc_allowed("catalog.items") is True


@pytest.mark.asyncio
async def test_live_ws_and_cookie_audit_real_users_without_passwords_and_no_handler_execution():
    """
    Проверяет:
    1. Реальное подключение по WS (login.refresh без знания пароля) и HTTP Cookie (ferro_session + rpc_jwt)
       под разными реальными пользователями (с комбинацией кастомных ролей, персональных прав и замещений).
    2. Проверку доступа к RPC через флаг check_access=True ГАРАНТИРОВАННО БЕЗ запуска самого обработчика RPC.
    3. Полную сверку ответов живого сокета с базой данных CRUD (permissions.audit_access).
    4. Мгновенный Hot-Reload прав у открытого WebSocket-соединения при сохранении в CRUD (permissions.save).
    """
    import secrets
    from datetime import datetime, timedelta, timezone
    from pyferro.db import system_db_session
    from pyferro.auth.auditor import LiveWsAuditClient, audit_target_permissions
    from pyferro.auth.permission_handlers import (
        handle_permissions_audit_access,
        handle_permissions_save,
    )
    from pyferro.auth.models import RefreshToken, UserDelegation

    trap_executions = 0

    @rpc_method("audit_trap.explode")
    async def trap_explode():
        """Опасный метод-ловушка, который категорически нельзя запускать при проверке прав."""
        nonlocal trap_executions
        trap_executions += 1
        raise RuntimeError("ОШИБКА: обработчик RPC был запущен во время проверки доступа!")

    @rpc_method("orders.approve")
    async def orders_approve():
        """Одобрение заказа менеджером."""
        nonlocal trap_executions
        trap_executions += 1
        return {"approved": True}

    @rpc_method("reports.audit_log")
    async def reports_audit_log():
        """Выгрузка журнала аудита."""
        nonlocal trap_executions
        trap_executions += 1
        return {"logs": []}

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await sync_rpc_permissions()

    admin_session = MagicMock()
    admin_session.user_role = "admin"
    admin_session.user_roles = ["admin"]
    admin_session.is_admin = True
    admin_session.is_superadmin = True
    admin_session.cookies = {}

    async with system_db_session() as db:
        # 1. Создаем кастомные роли manager и auditor
        role_mgr = (await db.execute(select(Role).where(Role.name == "manager_audit"))).scalar_one_or_none()
        if not role_mgr:
            role_mgr = Role(name="manager_audit", description="Менеджер заказов")
            db.add(role_mgr)

        role_aud = (await db.execute(select(Role).where(Role.name == "auditor_audit"))).scalar_one_or_none()
        if not role_aud:
            role_aud = Role(name="auditor_audit", description="Аудитор отчетов")
            db.add(role_aud)

        await db.commit()
        await db.refresh(role_mgr)
        await db.refresh(role_aud)

        # 2. Создаем разных реальных пользователей БЕЗ известных паролей (хеш неизвестен / не используется)
        stmt_mgr = select(User).options(selectinload(User.roles)).where(User.login == "real_manager_1")
        u_mgr = (await db.execute(stmt_mgr)).scalar_one_or_none()
        if not u_mgr:
            u_mgr = User(
                name="Реальный Менеджер",
                login="real_manager_1",
                password_hash=User._hash_password(secrets.token_urlsafe(24)),
                roles=[role_mgr],
            )
            db.add(u_mgr)
        else:
            u_mgr.roles = [role_mgr]

        stmt_combo = select(User).options(selectinload(User.roles)).where(User.login == "real_combo_user")
        u_combo = (await db.execute(stmt_combo)).scalar_one_or_none()
        if not u_combo:
            u_combo = User(
                name="Комбинированный Специалист",
                login="real_combo_user",
                password_hash=None,  # Вход только по OAuth/токену, пароля вообще нет!
                roles=[role_mgr, role_aud],
            )
            db.add(u_combo)
        else:
            u_combo.roles = [role_mgr, role_aud]
        await db.refresh(u_mgr)
        await db.refresh(u_combo)

        # Добавляем активное замещение (UserDelegation), чтобы проверить загрузку delegations_received при логине
        delegation = UserDelegation(
            from_user_id=u_mgr.id,
            to_user_id=u_combo.id,
            valid_from=datetime.now(timezone.utc) - timedelta(hours=1),
            valid_to=datetime.now(timezone.utc) + timedelta(hours=1),
            is_active=True,
        )
        db.add(delegation)
        await db.commit()

        mgr_role_id = role_mgr.id
        aud_role_id = role_aud.id
        u_mgr_id = u_mgr.id
        u_combo_id = u_combo.id

    # 3. Настраиваем права ролей и персональные права через CRUD API (permissions.save)
    await handle_permissions_save(
        admin_session,
        target_type="role",
        target_id=mgr_role_id,
        crud_permissions={"Role": {"can_read": True, "read_global": True}},
        rpc_permissions=["orders.approve"],
    )
    await handle_permissions_save(
        admin_session,
        target_type="role",
        target_id=aud_role_id,
        crud_permissions={},
        rpc_permissions=["reports.audit_log"],
    )
    # Персональное право для u_combo на метод-ловушку audit_trap.explode
    await handle_permissions_save(
        admin_session,
        target_type="user",
        target_id=u_combo_id,
        crud_permissions={"User": {"can_read": True, "read_global": False}},
        rpc_permissions=["audit_trap.explode"],
    )

    # 4. Проверяем полный аудит (WS + HTTP Cookie vs БД CRUD) для реального менеджера (не зная его пароля!)
    report_mgr = await handle_permissions_audit_access(admin_session, target_type="user", target_id=u_mgr_id)
    assert report_mgr["passed"] is True, f"Найдены расхождения для u_mgr: {report_mgr['mismatches']}"
    assert report_mgr["rpc_results"]["orders.approve"]["expected"] is True
    assert report_mgr["rpc_results"]["orders.approve"]["ws_actual"] is True
    assert report_mgr["rpc_results"]["orders.approve"]["cookie_actual"] is True
    assert report_mgr["rpc_results"]["reports.audit_log"]["expected"] is False
    assert report_mgr["rpc_results"]["reports.audit_log"]["ws_actual"] is False
    assert report_mgr["rpc_results"]["audit_trap.explode"]["expected"] is False
    assert report_mgr["rpc_results"]["audit_trap.explode"]["ws_actual"] is False

    # 5. Проверяем полный аудит для комбинированного пользователя (2 роли + персональное право на ловушку + делегирование)
    report_combo = await handle_permissions_audit_access(admin_session, target_type="user", target_id=u_combo_id)
    assert report_combo["passed"] is True, f"Найдены расхождения для u_combo: {report_combo['mismatches']}"
    assert report_combo["rpc_results"]["orders.approve"]["ws_actual"] is True
    assert report_combo["rpc_results"]["reports.audit_log"]["ws_actual"] is True
    assert report_combo["rpc_results"]["audit_trap.explode"]["ws_actual"] is True
    assert report_combo["rpc_results"]["audit_trap.explode"]["cookie_actual"] is True

    # 6. Проверяем аудит для кастомной роли и для гостей
    report_role = await handle_permissions_audit_access(admin_session, target_type="role", target_id=mgr_role_id)
    assert report_role["passed"] is True, f"Найдены расхождения для роли: {report_role['mismatches']}"

    report_guest = await handle_permissions_audit_access(admin_session, target_type="guest", target_id=0)
    assert report_guest["passed"] is True, f"Найдены расхождения для гостя: {report_guest['mismatches']}"
    assert report_guest["rpc_results"]["audit_trap.explode"]["ws_actual"] is False

    # 7. КРИТИЧЕСКАЯ ПРОВЕРКА: ни один из RPC-методов не был физически запущен!
    assert trap_executions == 0, f"Обработчик RPC был вызван {trap_executions} раз(а), хотя должен быть 0!"

    # 8. Проверка Hot-Reload прав на живом открытом WebSocket-соединении без переподключения
    async with system_db_session() as db:
        temp_rt = RefreshToken(
            user_id=u_mgr_id,
            token=f"live_test_{secrets.token_urlsafe(24)}",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.add(temp_rt)
        await db.commit()
        live_token = temp_rt.token

    async with LiveWsAuditClient() as live_ws:
        await live_ws.call("login.refresh", {"token": live_token})
        # До выдачи права доступ к audit_trap.explode закрыт
        res_before = await live_ws.check_access("audit_trap.explode")
        assert res_before["allowed"] is False
        assert res_before["code"] == -32003

        # Админ в CRUD выдает роли manager_audit право на audit_trap.explode
        await handle_permissions_save(
            admin_session,
            target_type="role",
            target_id=mgr_role_id,
            crud_permissions={"Role": {"can_read": True, "read_global": True}},
            rpc_permissions=["orders.approve", "audit_trap.explode"],
        )

        # На ТОМ ЖЕ открытом сокете без реконнекта право мгновенно появилось!
        res_after_grant = await live_ws.check_access("audit_trap.explode")
        assert res_after_grant["allowed"] is True
        assert trap_executions == 0  # И ловушка снова НЕ взорвалась!

        # Админ отзывает право в CRUD
        await handle_permissions_save(
            admin_session,
            target_type="role",
            target_id=mgr_role_id,
            crud_permissions={"Role": {"can_read": True, "read_global": True}},
            rpc_permissions=["orders.approve"],
        )

        # На ТОМ ЖЕ открытом сокете право мгновенно отозвано!
        res_after_revoke = await live_ws.check_access("audit_trap.explode")
        assert res_after_revoke["allowed"] is False


@pytest.mark.asyncio
async def test_rpc_is_framework_detection_and_schema():
    """Проверяет точное определение флага is_framework по файловому пути/модулю."""
    from pyferro.core.session import rpc_method, is_framework_handler, RPC_REGISTRY
    from pyferro.auth.permission_handlers import handle_permissions_get_schema
    from unittest.mock import MagicMock

    # 1. Метод, объявленный в текущем тестовом файле (прикладной)
    @rpc_method("custom_app.test_method")
    async def custom_app_fn():
        return True

    # 2. Метод с префиксом system., но объявленный вне pyferro (прикладной)
    @rpc_method("system.custom_ping")
    async def custom_system_ping():
        return True

    assert is_framework_handler(custom_app_fn) is False
    assert is_framework_handler(custom_system_ping) is False
    assert RPC_REGISTRY["custom_app.test_method"].is_framework is False
    assert RPC_REGISTRY["system.custom_ping"].is_framework is False

    # 3. Системные методы плагинов pyferro
    from pyferro.plugins.files.handlers import files_init_upload
    assert is_framework_handler(files_init_upload) is True

    # 4. Проверка схемы интроспекции permissions.get_schema
    admin_session = MagicMock()
    admin_session.user_role = "admin"
    admin_session.user_roles = ["admin"]
    admin_session.is_admin = True
    admin_session.is_superadmin = True
    admin_session.cookies = {}
    admin_session.data = None

    schema = await handle_permissions_get_schema(admin_session, all=True)
    methods_by_name = {m["name"]: m for m in schema["rpc_methods"]}

    assert methods_by_name["custom_app.test_method"]["is_framework"] is False
    assert methods_by_name["system.custom_ping"]["is_framework"] is False
    if "files.init_upload" in methods_by_name:
        assert methods_by_name["files.init_upload"]["is_framework"] is True


@pytest.mark.asyncio
async def test_sync_rpc_permissions_purges_obsolete_methods_and_cascades():
    """Проверяет автоматическую очистку несуществующих RPC методов из БД и каскадных связей."""
    from pyferro.auth.discovery import sync_rpc_permissions, ensure_system_roles
    from pyferro.auth.models import Role, RpcPermission, RoleRpcPermission
    from pyferro.db import system_db_session, engine, Base
    from sqlalchemy import select

    from pyferro.db.session import configure_db
    configure_db("sqlite+aiosqlite:///test_audit.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        admin_role, guest_role = await ensure_system_roles(db)

        # 1. Добавляем устаревший метод, которого реально нет в RPC_REGISTRY
        obsolete_perm = RpcPermission(name="obsolete.method_to_purge", description="Старый метод")
        wildcard_perm = RpcPermission(name="custom_reports.*", description="Wildcard маска")
        db.add_all([obsolete_perm, wildcard_perm])
        await db.flush()

        # 2. Привязываем оба права к роли
        role_perm1 = RoleRpcPermission(role_id=guest_role.id, rpc_permission_id=obsolete_perm.id)
        role_perm2 = RoleRpcPermission(role_id=guest_role.id, rpc_permission_id=wildcard_perm.id)
        db.add_all([role_perm1, role_perm2])
        await db.commit()

    # 3. Запускаем актуализацию при старте
    await sync_rpc_permissions()

    # 4. Проверяем состояние в БД
    async with system_db_session() as db:
        # Устаревший метод должен быть полностью удален
        stmt_obs = select(RpcPermission).where(RpcPermission.name == "obsolete.method_to_purge")
        res_obs = (await db.execute(stmt_obs)).scalar_one_or_none()
        assert res_obs is None, "Устаревший RPC метод не был удален из pf_auth_rpc_permission"

        # Связь устаревшего метода с ролью каскадно удалена
        stmt_link = select(RoleRpcPermission).where(RoleRpcPermission.rpc_permission_id == obsolete_perm.id)
        res_link = (await db.execute(stmt_link)).scalars().all()
        assert len(res_link) == 0, "Связка с ролью не была каскадно удалена"

        # Wildcard-маска НЕ должна быть удалена
        stmt_wild = select(RpcPermission).where(RpcPermission.name == "custom_reports.*")
        res_wild = (await db.execute(stmt_wild)).scalar_one_or_none()
        assert res_wild is not None, "Wildcard-маска ошибочно удалена"

        # Связь wildcard-маски с ролью сохранилась
        stmt_wild_link = select(RoleRpcPermission).where(RoleRpcPermission.rpc_permission_id == wildcard_perm.id)
        res_wild_link = (await db.execute(stmt_wild_link)).scalars().all()
        assert len(res_wild_link) == 1, "Связка wildcard-маски с ролью должна остаться"
