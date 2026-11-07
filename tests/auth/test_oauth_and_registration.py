"""
Тесты внешней авторизации (OAuth/SSO), брендинга, регистрации и подтверждения email.
"""

import hashlib
import hmac
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from pyferro2.auth.models import Role, User
from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro2.db.engine import Database
from pyferro2.files.storage import FileStorage
from pyferro2.oauth.mailer import verification_store
from pyferro2.oauth.manager import seed_auth_configs
from pyferro2.oauth.models import AuthConfig, OAuthAccount
from pyferro2.oauth.providers import ExternalUserProfile, PROVIDERS
from pyferro2.rpc.errors import ForbiddenError, InvalidParamsError, NotFoundError, UnauthorizedError
from pyferro2.server.app import PyFerroApp


@pytest.fixture
async def app(tmp_path: Path) -> PyFerroApp:
    db = Database("sqlite+aiosqlite:///:memory:")
    storage = FileStorage(storage_dir=tmp_path / "storage", tmp_root=tmp_path / "tmp")
    ferro_app = PyFerroApp(
        db=db,
        file_storage=storage,
        secret_key="test-secret-key-for-oauth-and-registration-32b!",
    )
    async with db.session() as session:
        await db.create_tables()
        from pyferro2.auth.seeder import seed_system_roles
        await seed_system_roles(session)
        await seed_auth_configs(session)
    return ferro_app


@pytest.mark.asyncio
async def test_public_config_and_branding(app: PyFerroApp) -> None:
    session = Session(session_id="s1", data=app.guest_session_data)
    res = await app.router.call("system.get_public_config", session, {}, db=app.db)

    assert "app_title" in res
    assert "providers" in res
    assert res["allow_registration"] is True
    assert isinstance(res["providers"], list)
    prov_names = [p["name"] for p in res["providers"]]
    assert "vk" in prov_names
    assert "yandex" in prov_names


@pytest.mark.asyncio
async def test_registration_direct_flow(app: PyFerroApp) -> None:
    session = Session(session_id="s_reg", data=app.guest_session_data)

    res = await app.router.call(
        "auth.register",
        session,
        {"email": "test_user@example.com", "password": "password123", "username": "test_alex"},
        db=app.db,
    )

    assert res["status"] == "registered"
    assert "token" in res
    assert res["user"]["username"] == "test_alex"
    assert "user" in res["user"]["roles"]
    assert not session.data.is_guest

    # Попытка повторной регистрации с тем же email
    session_guest = Session(session_id="s_dup", data=app.guest_session_data)
    with pytest.raises(InvalidParamsError, match="уже существует"):
        await app.router.call(
            "auth.register",
            session_guest,
            {"email": "test_user@example.com", "password": "password456"},
            db=app.db,
        )


@pytest.mark.asyncio
async def test_registration_with_email_verification(app: PyFerroApp) -> None:
    async with app.db.session() as db:
        reg_cfg_stmt = select(AuthConfig).where(AuthConfig.key == "registration")
        reg_cfg = (await db.execute(reg_cfg_stmt)).scalar_one()
        reg_cfg.config = {"allow_registration": True, "require_email_verification": True}
        await db.commit()

    session = Session(session_id="s_verif", data=app.guest_session_data)
    res = await app.router.call(
        "auth.register",
        session,
        {"email": "verify_me@example.com", "password": "secret_password"},
        db=app.db,
    )

    assert res["status"] == "verification_required"
    assert session.data.is_guest

    # Достаем сгенерированный код из хранилища
    pending = verification_store._pending.get("verify_me@example.com")
    assert pending is not None
    code = pending["code"]

    # Проверка неверного кода
    with pytest.raises(InvalidParamsError, match="Неверный или истекший"):
        await app.router.call(
            "auth.verify_email_code",
            session,
            {"email": "verify_me@example.com", "code": "000000"},
            db=app.db,
        )

    # Успешная верификация
    res_ok = await app.router.call(
        "auth.verify_email_code",
        session,
        {"email": "verify_me@example.com", "code": code},
        db=app.db,
    )
    assert res_ok["status"] == "verified"
    assert not session.data.is_guest
    assert res_ok["user"]["username"] == "verify_me"


@pytest.mark.asyncio
async def test_oauth_login_seamless_linking_by_email(app: PyFerroApp) -> None:
    # 1. Создаем существующего пользователя
    async with app.db.session() as db:
        existing_u = User(username="yandex_master", email="yandex_master@ya.ru", is_active=True)
        existing_u.set_password("pass12345")
        role_stmt = select(Role).where(Role.name == "user")
        user_role = (await db.execute(role_stmt)).scalar_one()
        existing_u.roles.append(user_role)
        db.add(existing_u)
        await db.commit()

    # 2. Мокаем ответ Яндекс-провайдера
    mock_profile = ExternalUserProfile(
        provider="yandex",
        provider_user_id="998877",
        email="yandex_master@ya.ru",
        username="yandex_master",
        display_name="Мастер Яндекса",
        avatar_url="https://avatar.url",
        raw_data={"id": 998877},
    )

    with patch.object(PROVIDERS["yandex"], "authenticate", new=AsyncMock(return_value=mock_profile)):
        # Включаем провайдер yandex
        async with app.db.session() as db:
            y_cfg_stmt = select(AuthConfig).where(AuthConfig.key == "yandex")
            y_cfg = (await db.execute(y_cfg_stmt)).scalar_one()
            y_cfg.is_enabled = True
            await db.commit()

        session = Session(session_id="s_oauth", data=app.guest_session_data)
        res = await app.router.call(
            "oauth.login",
            session,
            {"provider": "yandex", "code": "fake_auth_code"},
            db=app.db,
        )

        assert res["user"]["username"] == "yandex_master"
        assert not session.data.is_guest

        # Проверяем, что в базе создалась связка в pf_auth_oauth
        async with app.db.session() as db:
            acc_stmt = select(OAuthAccount).where(OAuthAccount.provider == "yandex")
            acc = (await db.execute(acc_stmt)).scalar_one()
            assert acc.provider_user_id == "998877"
            assert acc.user_id == res["user"]["user_id"]


@pytest.mark.asyncio
async def test_oauth_admin_api(app: PyFerroApp) -> None:
    admin_session_data = SessionData(
        user_id=1,
        username="admin",
        roles=frozenset({"admin"}),
        permissions=frozenset(),
    )
    session = Session(session_id="s_admin", data=admin_session_data)

    # 1. Получение всех конфигураций
    configs = await app.router.call("oauth.admin_get_all_configs", session, {}, db=app.db)
    assert "branding" in configs
    assert "smtp" in configs
    assert "registration" in configs

    # 2. Обновление брендинга
    await app.router.call(
        "oauth.admin_update_config",
        session,
        {
            "key": "branding",
            "is_enabled": True,
            "config": {
                "app_title": "Agrita Admin Custom",
                "app_logo_svg": "<svg>logo</svg>",
            },
        },
        db=app.db,
    )

    pub_res = await app.router.call("system.get_public_config", session, {}, db=app.db)
    assert pub_res["app_title"] == "Agrita Admin Custom"
    assert pub_res["app_logo_svg"] == "<svg>logo</svg>"


@pytest.mark.asyncio
async def test_oauth_login_vk_flow(app: PyFerroApp) -> None:
    """Проверка полного цикла авторизации через VK ID (OAuth 2.1 + PKCE) с получением токена и профиля."""
    # Включаем провайдер VK
    async with app.db.session() as db:
        vk_cfg_stmt = select(AuthConfig).where(AuthConfig.key == "vk")
        vk_cfg = (await db.execute(vk_cfg_stmt)).scalar_one()
        vk_cfg.is_enabled = True
        vk_cfg.config = {
            "client_id": "54878944",
            "client_secret": "vk_super_secret",
            "redirect_uri": "https://stage.agrita.ru/auth/callback",
        }
        await db.commit()

    session = Session(session_id="s_vk", data=app.guest_session_data)
    url_res = await app.router.call(
        "oauth.get_auth_url",
        session,
        {"provider": "vk", "state": "vk_pkce_state_1"},
        db=app.db,
    )
    assert "id.vk.com/authorize" in url_res["url"]
    assert "code_challenge=" in url_res["url"]
    assert "code_challenge_method=s256" in url_res["url"]

    captured_token_data = {}

    async def mock_async_http_json(url: str, method: str = "GET", **kwargs):
        if "id.vk.com/oauth2/auth" in url:
            captured_token_data.update(kwargs.get("data") or {})
            return {
                "access_token": "mock_vk_token_xyz",
                "user_id": 77112233,
                "email": "durov_vk@example.com",
            }
        if "id.vk.com/oauth2/user_info" in url:
            return {
                "user": {
                    "user_id": "77112233",
                    "first_name": "Павел",
                    "last_name": "Дуров",
                    "screen_name": "durov_vk",
                    "avatar": "https://vk.com/photo200.jpg",
                }
            }
        if "users.get" in url:
            return {
                "response": [
                    {
                        "id": 77112233,
                        "first_name": "Павел",
                        "last_name": "Дуров",
                        "screen_name": "durov_vk",
                        "photo_200": "https://vk.com/photo200.jpg",
                    }
                ]
            }
        return {}

    with patch("pyferro2.oauth.providers.async_http_json", new=mock_async_http_json):
        res = await app.router.call(
            "oauth.login",
            session,
            {
                "provider": "vk",
                "code": "valid_vk_auth_code",
                "payload": {"state": "vk_pkce_state_1", "device_id": "vk_dev_999"},
            },
            db=app.db,
        )

        assert res["user"]["username"] == "durov_vk"
        assert not session.data.is_guest
        assert len(captured_token_data.get("code_verifier", "")) == 64
        assert captured_token_data.get("device_id") == "vk_dev_999"

        # Проверяем связку в БД
        async with app.db.session() as db:
            acc_stmt = select(OAuthAccount).where(OAuthAccount.provider == "vk")
            acc = (await db.execute(acc_stmt)).scalar_one()
            assert acc.provider_user_id == "77112233"
            assert acc.user_id == res["user"]["user_id"]

@pytest.mark.asyncio
async def test_oauth_login_telegram_flow(app: PyFerroApp) -> None:
    """Проверка авторизации через Telegram Login Widget с валидацией HMAC-SHA256."""
    bot_token = "123456789:AAFakeTokenForTelegramVerificationXYZ"

    # Включаем провайдер Telegram
    async with app.db.session() as db:
        tg_cfg_stmt = select(AuthConfig).where(AuthConfig.key == "telegram")
        tg_cfg = (await db.execute(tg_cfg_stmt)).scalar_one()
        tg_cfg.is_enabled = True
        tg_cfg.config = {
            "bot_token": bot_token,
            "bot_username": "my_pyferro_bot",
        }
        await db.commit()

    # Формируем валидный payload от виджета Telegram
    tg_payload = {
        "id": "99881122",
        "first_name": "Telegram",
        "last_name": "Tester",
        "username": "tg_tester_user",
        "auth_date": "1730000000",
    }
    # Вычисляем эталонный HMAC-SHA256 подписи Telegram
    check_pairs = [f"{k}={tg_payload[k]}" for k in sorted(tg_payload.keys())]
    check_str = "\n".join(check_pairs)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    tg_payload["hash"] = hmac.new(secret_key, check_str.encode("utf-8"), hashlib.sha256).hexdigest()

    session = Session(session_id="s_tg", data=app.guest_session_data)
    res = await app.router.call(
        "oauth.login",
        session,
        {"provider": "telegram", "payload": tg_payload},
        db=app.db,
    )

    assert res["user"]["username"] == "tg_tester_user"
    assert not session.data.is_guest

    # Проверяем связку в pf_auth_oauth
    async with app.db.session() as db:
        acc_stmt = select(OAuthAccount).where(OAuthAccount.provider == "telegram")
        acc = (await db.execute(acc_stmt)).scalar_one()
        assert acc.provider_user_id == "99881122"
        assert acc.user_id == res["user"]["user_id"]


@pytest.mark.asyncio
async def test_oauth_login_telegram_invalid_hash(app: PyFerroApp) -> None:
    """Проверка отклонения поддельных данных Telegram виджета."""
    async with app.db.session() as db:
        tg_cfg_stmt = select(AuthConfig).where(AuthConfig.key == "telegram")
        tg_cfg = (await db.execute(tg_cfg_stmt)).scalar_one()
        tg_cfg.is_enabled = True
        tg_cfg.config = {
            "bot_token": "123456789:SecretBotToken",
            "bot_username": "my_pyferro_bot",
        }
        await db.commit()

    tampered_payload = {
        "id": "11223344",
        "username": "hacker",
        "auth_date": "1730000000",
        "hash": "invalid_or_fake_hmac_hash_1234567890abcdef",
    }

    session = Session(session_id="s_hacker", data=app.guest_session_data)
    with pytest.raises(UnauthorizedError, match="Недействительная подпись"):
        await app.router.call(
            "oauth.login",
            session,
            {"provider": "telegram", "payload": tampered_payload},
            db=app.db,
        )


@pytest.mark.asyncio
async def test_oauth_get_auth_url_providers(app: PyFerroApp) -> None:
    """Проверка генерации ссылок авторизации для VK, Яндекса и Telegram."""
    session = Session(session_id="s_urls", data=app.guest_session_data)

    async with app.db.session() as db:
        for p in ["vk", "yandex", "telegram"]:
            stmt = select(AuthConfig).where(AuthConfig.key == p)
            rec = (await db.execute(stmt)).scalar_one()
            rec.is_enabled = True
            rec.config = {
                "client_id": "12345",
                "redirect_uri": "https://stage.agrita.ru/auth/callback",
                "bot_username": "test_bot",
                "bot_id": "123456",
            }
        await db.commit()

    vk_url = await app.router.call(
        "oauth.get_auth_url",
        session,
        {"provider": "vk", "state": "test_state_123"},
        db=app.db,
    )
    assert "id.vk.com/authorize" in vk_url["url"]
    assert "client_id=12345" in vk_url["url"]
    assert "state=test_state_123" in vk_url["url"]
    assert "code_challenge=" in vk_url["url"]
    assert "code_challenge_method=s256" in vk_url["url"]

    ya_url = await app.router.call(
        "oauth.get_auth_url",
        session,
        {"provider": "yandex", "state": "state_ya"},
        db=app.db,
    )
    assert "oauth.yandex.ru/authorize" in ya_url["url"]
    assert "client_id=12345" in ya_url["url"]
