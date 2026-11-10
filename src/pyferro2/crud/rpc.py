"""
JSON-RPC обработчики для подсистемы CRUD и разделов панели управления (`/pyferro_admin`).

Архитектура без лишних сущностей:
- Каждая модель `Model` при `crud.register(Model)` автоматически регистрирует
  4 прямых метода в роутере: `Model.create`, `Model.read`, `Model.update`, `Model.delete`
  (а также любые кастомные `@rpc_method`, объявленные внутри класса `Model`).
- Имена методов берутся напрямую из структуры классов и функций (`class crud: async def schemas`,
  `class admin: async def get_permissions_matrix`) — без параметра `name=...`.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.auth.models import Role, User
from pyferro2.auth.passwords import hash_password
from pyferro2.core.constants import USER_ROLE, admRole
from pyferro2.core.session import Session
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
        async def verify_access(
            session: Session,
            db: AsyncSession,
            delay_ms: int = 10,
        ) -> AsyncIterator[dict[str, Any]]:
            """
            Сквозная верификация матрицы прав через Dry-run RPC со стримингом прогресса.
            """
            delay_sec = 0.0 if delay_ms <= 0 else max(delay_ms, 10) / 1000.0

            roles = (await db.execute(select(Role).order_by(Role.id))).scalars().all()
            methods = router.business_methods()

            # Формирование контекстов (только в ОЗУ, без записи в БД)
            contexts: list[tuple[str, SessionData]] = [
                ("guest", SessionData.guest(guest_permissions=frozenset())),
            ]
            for role in roles:
                if role.name == "guest":
                    if role.get_permissions():
                        contexts[0] = (
                            "guest",
                            SessionData.guest(guest_permissions=frozenset(role.get_permissions())),
                        )
                    continue
                contexts.append((
                    role.name,
                    SessionData(
                        user_id=-1,
                        username=f"__check_{role.name}",
                        roles=frozenset([role.name]),
                        permissions=frozenset(role.get_permissions()),
                    ),
                ))

            total_checks = len(contexts) * len(methods)
            completed = 0
            issues: list[dict[str, Any]] = []

            test_session = Session(session_id="verify_access_check", data=contexts[0][1])

            for role_name, context_data in contexts:
                test_session.data = context_data

                for method_name in methods:
                    spec = router.get_spec(method_name)
                    if spec is None:
                        completed += 1
                        continue

                    actual_access = await router.call(
                        method_name,
                        test_session,
                        params={"_dry": True},
                        db=db,
                    )

                    expected_access = False
                    if spec.public or context_data.is_admin:
                        expected_access = True
                    elif spec.required_roles is not None and not context_data.roles.isdisjoint(spec.required_roles):
                        expected_access = True
                    elif spec.allowed_permissions and not context_data.permissions.isdisjoint(spec.allowed_permissions):
                        expected_access = True

                    if actual_access != expected_access:
                        issues.append({
                            "role": role_name,
                            "method": method_name,
                            "expected": expected_access,
                            "actual": actual_access,
                            "reason": "Публичный метод закрыт" if expected_access else "Метод доступен без прав",
                        })

                    completed += 1
                    yield {
                        "done": False,
                        "progress": int((completed / total_checks) * 100) if total_checks > 0 else 100,
                        "current_role": role_name,
                        "current_method": method_name,
                        "issues_count": len(issues),
                    }

                    if delay_sec > 0:
                        await asyncio.sleep(delay_sec)

            yield {
                "done": True,
                "progress": 100,
                "total_checks": total_checks,
                "issues": issues,
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
