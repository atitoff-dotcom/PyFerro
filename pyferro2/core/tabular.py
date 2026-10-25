"""
Табличное сжатие данных (Tabular Data Compression, RFC 0002).

Упаковывает списки однотипных записей в компактную структуру:
`{"$tabular": True, "fields": [...], "rows": [[...], ...]}`
Устраняет многократное повторение ключей JSON, снижая объем трафика на 50–70%
и разгружая сборщик мусора Python и парсер JSON на клиенте.
"""

from collections.abc import Sequence
from typing import Any


def pack_tabular(
    items: Sequence[dict[str, Any] | tuple[Any, ...] | list[Any]],
    fields: Sequence[str] | None = None,
) -> dict[str, Any] | Any:
    """
    Упаковывает список словарей или кортежей в табличный пакет `{"$tabular": True, "fields": [...], "rows": [...]}`.
    """
    if not items:
        return {
            "$tabular": True,
            "fields": list(fields) if fields is not None else [],
            "rows": [],
        }

    first = items[0]
    if isinstance(first, dict):
        field_list = list(fields) if fields is not None else list(first.keys())
        rows = [[item.get(f) for f in field_list] for item in items]  # type: ignore[union-attr]
        return {
            "$tabular": True,
            "fields": field_list,
            "rows": rows,
        }

    if isinstance(first, (tuple, list)):
        if fields is None:
            raise ValueError("Параметр 'fields' обязателен при упаковке кортежей или списков")
        field_list = list(fields)
        rows = [list(r) if isinstance(r, (tuple, list)) else [r] for r in items]
        return {
            "$tabular": True,
            "fields": field_list,
            "rows": rows,
        }

    return items


def unpack_tabular(data: Any) -> Any:
    """
    Рекурсивно распаковывает пакеты `{"$tabular": True, "fields": [...], "rows": [...]}`
    обратно в стандартные списки словарей.
    """
    if not data or not isinstance(data, (dict, list)):
        return data

    if isinstance(data, dict):
        if data.get("$tabular") is True and "fields" in data and "rows" in data:
            fields = data["fields"]
            rows = data["rows"]
            items = [dict(zip(fields, row)) for row in rows]
            extra_keys = [k for k in data.keys() if k not in ("$tabular", "fields", "rows")]
            if not extra_keys:
                return items
            out = {k: unpack_tabular(data[k]) for k in extra_keys}
            out["items"] = items
            return out
        return {k: unpack_tabular(v) for k, v in data.items()}

    return [unpack_tabular(item) for item in data]


def is_tabular(data: Any) -> bool:
    """Возвращает True, если объект является табличным пакетом `$tabular`."""
    return (
        isinstance(data, dict)
        and data.get("$tabular") is True
        and "fields" in data
        and "rows" in data
    )


def apply_tabular_result(result: Any, fields: Sequence[str] | None = None) -> Any:
    """
    Автоматически упаковывает результат RPC-метода (если включен `@rpc_method(tabular=True)`):
    - Если возвращен `list[dict]` -> упаковывает сам список.
    - Если возвращен `dict` с ключом `"items"` (или `"rows"`, `"records"`, `"data"`) -> упаковывает вложенный список.
    """
    if isinstance(result, list):
        return pack_tabular(result, fields=fields)
    if isinstance(result, dict) and not is_tabular(result):
        for key in ("items", "records", "data", "rows"):
            val = result.get(key)
            if isinstance(val, list):
                out = dict(result)
                out[key] = pack_tabular(val, fields=fields)
                return out
    return result
