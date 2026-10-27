"""
Высокопроизводительная пагинация для SQLAlchemy 2.0 с автоматической упаковкой в Tabular Data ($tabular).

Поддерживает:
- Вызов от модели или `Select`: `paginate_tabular(db, Book, **params)` или `paginate_tabular(db, select(Book).where(...), **params)`.
- Два режима:
    1. Offset-пагинация (`page=1, limit=20`) с оптимизированным `count(*)` (очистка `order_by`).
    2. Keyset / Cursor-пагинация (`cursor="...", limit=20`) с выборкой $O(1)$ по индексу без подсчета `count`.
- Авто-трансляцию фильтров (`filters={"genre": "fiction"}`) и поиска (`search="текст"`).
- Zero-Hydration: извлечение чистых кортежей или атрибутов с конвертацией `datetime`, `UUID`, `Enum`, `Decimal`.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import json
import math
from typing import Any, TypeVar
import uuid

from sqlalchemy import Select, String, Text, Unicode, UnicodeText, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.db.base import Base

T = TypeVar("T", bound=Base)


def _serialize_val(val: Any) -> Any:
    """Безопасно преобразует значение ячейки базы данных в сериализуемый JSON-вид."""
    if val is None or isinstance(val, (int, float, str, bool)):
        return val
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, (list, tuple)):
        return [_serialize_val(v) for v in val]
    if isinstance(val, dict):
        return {k: _serialize_val(v) for k, v in val.items()}
    return str(val)


def encode_cursor(val: Any, col: str = "id", direction: str = "desc") -> str:
    """Кодирует значение граничной записи в URL-safe base64 токен курсора."""
    payload = {
        "v": _serialize_val(val),
        "c": col,
        "d": direction.lower(),
    }
    dumped = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(dumped.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Декодирует строку курсора обратно в словарь параметров."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "v" not in data:
            raise ValueError("Некорректная структура курсора")
        return data
    except Exception as e:
        raise ValueError(f"Невалидный токен курсора: {cursor}") from e


def _find_model_class(target: type[Base] | Select) -> type[Base] | None:
    """Определяет модель DeclarativeBase из аргумента target (класса или Select-запроса)."""
    if isinstance(target, type) and issubclass(target, Base):
        return target
    if isinstance(target, Select):
        for desc in target.column_descriptions:
            entity = desc.get("entity")
            if isinstance(entity, type) and issubclass(entity, Base):
                return entity
    return None


async def paginate_tabular(
    db: AsyncSession,
    target: type[Base] | Select,
    *,
    page: int | None = 1,
    limit: int = 20,
    cursor: str | None = None,
    cursor_column: str = "id",
    search: str | None = None,
    search_fields: Sequence[str] | None = None,
    filters: dict[str, Any] | None = None,
    sort_by: str | None = None,
    order: str = "desc",
    fields: Sequence[str] | None = None,
    count: bool = True,
    max_limit: int = 500,
    **extra_params: Any,
) -> dict[str, Any]:
    """
    Высокопроизводительная пагинация запроса SQLAlchemy с отдачей сжатого пакета `$tabular`.

    Параметры:
    - `db`: сессия SQLAlchemy (`AsyncSession`).
    - `target`: модель `Book` или сформированный `select(Book).where(...)`.
    - `page`: номер страницы (1-indexed). Приоритет отдается `cursor`, если он передан.
    - `limit`: максимальное количество строк (по умолчанию 20, ограничено `max_limit`).
    - `cursor`: строковый токен для курсорной пагинации ($O(1)$ по индексу).
    - `cursor_column`: колонка для курсора (по умолчанию "id").
    - `search`: поисковая строка (автоматически транслируется в `ILIKE` по строковым полям).
    - `search_fields`: явный список полей для поиска (если `None` — используются строковые поля модели).
    - `filters`: словарь точных совпадений `{"status": "published", "category_id": 5}`.
    - `sort_by`: имя колонки для сортировки.
    - `order`: направление сортировки (`"asc"` или `"desc"`).
    - `fields`: список желаемых колонок для вывода (если `None` — берутся все колонки модели).
    - `count`: вычислять ли точный `total` в режиме `page` (по умолчанию `True`).
    - `max_limit`: защитный максимум строк на страницу (по умолчанию 500).
    """
    safe_limit = max(1, min(int(limit or 20), max_limit))
    model_cls = _find_model_class(target)

    # 1. Приведение к Select
    if isinstance(target, Select):
        stmt = target
    elif model_cls is not None:
        stmt = select(model_cls)
    else:
        raise ValueError("Параметр 'target' должен быть моделью Base или объектом Select")

    # 2. Авто-фильтрация по точному совпадению
    if filters and isinstance(filters, dict) and model_cls is not None:
        for fname, fval in filters.items():
            if hasattr(model_cls, fname):
                col = getattr(model_cls, fname)
                if hasattr(col, "__clause_element__"):
                    if isinstance(fval, (list, tuple, set)):
                        stmt = stmt.where(col.in_(list(fval)))
                    elif fval is not None:
                        stmt = stmt.where(col == fval)

    # 3. Авто-поиск по подстроке (ILIKE)
    if search and str(search).strip():
        search_term = f"%{str(search).strip()}%"
        cols_to_search = []
        if search_fields:
            cols_to_search = [
                getattr(model_cls, sf)
                for sf in search_fields
                if hasattr(model_cls, sf) and hasattr(getattr(model_cls, sf), "__clause_element__")
            ]
        elif model_cls is not None:
            mapper = inspect(model_cls)
            cols_to_search = [
                col
                for col in mapper.columns
                if isinstance(col.type, (String, Text, Unicode, UnicodeText))
            ]

        if cols_to_search:
            stmt = stmt.where(or_(*[c.ilike(search_term) for c in cols_to_search]))

    # 4. Сортировка
    current_direction = order.lower() if order else "desc"
    active_sort_col_name = cursor_column
    if sort_by and model_cls is not None and hasattr(model_cls, sort_by):
        sort_col = getattr(model_cls, sort_by)
        if hasattr(sort_col, "__clause_element__"):
            active_sort_col_name = sort_by
            stmt = stmt.order_by(sort_col.desc() if current_direction == "desc" else sort_col.asc())
    elif not stmt._order_by_clauses and model_cls is not None and hasattr(model_cls, "id"):
        stmt = stmt.order_by(model_cls.id.desc() if current_direction == "desc" else model_cls.id.asc())

    # 5. Выполнение пагинации (Cursor vs Offset)
    total: int | None = None
    pages: int | None = None
    has_prev = False
    has_next = False
    next_cursor: str | None = None
    prev_cursor: str | None = None
    safe_page: int | None = None

    if cursor is not None:
        # ─── РЕЖИМ КУРСОРА (Keyset) ───
        decoded = decode_cursor(cursor)
        c_val = decoded.get("v")
        c_col = decoded.get("c", cursor_column)
        c_dir = decoded.get("d", current_direction)

        if model_cls is not None and hasattr(model_cls, c_col):
            col_target = getattr(model_cls, c_col)
            if hasattr(col_target, "__clause_element__"):
                if c_dir == "desc":
                    stmt = stmt.where(col_target < c_val)
                else:
                    stmt = stmt.where(col_target > c_val)

        # Берем limit + 1 для определения has_next без вызова COUNT
        exec_stmt = stmt.limit(safe_limit + 1)
        res = await db.execute(exec_stmt)
        raw_items = res.scalars().all() if _is_entity_select(stmt) else res.all()

        has_prev = True
        if len(raw_items) > safe_limit:
            has_next = True
            raw_items = raw_items[:safe_limit]
        else:
            has_next = False

        if raw_items and has_next:
            last_item = raw_items[-1]
            last_val = _extract_item_value(last_item, c_col)
            if last_val is not None:
                next_cursor = encode_cursor(last_val, col=c_col, direction=c_dir)

    else:
        # ─── РЕЖИМ OFFSET ───
        safe_page = max(1, int(page or 1))
        offset = (safe_page - 1) * safe_limit

        if count:
            # Очищаем order_by в подзапросе подсчета для максимальной скорости СУБД
            count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
            total = int((await db.execute(count_stmt)).scalar() or 0)
            pages = max(1, math.ceil(total / safe_limit)) if total > 0 else 1
            has_prev = safe_page > 1
            has_next = (offset + safe_limit) < total

            exec_stmt = stmt.offset(offset).limit(safe_limit)
            res = await db.execute(exec_stmt)
            raw_items = res.scalars().all() if _is_entity_select(stmt) else res.all()
        else:
            has_prev = safe_page > 1
            exec_stmt = stmt.offset(offset).limit(safe_limit + 1)
            res = await db.execute(exec_stmt)
            raw_items = res.scalars().all() if _is_entity_select(stmt) else res.all()
            if len(raw_items) > safe_limit:
                has_next = True
                raw_items = raw_items[:safe_limit]
            else:
                has_next = False

        if raw_items and has_next and model_cls is not None and hasattr(model_cls, active_sort_col_name):
            last_item = raw_items[-1]
            last_val = _extract_item_value(last_item, active_sort_col_name)
            if last_val is not None:
                next_cursor = encode_cursor(last_val, col=active_sort_col_name, direction=current_direction)

    # 6. Извлечение колонок и формирование tabular строк
    out_fields, tabular_rows = _format_tabular_rows(raw_items, stmt, model_cls, fields)

    return {
        "$tabular": True,
        "fields": out_fields,
        "rows": tabular_rows,
        "limit": safe_limit,
        "page": safe_page,
        "total": total,
        "pages": pages,
        "has_next": has_next,
        "has_prev": has_prev,
        "next_cursor": next_cursor,
        "prev_cursor": prev_cursor,
    }


def _is_entity_select(stmt: Select) -> bool:
    """Проверяет, выбирает ли Select полноценные ORM-сущности (`scalars`) или плоские колонки."""
    if not stmt.column_descriptions:
        return False
    first = stmt.column_descriptions[0]
    entity = first.get("entity")
    expr = first.get("expr")
    return entity is not None and expr is entity


def _extract_item_value(item: Any, col_name: str) -> Any:
    """Извлекает значение поля из ORM-инстанса или Row-кортежа."""
    if hasattr(item, col_name):
        return getattr(item, col_name)
    if hasattr(item, "_mapping") and col_name in item._mapping:
        return item._mapping[col_name]
    return None


def _format_tabular_rows(
    items: Sequence[Any],
    stmt: Select,
    model_cls: type[Base] | None,
    desired_fields: Sequence[str] | None,
) -> tuple[list[str], list[list[Any]]]:
    """Формирует итоговый список полей и сериализованные массивы значений."""
    if not items:
        if desired_fields:
            return list(desired_fields), []
        if model_cls is not None:
            mapper = inspect(model_cls)
            return [col.key for col in mapper.columns], []
        if stmt.column_descriptions:
            return [desc["name"] for desc in stmt.column_descriptions], []
        return [], []

    first = items[0]

    # Вариант 1: Строки Row (когда делался select(Book.id, Book.title))
    if hasattr(first, "_mapping"):
        row_fields = list(first._mapping.keys())
        out_fields = list(desired_fields) if desired_fields else row_fields
        tabular_rows = [
            [_serialize_val(row._mapping.get(f)) for f in out_fields]
            for row in items
        ]
        return out_fields, tabular_rows

    # Вариант 2: ORM-инстансы (когда делался select(Book) или передан класс Book)
    if model_cls is not None:
        mapper = inspect(model_cls)
        all_cols = [col.key for col in mapper.columns]
        out_fields = list(desired_fields) if desired_fields else all_cols
    elif desired_fields:
        out_fields = list(desired_fields)
    else:
        out_fields = [k for k in dir(first) if not k.startswith("_")]

    tabular_rows = [
        [_serialize_val(getattr(item, f, None)) for f in out_fields]
        for item in items
    ]
    return out_fields, tabular_rows
