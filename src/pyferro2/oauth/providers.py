"""
Драйверы внешних провайдеров авторизации (OAuth 2.0 / Telegram).

Каждый провайдер изолирован и реализует унифицированный контракт:
1. `get_auth_url(...)` — получение URL для редиректа/попапа.
2. `authenticate(...)` — обмен кода/payload на нормализованный профиль пользователя.
"""

from dataclasses import dataclass
import hashlib
import hmac
from typing import Any
import urllib.parse

from pyferro2.oauth.http_client import async_http_json
from pyferro2.rpc.errors import UnauthorizedError, ValidationError


@dataclass
class ExternalUserProfile:
    """Нормализованный профиль пользователя, полученный от внешнего провайдера."""

    provider: str
    provider_user_id: str
    email: str | None
    username: str | None
    display_name: str
    avatar_url: str
    raw_data: dict[str, Any]


class BaseProvider:
    """Базовый класс провайдера авторизации."""

    name: str = ""
    title: str = ""

    def get_auth_url(self, config: dict[str, Any], redirect_uri: str, state: str) -> str:
        raise NotImplementedError

    async def authenticate(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
        redirect_uri: str,
    ) -> ExternalUserProfile:
        raise NotImplementedError


class YandexProvider(BaseProvider):
    name = "yandex"
    title = "Яндекс ID"

    def get_auth_url(self, config: dict[str, Any], redirect_uri: str, state: str) -> str:
        client_id = config.get("client_id", "")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri or config.get("redirect_uri", ""),
            "state": state,
        }
        return f"https://oauth.yandex.ru/authorize?{urllib.parse.urlencode(params)}"

    async def authenticate(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
        redirect_uri: str,
    ) -> ExternalUserProfile:
        code = payload.get("code")
        if not code:
            raise ValidationError("Отсутствует параметр 'code'")

        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        actual_redirect = redirect_uri or config.get("redirect_uri", "")

        token_res = await async_http_json(
            "https://oauth.yandex.ru/token",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": actual_redirect,
            },
        )

        access_token = token_res.get("access_token")
        if not access_token:
            err = token_res.get("error_description") or token_res.get("error") or "Не удалось получить токен Яндекса"
            raise UnauthorizedError(f"Ошибка Яндекс ID: {err}")

        info = await async_http_json(
            "https://login.yandex.ru/info",
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        )

        user_id = str(info.get("id", ""))
        if not user_id:
            raise UnauthorizedError("Яндекс не вернул идентификатор пользователя")

        email = info.get("default_email") or (info.get("emails", [None])[0] if info.get("emails") else None)
        username = info.get("login") or f"yandex_{user_id}"
        display_name = info.get("real_name") or info.get("display_name") or username
        avatar_id = info.get("default_avatar_id")
        avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else ""

        return ExternalUserProfile(
            provider=self.name,
            provider_user_id=user_id,
            email=email,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
            raw_data=info,
        )


class VkProvider(BaseProvider):
    name = "vk"
    title = "VK ID"

    def get_auth_url(self, config: dict[str, Any], redirect_uri: str, state: str) -> str:
        client_id = config.get("client_id", "")
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri or config.get("redirect_uri", ""),
            "response_type": "code",
            "scope": "email",
            "display": "page",
            "v": "5.131",
            "state": state,
        }
        return f"https://oauth.vk.com/authorize?{urllib.parse.urlencode(params)}"

    async def authenticate(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
        redirect_uri: str,
    ) -> ExternalUserProfile:
        code = payload.get("code")
        if not code:
            raise ValidationError("Отсутствует параметр 'code'")

        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        actual_redirect = redirect_uri or config.get("redirect_uri", "")

        token_res = await async_http_json(
            "https://oauth.vk.com/access_token",
            method="GET",
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": actual_redirect,
                "code": code,
            },
        )

        access_token = token_res.get("access_token")
        user_id = str(token_res.get("user_id", ""))
        email = token_res.get("email")

        if not access_token or not user_id:
            err = token_res.get("error_description") or token_res.get("error") or "Не удалось получить токен VK"
            raise UnauthorizedError(f"Ошибка VK ID: {err}")

        user_info_res = await async_http_json(
            "https://api.vk.com/method/users.get",
            method="GET",
            params={
                "user_ids": user_id,
                "fields": "photo_200,screen_name",
                "access_token": access_token,
                "v": "5.131",
            },
        )

        items = user_info_res.get("response", [])
        u_data = items[0] if items else {}

        username = u_data.get("screen_name") or f"vk_{user_id}"
        first_name = u_data.get("first_name", "")
        last_name = u_data.get("last_name", "")
        display_name = f"{first_name} {last_name}".strip() or username
        avatar_url = u_data.get("photo_200", "")

        return ExternalUserProfile(
            provider=self.name,
            provider_user_id=user_id,
            email=email,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
            raw_data={"token": token_res, "user": u_data},
        )


class TelegramProvider(BaseProvider):
    name = "telegram"
    title = "Telegram"

    def get_auth_url(self, config: dict[str, Any], redirect_uri: str, state: str) -> str:
        # Для Telegram авторизация идет через виджет или прямое открытие диалога бота
        bot_username = config.get("bot_username", "").lstrip("@")
        if bot_username:
            return f"https://oauth.telegram.org/auth?bot_id={config.get('bot_id', '')}&origin={urllib.parse.quote(redirect_uri)}"
        return ""

    async def authenticate(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
        redirect_uri: str,
    ) -> ExternalUserProfile:
        bot_token = config.get("bot_token", "")
        if not bot_token:
            raise UnauthorizedError("Telegram bot_token не настроен")

        received_hash = payload.get("hash")
        if not received_hash:
            raise ValidationError("Отсутствует подпись 'hash' Telegram виджета")

        data_check = []
        for k in sorted(payload.keys()):
            if k != "hash":
                data_check.append(f"{k}={payload[k]}")
        check_str = "\n".join(data_check)

        secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
        computed_hash = hmac.new(secret_key, check_str.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            raise UnauthorizedError("Недействительная подпись данных Telegram")

        user_id = str(payload.get("id", ""))
        first_name = payload.get("first_name", "")
        last_name = payload.get("last_name", "")
        username = payload.get("username") or f"tg_{user_id}"
        display_name = f"{first_name} {last_name}".strip() or username
        avatar_url = payload.get("photo_url", "")

        return ExternalUserProfile(
            provider=self.name,
            provider_user_id=user_id,
            email=None,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
            raw_data=payload,
        )


class GoogleProvider(BaseProvider):
    name = "google"
    title = "Google"

    def get_auth_url(self, config: dict[str, Any], redirect_uri: str, state: str) -> str:
        client_id = config.get("client_id", "")
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri or config.get("redirect_uri", ""),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    async def authenticate(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
        redirect_uri: str,
    ) -> ExternalUserProfile:
        code = payload.get("code")
        if not code:
            raise ValidationError("Отсутствует параметр 'code'")

        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        actual_redirect = redirect_uri or config.get("redirect_uri", "")

        token_res = await async_http_json(
            "https://oauth2.googleapis.com/token",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": actual_redirect,
                "grant_type": "authorization_code",
            },
        )

        access_token = token_res.get("access_token")
        if not access_token:
            err = token_res.get("error_description") or token_res.get("error") or "Не удалось получить токен Google"
            raise UnauthorizedError(f"Ошибка Google OAuth: {err}")

        info = await async_http_json(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        user_id = str(info.get("sub", ""))
        email = info.get("email")
        display_name = info.get("name") or email or f"Google User {user_id}"
        username = email.split("@")[0] if email else f"google_{user_id}"
        avatar_url = info.get("picture", "")

        return ExternalUserProfile(
            provider=self.name,
            provider_user_id=user_id,
            email=email,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
            raw_data=info,
        )


PROVIDERS: dict[str, BaseProvider] = {
    "yandex": YandexProvider(),
    "vk": VkProvider(),
    "telegram": TelegramProvider(),
    "google": GoogleProvider(),
}
