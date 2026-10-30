"""
Автоматический сидинг системных ролей и базового администратора (Boot Seeder).

Гарантирует, что при старте платформы в БД всегда присутствуют все системные роли
(`guest`, `user`, `admin`, `adm_*`) с флагом `is_system=True`.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.auth.models import Role, User
from pyferro2.auth.passwords import hash_password
from pyferro2.core.constants import GUEST_ROLE, USER_ROLE, admRole
from pyferro2.core.session_data import SessionData

# Понятные человекочитаемые описания всех системных ролей
SYSTEM_ROLE_DESCRIPTIONS: dict[str, str] = {
    GUEST_ROLE: "Неавторизованный посетитель (гость)",
    USER_ROLE: "Авторизованный пользователь",
    admRole.admin.value: "Главный администратор платформы (полный доступ)",
    admRole.adm_crud.value: "Доступ к разделу управления таблицами и данными (CRUD)",
    admRole.adm_users.value: "Доступ к разделу управления пользователями",
    admRole.adm_roles.value: "Доступ к разделу управления ролями и матрицей прав",
    admRole.adm_settings.value: "Доступ к системным настройкам",
    admRole.adm_rpc.value: "Доступ к инспектору и правам JSON-RPC методов",
    admRole.adm_help.value: "Чтение справки PyFerro2",
    admRole.adm_seo.value: "Доступ к управлению SEO-правилами и страницами",
}


async def seed_system_roles(session: AsyncSession) -> dict[str, Role]:
    """
    Идемпотентно создает недостающие системные роли в БД (`is_system=True`).
    Возвращает словарь `{имя_роли: объект_Role}`.
    """
    result = await session.execute(select(Role))
    existing_roles: dict[str, Role] = {role.name: role for role in result.scalars().all()}

    created_any = False
    for role_name, description in SYSTEM_ROLE_DESCRIPTIONS.items():
        if role_name not in existing_roles:
            new_role = Role(
                name=role_name,
                description=description,
                is_system=True,
            )
            session.add(new_role)
            existing_roles[role_name] = new_role
            created_any = True

    if created_any:
        await session.commit()

    return existing_roles


async def ensure_admin_user(
    session: AsyncSession,
    username: str = "admin",
    password: str = "admin",
    full_name: str = "Administrator",
    email: str | None = None,
) -> User:
    """
    Гарантирует наличие администратора с привязанной системной ролью `'admin'`.
    Если пользователь с таким `username` уже существует, убеждается, что у него есть роль `'admin'`.
    """
    roles_by_name = await seed_system_roles(session)
    admin_role = roles_by_name[admRole.admin.value]

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            email=email,
            is_active=True,
            roles=[admin_role],
        )
        session.add(user)
        await session.commit()
    else:
        user.password_hash = hash_password(password)
        if all(r.name != admRole.admin.value for r in user.roles):
            user.roles.append(admin_role)
        await session.commit()

    return user


async def load_guest_session_data(session: AsyncSession) -> SessionData:
    """
    Загружает разрешения системной роли `'guest'` из БД и возвращает готовый
    кэшированный `SessionData` для неавторизованных сессий.
    """
    result = await session.execute(select(Role).where(Role.name == GUEST_ROLE))
    guest_role = result.scalar_one_or_none()
    if guest_role is None:
        return SessionData.guest()
    return SessionData.guest(permissions=guest_role.get_permissions())
