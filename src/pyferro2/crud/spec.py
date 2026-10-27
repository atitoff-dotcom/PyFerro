"""
Описание одной видимой колонки модели для UI и сериализации (`ModelSpec`).

Интроспекция колонок (`sqlalchemy.inspect`) вызывается **ровно 1 раз при старте**
в момент `crud.register(Model)`.
Каждая модель получает единые точечные константы методов/разрешений:
`Model.create`, `Model.read`, `Model.update`, `Model.delete` (и `*_own`).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect as sa_inspect

from pyferro2.db.base import Base, RowSecureModel


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Описание одной видимой колонки модели для UI и сериализации."""

    name: str
    type_name: str
    primary_key: bool
    nullable: bool
    readonly: bool
    searchable: bool
    foreign_key_table: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "type": self.type_name,
            "primary_key": self.primary_key,
            "nullable": self.nullable,
            "readonly": self.readonly,
            "searchable": self.searchable,
        }
        if self.foreign_key_table is not None:
            out["foreign_key_table"] = self.foreign_key_table
        return out


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """
    Предкомпилированная спецификация CRUD-модели.
    Хранит готовые списки полей и предвычисленные константы разрешений (`Model.action` / `Model.action_own`).
    """

    name: str
    title: str
    table_name: str
    model_cls: type[Base]
    has_creator_id: bool

    fields: tuple[FieldSpec, ...]
    readable_fields: tuple[str, ...]
    writable_fields: frozenset[str]
    readonly_fields: frozenset[str]
    hidden_fields: frozenset[str]
    searchable_fields: tuple[str, ...]

    # Предвычисленные строки разрешений (единый формат Плашка.метод для поиска в SessionData.permissions за ~15 нс)
    perm_create: str
    perm_create_own: str
    perm_read: str
    perm_read_own: str
    perm_update: str
    perm_update_own: str
    perm_delete: str
    perm_delete_own: str
    all_permissions: tuple[str, ...]

    def to_schema_dict(self) -> dict[str, Any]:
        """Возвращает декларативную схему модели для фронтенда админ-панели."""
        return {
            "name": self.name,
            "title": self.title,
            "table_name": self.table_name,
            "has_creator_id": self.has_creator_id,
            "fields": [f.to_dict() for f in self.fields],
            "searchable": list(self.searchable_fields),
            "permissions": list(self.all_permissions),
        }


def _map_sa_type(col_type: Any) -> str:
    type_cls_name = type(col_type).__name__.lower()
    if "int" in type_cls_name:
        return "integer"
    if "bool" in type_cls_name:
        return "boolean"
    if "date" in type_cls_name or "time" in type_cls_name:
        return "datetime"
    if "float" in type_cls_name or "numeric" in type_cls_name or "decimal" in type_cls_name:
        return "float"
    return "string"


def compile_model_spec(
    model_cls: type[Base],
    *,
    name: str | None = None,
    title: str | None = None,
    searchable: Iterable[str] | None = None,
    readonly: Iterable[str] | None = None,
    hidden: Iterable[str] | None = None,
) -> ModelSpec:
    """
    Читает настройки из вложенного `class Crud:` модели (или переданных аргументов)
    и один раз строит неизменяемый `ModelSpec`.
    """
    if not isinstance(model_cls, type) or not issubclass(model_cls, Base):
        raise TypeError(f"Модель {model_cls!r} должна наследоваться от pyferro2.db.Base")

    crud_meta = getattr(model_cls, "Crud", None)
    model_name = name or getattr(crud_meta, "name", None) or model_cls.__name__
    model_title = title or getattr(crud_meta, "title", None) or model_name
    table_name = getattr(model_cls, "__tablename__", model_name.lower())

    raw_searchable = (
        searchable if searchable is not None else getattr(crud_meta, "searchable", ())
    )
    raw_readonly = (
        readonly if readonly is not None else getattr(crud_meta, "readonly", ())
    )
    raw_hidden = (
        hidden if hidden is not None else getattr(crud_meta, "hidden", ())
    )

    hidden_set = frozenset(str(x) for x in raw_hidden)
    # Первичный ключ id и служебные метки RowSecureModel всегда readonly по умолчанию
    default_readonly = {"id", "creator_id", "created_at", "updated_at"}
    readonly_set = frozenset(str(x) for x in raw_readonly) | default_readonly
    searchable_set = frozenset(str(x) for x in raw_searchable)

    mapper = sa_inspect(model_cls)
    field_specs: list[FieldSpec] = []
    readable_names: list[str] = []
    writable_names: set[str] = set()
    searchable_names: list[str] = []

    for col in mapper.columns:
        col_name = col.key
        if col_name in hidden_set:
            continue

        is_ro = col_name in readonly_set or col.primary_key
        is_search = col_name in searchable_set
        fk_table: str | None = None
        if col.foreign_keys:
            first_fk = next(iter(col.foreign_keys))
            fk_table = first_fk.column.table.name

        f_spec = FieldSpec(
            name=col_name,
            type_name=_map_sa_type(col.type),
            primary_key=bool(col.primary_key),
            nullable=bool(col.nullable),
            readonly=is_ro,
            searchable=is_search,
            foreign_key_table=fk_table,
        )
        field_specs.append(f_spec)
        readable_names.append(col_name)
        if not is_ro:
            writable_names.add(col_name)
        if is_search:
            searchable_names.append(col_name)

    has_creator = issubclass(model_cls, RowSecureModel)

    p_create = f"{model_name}.create"
    p_create_own = f"{model_name}.create_own"
    p_read = f"{model_name}.read"
    p_read_own = f"{model_name}.read_own"
    p_update = f"{model_name}.update"
    p_update_own = f"{model_name}.update_own"
    p_delete = f"{model_name}.delete"
    p_delete_own = f"{model_name}.delete_own"

    all_perms: tuple[str, ...] = (p_create, p_read, p_update, p_delete)

    return ModelSpec(
        name=model_name,
        title=model_title,
        table_name=table_name,
        model_cls=model_cls,
        has_creator_id=has_creator,
        fields=tuple(field_specs),
        readable_fields=tuple(readable_names),
        writable_fields=frozenset(writable_names),
        readonly_fields=readonly_set,
        hidden_fields=hidden_set,
        searchable_fields=tuple(searchable_names),
        perm_create=p_create,
        perm_create_own=p_create_own,
        perm_read=p_read,
        perm_read_own=p_read_own,
        perm_update=p_update,
        perm_update_own=p_update_own,
        perm_delete=p_delete,
        perm_delete_own=p_delete_own,
        all_permissions=all_perms,
    )
