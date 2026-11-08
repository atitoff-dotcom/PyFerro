"""
Песочница шаблонизации Jinja2 для SEO-страниц и Dynamic Rendering в PyFerro 2.0 (`pyferro2/seo/jinja_engine.py`).

Обеспечивает:
- Безопасную асинхронную песочницу `SandboxedEnvironment(enable_async=True, autoescape=True)`
- Доступ к полям текущей записи (`{{ record.title }}`, `{{ record.slug }}`) и связям (`{{ parent.name }}`)
- Циклы перебора по разрешенным для роли `guest` (`Model.read`) таблицам БД (`{% for x in Book %}`)
- Поддержку `.where(...)`, `.order_by("-id")`, срезов `[:10]` и `.count()`
- Строгую изоляцию системных таблиц (`User`, `Role`, `RolePermission`, `StoredFile`, `SeoConfigRecord`)
  и фильтрацию секретных колонок (`password`, `hash`, `secret`, `token`, `key`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jinja2.exceptions import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import asc, desc, func, select

if TYPE_CHECKING:
    from pyferro2.crud.engine import CrudEngine
    from pyferro2.crud.spec import ModelSpec
    from pyferro2.db.engine import Database

SYSTEM_SECURITY_MODELS: frozenset[str] = frozenset({
    "User",
    "Role",
    "RolePermission",
    "StoredFile",
    "SeoConfigRecord",
})

SYSTEM_SECURITY_PREFIXES: tuple[str, ...] = (
    "pf_auth_",
    "pf_file_",
    "pf_seo_",
    "pf_system_",
)

SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "password",
    "_hash",
    "secret",
    "token",
    "private_key",
    "api_key",
)


def is_sensitive_field(field_name: str) -> bool:
    """Проверяет, является ли имя поля потенциально секретным (пароль, хэш, токен)."""
    low = field_name.lower()
    return any(kw in low for kw in SENSITIVE_KEYWORDS)


def is_model_allowed_for_seo(
    spec: ModelSpec | None,
    guest_permissions: frozenset[str] | None = None,
) -> bool:
    """
    Проверяет, разрешена ли модель для чтения через SEO-движок и шаблоны Jinja2.
    Правило PyFerro 2.0:
    1. Системные таблицы (`User`, `Role`, `StoredFile`, `pf_auth_*`) всегда строго запрещены.
    2. Прикладная таблица разрешена, если у роли `guest` включено право `Model.read`
       (либо если `guest_permissions` явно не передан в тестовом/превью вызове).
    """
    if spec is None:
        return False
    if spec.name in SYSTEM_SECURITY_MODELS:
        return False
    if spec.table_name.startswith(SYSTEM_SECURITY_PREFIXES):
        return False
    if guest_permissions is not None:
        return spec.perm_read in guest_permissions
    return True


def serialize_safe_record(record: Any, spec: ModelSpec | None = None) -> dict[str, Any]:
    """
    Безопасная сериализация записи в словарь для Jinja2 контекста.
    Гарантированно исключает `hidden_fields` из `ModelSpec` и любые секретные поля.
    """
    if record is None:
        return {}

    result: dict[str, Any] = {}

    if spec is not None and not isinstance(record, dict):
        for fname in spec.readable_fields:
            if fname in spec.hidden_fields or is_sensitive_field(fname):
                continue
            val = getattr(record, fname, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            result[fname] = val
    elif isinstance(record, dict):
        hidden = spec.hidden_fields if spec is not None else frozenset()
        for k, v in record.items():
            if k not in hidden and not is_sensitive_field(str(k)):
                result[str(k)] = v.isoformat() if hasattr(v, "isoformat") else v
    elif hasattr(record, "__table__"):
        for col in record.__table__.columns:
            cname = col.name
            if is_sensitive_field(cname):
                continue
            val = getattr(record, cname, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            result[cname] = val

    return result


class RecordWrapper:
    """Безопасная обертка над записью БД для удобного доступа к полям через точку и словарь."""

    __slots__ = ("_data", "_relations")

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        relations: dict[str, Any] | None = None,
    ) -> None:
        self._data = serialize_safe_record(data) if data else {}
        self._relations = {
            k: (serialize_safe_record(v) if isinstance(v, dict) else v)
            for k, v in (relations or {}).items()
            if not is_sensitive_field(k)
        }

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or is_sensitive_field(name):
            return None
        if name in self._data:
            return self._data[name]
        if name in self._relations:
            rel = self._relations[name]
            if isinstance(rel, dict):
                return RecordWrapper(rel)
            return rel

        # Умные фолбэки для распространенных полей в шаблонах
        if name == "title":
            return self._data.get("name") or self._data.get("caption") or self._data.get("header")
        if name == "name":
            return self._data.get("title") or self._data.get("caption") or self._data.get("header")
        if name in ("desc", "description"):
            return (
                self._data.get("description")
                or self._data.get("content")
                or self._data.get("summary")
                or self._data.get("text")
            )
        if name in ("slug", "url"):
            return self._data.get("slug") or self._data.get("code") or self._data.get("id")

        return None

    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)

    def __contains__(self, name: str) -> bool:
        if is_sensitive_field(name):
            return False
        return name in self._data or name in self._relations

    def get(self, name: str, default: Any = None) -> Any:
        val = self.__getattr__(name)
        return val if val is not None else default

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"<RecordWrapper {self._data}>"


def resolve_foreign_target_spec(
    crud_engine: CrudEngine,
    field_name: str,
    fk_table: str | None,
) -> ModelSpec | None:
    """Находит целевую `ModelSpec` по имени таблицы внешнего ключа или суффиксу `<name>_id`."""
    if fk_table:
        for spec in crud_engine.models.values():
            if spec.table_name == fk_table:
                return spec
    if field_name.endswith("_id"):
        prefix = field_name[:-3].lower()
        for spec in crud_engine.models.values():
            if spec.name.lower() == prefix or spec.table_name.lower() in (prefix, f"{prefix}s", f"{prefix}es"):
                return spec
    return None


class ModelQueryWrapper:
    """
    Ленивый построитель запросов к модели SQLAlchemy внутри шаблона Jinja2.
    Примеры в шаблоне:
      {% for cat in Category.where(parent_id=None) %}
      {% for book in Book.where(category_id=record.id).order_by("-id")[:20] %}
    """

    __slots__ = (
        "spec",
        "db",
        "crud_engine",
        "guest_permissions",
        "_is_allowed",
        "filters",
        "order_by_fields",
        "limit_val",
        "offset_val",
    )

    def __init__(
        self,
        spec: ModelSpec,
        db: Database,
        crud_engine: CrudEngine,
        guest_permissions: frozenset[str] | None = None,
        filters: dict[str, Any] | None = None,
        order_by_fields: list[str] | None = None,
        limit_val: int | None = 100,
        offset_val: int | None = 0,
    ) -> None:
        self.spec = spec
        self.db = db
        self.crud_engine = crud_engine
        self.guest_permissions = guest_permissions
        self._is_allowed = is_model_allowed_for_seo(spec, guest_permissions)
        self.filters = filters or {}
        self.order_by_fields = order_by_fields or []
        self.limit_val = min(limit_val or 100, 500)
        self.offset_val = offset_val or 0

    def _clone(self, **kwargs: Any) -> ModelQueryWrapper:
        return ModelQueryWrapper(
            spec=self.spec,
            db=self.db,
            crud_engine=self.crud_engine,
            guest_permissions=self.guest_permissions,
            filters=dict(kwargs.get("filters", self.filters)),
            order_by_fields=list(kwargs.get("order_by_fields", self.order_by_fields)),
            limit_val=kwargs.get("limit_val", self.limit_val),
            offset_val=kwargs.get("offset_val", self.offset_val),
        )

    def where(self, **kwargs: Any) -> ModelQueryWrapper:
        """Добавляет условия фильтрации `.where(category_id=record.id)`."""
        new_filters = dict(self.filters)
        for k, v in kwargs.items():
            if not is_sensitive_field(k):
                if isinstance(v, RecordWrapper):
                    v = v.id
                new_filters[k] = v
        return self._clone(filters=new_filters)

    def filter_by(self, **kwargs: Any) -> ModelQueryWrapper:
        return self.where(**kwargs)

    def all(self) -> ModelQueryWrapper:
        return self._clone()

    def order_by(self, *fields: str) -> ModelQueryWrapper:
        """Задает сортировку `.order_by('-id', 'title')`."""
        safe_fields = [f for f in fields if not is_sensitive_field(f.lstrip("-"))]
        return self._clone(order_by_fields=safe_fields)

    def limit(self, n: int) -> ModelQueryWrapper:
        return self._clone(limit_val=min(max(1, int(n)), 500))

    def __getitem__(self, item: Any) -> ModelQueryWrapper:
        """Поддержка срезов `Model[:10]` или `Model[5:15]`."""
        if isinstance(item, slice):
            start = item.start or 0
            stop = item.stop
            if stop is not None:
                lim = max(0, stop - start)
                return self._clone(offset_val=start, limit_val=min(lim, 500))
            return self._clone(offset_val=start)
        raise TypeError("ModelQueryWrapper поддерживает только срезы [:N] или [A:B]")

    @staticmethod
    def _coerce_filter_val(col: Any, v: Any) -> Any:
        if v is None:
            return None
        try:
            if hasattr(col, "type") and hasattr(col.type, "python_type") and col.type.python_type is int:
                return int(v)
        except Exception:
            pass
        return v

    async def count(self) -> int:
        if not self._is_allowed:
            return 0
        model_cls = self.spec.model_cls
        async with self.db.session() as session:
            stmt = select(func.count()).select_from(model_cls)
            for k, v in self.filters.items():
                col = getattr(model_cls, k, None)
                if col is not None:
                    c_val = self._coerce_filter_val(col, v)
                    stmt = stmt.where(col.is_(None) if c_val is None else col == c_val)
            val = (await session.execute(stmt)).scalar() or 0
            return int(val)

    def __aiter__(self):
        """Асинхронный генератор для `SandboxedEnvironment(enable_async=True)`."""
        async def _generator():
            if not self._is_allowed:
                return

            model_cls = self.spec.model_cls
            async with self.db.session() as session:
                stmt = select(model_cls)
                for k, v in self.filters.items():
                    col = getattr(model_cls, k, None)
                    if col is not None:
                        c_val = self._coerce_filter_val(col, v)
                        stmt = stmt.where(col.is_(None) if c_val is None else col == c_val)
                for fld in self.order_by_fields:
                    desc_order = fld.startswith("-")
                    clean_fld = fld[1:] if desc_order else fld
                    col = getattr(model_cls, clean_fld, None)
                    if col is not None:
                        stmt = stmt.order_by(desc(col) if desc_order else asc(col))

                if self.offset_val:
                    stmt = stmt.offset(self.offset_val)
                if self.limit_val:
                    stmt = stmt.limit(self.limit_val)

                rows = (await session.execute(stmt)).scalars().all()
                if not rows:
                    return

                # Пакетная подгрузка родительских связей по внешним ключам
                fk_fields = [
                    f for f in self.spec.fields
                    if f.foreign_key_table or f.name.endswith("_id")
                ]
                fk_targets: dict[str, dict[Any, dict[str, Any]]] = {}

                for f in fk_fields:
                    target_spec = resolve_foreign_target_spec(
                        self.crud_engine, f.name, f.foreign_key_table
                    )
                    if not target_spec or not is_model_allowed_for_seo(target_spec, self.guest_permissions):
                        continue
                    ids = {getattr(r, f.name) for r in rows if getattr(r, f.name, None) is not None}
                    if ids:
                        t_cls = target_spec.model_cls
                        t_rows = (await session.execute(select(t_cls).where(t_cls.id.in_(ids)))).scalars().all()
                        fk_targets[f.name] = {
                            tr.id: serialize_safe_record(tr, target_spec)
                            for tr in t_rows
                        }

                for r in rows:
                    rec_dict = serialize_safe_record(r, self.spec)
                    relations: dict[str, Any] = {}
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


import html as _html
import re as _re
from markupsafe import Markup


def render_markdown_filter(md_text: Any) -> Markup:
    """
    Конвертирует Markdown в чистый семантический HTML5 для поисковых ботов:
    - Заголовки: # -> <h2>, ## -> <h3>, ### -> <h4>
    - Картинки: ![alt](url) -> <figure><img src="url" alt="alt" ... /><figcaption>alt</figcaption></figure>
    - Ссылки: [text](url) -> <a href="url">text</a>
    - Выделение: **bold**, *italic*, `code`
    - Списки: - пункт
    - Таблицы: | col1 | col2 |
    - Цитаты: > цитата
    """
    if not md_text:
        return Markup("")
    raw = str(md_text)

    # 1. Извлекаем блоки кода ```lang\ncode\n```
    code_blocks: list[str] = []

    def _save_code(m: _re.Match[str]) -> str:
        code_body = _html.escape(m.group(2))
        idx = len(code_blocks)
        code_blocks.append(
            f'<pre style="background:#1e293b;color:#f8fafc;padding:14px;border-radius:8px;overflow-x:auto;"><code>{code_body}</code></pre>'
        )
        return f"__CODE_BLOCK_{idx}__"

    text = _re.sub(r"```([a-zA-Z0-9_-]*)\n([\s\S]*?)```", _save_code, raw)

    # 2. Инлайн-элементы (картинки, ссылки, стили)
    def _format_inline(s: str) -> str:
        def _img(m: _re.Match[str]) -> str:
            alt = _html.escape(m.group(1), quote=True)
            src = _html.escape(m.group(2), quote=True)
            caption = (
                f'<figcaption style="font-size:13px;color:#64748b;margin-top:6px;">{alt}</figcaption>'
                if alt
                else ""
            )
            return (
                f'<figure style="margin:18px 0;text-align:center;">'
                f'<img src="{src}" alt="{alt}" loading="lazy" style="max-width:100%;height:auto;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.06);" />'
                f"{caption}</figure>"
            )

        s = _re.sub(r"!\[(.*?)\]\((.*?)\)", _img, s)

        def _link(m: _re.Match[str]) -> str:
            t = _html.escape(m.group(1))
            u = _html.escape(m.group(2), quote=True)
            return f'<a href="{u}" style="color:#0f766e;text-decoration:underline;">{t}</a>'

        s = _re.sub(r"\[(.*?)\]\((.*?)\)", _link, s)
        s = _re.sub(r"\*\*(.*?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", s)
        s = _re.sub(r"__(.*?)__", lambda m: f"<strong>{m.group(1)}</strong>", s)
        s = _re.sub(r"\*(.*?)\*", lambda m: f"<em>{m.group(1)}</em>", s)
        s = _re.sub(r"(?<![a-zA-Z0-9])_(.*?)_(?![a-zA-Z0-9])", lambda m: f"<em>{m.group(1)}</em>", s)
        s = _re.sub(
            r"`(.*?)`",
            lambda m: f'<code style="background:#f1f5f9;color:#0f766e;padding:2px 6px;border-radius:4px;font-size:14px;">{_html.escape(m.group(1))}</code>',
            s,
        )
        return s

    lines = text.splitlines()
    out_parts: list[str] = []
    in_list = False
    in_table = False
    table_rows: list[list[str]] = []
    para_lines: list[str] = []

    def _flush_para() -> None:
        nonlocal para_lines
        if para_lines:
            joined = " ".join(para_lines).strip()
            if joined:
                out_parts.append(
                    f'<p style="margin-bottom:14px;line-height:1.75;">{_format_inline(joined)}</p>'
                )
            para_lines = []

    def _flush_list() -> None:
        nonlocal in_list
        if in_list:
            out_parts.append("</ul>")
            in_list = False

    def _flush_table() -> None:
        nonlocal in_table, table_rows
        if in_table and table_rows:
            html_t = [
                '<table style="width:100%;border-collapse:collapse;margin:18px 0;font-size:14px;">'
            ]
            html_t.append('<thead><tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0;">')
            for cell in table_rows[0]:
                html_t.append(
                    f'<th style="padding:10px 12px;text-align:left;font-weight:600;">{_format_inline(cell)}</th>'
                )
            html_t.append("</tr></thead><tbody>")
            for row in table_rows[1:]:
                html_t.append('<tr style="border-bottom:1px solid #f1f5f9;">')
                for cell in row:
                    html_t.append(f'<td style="padding:8px 12px;">{_format_inline(cell)}</td>')
                html_t.append("</tr>")
            html_t.append("</tbody></table>")
            out_parts.append("".join(html_t))
            table_rows = []
            in_table = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("__CODE_BLOCK_"):
            _flush_para()
            _flush_list()
            _flush_table()
            out_parts.append(stripped)
            continue

        if not stripped:
            _flush_para()
            _flush_list()
            _flush_table()
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            _flush_para()
            _flush_list()
            if _re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            _flush_table()

        if stripped.startswith("#### "):
            _flush_para()
            _flush_list()
            out_parts.append(
                f'<h5 style="margin-top:20px;margin-bottom:8px;font-size:16px;">{_format_inline(stripped[5:])}</h5>'
            )
            continue
        if stripped.startswith("### "):
            _flush_para()
            _flush_list()
            out_parts.append(
                f'<h4 style="margin-top:22px;margin-bottom:10px;font-size:18px;">{_format_inline(stripped[4:])}</h4>'
            )
            continue
        if stripped.startswith("## "):
            _flush_para()
            _flush_list()
            out_parts.append(
                f'<h3 style="margin-top:26px;margin-bottom:12px;font-size:20px;color:#0f766e;">{_format_inline(stripped[3:])}</h3>'
            )
            continue
        if stripped.startswith("# "):
            _flush_para()
            _flush_list()
            out_parts.append(
                f'<h2 style="margin-top:30px;margin-bottom:14px;font-size:24px;border-bottom:1px solid #e2e8f0;padding-bottom:6px;">{_format_inline(stripped[2:])}</h2>'
            )
            continue

        if stripped.startswith("> "):
            _flush_para()
            _flush_list()
            q_txt = _format_inline(stripped[2:])
            out_parts.append(
                f'<blockquote style="border-left:4px solid #0f766e;padding:8px 14px;margin:16px 0;background:#f8fafc;color:#334155;border-radius:0 8px 8px 0;"><p style="margin:0;">{q_txt}</p></blockquote>'
            )
            continue

        if stripped.startswith(("- ", "* ", "+ ")):
            _flush_para()
            if not in_list:
                out_parts.append('<ul style="padding-left:22px;margin-bottom:16px;">')
                in_list = True
            out_parts.append(f'<li style="margin-bottom:6px;">{_format_inline(stripped[2:])}</li>')
            continue
        else:
            _flush_list()

        if stripped in ("---", "***", "___"):
            _flush_para()
            out_parts.append('<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;" />')
            continue

        if stripped.startswith("![") and stripped.endswith(")"):
            _flush_para()
            out_parts.append(_format_inline(stripped))
            continue

        para_lines.append(stripped)
    _flush_para()
    _flush_list()
    _flush_table()

    res = "\n".join(out_parts)
    for idx, c_html in enumerate(code_blocks):
        res = res.replace(f"__CODE_BLOCK_{idx}__", c_html)

    return Markup(res)


def get_jinja_env() -> SandboxedEnvironment:
    """Создает безопасное асинхронное окружение Jinja2."""
    env = SandboxedEnvironment(
        enable_async=True,
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["markdown"] = render_markdown_filter
    env.filters["md"] = render_markdown_filter
    return env

def validate_jinja_template(template_str: str) -> dict[str, Any]:
    """
    Проверяет синтаксис Jinja2 шаблона.
    Возвращает `{"valid": True, "error": None, "line": None}` или описание ошибки.
    """
    if not template_str or not template_str.strip():
        return {"valid": True, "error": None, "line": None}

    env = get_jinja_env()
    try:
        env.parse(template_str)
        return {"valid": True, "error": None, "line": None}
    except TemplateSyntaxError as exc:
        return {
            "valid": False,
            "error": f"Синтаксическая ошибка: {exc.message}",
            "line": exc.lineno,
        }
    except Exception as exc:
        return {
            "valid": False,
            "error": str(exc),
            "line": None,
        }


def build_template_context(
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
    record: dict[str, Any] | None = None,
    relations: dict[str, Any] | None = None,
    site_url: str = "",
    site_name: str = "",
    breadcrumbs: list[tuple[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Формирует глобальный контекст для шаблона Jinja2:
    - Разрешенные для `guest` (`Model.read`) прикладные модели как `ModelQueryWrapper`
    - `record` (текущая запись, очищенная от скрытых/чувствительных полей)
    - `parent`, `root` и именованные связи
    - `site_url`, `site_name`, `breadcrumbs`
    """
    ctx: dict[str, Any] = {
        "site_url": site_url,
        "site_name": site_name,
        "breadcrumbs": breadcrumbs or [],
    }

    if db is not None and crud_engine is not None:
        for key, spec in crud_engine.models.items():
            if (
                spec.name not in SYSTEM_SECURITY_MODELS
                and not spec.table_name.startswith(SYSTEM_SECURITY_PREFIXES)
            ):
                ctx[key] = ModelQueryWrapper(
                    spec=spec,
                    db=db,
                    crud_engine=crud_engine,
                    guest_permissions=guest_permissions,
                )
    safe_record = serialize_safe_record(record) if record else None
    safe_relations = (
        {
            k: (serialize_safe_record(v) if isinstance(v, dict) else v)
            for k, v in relations.items()
            if not is_sensitive_field(k)
        }
        if relations
        else None
    )

    rec_wrapper = RecordWrapper(safe_record, safe_relations) if safe_record else None
    ctx["record"] = rec_wrapper
    if safe_record:
        for k, v in safe_record.items():
            if k not in ctx and not is_sensitive_field(k):
                ctx[k] = v

    if safe_relations:
        for k, v in safe_relations.items():
            if not is_sensitive_field(k):
                ctx[k] = RecordWrapper(v) if isinstance(v, dict) else v

    if extra:
        safe_extra = {k: v for k, v in extra.items() if not is_sensitive_field(k)}
        ctx.update(safe_extra)

    return ctx


async def render_jinja_template(template_str: str, context: dict[str, Any]) -> str:
    """Безопасно рендерит Jinja2 шаблон в асинхронном песочном окружении."""
    env = get_jinja_env()
    tpl = env.from_string(template_str)
    return await tpl.render_async(**context)
