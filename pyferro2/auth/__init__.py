"""
Подсистема аутентификации, ролевых моделей и сидинга PyFerro 2.0 (`pyferro2/auth/`).
"""

from pyferro2.auth.models import Role, RolePermission, User, user_role_table
from pyferro2.auth.passwords import hash_password, verify_password
from pyferro2.auth.seeder import (
    SYSTEM_ROLE_DESCRIPTIONS,
    ensure_admin_user,
    load_guest_session_data,
    seed_system_roles,
)

__all__ = [
    "User",
    "Role",
    "RolePermission",
    "user_role_table",
    "hash_password",
    "verify_password",
    "SYSTEM_ROLE_DESCRIPTIONS",
    "seed_system_roles",
    "ensure_admin_user",
    "load_guest_session_data",
]
