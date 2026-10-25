"""
Модульные тесты Этапа 1: проверка строгих контрактов ядра (`pyferro2/core/`).
"""

from dataclasses import FrozenInstanceError
import pytest

from pyferro2.core import (
    ADM_SECTION_ROLES,
    GUEST_ROLE,
    GUEST_SESSION_DATA,
    SESSION_COOKIE_NAME,
    SYSTEM_ROLES,
    USER_ROLE,
    JsonRpcErrorCode,
    Session,
    SessionData,
    WsCloseCode,
    admRole,
)


class TestConstants:
    """Проверка констант ролей, множеств и кодов протокола."""

    def test_adm_roles_values(self) -> None:
        assert admRole.admin == "admin"
        assert admRole.adm_crud == "adm_crud"
        assert admRole.adm_users == "adm_users"
        assert admRole.adm_roles == "adm_roles"
        assert admRole.adm_settings == "adm_settings"
        assert admRole.adm_rpc == "adm_rpc"
        assert admRole.adm_help == "adm_help"
        assert admRole.adm_seo == "adm_seo"

    def test_role_sets_are_frozensets(self) -> None:
        assert isinstance(ADM_SECTION_ROLES, frozenset)
        assert isinstance(SYSTEM_ROLES, frozenset)
        assert "admin" not in ADM_SECTION_ROLES
        assert "adm_crud" in ADM_SECTION_ROLES
        assert {"guest", "user", "admin"}.issubset(SYSTEM_ROLES)
        assert ADM_SECTION_ROLES.issubset(SYSTEM_ROLES)

    def test_protocol_codes_and_cookie(self) -> None:
        assert SESSION_COOKIE_NAME == "ferro_session"
        assert JsonRpcErrorCode.PARSE_ERROR == -32700
        assert JsonRpcErrorCode.INVALID_REQUEST == -32600
        assert JsonRpcErrorCode.METHOD_NOT_FOUND == -32601
        assert JsonRpcErrorCode.INVALID_PARAMS == -32602
        assert JsonRpcErrorCode.INTERNAL_ERROR == -32603
        assert JsonRpcErrorCode.UNAUTHORIZED == -32001
        assert JsonRpcErrorCode.FORBIDDEN == -32003
        assert WsCloseCode.NORMAL == 1000
        assert WsCloseCode.POLICY_VIOLATION == 1008
        assert WsCloseCode.UNAUTHORIZED == 4001
        assert WsCloseCode.FORBIDDEN == 4003


class TestSessionData:
    """Проверка неизменяемости, памяти (`__slots__`), Fail-Fast валидации и O(1) методов `SessionData`."""

    def test_guest_singleton_reuse(self) -> None:
        guest = SessionData.guest()
        assert guest is GUEST_SESSION_DATA
        assert guest.is_guest is True
        assert guest.is_admin is False
        assert guest.user_id is None
        assert guest.username == GUEST_ROLE
        assert guest.roles == frozenset({GUEST_ROLE})
        assert guest.permissions == frozenset()

    def test_guest_with_custom_permissions(self) -> None:
        perms = frozenset({"catalog.list", "Article:read"})
        guest = SessionData.guest(permissions=perms)
        assert guest is not GUEST_SESSION_DATA
        assert guest.is_guest is True
        assert guest.has_permission("catalog.list") is True
        assert guest.has_permission("Article:read") is True
        assert guest.has_permission("Article:delete") is False

    def test_authenticated_user_and_permissions(self) -> None:
        data = SessionData(
            user_id=42,
            username="ivan",
            roles=frozenset({USER_ROLE, admRole.adm_crud.value}),
            permissions=frozenset({"orders.create", "Order:read"}),
        )
        assert data.user_id == 42
        assert data.username == "ivan"
        assert data.is_guest is False
        assert data.is_admin is False
        assert data.has_role(USER_ROLE) is True
        assert data.has_role("admin") is False
        assert data.has_permission("orders.create") is True
        assert data.has_permission("orders.delete") is False
        assert data.has_admin_access("crud") is True
        assert data.has_admin_access("adm_crud") is True
        assert data.has_admin_access("users") is False

    def test_admin_has_all_permissions_and_sections(self) -> None:
        admin = SessionData(
            user_id=1,
            username="root",
            roles=frozenset({admRole.admin.value}),
        )
        assert admin.is_admin is True
        assert admin.is_guest is False
        assert admin.has_permission("any.rpc.method") is True
        assert admin.has_permission("AnyModel:delete") is True
        assert admin.has_admin_access("crud") is True
        assert admin.has_admin_access("users") is True
        assert admin.has_admin_access("adm_seo") is True

    def test_slots_and_immutability(self) -> None:
        data = SessionData(user_id=7, username="alex", roles=frozenset({USER_ROLE}))
        assert not hasattr(data, "__dict__")
        with pytest.raises(FrozenInstanceError):
            data.user_id = 99  # type: ignore[misc]
        with pytest.raises((AttributeError, TypeError)):
            data.uid = 7  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "bad_user_id",
        [True, False, 0, -5, "12", 1.5],
    )
    def test_fail_fast_invalid_user_id(self, bad_user_id: object) -> None:
        with pytest.raises(TypeError):
            SessionData(
                user_id=bad_user_id,  # type: ignore[arg-type]
                username="user",
                roles=frozenset({USER_ROLE}),
            )

    @pytest.mark.parametrize("bad_username", ["", None, 123])
    def test_fail_fast_invalid_username(self, bad_username: object) -> None:
        with pytest.raises(ValueError):
            SessionData(
                user_id=1,
                username=bad_username,  # type: ignore[arg-type]
                roles=frozenset({USER_ROLE}),
            )

    def test_fail_fast_mutable_roles_or_permissions(self) -> None:
        with pytest.raises(TypeError):
            SessionData(
                user_id=1,
                username="alex",
                roles={"user"},  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError):
            SessionData(
                user_id=1,
                username="alex",
                roles=frozenset({"user"}),
                permissions=["rpc.call"],  # type: ignore[arg-type]
            )


class TestSession:
    """Проверка контракта сессии `Session`: слоты, смена пользователя и отправка уведомлений."""

    def test_session_defaults_and_slots(self) -> None:
        session = Session(session_id="sess-001")
        assert session.session_id == "sess-001"
        assert session.data is GUEST_SESSION_DATA
        assert not hasattr(session, "__dict__")
        with pytest.raises(AttributeError):
            session.extra_field = "forbidden"  # type: ignore[attr-defined]

    def test_authenticate_and_reset_to_guest(self) -> None:
        session = Session(session_id="sess-002")
        assert session.data.is_guest is True

        user_data = SessionData(
            user_id=10,
            username="maria",
            roles=frozenset({USER_ROLE}),
            permissions=frozenset({"profile.read"}),
        )
        session.authenticate(user_data)
        assert session.data is user_data
        assert session.data.user_id == 10

        session.reset_to_guest()
        assert session.data is GUEST_SESSION_DATA

    @pytest.mark.asyncio
    async def test_notify_with_and_without_callback(self) -> None:
        # 1. Без колбэка (например, в HTTP или юнит-тестах) — безопасный no-op
        silent_session = Session(session_id="sess-silent")
        await silent_session.notify("export.progress", {"percent": 50})

        # 2. С подключенным транспортным колбэком
        sent_events: list[tuple[str, object]] = []

        async def fake_transport_notify(event: str, payload: object) -> None:
            sent_events.append((event, payload))

        live_session = Session(session_id="sess-live", notify=fake_transport_notify)
        await live_session.notify("export.progress", {"percent": 100})

        assert sent_events == [("export.progress", {"percent": 100})]

    @pytest.mark.asyncio
    async def test_session_fail_fast_validation(self) -> None:
        with pytest.raises(ValueError):
            Session(session_id="")
        with pytest.raises(TypeError):
            Session(session_id="s1", data={"user_id": 1})  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Session(session_id="s1", notify="not_callable")  # type: ignore[arg-type]

        session = Session(session_id="s1")
        with pytest.raises(TypeError):
            session.authenticate(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            await session.notify("", {"a": 1})
