"""
Пакет внешней авторизации (OAuth/SSO), брендинга и подтверждения email для PyFerro 2.0.
"""

from pyferro2.oauth.models import AuthConfig, OAuthAccount

__all__ = ["OAuthAccount", "AuthConfig"]
