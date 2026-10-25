# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock
from pyferro.core.constants import ADM_HELP_ROLE, SYSTEM_ROLES
from pyferro.core.session import RPCError
from pyferro.plugins.help.handlers import (
    help_ping,
    help_echo,
    help_multi_output,
    help_tabular_demo,
    help_reverse_call,
    help_migration_status,
    help_migration_dry_run,
)


def test_help_system_role_constant():
    assert ADM_HELP_ROLE == "adm_help"
    assert ADM_HELP_ROLE in SYSTEM_ROLES


@pytest.mark.asyncio
async def test_help_ping():
    session = MagicMock()
    session.session_id = 42
    session.user_id = 1
    session.username = "tester"
    session.user_roles = ["adm_help"]
    res = await help_ping(session)
    assert res["status"] == "pong"
    assert res["client_session_id"] == 42
    assert res["username"] == "tester"


@pytest.mark.asyncio
async def test_help_echo_success_and_error():
    session = MagicMock()
    session.username = "alice"

    # Success call
    res = await help_echo(session, {"message": "Hello PyFerro"})
    assert res["echo"] == "Hello PyFerro"
    assert res["length"] == len("Hello PyFerro")

    # Simulated error call
    with pytest.raises(RPCError) as exc_info:
        await help_echo(session, {"simulate_error": True})
    assert exc_info.value.code == -32000
    assert "simulate_error=True" in str(exc_info.value)


@pytest.mark.asyncio
async def test_help_multi_output_streaming():
    session = MagicMock()
    session.send_notification = AsyncMock()

    res = await help_multi_output(session, {"steps": 3, "delay": 0.01})
    assert res["status"] == "completed"
    assert res["total_steps"] == 3
    # Check that send_notification was called 3 times
    assert session.send_notification.call_count == 3
    first_call = session.send_notification.call_args_list[0]
    assert first_call[0][0] == "help.stream_chunk"
    assert first_call[0][1]["step"] == 1


@pytest.mark.asyncio
async def test_help_migration_status_and_dry_run():
    session = MagicMock()
    status_res = await help_migration_status(session)
    assert "is_up_to_date" in status_res
    assert "applied" in status_res

    dry_run_res = await help_migration_dry_run(session)
    assert dry_run_res["verified"] is True
    assert "check_duration_ms" in dry_run_res


@pytest.mark.asyncio
async def test_auth_session_unified_contract():
    from pyferro.auth.core import AuthSession
    from pyferro.core.session import current_transport_ctx

    mock_transport = MagicMock()
    mock_transport.session_id = 105
    mock_transport.send_notification = AsyncMock()

    auth_sess = AuthSession(
        uid=1,
        user=None,
        user_name="admin",
        user_role="admin",
        user_roles=["admin"],
        session_db_id=99,
    )

    # 1. When current_transport_ctx is set, delegates to transport
    token = current_transport_ctx.set(mock_transport)
    try:
        assert auth_sess.session_id == 105
        await auth_sess.send_notification("test.event", {"foo": "bar"})
        mock_transport.send_notification.assert_awaited_once_with("test.event", {"foo": "bar"})
    finally:
        current_transport_ctx.reset(token)

    # 2. When current_transport_ctx is empty, fallback to session_db_id
    assert auth_sess.session_id == 99


@pytest.mark.asyncio
async def test_help_tabular_demo():
    session = MagicMock()
    res = await help_tabular_demo(session, {"count": 25})
    assert res["count"] == 25
    assert len(res["raw_records"]) == 25
    assert res["tabular_package"]["$tabular"] is True
    assert "fields" in res["tabular_package"]
    assert len(res["tabular_package"]["rows"]) == 25
    assert res["raw_bytes"] > res["packed_bytes"]
    assert res["saving_pct"] > 0


@pytest.mark.asyncio
async def test_help_reverse_call():
    session = MagicMock()
    session.send_request = AsyncMock(return_value={"screen": "1920x1080", "tz": "UTC"})
    session.username = "alice"

    res = await help_reverse_call(session, {"method": "client.get_environment"})
    assert res["status"] == "success"
    assert res["invoked_method"] == "client.get_environment"
    assert res["client_reported"]["screen"] == "1920x1080"
    assert "reverse_rtt_ms" in res

@pytest.mark.asyncio
async def test_help_static_zero_leakage_404_and_authorized():
    from pyferro.plugins.help.static_handler import serve_help_static
    from pyferro.plugins.crud.auth import create_crud_session
    from pyferro.app import FerroApp

    # Создаем экземпляр с активным Zero-Leakage 404 (пользовательский фронтенд или public_help=False)
    app = FerroApp(public_help=False)

    # 1. Unauthenticated request with Zero-Leakage -> 404 Not Found
    scope_anon = MagicMock()
    scope_anon.path = "/admin/help/index.html"
    scope_anon.headers = []
    proto_anon = MagicMock()
    proto_anon.response_str = MagicMock()

    await serve_help_static(scope_anon, proto_anon)
    assert proto_anon.response_str.call_count == 1
    call_args = proto_anon.response_str.call_args[1]
    assert call_args["status"] == 404

    # 2. Redirect /admin/help -> /admin/help/
    scope_redir = MagicMock()
    scope_redir.path = "/admin/help"
    scope_redir.headers = []
    proto_redir = MagicMock()
    proto_redir.response_str = MagicMock()
    await serve_help_static(scope_redir, proto_redir)
    assert proto_redir.response_str.call_args[1]["status"] == 307

    # 3. Authenticated request with adm-help role -> 200
    token = create_crud_session({"user_id": 1, "username": "help_user", "roles": ["adm_help"]})
    scope_auth = MagicMock()
    scope_auth.path = "/admin/help/index.html"
    scope_auth.headers = [(b"cookie", f"ferro_crud_session={token}".encode("utf-8"))]
    proto_auth = MagicMock()
    proto_auth.response_bytes = MagicMock()
    proto_auth.response_str = MagicMock()

    await serve_help_static(scope_auth, proto_auth)
    assert proto_auth.response_bytes.call_count == 1
    assert proto_auth.response_bytes.call_args[1]["status"] == 200

    # 4. Режим без пользовательского приложения (чистый dev-старт, public_help=True) -> гость получает 200
    app_bare = FerroApp(public_help=True)
    proto_bare = MagicMock()
    proto_bare.response_bytes = MagicMock()
    proto_bare.response_file = MagicMock()
    proto_bare.response_str = MagicMock()
    await serve_help_static(scope_anon, proto_bare)
    assert proto_bare.response_bytes.call_count == 1 or proto_bare.response_file.call_count == 1