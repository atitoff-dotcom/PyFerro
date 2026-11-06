"""
Модуль отправки почты (SMTP) и управления кодами подтверждения email.

Без сторонних библиотек: использует встроенный `smtplib` + `ssl` + `asyncio.to_thread`.
Поддерживает Gmail (STARTTLS / SSL), Яндекс, Mail.ru и кастомные SMTP-серверы.
"""

import asyncio
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import secrets
import smtplib
import ssl
from typing import Any

logger = logging.getLogger("pyferro2.oauth.mailer")


def _send_smtp_sync(
    host: str,
    port: int,
    user: str,
    password: str,
    to_email: str,
    subject: str,
    html_content: str,
    from_email: str = "",
    use_ssl: bool = False,
    timeout: float = 12.0,
) -> None:
    sender = from_email or user
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    context = ssl.create_default_context()

    if use_ssl or port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            try:
                server.starttls(context=context)
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass  # Сервер без TLS (локальный relay)
            if user and password:
                server.login(user, password)
            server.send_message(msg)


async def send_email(
    host: str,
    port: int,
    user: str,
    password: str,
    to_email: str,
    subject: str,
    html_content: str,
    from_email: str = "",
    use_ssl: bool = False,
    timeout: float = 12.0,
) -> None:
    """Асинхронная отправка письма через SMTP в отдельном потоке."""
    await asyncio.to_thread(
        _send_smtp_sync,
        host=host,
        port=port,
        user=user,
        password=password,
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        from_email=from_email,
        use_ssl=use_ssl,
        timeout=timeout,
    )


class EmailVerificationStore:
    """
    Хранилище временных кодов подтверждения email в памяти с TTL.
    """

    def __init__(self, code_ttl_seconds: int = 600, max_attempts: int = 5) -> None:
        self.code_ttl_seconds = code_ttl_seconds
        self.max_attempts = max_attempts
        self._pending: dict[str, dict[str, Any]] = {}

    def generate_code(self) -> str:
        """Генерирует криптографически стойкий 6-значный цифровой код."""
        return f"{secrets.randbelow(1_000_000):06d}"

    def set_pending_registration(
        self,
        email: str,
        password: str,
        username: str = "",
        full_name: str = "",
    ) -> str:
        """Сохраняет черновик регистрации и возвращает 6-значный код."""
        norm_email = email.strip().lower()
        code = self.generate_code()
        now = datetime.now(timezone.utc).timestamp()
        self._pending[norm_email] = {
            "code": code,
            "password": password,
            "username": username,
            "full_name": full_name,
            "expires_at": now + self.code_ttl_seconds,
            "attempts": 0,
        }
        return code

    def verify_code(self, email: str, code: str) -> dict[str, Any] | None:
        """
        Проверяет введенный код.
        Возвращает данные пользователя при успехе, либо None при ошибке/истечении.
        """
        norm_email = email.strip().lower()
        record = self._pending.get(norm_email)
        if not record:
            return None

        now = datetime.now(timezone.utc).timestamp()
        if now > record["expires_at"]:
            self._pending.pop(norm_email, None)
            return None

        record["attempts"] += 1
        if record["attempts"] > self.max_attempts:
            self._pending.pop(norm_email, None)
            return None

        if record["code"] == code.strip():
            self._pending.pop(norm_email, None)
            return {
                "email": norm_email,
                "password": record["password"],
                "username": record["username"],
                "full_name": record["full_name"],
            }

        return None


verification_store = EmailVerificationStore()
