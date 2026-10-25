"""
JSON-RPC обработчики для подсистемы CRUD и разделов панели управления (`/pyferro_admin`).

Архитектура без лишних сущностей:
- Каждая модель `Model` при `crud.register(Model)` автоматически регистрирует
  4 прямых метода в роутере: `Model.create`, `Model.read`, `Model.update`, `Model.delete`
  (а также любые кастомные `@rpc_method`, объявленные внутри класса `Model`).
- Имена методов берутся напрямую из структуры классов и функций (`class crud: async def schemas`,
  `class admin: async def get_permissions_matrix`) — без параметра `name=...`.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.auth.models import Role, User
from pyferro2.auth.passwords import hash_password
from pyferro2.core.constants import USER_ROLE, admRole
from pyferro2.core.session_data import SessionData
from pyferro2.crud.engine import CrudEngine
from pyferro2.rpc.errors import InvalidParamsError
from pyferro2.rpc.router import RpcRouter


def register_crud_rpc(router: RpcRouter, crud_engine: CrudEngine) -> None:
    """Привязывает `CrudEngine` к `RpcRouter` и регистрирует методы управления."""
    crud_engine.attach_router(router)

    class crud:
        @router.rpc_method(public=True)
        async def schemas(session_data: SessionData) -> list[dict[str, Any]]:
            return crud_engine.list_schemas(session_data)

    # ─── Административные методы управления ролями, матрицей прав и пользователями ───

    class admin:
        @router.rpc_method(role=[admRole.adm_roles, admRole.adm_rpc])
        async def get_permissions_matrix(db: AsyncSession) -> dict[str, Any]:
            """
            Возвращает роли и единый список всех прикладных RPC-методов (`methods`),
            включая табличные `Article.create/read/update/delete` и кастомные `Book.transfer`.
            """
            roles = (await db.execute(select(Role).order_by(Role.id))).scalars().all()
            return {
                "roles": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "description": r.description,
                        "is_system": r.is_system,
                        "permissions": sorted(r.get_permissions()),
                    }
                    for r in roles
                ],
                "methods": router.business_methods(),
            }

        @router.rpc_method(role=[admRole.adm_roles, admRole.adm_rpc])
        async def set_role_permissions(
            db: AsyncSession,
            role_name: str,
            permissions: list[str],
        ) -> dict[str, Any]:
            return await crud_engine.set_role_permissions(db, role_name, permissions)

        @router.rpc_method(role=[admRole.adm_users, admRole.adm_roles])
        async def set_user_roles(
            db: AsyncSession,
            user_id: int,
            roles: list[str],
        ) -> dict[str, Any]:
            return await crud_engine.set_user_roles(db, user_id, roles)

        @router.rpc_method(role=[admRole.adm_users])
        async def create_user(
            db: AsyncSession,
            username: str,
            password: str,
            full_name: str = "",
            email: str | None = None,
            roles: list[str] | None = None,
        ) -> dict[str, Any]:
            if not username or not password:
                raise InvalidParamsError("Поля 'username' и 'password' обязательны")

            target_role_names = set(roles) if roles is not None else {USER_ROLE}
            role_objs = list(
                (await db.execute(select(Role).where(Role.name.in_(target_role_names)))).scalars().all()
            )

            user = User(
                username=username,
                password_hash=hash_password(password),
                full_name=full_name,
                email=email,
                is_active=True,
                roles=role_objs,
            )
            db.add(user)
            try:
                await db.commit()
            except Exception as exc:
                await db.rollback()
                raise InvalidParamsError(f"Не удалось создать пользователя '{username}': {exc}") from exc

            return {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "is_active": user.is_active,
                "roles": sorted(r.name for r in user.roles),
            }
