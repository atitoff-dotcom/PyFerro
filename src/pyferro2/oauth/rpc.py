"""
RPC-методы для внешней авторизации, регистрации, брендинга и админки OAuth.
"""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import orjson

from pyferro2.auth.models import Role, User
from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro2.oauth.mailer import send_email, verification_store
from pyferro2.oauth.manager import (
    find_available_username,
    get_or_create_config,
    link_or_create_oauth_user,
    seed_auth_configs,
)
from pyferro2.oauth.models import AuthConfig, OAuthAccount
from pyferro2.oauth.providers import PROVIDERS
from pyferro2.rpc.errors import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from pyferro2.rpc.router import RpcRouter
from pyferro2.cache.manager import cache_manager
from pyferro2.server.auth_rpc import serialize_session_data
from pyferro2.server.tokens import TokenManager


def register_oauth_rpc(router: RpcRouter, token_manager: TokenManager) -> None:
    """Регистрирует методы `system.get_public_config`, `auth.register`, `auth.verify_email_code` и `oauth.*`."""

    class system:
        @router.rpc_method(public=True)
        async def get_public_config(db: AsyncSession) -> dict[str, Any]:
            await seed_auth_configs(db)

            brand_cfg = await get_or_create_config(db, "branding")
            reg_cfg = await get_or_create_config(db, "registration")

            prov_list = []
            for p_name, p_inst in PROVIDERS.items():
                p_cfg = await get_or_create_config(db, p_name)
                prov_list.append({
                    "name": p_name,
                    "title": p_inst.title,
                    "is_enabled": p_cfg.is_enabled,
                    "client_id": p_cfg.config.get("client_id", ""),
                    "redirect_uri": p_cfg.config.get("redirect_uri", ""),
                })

            return {
                "app_title": brand_cfg.config.get("app_title", "PyFerro 2.0 Admin"),
                "app_logo_svg": brand_cfg.config.get("app_logo_svg", ""),
                "allow_registration": reg_cfg.config.get("allow_registration", True) and reg_cfg.is_enabled,
                "require_email_verification": reg_cfg.config.get("require_email_verification", False),
                "providers": prov_list,
                "cache_manifest": cache_manager.config.to_public_manifest(),
            }
    class auth:
        @router.rpc_method(public=True)
        async def register(
            session: Session,
            db: AsyncSession,
            email: str,
            password: str,
            username: str = "",
            full_name: str = "",
        ) -> dict[str, Any]:
            clean_email = email.strip().lower()
            if not clean_email or "@" not in clean_email:
                raise ValidationError("Некорректный адрес электронной почты")

            if len(password) < 6:
                raise ValidationError("Пароль должен содержать минимум 6 символов")

            reg_cfg = await get_or_create_config(db, "registration")
            if not reg_cfg.is_enabled or not reg_cfg.config.get("allow_registration", True):
                raise ForbiddenError("Регистрация новых пользователей отключена")

            # Проверка уникальности email
            email_stmt = select(User.id).where(User.email == clean_email)
            if (await db.execute(email_stmt)).scalar_one_or_none() is not None:
                raise ValidationError("Пользователь с таким email уже существует")

            # Проверка username, если указан
            final_username = username.strip()
            if final_username:
                u_stmt = select(User.id).where(User.username == final_username)
                if (await db.execute(u_stmt)).scalar_one_or_none() is not None:
                    raise ValidationError("Это имя пользователя уже занято")
            else:
                final_username = await find_available_username(db, clean_email.split("@")[0])

            # Требуется ли подтверждение email через код?
            if reg_cfg.config.get("require_email_verification", False):
                code = verification_store.set_pending_registration(
                    email=clean_email,
                    password=password,
                    username=final_username,
                    full_name=full_name.strip() or final_username,
                )

                smtp_cfg = await get_or_create_config(db, "smtp")
                brand_cfg = await get_or_create_config(db, "branding")
                app_title = brand_cfg.config.get("app_title", "PyFerro 2.0")

                if smtp_cfg.is_enabled and smtp_cfg.config.get("host"):
                    try:
                        html = f"""
                        <div style="font-family: sans-serif; padding: 20px; line-height: 1.5;">
                            <h2>Подтверждение регистрации в {app_title}</h2>
                            <p>Ваш одноразовый код подтверждения:</p>
                            <h1 style="color: #2563eb; letter-spacing: 4px; font-size: 32px;">{code}</h1>
                            <p style="color: #666; font-size: 13px;">Код действителен в течение 10 минут. Если вы не запрашивали регистрацию, проигнорируйте это письмо.</p>
                        </div>
                        """
                        await send_email(
                            host=smtp_cfg.config.get("host", ""),
                            port=int(smtp_cfg.config.get("port", 587)),
                            user=smtp_cfg.config.get("user", ""),
                            password=smtp_cfg.config.get("password", ""),
                            to_email=clean_email,
                            subject=f"Код подтверждения: {code} — {app_title}",
                            html_content=html,
                            from_email=smtp_cfg.config.get("from_email", ""),
                            use_ssl=bool(smtp_cfg.config.get("use_ssl", False)),
                        )
                    except Exception as e:
                        raise ValidationError(f"Не удалось отправить письмо с кодом: {e}")

                return {
                    "status": "verification_required",
                    "email": clean_email,
                    "message": "Код подтверждения отправлен на вашу почту",
                }

            # Прямая регистрация без подтверждения
            new_user = User(
                username=final_username,
                email=clean_email,
                full_name=full_name.strip() or final_username,
                is_active=True,
            )
            new_user.set_password(password)

            role_stmt = select(Role).where(Role.name == "user")
            user_role = (await db.execute(role_stmt)).scalar_one_or_none()
            if user_role is not None:
                new_user.roles.append(user_role)

            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)

            session_data = new_user.to_session_data()
            session.authenticate(session_data)
            token = token_manager.issue_token(session_data)

            return {
                "status": "registered",
                "token": token,
                "user": serialize_session_data(session_data),
            }

        @router.rpc_method(public=True)
        async def verify_email_code(
            session: Session,
            db: AsyncSession,
            email: str,
            code: str,
        ) -> dict[str, Any]:
            verified = verification_store.verify_code(email, code)
            if not verified:
                raise ValidationError("Неверный или истекший код подтверждения")

            # Создаем пользователя
            new_user = User(
                username=verified["username"],
                email=verified["email"],
                full_name=verified["full_name"],
                is_active=True,
            )
            new_user.set_password(verified["password"])

            role_stmt = select(Role).where(Role.name == "user")
            user_role = (await db.execute(role_stmt)).scalar_one_or_none()
            if user_role is not None:
                new_user.roles.append(user_role)

            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)

            session_data = new_user.to_session_data()
            session.authenticate(session_data)
            token = token_manager.issue_token(session_data)

            return {
                "status": "verified",
                "token": token,
                "user": serialize_session_data(session_data),
            }

    class oauth:
        @router.rpc_method(public=True)
        async def status(db: AsyncSession) -> dict[str, Any]:
            prov_list = []
            for p_name, p_inst in PROVIDERS.items():
                p_cfg = await get_or_create_config(db, p_name)
                prov_list.append({
                    "name": p_name,
                    "title": p_inst.title,
                    "is_enabled": p_cfg.is_enabled,
                    "client_id": p_cfg.config.get("client_id", ""),
                    "redirect_uri": p_cfg.config.get("redirect_uri", ""),
                })
            return {"providers": prov_list}

        @router.rpc_method(public=True)
        async def get_auth_url(
            db: AsyncSession,
            provider: str,
            state: str = "",
            redirect_uri: str = "",
        ) -> dict[str, Any]:
            prov = PROVIDERS.get(provider)
            if not prov:
                raise NotFoundError(f"Провайдер '{provider}' не поддерживается")

            p_cfg = await get_or_create_config(db, provider)
            if not p_cfg.is_enabled:
                raise ForbiddenError(f"Авторизация через '{prov.title}' временно отключена")

            url = prov.get_auth_url(p_cfg.config, redirect_uri, state)
            return {"url": url}

        @router.rpc_method(public=True)
        async def login(
            session: Session,
            db: AsyncSession,
            provider: str,
            payload: dict[str, Any] | None = None,
            code: str | None = None,
            state: str | None = None,
            device_id: str | None = None,
            redirect_uri: str = "",
        ) -> dict[str, Any]:
            prov = PROVIDERS.get(provider)
            if not prov:
                raise NotFoundError(f"Неизвестный провайдер '{provider}'")

            p_cfg = await get_or_create_config(db, provider)
            if not p_cfg.is_enabled:
                raise ForbiddenError(f"Авторизация через '{prov.title}' отключена")

            call_payload = dict(payload or {})
            if code:
                call_payload["code"] = code
            if state and "state" not in call_payload:
                call_payload["state"] = state
            if device_id and "device_id" not in call_payload:
                call_payload["device_id"] = device_id

            profile = await prov.authenticate(p_cfg.config, call_payload, redirect_uri)
            user = await link_or_create_oauth_user(db, profile, session.data)

            session_data = user.to_session_data()
            session.authenticate(session_data)
            token = token_manager.issue_token(session_data)

            return {
                "token": token,
                "user": serialize_session_data(session_data),
            }

        @router.rpc_method()
        async def my_accounts(session_data: SessionData, db: AsyncSession) -> list[dict[str, Any]]:
            if session_data.is_guest or session_data.user_id is None:
                raise UnauthorizedError("Требуется авторизация")

            stmt = select(OAuthAccount).where(OAuthAccount.user_id == session_data.user_id)
            accounts = (await db.execute(stmt)).scalars().all()
            return [
                {
                    "id": a.id,
                    "provider": a.provider,
                    "provider_user_id": a.provider_user_id,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "profile": a.profile_data,
                }
                for a in accounts
            ]

        @router.rpc_method()
        async def unlink(
            session_data: SessionData,
            db: AsyncSession,
            provider: str,
        ) -> dict[str, Any]:
            if session_data.is_guest or session_data.user_id is None:
                raise UnauthorizedError("Требуется авторизация")

            stmt = select(OAuthAccount).where(
                OAuthAccount.user_id == session_data.user_id,
                OAuthAccount.provider == provider,
            )
            acc = (await db.execute(stmt)).scalar_one_or_none()
            if not acc:
                raise NotFoundError(f"Связка с '{provider}' не найдена")

            await db.delete(acc)
            await db.commit()
            return {"status": "unlinked", "provider": provider}

        # ---------------- Админские методы ----------------

        @router.rpc_method(role=["admin", "adm_auth"])
        async def admin_list(
            db: AsyncSession,
            search: str = "",
            provider: str = "",
            limit: int = 50,
            offset: int = 0,
        ) -> dict[str, Any]:
            query = select(OAuthAccount, User).join(User, OAuthAccount.user_id == User.id)

            if provider:
                query = query.where(OAuthAccount.provider == provider)

            if search:
                term = f"%{search.strip()}%"
                query = query.where(
                    (User.username.ilike(term))
                    | (User.email.ilike(term))
                    | (OAuthAccount.provider_user_id.ilike(term))
                )

            count_stmt = select(func.count()).select_from(query.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0

            records = (await db.execute(query.limit(limit).offset(offset))).all()
            items = []
            for acc, u in records:
                p_data = acc.profile_data
                items.append({
                    "id": acc.id,
                    "user_id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "provider": acc.provider,
                    "provider_user_id": acc.provider_user_id,
                    "display_name": p_data.get("display_name") or p_data.get("name") or u.full_name or u.username,
                    "avatar_url": p_data.get("avatar_url") or p_data.get("photo_url") or "",
                    "created_at": acc.created_at.isoformat() if acc.created_at else None,
                })

            return {"items": items, "total": total}

        @router.rpc_method(role=["admin", "adm_auth"])
        async def admin_delete(db: AsyncSession, account_id: int) -> dict[str, Any]:
            stmt = select(OAuthAccount).where(OAuthAccount.id == account_id)
            acc = (await db.execute(stmt)).scalar_one_or_none()
            if not acc:
                raise NotFoundError("Запись связки не найдена")

            await db.delete(acc)
            await db.commit()
            return {"status": "deleted", "account_id": account_id}

        @router.rpc_method(role=["admin", "adm_auth"])
        async def admin_get_all_configs(db: AsyncSession) -> dict[str, Any]:
            await seed_auth_configs(db)
            stmt = select(AuthConfig)
            records = (await db.execute(stmt)).scalars().all()
            res = {}
            for r in records:
                res[r.key] = {
                    "is_enabled": r.is_enabled,
                    "config": r.config,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
            return res

        @router.rpc_method(role=["admin", "adm_auth"])
        async def admin_update_config(
            db: AsyncSession,
            key: str,
            is_enabled: bool,
            config: dict[str, Any],
        ) -> dict[str, Any]:
            cfg = await get_or_create_config(db, key)
            cfg.is_enabled = is_enabled
            cfg.config = config
            await db.commit()
            return {"status": "updated", "key": key}

        @router.rpc_method(role=["admin", "adm_auth"])
        async def admin_test_smtp(
            db: AsyncSession,
            target_email: str,
            smtp_config: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            target = target_email.strip()
            if not target or "@" not in target:
                raise ValidationError("Некорректный email для проверки")

            if smtp_config:
                cfg = smtp_config
            else:
                db_cfg = await get_or_create_config(db, "smtp")
                cfg = db_cfg.config

            host = cfg.get("host", "").strip()
            if not host:
                raise ValidationError("SMTP сервер не указан")

            brand = await get_or_create_config(db, "branding")
            app_title = brand.config.get("app_title", "PyFerro 2.0")

            html = f"""
            <div style="font-family: sans-serif; padding: 20px;">
                <h2 style="color: #10b981;">✓ Тестовое письмо успешно доставлено</h2>
                <p>Ваш SMTP-сервер в <b>{app_title}</b> настроен и работает корректно!</p>
                <p style="color: #666; font-size: 13px;">Хост: {host}:{cfg.get('port', 587)} | Отправитель: {cfg.get('user', '')}</p>
            </div>
            """
            try:
                await send_email(
                    host=host,
                    port=int(cfg.get("port", 587)),
                    user=cfg.get("user", ""),
                    password=cfg.get("password", ""),
                    to_email=target,
                    subject=f"Тест SMTP: {app_title}",
                    html_content=html,
                    from_email=cfg.get("from_email", ""),
                    use_ssl=bool(cfg.get("use_ssl", False)),
                )
            except Exception as e:
                raise ValidationError(f"Ошибка отправки тестового письма: {e}")

            return {"status": "sent", "to": target}
