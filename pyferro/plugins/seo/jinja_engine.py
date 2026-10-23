# -*- coding: utf-8 -*-
"""
pyferro.plugins.seo.jinja_engine: Песочница шаблонизации Jinja2 для SEO-страниц и Dynamic Rendering.

Позволяет создавать полноценные семантические HTML веб-страницы для поисковых ботов:
- Поддержка циклов перебора по одной или нескольким таблицам БД ({% for x in Model %})
- Доступ к полям текущей записи ({{ record.title }}, {{ record.slug }})
- Доступ к родительской записи ({{ parent.name }}, {{ parent.slug }})
- Фильтрация (.where(active=True, category_id=parent.id))
- Срезы и лимиты ([:5], [:10])
- Сортировка (.order_by("-id"))
- Безопасная асинхронная песочница SandboxedEnvironment
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from jinja2.sandbox import SandboxedEnvironment
from jinja2.exceptions import TemplateSyntaxError, TemplateError
from sqlalchemy import select, desc, asc, func

from pyferro.core.logger import logger
from pyferro.db import async_session
from pyferro.plugins.crud import ModelRegistry


class RecordWrapper:
    """Безопасная обертка над записью БД для удобного доступа к полям через точку и словарь."""
    def __init__(self, data: Optional[Dict[str, Any]] = None, relations: Optional[Dict[str, Any]] = None):
        self._data = dict(data) if data else {}
        self._relations = dict(relations) if relations else {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return None
        if name in self._data:
            return self._data[name]
        if name in self._relations:
            rel = self._relations[name]
            if isinstance(rel, dict):
                return RecordWrapper(rel)
            return rel

        # Умные синонимы для предотвращения человеческих ошибок (name <-> title, desc, slug)
        if name == "title":
            return self._data.get("name") or self._data.get("caption") or self._data.get("header")
        if name == "name":
            return self._data.get("title") or self._data.get("caption") or self._data.get("header")
        if name in ("desc", "description"):
            return (
                self._data.get("description")
                or self._data.get("first_post_text")
                or self._data.get("content")
                or self._data.get("text")
                or self._data.get("summary")
            )
        if name in ("slug", "url"):
            return self._data.get("slug") or self._data.get("code") or self._data.get("alias")

        return None
    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)

    def __contains__(self, name: str) -> bool:
        return name in self._data or name in self._relations

    def get(self, name: str, default: Any = None) -> Any:
        val = self.__getattr__(name)
        return val if val is not None else default

    def to_dict(self) -> Dict[str, Any]:
        res = dict(self._data)
        for k, v in self._relations.items():
            if isinstance(v, RecordWrapper):
                res[k] = v.to_dict()
            else:
                res[k] = v
        return res

    def __repr__(self) -> str:
        ident = self._data.get("slug") or self._data.get("id") or self._data.get("title") or self._data.get("name")
        return f"<RecordWrapper {ident}>"

    def __str__(self) -> str:
        return str(self._data.get("title") or self._data.get("name") or self._data.get("id") or "")


class ModelQueryWrapper:
    """
    Асинхронный итерируемый построитель запросов для шаблонов Jinja2.
    Поддерживает:
      {% for cat in ForumCategory %}
      {% for topic in ForumTopic.where(category_id=parent.id)[:5] %}
      {% for item in Product.order_by("-price") %}
    """
    def __init__(
        self,
        meta: Any,
        filters: Optional[Dict[str, Any]] = None,
        order_by_fields: Optional[List[str]] = None,
        limit_val: Optional[int] = None,
        offset_val: Optional[int] = None,
    ):
        self.meta = meta
        self.model_cls = meta.model_cls
        self.filters = filters or {}
        self.order_by_fields = order_by_fields or []
        self.limit_val = limit_val
        self.offset_val = offset_val

    def where(self, **kwargs) -> "ModelQueryWrapper":
        new_filters = dict(self.filters)
        new_filters.update(kwargs)
        return ModelQueryWrapper(
            self.meta,
            filters=new_filters,
            order_by_fields=self.order_by_fields,
            limit_val=self.limit_val,
            offset_val=self.offset_val,
        )

    def order_by(self, *fields: str) -> "ModelQueryWrapper":
        new_order = list(self.order_by_fields) + list(fields)
        return ModelQueryWrapper(
            self.meta,
            filters=self.filters,
            order_by_fields=new_order,
            limit_val=self.limit_val,
            offset_val=self.offset_val,
        )

    def limit(self, n: int) -> "ModelQueryWrapper":
        return ModelQueryWrapper(
            self.meta,
            filters=self.filters,
            order_by_fields=self.order_by_fields,
            limit_val=n,
            offset_val=self.offset_val,
        )

    def offset(self, n: int) -> "ModelQueryWrapper":
        return ModelQueryWrapper(
            self.meta,
            filters=self.filters,
            order_by_fields=self.order_by_fields,
            limit_val=self.limit_val,
            offset_val=n,
        )

    def __getitem__(self, item: Any) -> "ModelQueryWrapper":
        if isinstance(item, slice):
            start = item.start or 0
            stop = item.stop
            calc_limit = (stop - start) if stop is not None else None
            calc_offset = (self.offset_val or 0) + start if start > 0 else self.offset_val
            return ModelQueryWrapper(
                self.meta,
                filters=self.filters,
                order_by_fields=self.order_by_fields,
                limit_val=calc_limit,
                offset_val=calc_offset,
            )
        raise TypeError(f"ModelQueryWrapper поддерживает только срезы [:N] или [A:B], получено: {type(item)}")

    async def count(self) -> int:
        async with async_session() as db:
            stmt = select(func.count()).select_from(self.model_cls)
            for k, v in self.filters.items():
                col = getattr(self.model_cls, k, None)
                if col is not None:
                    if v is None:
                        stmt = stmt.where(col.is_(None))
                    else:
                        stmt = stmt.where(col == v)
            val = (await db.execute(stmt)).scalar() or 0
            return int(val)

    def __aiter__(self):
        """Асинхронный генератор для Jinja2 SandboxedEnvironment(enable_async=True)."""
        async def _generator():
            async with async_session() as db:
                stmt = select(self.model_cls)
                for k, v in self.filters.items():
                    col = getattr(self.model_cls, k, None)
                    if col is not None:
                        if v is None:
                            stmt = stmt.where(col.is_(None))
                        else:
                            stmt = stmt.where(col == v)

                for fld in self.order_by_fields:
                    desc_order = fld.startswith("-")
                    clean_fld = fld[1:] if desc_order else fld
                    col = getattr(self.model_cls, clean_fld, None)
                    if col is not None:
                        stmt = stmt.order_by(desc(col) if desc_order else asc(col))

                if self.offset_val:
                    stmt = stmt.offset(self.offset_val)
                if self.limit_val:
                    stmt = stmt.limit(self.limit_val)

                rows = (await db.execute(stmt)).scalars().all()
                if not rows:
                    return

                # Пакетная подгрузка родительских связей для быстродействия
                fk_fields = [f for f in self.meta.get_column_fields() if f.foreign_key or f.name.endswith("_id")]
                fk_targets: Dict[str, Dict[Any, Dict[str, Any]]] = {}

                for f in fk_fields:
                    fk_dict = f.foreign_key if isinstance(f.foreign_key, dict) else {}
                    target_key = f.target_model or fk_dict.get("target_table") or fk_dict.get("target_model")
                    target_meta = ModelRegistry.get(target_key)
                    if not target_meta:
                        continue
                    ids = {getattr(r, f.name) for r in rows if getattr(r, f.name, None) is not None}
                    if ids:
                        t_cls = target_meta.model_cls
                        t_rows = (await db.execute(select(t_cls).where(t_cls.id.in_(ids)))).scalars().all()
                        fk_targets[f.name] = {
                            tr.id: (tr.to_dict() if hasattr(tr, "to_dict") else {c.name: getattr(tr, c.name, None) for c in t_cls.__table__.columns})
                            for tr in t_rows
                        }

                for r in rows:
                    rec_dict = r.to_dict() if hasattr(r, "to_dict") else {c.name: getattr(r, c.name, None) for c in self.model_cls.__table__.columns}
                    relations = {}
                    for f in fk_fields:
                        val = getattr(r, f.name, None)
                        if val is not None and f.name in fk_targets and val in fk_targets[f.name]:
                            rel_dict = fk_targets[f.name][val]
                            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                            relations[rel_name] = rel_dict
                            if rel_name in ("parent", "category"):
                                relations["parent"] = rel_dict
                    yield RecordWrapper(rec_dict, relations)

        return _generator()


def get_jinja_env() -> SandboxedEnvironment:
    """Создает безопасное асинхронное окружение Jinja2."""
    env = SandboxedEnvironment(
        enable_async=True,
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def validate_jinja_template(template_str: str) -> Dict[str, Any]:
    """
    Проверяет синтаксис Jinja2 шаблона.
    Возвращает:
      {"valid": True, "error": None, "line": None} или
      {"valid": False, "error": "Описание ошибки", "line": 4}
    """
    if not template_str or not template_str.strip():
        return {"valid": True, "error": None, "line": None}

    env = get_jinja_env()
    try:
        env.parse(template_str)
        return {"valid": True, "error": None, "line": None}
    except TemplateSyntaxError as e:
        return {
            "valid": False,
            "error": f"Синтаксическая ошибка: {e.message}",
            "line": e.lineno,
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "line": None,
        }


def build_template_context(
    record: Optional[Dict[str, Any]] = None,
    relations: Optional[Dict[str, Any]] = None,
    parent_chain: Optional[List[Dict[str, Any]]] = None,
    site_url: str = "",
    site_name: str = "",
    breadcrumbs: Optional[List[Tuple[str, str]]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Формирует полный глобальный контекст для шаблона Jinja2:
    - Все модели проекта как ModelQueryWrapper (ForumCategory, ForumTopic и т.д.)
    - record (текущая запись, если есть)
    - parent (родительская запись)
    - root (корневая запись)
    - site_url, site_name, breadcrumbs
    """
    try:
        import pyferro.plugins.help
    except Exception:
        pass

    ctx: Dict[str, Any] = {
        "site_url": site_url,
        "site_name": site_name,
        "breadcrumbs": breadcrumbs or [],
    }

    # Подключаем все доступные модели
    for key, meta in ModelRegistry.all().items():
        if meta.is_internal:
            continue
        ctx[key] = ModelQueryWrapper(meta)

    # Текущая запись
    rec_wrapper = RecordWrapper(record, relations) if record else None
    ctx["record"] = rec_wrapper
    if record:
        for k, v in record.items():
            if k not in ctx:
                ctx[k] = v

    # Родительские связи
    if relations:
        for k, v in relations.items():
            ctx[k] = RecordWrapper(v) if isinstance(v, dict) else v

    if extra:
        ctx.update(extra)

    return ctx


async def render_jinja_template(template_str: str, context: Dict[str, Any]) -> str:
    """Безопасно рендерит Jinja2 шаблон в асинхронном окружении."""
    env = get_jinja_env()
    tpl = env.from_string(template_str)
    return await tpl.render_async(**context)