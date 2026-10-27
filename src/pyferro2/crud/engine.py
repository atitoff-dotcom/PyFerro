"""
Движок декларативного CRUD и матрицы прав (`CrudEngine`).

Обеспечивает:
1. Единую точечную модель: каждая зарегистрированная таблица `Model` автоматически
   регистрирует в роутере 4 RPC-метода: `Model.create`, `Model.read`, `Model.update`, `Model.delete`.
2. Двухуровневую проверку прав за O(1) в памяти:
   - Полные права (`"Model.read"`, `"Model.update"`, `"Model.delete"`),
   - Права «только свои» (`"Model.read_own"`, `"Model.update_own"`, `"Model.delete_own"`).
     Если у модели нет `creator_id` (или это `create`), включенная галочка `*_own`
     спокойно работает без ошибок.
3. Защиту системных записей (`Role` с `is_system=True`).
4. Управление матрицей прав ролей и ролями пользователей с автоматическим
   корректным дисконнектом затронутых пользователей.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.auth.models import Role, RolePermission, User
from pyferro2.core.constants import GUEST_ROLE, admRole
from pyferro2.core.session_data import SessionData
from pyferro2.crud.spec import ModelSpec, compile_model_spec
from pyferro2.db.base import Base
from pyferro2.files.models import StoredFile
from pyferro2.rpc.errors import (
    ForbiddenError,
    InvalidParamsError,
    RpcError,
    UnauthorizedError,
)
from pyferro2.seo.page_cache import clear_seo_cache
from pyferro2.seo.sitemap import invalidate_sitemap_cache

if TYPE_CHECKING:
    from pyferro2.rpc.router import RpcRouter

DisconnectUserCallback = Callable[[int], Awaitable[None]]
GuestPermissionsCallback = Callable[[frozenset[str]], None]


def _serialize_instance(instance: Base, spec: ModelSpec) -> dict[str, Any]:
    """Сериализует только видимые (`readable_fields`) колонки ORM-объекта, исключая `hidden`."""
    out: dict[str, Any] = {}
    for field_name in spec.readable_fields:
        val = getattr(instance, field_name, None)
        if isinstance(val, datetime):
            out[field_name] = val.isoformat()
        else:
            out[field_name] = val
    if isinstance(instance, User):
        out["roles"] = sorted(r.name for r in instance.roles)
    elif isinstance(instance, Role):
        out["permissions"] = sorted(instance.get_permissions())
    return out


class CrudEngine:
    """
    Реестр моделей и исполнитель CRUD-операций с проверкой прав доступа.
    """

    __slots__ = (
        "_models",
        "_router",
        "_on_disconnect_user",
        "_on_guest_permissions_updated",
    )

    def __init__(
        self,
        *,
        on_disconnect_user: DisconnectUserCallback | None = None,
        on_guest_permissions_updated: GuestPermissionsCallback | None = None,
        register_system_models: bool = True,
    ) -> None:
        self._models: dict[str, ModelSpec] = {}
        self._router: RpcRouter | None = None
        self._on_disconnect_user = on_disconnect_user
        self._on_guest_permissions_updated = on_guest_permissions_updated

        if register_system_models:
            self.register(
                User,
                title="Пользователи",
                searchable=("username", "email", "full_name"),
                readonly=("id",),
                hidden=("password_hash",),
            )
            self.register(
                Role,
                title="Роли безопасности",
                searchable=("name", "description"),
                readonly=("id", "is_system"),
            )
            self.register(
                StoredFile,
                title="Файлы",
                searchable=("filename", "original_name", "folder_hash"),
                readonly=("id", "creator_id", "folder_hash", "size", "sha256", "created_at", "updated_at"),
            )

    def attach_router(self, router: RpcRouter) -> None:
        """Привязывает `RpcRouter` и регистрирует `<Model>.create / read / update / delete` для всех моделей."""
        self._router = router
        for spec in self._models.values():
            self._bind_model_rpc(spec)

    def _bind_model_rpc(self, spec: ModelSpec) -> None:
        """Регистрирует 4 метода `<Model>.create / read / update / delete` в роутере."""
        if self._router is None:
            return

        model_name = spec.name
        is_sys_rbac = spec.model_cls in (User, Role)
        extra_roles: list[str] = [admRole.adm_crud]
        if spec.model_cls is User:
            extra_roles.append(admRole.adm_users)
        elif spec.model_cls is Role:
            extra_roles.append(admRole.adm_roles)

        async def _create(
            session_data: SessionData,
            db: AsyncSession,
            data: dict[str, Any],
        ) -> dict[str, Any]:
            return await self.create_record(db, session_data, model_name, data)

        async def _read(
            session_data: SessionData,
            db: AsyncSession,
            id: int | None = None,
            page: int = 1,
            limit: int = 50,
            search: str = "",
            tabular: bool = False,
        ) -> dict[str, Any]:
            if id is not None:
                return await self.get_record(db, session_data, model_name, id)
            return await self.list_records(
                db,
                session_data,
                model_name,
                page=page,
                limit=limit,
                search=search,
                tabular=tabular,
            )

        async def _update(
            session_data: SessionData,
            db: AsyncSession,
            id: int,
            data: dict[str, Any],
        ) -> dict[str, Any]:
            return await self.update_record(db, session_data, model_name, id, data)

        async def _delete(
            session_data: SessionData,
            db: AsyncSession,
            id: int,
        ) -> dict[str, Any]:
            return await self.delete_record(db, session_data, model_name, id)

        for action, fn in (
            ("create", _create),
            ("read", _read),
            ("update", _update),
            ("delete", _delete),
        ):
            fn.__name__ = action
            fn.__qualname__ = f"{model_name}.{action}"
            self._router.rpc_method(
                fn,
                role=extra_roles,
                allow_permissions=not is_sys_rbac,
            )

        # Также автоматически подхватываем любые кастомные @rpc_method методы,
        # объявленные прямо внутри класса модели (например `class Book(RowSecureModel): async def transfer(...)`)
        for attr in spec.model_cls.__dict__.values():
            custom_spec = getattr(attr, "__rpc_spec__", None)
            if custom_spec is not None:
                self._router.methods[custom_spec.name] = custom_spec

    @property
    def models(self) -> dict[str, ModelSpec]:
        """Возвращает словарь всех зарегистрированных `ModelSpec`."""
        return self._models

    def get_spec(self, model_name: str) -> ModelSpec:
        spec = self._models.get(model_name)
        if spec is None:
            raise InvalidParamsError(f"Модель '{model_name}' не зарегистрирована в CRUD")
        return spec

    def register(
        self,
        model_cls: type[Base],
        *,
        name: str | None = None,
        title: str | None = None,
        searchable: Iterable[str] | None = None,
        readonly: Iterable[str] | None = None,
        hidden: Iterable[str] | None = None,
    ) -> ModelSpec:
        """Компилирует `ModelSpec` один раз и регистрирует 4 метода `<Model>.create/read/update/delete`."""
        spec = compile_model_spec(
            model_cls,
            name=name,
            title=title,
            searchable=searchable,
            readonly=readonly,
            hidden=hidden,
        )
        self._models[spec.name] = spec
        if self._router is not None:
            self._bind_model_rpc(spec)
        return spec

    def _has_admin_bypass(self, spec: ModelSpec, session_data: SessionData) -> bool:
        """Проверяет, есть ли у пользователя административный доступ к данной модели."""
        if session_data.is_admin or session_data.has_admin_access("crud"):
            return True
        if spec.model_cls is User and session_data.has_admin_access("users"):
            return True
        if spec.model_cls is Role and session_data.has_admin_access("roles"):
            return True
        return False

    def _check_access_mode(
        self,
        spec: ModelSpec,
        session_data: SessionData,
        global_perm: str,
        own_perm: str | None = None,
    ) -> str:
        """
        Возвращает режим доступа к операции:
        - `'all'` — доступ ко всем записям таблицы,
        - `'own'` — доступ только к своим записям (`creator_id == session_data.user_id`).
        Если админ включил галочку `*_own` на `create` или на модели без `creator_id` —
        спокойно возвращает `'all'` без ошибок.
        """
        if self._has_admin_bypass(spec, session_data) or global_perm in session_data.permissions:
            return "all"
        if own_perm and own_perm in session_data.permissions:
            if session_data.is_guest:
                raise UnauthorizedError("Для работы со своими записями необходима авторизация")
            return "own" if spec.has_creator_id else "all"

        if session_data.is_guest:
            raise UnauthorizedError(f"Требуется авторизация для доступа к '{global_perm}'")
        raise ForbiddenError(f"Недостаточно прав: требуется разрешение '{global_perm}'")

    def list_schemas(self, session_data: SessionData) -> list[dict[str, Any]]:
        """
        Возвращает список декларативных схем моделей, доступных текущему пользователю.
        Системные таблицы `User` и `Role` доступны только администраторам (`admin` / `adm_*`).
        """
        out: list[dict[str, Any]] = []
        for spec in self._models.values():
            if spec.model_cls in (User, Role):
                if self._has_admin_bypass(spec, session_data):
                    out.append(spec.to_schema_dict())
                continue

            if (
                self._has_admin_bypass(spec, session_data)
                or spec.perm_read in session_data.permissions
                or spec.perm_read_own in session_data.permissions
            ):
                out.append(spec.to_schema_dict())
        return out

    async def list_records(
        self,
        db: AsyncSession,
        session_data: SessionData,
        model_name: str,
        *,
        page: int = 1,
        limit: int = 50,
        search: str = "",
        tabular: bool = False,
    ) -> dict[str, Any]:
        """Возвращает пагинированный список записей таблицы (с поддержкой RLS и `$tabular`)."""
        spec = self.get_spec(model_name)
        mode = self._check_access_mode(spec, session_data, spec.perm_read, spec.perm_read_own)

        model_cls = spec.model_cls
        stmt = select(model_cls)
        count_stmt = select(func.count(model_cls.id))

        if mode == "own":
            owner_filter = getattr(model_cls, "creator_id") == session_data.user_id
            stmt = stmt.where(owner_filter)
            count_stmt = count_stmt.where(owner_filter)

        search_clean = search.strip() if search else ""
        if search_clean and spec.searchable_fields:
            like_pattern = f"%{search_clean}%"
            clauses = [
                getattr(model_cls, fname).ilike(like_pattern)
                for fname in spec.searchable_fields
            ]
            search_cond = or_(*clauses)
            stmt = stmt.where(search_cond)
            count_stmt = count_stmt.where(search_cond)

        safe_page = max(1, page)
        safe_limit = min(max(1, limit), 200)
        offset = (safe_page - 1) * safe_limit

        total = (await db.execute(count_stmt)).scalar() or 0
        rows = (
            await db.execute(stmt.order_by(model_cls.id.desc()).offset(offset).limit(safe_limit))
        ).scalars().all()

        if tabular:
            fields = list(spec.readable_fields)
            if spec.model_cls is User:
                fields.append("roles")
            elif spec.model_cls is Role:
                fields.append("permissions")

            tabular_rows: list[list[Any]] = []
            for row in rows:
                r_vals: list[Any] = []
                for fname in spec.readable_fields:
                    val = getattr(row, fname, None)
                    r_vals.append(val.isoformat() if isinstance(val, datetime) else val)
                if isinstance(row, User):
                    r_vals.append(sorted(r.name for r in row.roles))
                elif isinstance(row, Role):
                    r_vals.append(sorted(row.get_permissions()))
                tabular_rows.append(r_vals)

            return {
                "$tabular": True,
                "model": spec.name,
                "total": int(total),
                "page": safe_page,
                "limit": safe_limit,
                "fields": fields,
                "rows": tabular_rows,
            }

        return {
            "model": spec.name,
            "total": int(total),
            "page": safe_page,
            "limit": safe_limit,
            "items": [_serialize_instance(row, spec) for row in rows],
        }

    async def get_record(
        self,
        db: AsyncSession,
        session_data: SessionData,
        model_name: str,
        record_id: int,
    ) -> dict[str, Any]:
        """Возвращает одну запись по `id` с проверкой глобального или построчного права чтения."""
        spec = self.get_spec(model_name)
        mode = self._check_access_mode(spec, session_data, spec.perm_read, spec.perm_read_own)

        instance = (
            await db.execute(select(spec.model_cls).where(spec.model_cls.id == record_id))
        ).scalar_one_or_none()
        if instance is None:
            raise RpcError(f"Запись {spec.name}#{record_id} не найдена", code=-32004)

        if mode == "own" and getattr(instance, "creator_id", None) != session_data.user_id:
            raise ForbiddenError("Нет прав на чтение чужой записи")

        return _serialize_instance(instance, spec)

    async def create_record(
        self,
        db: AsyncSession,
        session_data: SessionData,
        model_name: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Создает новую запись (автоматически проставляя `creator_id` для `RowSecureModel`)."""
        spec = self.get_spec(model_name)
        self._check_access_mode(spec, session_data, spec.perm_create, spec.perm_create_own)

        if not isinstance(data, dict):
            raise InvalidParamsError("Поле 'data' должно быть словарем")

        clean_kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k in spec.writable_fields:
                clean_kwargs[k] = v

        if spec.has_creator_id:
            clean_kwargs["creator_id"] = session_data.user_id

        try:
            instance = spec.model_cls(**clean_kwargs)
            db.add(instance)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise InvalidParamsError(f"Ошибка создания записи {spec.name}: {exc}") from exc

        clear_seo_cache()
        invalidate_sitemap_cache()
        return _serialize_instance(instance, spec)

    async def update_record(
        self,
        db: AsyncSession,
        session_data: SessionData,
        model_name: str,
        record_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Обновляет запись по `id` (защищая `readonly`-поля и системные роли `is_system=True`)."""
        spec = self.get_spec(model_name)
        mode = self._check_access_mode(spec, session_data, spec.perm_update, spec.perm_update_own)

        if not isinstance(data, dict):
            raise InvalidParamsError("Поле 'data' должно быть словарем")

        instance = (
            await db.execute(select(spec.model_cls).where(spec.model_cls.id == record_id))
        ).scalar_one_or_none()
        if instance is None:
            raise RpcError(f"Запись {spec.name}#{record_id} не найдена", code=-32004)

        if mode == "own" and getattr(instance, "creator_id", None) != session_data.user_id:
            raise ForbiddenError("Нет прав на редактирование чужой записи")

        # Явная защита системных ролей при попытке смены имени через CRUD
        if isinstance(instance, Role) and instance.is_system:
            if "name" in data and data["name"] != instance.name:
                raise ForbiddenError(f"Запрещено переименовывать системную роль '{instance.name}'")

        readonly_attempted = data.keys() & spec.readonly_fields
        if readonly_attempted:
            raise ForbiddenError(
                f"Поля только для чтения нельзя изменять: {', '.join(sorted(readonly_attempted))}"
            )

        for k, v in data.items():
            if k in spec.writable_fields:
                setattr(instance, k, v)

        try:
            await db.commit()
        except ValueError as exc:
            await db.rollback()
            raise ForbiddenError(str(exc)) from exc
        except Exception as exc:
            await db.rollback()
            raise InvalidParamsError(f"Ошибка обновления записи {spec.name}: {exc}") from exc

        # Если пользователя деактивировали (is_active=False) — сразу отключаем его активные сессии
        if isinstance(instance, User) and not instance.is_active and self._on_disconnect_user:
            await self._on_disconnect_user(instance.id)

        clear_seo_cache()
        invalidate_sitemap_cache()
        return _serialize_instance(instance, spec)

    async def delete_record(
        self,
        db: AsyncSession,
        session_data: SessionData,
        model_name: str,
        record_id: int,
    ) -> dict[str, Any]:
        """Удаляет запись по `id` (блокируя удаление системных ролей `is_system=True`)."""
        spec = self.get_spec(model_name)
        mode = self._check_access_mode(spec, session_data, spec.perm_delete, spec.perm_delete_own)

        instance = (
            await db.execute(select(spec.model_cls).where(spec.model_cls.id == record_id))
        ).scalar_one_or_none()
        if instance is None:
            raise RpcError(f"Запись {spec.name}#{record_id} не найдена", code=-32004)

        if mode == "own" and getattr(instance, "creator_id", None) != session_data.user_id:
            raise ForbiddenError("Нет прав на удаление чужой записи")

        if isinstance(instance, Role) and instance.is_system:
            raise ForbiddenError(f"Запрещено удалять системную роль '{instance.name}'")

        deleted_user_id = instance.id if isinstance(instance, User) else None

        try:
            await db.delete(instance)
            await db.commit()
        except ValueError as exc:
            await db.rollback()
            raise ForbiddenError(str(exc)) from exc

        if deleted_user_id is not None and self._on_disconnect_user is not None:
            await self._on_disconnect_user(deleted_user_id)

        clear_seo_cache()
        invalidate_sitemap_cache()
        return {"deleted": True, "model": spec.name, "id": record_id}

    async def set_role_permissions(
        self,
        db: AsyncSession,
        role_name: str,
        permissions: Iterable[str],
    ) -> dict[str, Any]:
        """
        Устанавливает полный набор разрешений для указанной роли (включая `guest` и `user`).
        После сохранения инициирует корректный дисконнект всех пользователей с этой ролью,
        чтобы они переподключились с новыми правами.
        """
        role = (
            await db.execute(select(Role).where(Role.name == role_name))
        ).scalar_one_or_none()
        if role is None:
            raise RpcError(f"Роль '{role_name}' не найдена", code=-32004)

        clean_perms = sorted({str(p).strip() for p in permissions if str(p).strip()})
        role.role_permissions.clear()
        await db.flush()
        role.role_permissions = [RolePermission(permission=p) for p in clean_perms]
        await db.commit()
        new_perm_set = frozenset(clean_perms)
        if role.name == GUEST_ROLE and self._on_guest_permissions_updated is not None:
            self._on_guest_permissions_updated(new_perm_set)

        clear_seo_cache()
        invalidate_sitemap_cache()

        if self._on_disconnect_user is not None:
            stmt = select(User.id).join(User.roles).where(Role.id == role.id)
            affected_user_ids = (await db.execute(stmt)).scalars().all()
            for uid in affected_user_ids:
                await self._on_disconnect_user(uid)

        return {
            "role": role.name,
            "is_system": role.is_system,
            "permissions": clean_perms,
        }

    async def set_user_roles(
        self,
        db: AsyncSession,
        user_id: int,
        role_names: Iterable[str],
    ) -> dict[str, Any]:
        """
        Назначает пользователю указанный список ролей (включая `admin` или `adm_*`)
        и выполняет корректный дисконнект его активных сессий для обновления прав.
        """
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise RpcError(f"Пользователь id={user_id} не найден", code=-32004)

        requested_names = {str(r).strip() for r in role_names if str(r).strip()}
        if requested_names:
            roles = list(
                (await db.execute(select(Role).where(Role.name.in_(requested_names)))).scalars().all()
            )
            found_names = {r.name for r in roles}
            missing = requested_names - found_names
            if missing:
                raise InvalidParamsError(f"Неизвестные роли: {', '.join(sorted(missing))}")
        else:
            roles = []

        user.roles = roles
        await db.commit()

        if self._on_disconnect_user is not None:
            await self._on_disconnect_user(user.id)

        return {
            "user_id": user.id,
            "username": user.username,
            "roles": sorted(r.name for r in user.roles),
        }
