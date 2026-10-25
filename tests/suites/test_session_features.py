import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from pyferro.core.session import JsonRpcSession, rpc_method, RPC_REGISTRY, RPCError

class MockWs:
    def __init__(self, incoming_messages=None):
        self.sent = []
        self.incoming = list(incoming_messages or [])

    async def receive(self):
        if not self.incoming:
            # Emulate close message
            msg = MagicMock()
            msg.__class__.__name__ = "WebsocketInboundCloseMessage"
            return msg
        item = self.incoming.pop(0)
        msg = MagicMock()
        msg.__class__.__name__ = "WebsocketInboundTextMessage"
        msg.data = item
        return msg

    def send_str(self, text):
        self.sent.append(text)
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(None)
        return fut


@pytest.mark.asyncio
async def test_session_rejects_non_dict_json():
    ws = MockWs([b"[1, 2, 3]"])
    session = JsonRpcSession(ws, session_id=1)
    await session.start()
    
    assert len(ws.sent) == 1
    assert "Invalid Request: root must be a JSON object" in ws.sent[0]
    assert "-32600" in ws.sent[0]


@pytest.mark.asyncio
async def test_session_message_size_limit():
    large_payload = b'{"jsonrpc": "2.0", "method": "test", "params": "' + (b'x' * (11 * 1024 * 1024)) + b'"}'
    ws = MockWs([large_payload])
    session = JsonRpcSession(ws, session_id=2)
    await session.start()

    assert len(ws.sent) == 1
    assert "Message too large" in ws.sent[0]


@pytest.mark.asyncio
async def test_session_send_request_cleanup_on_timeout():
    ws = MockWs([])
    session = JsonRpcSession(ws, session_id=3)
    session.data = MagicMock()  # Mark authenticated

    with pytest.raises(asyncio.TimeoutError):
        await session.send_request("client.test", timeout=0.01)

    # Future must be removed from pending requests on timeout
    assert len(session._pending_requests) == 0


@pytest.mark.asyncio
async def test_session_multi_roles_access():
    # 1. rpc_method requires string name
    with pytest.raises(TypeError):
        @rpc_method(None)  # type: ignore
        async def invalid_method():
            pass

    # 2. Valid registration
    @rpc_method("editor.only")
    async def editor_action(session, params):
        return {"status": "ok"}

    handler = RPC_REGISTRY["editor.only"]
    res = await handler(None, {})
    assert res == {"status": "ok"}


@pytest.mark.asyncio
async def test_rpc_method_with_invalidates_and_wrappers():
    from pyferro.smart_cache import invalidates

    called = {}

    @rpc_method("test.delete_topic")
    @invalidates(tags=["forum.topics", "forum.topic.{topic_id|id}"])
    async def delete_topic(session, params):
        called["session"] = session
        called["params"] = params
        return {"deleted": True}

    handler = RPC_REGISTRY["test.delete_topic"]
    mock_session = MagicMock()
    res = await handler(mock_session, {"topic_id": 42})
    assert res == {"deleted": True}
    assert called["session"] is mock_session
    assert called["params"] == {"topic_id": 42}

    # Test generic wrapper without @wraps
    def dummy_decorator_no_wraps(func):
        async def generic_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return generic_wrapper

    called_generic = {}

    @rpc_method("test.generic_wrapped")
    @dummy_decorator_no_wraps
    async def generic_handler(session, params):
        called_generic["session"] = session
        called_generic["params"] = params
        return {"ok": True}

    handler_generic = RPC_REGISTRY["test.generic_wrapped"]
    res_generic = await handler_generic(mock_session, {"foo": "bar"})
    assert res_generic == {"ok": True}
    assert called_generic["session"] is mock_session
    assert called_generic["params"] == {"foo": "bar"}

    # Test invalidates with kwargs mapping
    called_kwargs = {}

    @rpc_method("test.kwargs_wrapped")
    @invalidates(tags=["forum.topic.{topic_id}"])
    async def kwargs_handler(topic_id: int):
        called_kwargs["topic_id"] = topic_id
        return {"id": topic_id}

    handler_kwargs = RPC_REGISTRY["test.kwargs_wrapped"]
    res_kwargs = await handler_kwargs(mock_session, {"topic_id": 99})
    assert res_kwargs == {"id": 99}
    assert called_kwargs["topic_id"] == 99


@pytest.mark.asyncio
async def test_guest_vs_user_idle_and_auth_timeout():
    from pyferro.core.lib.config import configure, settings

    # 1. By default auth_timeout == 0 (guests not kicked)
    configure(auth_timeout=0, guest_idle_timeout=1, user_idle_timeout=5)
    assert settings.security.get("auth_timeout") == 0
    assert settings.security.get("guest_idle_timeout") == 1
    assert settings.security.get("user_idle_timeout") == 5

    ws = MockWs([])
    session = JsonRpcSession(ws, session_id=101)
    
    # Run _auth_timeout_loop -> returns immediately without cancelling
    await session._auth_timeout_loop()
    assert session._closed is False

    # 2. Config with auth_timeout > 0 kicks unauthenticated
    configure(auth_timeout=0.01)
    session2 = JsonRpcSession(ws, session_id=102)
    dummy_task = asyncio.create_task(asyncio.sleep(0.2))
    session2._main_task = dummy_task
    
    # Should kick unauthenticated session after timeout
    await session2._auth_timeout_loop()
    assert dummy_task.cancelling() > 0 or dummy_task.cancelled()
    try:
        await dummy_task
    except asyncio.CancelledError:
        pass

    # Restore defaults
    configure(auth_timeout=0, guest_idle_timeout=0, user_idle_timeout=0)
    await session.close()
    await session2.close()

def test_session_contract_guest_and_authenticated():
    from pyferro.auth.core import AuthSession

    ws = MockWs([])
    session = JsonRpcSession(ws, session_id=1)

    # 1. Guest state
    assert session.authenticated is False
    assert session.user_id is None
    assert session.username == 'guest'
    assert session.is_superadmin is False
    assert session.is_admin is False
    assert session.user_role == 'guest'
    assert session.user_roles == ['guest']

    # 2. Authenticated via dict (backward compatibility)
    session.data = {
        'uid': 42,
        'username': 'alice',
        'is_superadmin': False,
        'role': 'editor',
        'roles': ['editor'],
    }
    assert session.authenticated is True
    assert session.user_id == 42
    assert session.username == 'alice'
    assert session.is_superadmin is False
    assert session.is_admin is False
    assert session.user_role == 'editor'
    assert session.user_roles == ['editor']

    # 3. Authenticated admin via dict
    session.data = {
        'id': '100',
        'user_name': 'root',
        'role': 'admin',
    }
    assert session.user_id == 100
    assert session.username == 'root'
    assert session.is_superadmin is True
    assert session.is_admin is True

    # 4. Authenticated via AuthSession object
    auth_session = AuthSession(
        uid=7,
        user=None,
        user_name='bob',
        user_role='moderator',
        user_roles=['moderator'],
        session_db_id=1,
    )
    session.data = auth_session
    assert session.user_id == 7
    assert session.username == 'bob'
    assert session.is_superadmin is False
    assert session.is_admin is False

    # 5. AuthSession direct properties
    assert auth_session.user_id == 7
    assert auth_session.username == 'bob'
    assert auth_session.is_superadmin is False
    assert auth_session.is_admin is False

    # 6. AuthSession as admin
    admin_auth = AuthSession(
        uid=1,
        user=None,
        user_name='admin_user',
        user_role='admin',
        user_roles=['admin'],
        session_db_id=2,
    )
    assert admin_auth.user_id == 1
    assert admin_auth.username == 'admin_user'
    assert admin_auth.is_superadmin is True
    assert admin_auth.is_admin is True


@pytest.mark.asyncio
async def test_get_session_uid_and_send_to_user():
    from pyferro.broadcast import get_session_uid, send_to_user
    from pyferro.core.session import ACTIVE_SESSIONS_SET

    # None and empty checks
    assert get_session_uid(None) is None

    # Object with property user_id
    class DummySession:
        def __init__(self, uid):
            self._uid = uid

        @property
        def user_id(self):
            return self._uid

    assert get_session_uid(DummySession(42)) == 42
    assert get_session_uid(DummySession("100")) == 100
    assert get_session_uid(DummySession(None)) is None
    assert get_session_uid(DummySession("invalid")) is None
    assert get_session_uid(DummySession(True)) is None

    # Dict compatibility
    assert get_session_uid({"user_id": 55}) == 55
    assert get_session_uid({"user_id": "77"}) == 77
    assert get_session_uid({"user_id": None}) is None
    assert get_session_uid({}) is None

    # Test send_to_user with ACTIVE_SESSIONS_SET
    ws1 = MockWs([])
    ws2 = MockWs([])
    s1 = JsonRpcSession(ws1, session_id=101)
    s1.data = {"uid": 500}
    s2 = JsonRpcSession(ws2, session_id=102)
    s2.data = {"uid": 600}

    ACTIVE_SESSIONS_SET.add(s1)
    ACTIVE_SESSIONS_SET.add(s2)
    try:
        sent = await send_to_user(500, "user.notify", {"msg": "hello"})
        assert sent == 1
        assert len(ws1.sent) == 1
        assert "user.notify" in ws1.sent[0]
        assert len(ws2.sent) == 0

        # Non-existent user
        sent_none = await send_to_user(999, "user.notify", {})
        assert sent_none == 0
    finally:
        ACTIVE_SESSIONS_SET.discard(s1)
        ACTIVE_SESSIONS_SET.discard(s2)


def test_extract_username_safe_and_context_logging():
    from pyferro.core.logger import _extract_username_safe, ContextColoredFormatter
    from pyferro.core.session import current_transport_ctx
    import logging

    # None and empty session
    assert _extract_username_safe(None) == "guest"

    # Guest session (no auth data)
    ws = MockWs([])
    guest_session = JsonRpcSession(ws, session_id=1, ip="192.168.1.50")
    assert _extract_username_safe(guest_session) == "guest"

    # Authenticated session via dict
    auth_session_dict = JsonRpcSession(ws, session_id=2, ip="192.168.1.51")
    auth_session_dict.data = {"username": "charlie"}
    assert _extract_username_safe(auth_session_dict) == "charlie"

    # Authenticated session via user_name in dict
    auth_session_dict2 = JsonRpcSession(ws, session_id=3, ip="192.168.1.52")
    auth_session_dict2.data = {"user_name": "dave"}
    assert _extract_username_safe(auth_session_dict2) == "dave"

    # Object without username attribute
    assert _extract_username_safe(object()) == "guest"

    # ContextFormatter test with session in context
    formatter = ContextColoredFormatter()
    record = logging.LogRecord("test", logging.INFO, "test.py", 10, "Hello", (), None)

    # Without session -> SYSTEM
    formatted_system = formatter.format(record)
    assert "[SYSTEM]" in formatted_system

    # With guest session in context
    token = current_transport_ctx.set(guest_session)
    try:
        formatted_guest = formatter.format(record)
        assert "[192.168.1.50 | guest]" in formatted_guest

        # With authenticated session in context
        current_transport_ctx.set(auth_session_dict)
        formatted_user = formatter.format(record)
        assert "[192.168.1.51 | charlie]" in formatted_user
    finally:
        current_transport_ctx.reset(token)
