"""
Универсальный движок «Живого дерева сайта» (Site Tree Engine) для SEO и Dynamic Rendering в PyFerro 2.0 (`pyferro2/seo/site_tree.py`).

Обеспечивает:
1. Хранение дерева сайта и настроек SEO в таблице `pf_seo_config` (с in-memory кэшированием).
2. Поддержку универсального родительского контекста `{parent.slug}`, `{parent.title}`, `{parent.id}`.
3. Автоматическую генерацию семантических ссылок `<a href="...">` для ботов на каждом уровне.
4. Автоматическую сборку хлебных крошек (Breadcrumbs) снизу вверх по родительским узлам.
5. Автоматическую сборку `sitemap.xml` прямо из обхода дерева.
6. Строгую проверку доступа: модели доступны для рендеринга и выборки только если у роли `guest`
   есть право `Model.read` (и исключены системные таблицы `User`, `Role`, `StoredFile`).
"""

from __future__ import annotations

import copy
import html
import logging
import re
from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.seo.jinja_engine import (
    build_template_context,
    is_model_allowed_for_seo,
    render_jinja_template,
    resolve_foreign_target_spec,
    serialize_safe_record,
)
from pyferro2.seo.models import (
    SeoConfigRecord,
    SeoPageData,
    configure_seo,
    get_seo_config,
)
from pyferro2.seo.page_cache import clear_seo_cache
from pyferro2.seo.renderer import HtmlBuilder

if TYPE_CHECKING:
    from pyferro2.crud.engine import CrudEngine
    from pyferro2.crud.spec import ModelSpec
    from pyferro2.db.engine import Database

logger = logging.getLogger("pyferro2.seo.site_tree")

PARAM_RE = re.compile(r"\{([a-zA-Z0-9_.]+)(?::([a-zA-Z_]+))?\}")

HUMAN_FIELD_LABELS: dict[str, str] = {
    "name": "Название",
    "title": "Заголовок",
    "slug": "Короткий адрес (slug)",
    "description": "Описание",
    "content": "Текст статьи",
    "author": "Автор",
    "author_name": "Автор",
    "id": "Номер ID",
    "parent_id": "Родительский раздел",
    "category_id": "Категория",
    "created_at": "Дата создания",
    "price": "Цена",
    "sku": "Артикул",
    "image": "Изображение",
    "cover": "Обложка",
}

STRUCTURE_PRESETS: dict[str, dict[str, Any]] = {
    "clean": {
        "title": "Минимальный сайт (Главная + Страницы)",
        "description": "Простая структура: главная страница и статические разделы (О нас, Контакты)",
        "icon": "📄",
        "tree": {
            "id": "root",
            "title": "Главная страница",
            "url_pattern": "/",
            "node_type": "static",
            "meta_title": "{site_name} — современное веб-приложение",
            "meta_description": "Добро пожаловать на наш сайт. Актуальная информация, услуги и контакты.",
            "og_image": "",
            "schema_type": "WebPage",
            "sitemap_enabled": True,
            "sitemap_priority": 1.0,
            "sitemap_changefreq": "daily",
            "children": [
                {
                    "id": "about",
                    "title": "О компании",
                    "url_pattern": "/about",
                    "node_type": "static",
                    "meta_title": "О нашей компании и миссии",
                    "meta_description": "Узнайте больше о нашей истории, команде и ключевых ценностях.",
                    "og_image": "",
                    "schema_type": "AboutPage",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.6,
                    "sitemap_changefreq": "monthly",
                    "children": [],
                },
                {
                    "id": "contacts",
                    "title": "Контакты",
                    "url_pattern": "/contacts",
                    "node_type": "static",
                    "meta_title": "Контактная информация и схема проезда",
                    "meta_description": "Свяжитесь с нами по телефону, электронной почте или через форму обратной связи.",
                    "og_image": "",
                    "schema_type": "ContactPage",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.6,
                    "sitemap_changefreq": "monthly",
                    "children": [],
                },
            ],
        },
    },
    "catalog": {
        "title": "Каталог / Библиотека (Разделы и карточки)",
        "description": "Готовая структура для каталога книг, товаров или услуг с динамическими карточками из БД",
        "icon": "📚",
        "tree": {
            "id": "root",
            "title": "Главная страница",
            "url_pattern": "/",
            "node_type": "static",
            "meta_title": "{site_name} — официальный каталог",
            "meta_description": "Полный каталог позиций с подробными описаниями и характеристиками.",
            "og_image": "",
            "schema_type": "WebSite",
            "sitemap_enabled": True,
            "sitemap_priority": 1.0,
            "sitemap_changefreq": "daily",
            "children": [
                {
                    "id": "books_list",
                    "title": "Каталог книг",
                    "url_pattern": "/books",
                    "node_type": "collection",
                    "model_key": "Book",
                    "meta_title": "Каталог книг — все издания",
                    "meta_description": "Список всех доступных книг в нашей библиотеке.",
                    "og_image": "",
                    "schema_type": "CollectionPage",
                    "item_link_pattern": "/books/{id}",
                    "item_title_pattern": "{title}",
                    "item_desc_pattern": "{author}",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.9,
                    "sitemap_changefreq": "daily",
                    "children": [
                        {
                            "id": "book_detail",
                            "title": "Карточка книги",
                            "url_pattern": "/books/{id}",
                            "node_type": "detail",
                            "model_key": "Book",
                            "meta_title": "{title} — {author}",
                            "meta_description": "Книга «{title}», автор: {author}.",
                            "og_image": "",
                            "schema_type": "Book",
                            "sitemap_enabled": True,
                            "sitemap_priority": 0.8,
                            "sitemap_changefreq": "weekly",
                            "children": [],
                        }
                    ],
                }
            ],
        },
    },
    "blog": {
        "title": "Блог / Корпоративный портал со статьями",
        "description": "Главная -> Лента статей -> Детальная страница статьи с микроразметкой Article",
        "icon": "📰",
        "tree": {
            "id": "root",
            "title": "Главная страница",
            "url_pattern": "/",
            "node_type": "static",
            "meta_title": "{site_name} — блог и статьи",
            "meta_description": "Экспертные материалы, руководства и свежие публикации.",
            "og_image": "",
            "schema_type": "WebSite",
            "sitemap_enabled": True,
            "sitemap_priority": 1.0,
            "sitemap_changefreq": "daily",
            "children": [
                {
                    "id": "articles_hub",
                    "title": "Статьи и новости",
                    "url_pattern": "/articles",
                    "node_type": "collection",
                    "model_key": "Article",
                    "meta_title": "Все публикации и статьи блога",
                    "meta_description": "Читайте свежие обзоры, аналитику и новости в нашем блоге.",
                    "og_image": "",
                    "schema_type": "Blog",
                    "item_link_pattern": "/articles/{slug}",
                    "item_title_pattern": "{title}",
                    "item_desc_pattern": "{description}",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.9,
                    "sitemap_changefreq": "daily",
                    "children": [
                        {
                            "id": "article_detail",
                            "title": "Страница статьи",
                            "url_pattern": "/articles/{slug}",
                            "node_type": "detail",
                            "model_key": "Article",
                            "meta_title": "{title}",
                            "meta_description": "{description}",
                            "og_image": "",
                            "schema_type": "Article",
                            "sitemap_enabled": True,
                            "sitemap_priority": 0.8,
                            "sitemap_changefreq": "weekly",
                            "children": [],
                        }
                    ],
                }
            ],
        },
    },
}

_CACHED_TREE: dict[str, Any] | None = None


def resolve_template(
    template: str,
    record: dict[str, Any],
    relations: dict[str, dict[str, Any]],
) -> str:
    """
    Подставляет значения колонок и связей по внешним ключам в шаблон строки:
      `{title}` -> `record['title']`
      `{category.name}` -> `relations['category']['name']`
      `{site_name}` -> `get_seo_config().site_name`
    """
    if not template:
        return ""

    cfg = get_seo_config()

    def replace_match(m: re.Match[str]) -> str:
        full_key = m.group(1)
        if full_key == "site_name":
            return cfg.site_name
        if full_key == "site_url":
            return cfg.site_url
        if "." in full_key:
            rel_name, field_name = full_key.split(".", 1)
            rel_obj = relations.get(rel_name)
            if isinstance(rel_obj, dict):
                val = rel_obj.get(field_name)
                return str(val) if val is not None else ""
            return ""
        val = record.get(full_key)
        return str(val) if val is not None else ""

    return PARAM_RE.sub(replace_match, template)


def compile_pattern_to_regex(pattern: str) -> tuple[re.Pattern[str], list[tuple[str, str]]]:
    """Превращает шаблон вида `/forum/{category.slug}/{slug}` в скомпилированный regex и список ключей."""
    keys: list[tuple[str, str]] = []
    regex_pattern = "^"
    last_idx = 0

    for match in PARAM_RE.finditer(pattern):
        start, end = match.span()
        regex_pattern += re.escape(pattern[last_idx:start])
        full_key = match.group(1)
        clean_key = full_key.replace(".", "__")
        keys.append((full_key, clean_key))
        regex_pattern += f"(?P<{clean_key}>[^/]+)"
        last_idx = end

    regex_pattern += re.escape(pattern[last_idx:]) + "$"
    return re.compile(regex_pattern), keys


def get_default_tree() -> dict[str, Any]:
    """Возвращает глубокую копию дефолтного дерева сайта."""
    return copy.deepcopy(STRUCTURE_PRESETS["clean"]["tree"])


def get_cached_site_tree() -> dict[str, Any]:
    """Возвращает текущее дерево сайта из памяти (или дефолтное, если еще не загружено)."""
    global _CACHED_TREE
    if _CACHED_TREE is None:
        _CACHED_TREE = get_default_tree()
    return _CACHED_TREE


def set_cached_site_tree(tree_data: dict[str, Any]) -> None:
    """Обновляет дерево сайта в памяти и очищает кэш отрендеренных страниц."""
    global _CACHED_TREE
    _CACHED_TREE = copy.deepcopy(tree_data)
    clear_seo_cache()


async def load_seo_from_db(session: AsyncSession) -> dict[str, Any]:
    """
    Загружает конфигурацию SEO и структуру дерева сайта из таблицы `pf_seo_config`
    (при отсутствии первой записи — создает ее с дефолтным деревом).
    """
    record = (await session.execute(select(SeoConfigRecord).where(SeoConfigRecord.id == 1))).scalar_one_or_none()
    if record is None:
        default_tree = get_default_tree()
        cfg = get_seo_config()
        record = SeoConfigRecord(
            id=1,
            site_url=cfg.site_url,
            site_name=cfg.site_name,
            default_title=cfg.default_title,
            default_description=cfg.default_description,
            default_og_image=cfg.default_og_image or "",
            default_lang=cfg.default_lang,
            indexnow_key=cfg.indexnow_key or "",
            sitemap_ttl=cfg.sitemap_ttl,
            tree_json=orjson.dumps(default_tree).decode("utf-8"),
        )
        session.add(record)
        await session.commit()
        set_cached_site_tree(default_tree)
        return default_tree

    configure_seo(
        site_url=record.site_url,
        site_name=record.site_name,
        default_title=record.default_title,
        default_description=record.default_description,
        default_og_image=record.default_og_image or None,
        default_lang=record.default_lang,
        indexnow_key=record.indexnow_key or None,
        sitemap_ttl=record.sitemap_ttl,
    )

    try:
        parsed_tree = orjson.loads(record.tree_json) if record.tree_json else {}
        if not isinstance(parsed_tree, dict) or "id" not in parsed_tree:
            parsed_tree = get_default_tree()
    except Exception:
        parsed_tree = get_default_tree()

    set_cached_site_tree(parsed_tree)
    return parsed_tree


async def save_seo_to_db(
    session: AsyncSession,
    *,
    tree: dict[str, Any] | None = None,
    site_url: str | None = None,
    site_name: str | None = None,
    default_title: str | None = None,
    default_description: str | None = None,
    default_og_image: str | None = None,
    indexnow_key: str | None = None,
    sitemap_ttl: int | None = None,
) -> dict[str, Any]:
    """
    Сохраняет обновленное дерево сайта и глобальные настройки SEO в таблицу `pf_seo_config`
    и синхронизирует кэш в оперативной памяти.
    """
    record = (await session.execute(select(SeoConfigRecord).where(SeoConfigRecord.id == 1))).scalar_one_or_none()
    if record is None:
        record = SeoConfigRecord(id=1, tree_json=orjson.dumps(get_cached_site_tree()).decode("utf-8"))
        session.add(record)

    if site_url is not None:
        record.site_url = site_url.rstrip("/")
    if site_name is not None:
        record.site_name = site_name
    if default_title is not None:
        record.default_title = default_title
    if default_description is not None:
        record.default_description = default_description
    if default_og_image is not None:
        record.default_og_image = default_og_image
    if indexnow_key is not None:
        record.indexnow_key = indexnow_key
    if sitemap_ttl is not None:
        record.sitemap_ttl = int(sitemap_ttl)

    if tree is not None:
        record.tree_json = orjson.dumps(tree).decode("utf-8")
        set_cached_site_tree(tree)

    await session.commit()

    configure_seo(
        site_url=record.site_url,
        site_name=record.site_name,
        default_title=record.default_title,
        default_description=record.default_description,
        default_og_image=record.default_og_image or None,
        indexnow_key=record.indexnow_key or None,
        sitemap_ttl=record.sitemap_ttl,
    )

    from pyferro2.seo.sitemap import invalidate_sitemap_cache
    invalidate_sitemap_cache()

    return get_cached_site_tree()


def flatten_tree_nodes(
    node: dict[str, Any],
    parent_chain: list[dict[str, Any]] | None = None,
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Рекурсивно разворачивает дерево в плоский список пар `(узел, цепочка_родителей)`."""
    if parent_chain is None:
        parent_chain = []
    result = [(node, parent_chain)]
    new_chain = parent_chain + [node]
    for child in node.get("children", []):
        result.extend(flatten_tree_nodes(child, new_chain))
    return result


def get_model_schema_for_seo(
    crud_engine: CrudEngine,
    model_key: str,
    guest_permissions: frozenset[str] | None = None,
) -> dict[str, Any]:
    """
    Возвращает схему полей и связей модели для отображения подсказок/чипсов в GUI `/pyferro_admin`.
    """
    spec = crud_engine.models.get(model_key)
    if spec is None:
        return {"key": model_key, "fields": [], "relations": []}

    fields = []
    for f in spec.fields:
        lbl = HUMAN_FIELD_LABELS.get(f.name, f.name)
        fields.append({
            "name": f.name,
            "type": f.type_name,
            "label": lbl,
            "primary_key": f.primary_key,
        })

    relations = []
    for f in spec.fields:
        if f.foreign_key_table or f.name.endswith("_id"):
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            target_spec = resolve_foreign_target_spec(crud_engine, f.name, f.foreign_key_table)
            if target_spec is not None:
                rel_fields = []
                for tf in target_spec.fields:
                    t_lbl = HUMAN_FIELD_LABELS.get(tf.name, tf.name)
                    rel_fields.append({
                        "name": tf.name,
                        "chip": f"{rel_name}.{tf.name}",
                        "label": f"{target_spec.title}: {t_lbl}",
                        "type": tf.type_name,
                    })
                relations.append({
                    "relation_name": rel_name,
                    "fk_field": f.name,
                    "target_model": target_spec.name,
                    "fields": rel_fields,
                })

    return {
        "key": spec.name,
        "verbose_name": spec.title,
        "table_name": spec.table_name,
        "seo_allowed": is_model_allowed_for_seo(spec, guest_permissions),
        "fields": fields,
        "relations": relations,
    }


def _build_breadcrumbs(
    parents: list[dict[str, Any]],
    current_title: str,
    current_path: str,
    record: dict[str, Any] | None = None,
    relations: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Собирает валидные хлебные крошки `(название, URL)` для краулеров и Schema.org."""
    breadcrumbs: list[tuple[str, str]] = []
    record = record or {}
    relations = relations or {}

    dynamic_parents = [p for p in parents if "{" in p.get("url_pattern", "")]

    for p in parents:
        pattern = p.get("url_pattern", "/")
        if "{" not in pattern:
            breadcrumbs.append((p.get("title", ""), pattern))
            continue

        dyn_idx = dynamic_parents.index(p)
        is_immediate_parent = dyn_idx == len(dynamic_parents) - 1
        is_grandparent = dyn_idx == len(dynamic_parents) - 2

        if is_immediate_parent and relations.get("parent"):
            p_rec = relations["parent"]
            p_rel = {"parent": relations.get("root", {})}
        elif is_grandparent and relations.get("root"):
            p_rec = relations["root"]
            p_rel = {}
        else:
            p_rec = relations.get("root") or relations.get("parent") or record
            p_rel = relations

        p_title = (
            p_rec.get("name")
            or p_rec.get("title")
            or resolve_template(p.get("title", ""), p_rec, p_rel)
            or p.get("title", "")
        )
        p_url = resolve_template(pattern, p_rec, p_rel)
        if not p_url or "{" in p_url or "}" in p_url:
            p_url = pattern

        breadcrumbs.append((str(p_title), p_url))

    breadcrumbs.append((current_title, current_path))
    return breadcrumbs


def _coerce_column_value(col: Any, val: Any) -> Any:
    try:
        if hasattr(col, "type") and hasattr(col.type, "python_type") and col.type.python_type is int:
            return int(val)
    except Exception:
        pass
    return val


def _get_allowed_spec(
    crud_engine: CrudEngine | None,
    model_key: str | None,
    guest_permissions: frozenset[str] | None,
) -> ModelSpec | None:
    if not crud_engine or not model_key:
        return None
    spec = crud_engine.models.get(model_key)
    if spec is None or not is_model_allowed_for_seo(spec, guest_permissions):
        return None
    return spec


async def render_static_node(
    node: dict[str, Any],
    parents: list[dict[str, Any]],
    current_path: str,
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
) -> SeoPageData:
    """Рендерит статический узел (например `/` или `/about`) со ссылками на дочерние разделы."""
    raw_title = node.get("meta_title") or node.get("title", "")
    raw_desc = node.get("meta_description", "")
    title = resolve_template(raw_title, {}, {})
    description = resolve_template(raw_desc, {}, {})
    og_image = node.get("og_image") or None
    schema_type = node.get("schema_type") or "WebPage"

    breadcrumbs: list[tuple[str, str]] = []
    for p in parents:
        breadcrumbs.append((p.get("title", ""), p.get("url_pattern", "/")))
    if current_path != "/":
        breadcrumbs.append((node.get("title", ""), current_path))

    template_str = (node.get("template") or "").strip()
    if template_str:
        ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            breadcrumbs=breadcrumbs,
            site_url=current_path,
            site_name=title,
            extra={"title": title, "description": description, "current_path": current_path},
        )
        try:
            body_html = await render_jinja_template(template_str, ctx)
        except Exception as exc:
            logger.error("[SEO Tree] Ошибка рендеринга Jinja2 шаблона для %s: %s", node.get("title"), exc)
            body_html = f'<div class="seo-template-error">Ошибка шаблона: {html.escape(str(exc))}</div>'
    else:
        builder = HtmlBuilder()
        builder.h1(title)
        if description:
            builder.p(description)

        children = node.get("children", [])
        if children:
            child_links = []
            for child in children:
                child_url = child.get("url_pattern", "")
                child_title = child.get("title", "")
                if "{" not in child_url and child_url:
                    child_links.append((child_url, child_title, child.get("meta_description", "")))

            if child_links:
                builder.raw('<nav class="seo-navigation" aria-label="Разделы">')
                builder.h2("Основные разделы:")
                builder.raw("<ul>")
                for u, t, d in child_links:
                    desc_span = f" — <span>{html.escape(d)}</span>" if d else ""
                    builder.raw(
                        f'  <li><a href="{html.escape(u, quote=True)}"><strong>{html.escape(t)}</strong></a>{desc_span}</li>'
                    )
                builder.raw("</ul>")
                builder.raw("</nav>")
        body_html = builder.to_html()

    return SeoPageData(
        title=title,
        description=description,
        canonical_url=current_path,
        og_image=og_image,
        schema_type=schema_type,
        breadcrumbs=breadcrumbs,
        body_html=body_html,
    )


async def render_collection_node(
    node: dict[str, Any],
    parents: list[dict[str, Any]],
    current_path: str,
    extracted_params: dict[str, str],
    keys: list[tuple[str, str]],
    *,
    db: Database,
    crud_engine: CrudEngine,
    guest_permissions: frozenset[str] | None = None,
) -> SeoPageData | None:
    """
    Рендерит хаб/раздел коллекций (например `/books` или `/catalog/{parent.slug}`).
    Извлекает записи из БД и генерирует живой HTML-список `<a href="...">` для краулера.
    """
    model_key = node.get("model_key")
    spec = _get_allowed_spec(crud_engine, model_key, guest_permissions)
    if spec is None:
        if not model_key:
            return await render_static_node(
                node,
                parents,
                current_path,
                db=db,
                crud_engine=crud_engine,
                guest_permissions=guest_permissions,
            )
        return None

    parent_record: dict[str, Any] = {}
    parent_relations: dict[str, dict[str, Any]] = {}

    if keys:
        for full_key, clean_key in keys:
            val = extracted_params.get(clean_key)
            if not val:
                return None
            key_resolved = False
            if "." in full_key:
                rel_name, field_name = full_key.split(".", 1)
                for f in spec.fields:
                    if (
                        rel_name in ("parent", "root", "grandparent")
                        or f.name.startswith(rel_name)
                        or (f.foreign_key_table and rel_name in f.name)
                    ):
                        target_spec = resolve_foreign_target_spec(
                            crud_engine, f.name, f.foreign_key_table
                        )
                        if target_spec and is_model_allowed_for_seo(target_spec, guest_permissions):
                            async with db.session() as session:
                                t_cls = target_spec.model_cls
                                col = getattr(t_cls, field_name, None)
                                if col is not None:
                                    c_val = _coerce_column_value(col, val)
                                    row = (
                                        await session.execute(select(t_cls).where(col == c_val))
                                    ).scalar_one_or_none()
                                    if row:
                                        p_dict = serialize_safe_record(row, target_spec)
                                        parent_relations[rel_name] = p_dict
                                        if rel_name == "parent":
                                            parent_record.update(p_dict)
                                        key_resolved = True
                                        break
                if not key_resolved:
                    return None
            else:
                async with db.session() as session:
                    t_cls = spec.model_cls
                    col = getattr(t_cls, full_key, None)
                    if col is not None:
                        c_val = _coerce_column_value(col, val)
                        row = (
                            await session.execute(select(t_cls).where(col == c_val))
                        ).scalar_one_or_none()
                        if row:
                            p_dict = serialize_safe_record(row, spec)
                            parent_record.update(p_dict)
                            key_resolved = True
                if not key_resolved:
                    return None

    raw_title = node.get("meta_title") or node.get("title", "")
    raw_desc = node.get("meta_description", "")

    if "{{" in raw_title or "{%" in raw_title:
        t_ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            record=parent_record,
            relations=parent_relations,
        )
        resolved_title = await render_jinja_template(raw_title, t_ctx)
    else:
        resolved_title = (
            resolve_template(raw_title, parent_record, parent_relations)
            or parent_record.get("name")
            or parent_record.get("title")
            or raw_title
        )

    if "{{" in raw_desc or "{%" in raw_desc:
        t_ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            record=parent_record,
            relations=parent_relations,
        )
        resolved_desc = await render_jinja_template(raw_desc, t_ctx)
    else:
        resolved_desc = (
            resolve_template(raw_desc, parent_record, parent_relations)
            or parent_record.get("description")
            or raw_desc
        )

    breadcrumbs = _build_breadcrumbs(
        parents=parents,
        current_title=str(resolved_title),
        current_path=current_path,
        record=parent_record,
        relations=parent_relations,
    )

    template_str = (node.get("template") or "").strip()
    if template_str:
        ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            record=parent_record,
            relations=parent_relations,
            breadcrumbs=breadcrumbs,
            extra={
                "title": resolved_title,
                "description": resolved_desc,
                "current_path": current_path,
                "extracted_params": extracted_params,
            },
        )
        try:
            body_html = await render_jinja_template(template_str, ctx)
        except Exception as exc:
            logger.error("[SEO Tree] Ошибка рендеринга Jinja2 шаблона: %s", exc)
            body_html = f'<div class="seo-template-error">Ошибка шаблона: {html.escape(str(exc))}</div>'
    else:
        async with db.session() as session:
            model_cls = spec.model_cls
            stmt = select(model_cls)

            filter_field = node.get("filter_field")
            if filter_field:
                col = getattr(model_cls, filter_field, None)
                if col is not None:
                    parent_id_val = parent_record.get("id") or (parent_relations.get("parent") or {}).get("id")
                    if parent_id_val is not None:
                        stmt = stmt.where(col == parent_id_val)
                    else:
                        stmt = stmt.where(col.is_(None))

            stmt = stmt.limit(100)
            rows = (await session.execute(stmt)).scalars().all()
            items_data: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
            for r in rows:
                rec_dict = serialize_safe_record(r, spec)
                item_rels = dict(parent_relations)
                if parent_record and "parent" not in item_rels:
                    item_rels["parent"] = parent_record
                items_data.append((rec_dict, item_rels))

        builder = HtmlBuilder()
        builder.h1(str(resolved_title))
        if resolved_desc:
            builder.p(str(resolved_desc))

        item_link_pat = node.get("item_link_pattern")
        if not item_link_pat and node.get("children"):
            item_link_pat = node["children"][0].get("url_pattern")

        item_title_pat = node.get("item_title_pattern") or "{title}"
        item_desc_pat = node.get("item_desc_pattern") or "{description}"

        if items_data and item_link_pat:
            builder.raw('<section class="seo-collection-items">')
            builder.h2("Список материалов раздела:")
            builder.raw("<ul>")
            for rec, rels in items_data:
                href = resolve_template(item_link_pat, rec, rels)
                t_text = (
                    resolve_template(item_title_pat, rec, rels)
                    or rec.get("title")
                    or rec.get("name")
                    or f"Запись #{rec.get('id')}"
                )
                d_text = resolve_template(item_desc_pat, rec, rels)
                if d_text and len(d_text) > 160:
                    d_text = d_text[:157] + "..."
                desc_html = f" — <span>{html.escape(str(d_text))}</span>" if d_text else ""
                builder.raw(
                    f'  <li><a href="{html.escape(href, quote=True)}"><strong>{html.escape(str(t_text))}</strong></a>{desc_html}</li>'
                )
            builder.raw("</ul>")
            builder.raw("</section>")
        else:
            builder.raw('<p class="seo-empty">В данном разделе пока нет записей.</p>')
        body_html = builder.to_html()

    return SeoPageData(
        title=str(resolved_title),
        description=str(resolved_desc),
        canonical_url=current_path,
        og_image=node.get("og_image") or None,
        schema_type=node.get("schema_type") or "CollectionPage",
        breadcrumbs=breadcrumbs,
        body_html=body_html,
    )


async def render_detail_node(
    node: dict[str, Any],
    parents: list[dict[str, Any]],
    current_path: str,
    extracted_params: dict[str, str],
    keys: list[tuple[str, str]],
    *,
    db: Database,
    crud_engine: CrudEngine,
    guest_permissions: frozenset[str] | None = None,
) -> SeoPageData | None:
    """
    Рендерит детальную страницу записи (книга, товар, статья, публикация).
    Извлекает запись и родительские связи, формирует разметку Schema.org и крошки.
    """
    model_key = node.get("model_key")
    spec = _get_allowed_spec(crud_engine, model_key, guest_permissions)
    if spec is None:
        return None

    async with db.session() as session:
        model_cls = spec.model_cls
        stmt = select(model_cls)

        main_param_val: Any = None
        main_field = "slug" if hasattr(model_cls, "slug") else "id"

        for full_key, clean_key in keys:
            if "." not in full_key:
                val = extracted_params.get(clean_key)
                if val:
                    main_field = full_key
                    main_param_val = val
                    break

        if main_param_val is None and keys:
            fk, ck = keys[-1]
            main_field = fk.split(".")[-1]
            main_param_val = extracted_params.get(ck)

        if main_param_val is None:
            return None

        col = getattr(model_cls, main_field, None)
        if col is None:
            return None

        main_param_val = _coerce_column_value(col, main_param_val)
        row = (await session.execute(stmt.where(col == main_param_val))).scalar_one_or_none()
        if not row:
            return None

        record = serialize_safe_record(row, spec)

        # Загружаем связанные сущности (Foreign Keys)
        relations: dict[str, dict[str, Any]] = {}
        for f in spec.fields:
            if f.foreign_key_table or f.name.endswith("_id"):
                fk_val = record.get(f.name)
                if fk_val is None:
                    continue
                rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                target_spec = resolve_foreign_target_spec(
                    crud_engine, f.name, f.foreign_key_table
                )
                if target_spec and is_model_allowed_for_seo(target_spec, guest_permissions):
                    t_cls = target_spec.model_cls
                    rel_row = (
                        await session.execute(select(t_cls).where(t_cls.id == fk_val))
                    ).scalar_one_or_none()
                    if rel_row:
                        r_dict = serialize_safe_record(rel_row, target_spec)
                        relations[rel_name] = r_dict
                        relations["parent"] = r_dict

        # Проверяем соответствие родительским параметрам в URL
        for full_key, clean_key in keys:
            if "." in full_key:
                r_prefix, f_name = full_key.split(".", 1)
                expected_val = str(extracted_params.get(clean_key) or "")
                actual_val = str((relations.get(r_prefix) or relations.get("parent") or {}).get(f_name) or "")
                if expected_val and (not actual_val or expected_val != actual_val):
                    return None

    field_names = [f.name for f in spec.fields]
    fallback_title_field = next((f for f in ("title", "name", "caption", "header") if f in field_names), "title")
    fallback_desc_field = next(
        (f for f in ("description", "content", "summary", "text", "author") if f in field_names),
        "description",
    )
    fallback_img_field = next(
        (f for f in ("image", "og_image", "cover", "photo", "avatar") if f in field_names),
        "",
    )

    raw_title = node.get("meta_title") or f"{{{fallback_title_field}}}"
    raw_desc = node.get("meta_description") or f"{{{fallback_desc_field}}}"
    raw_img = node.get("og_image") or (f"{{{fallback_img_field}}}" if fallback_img_field else "")

    if "{{" in raw_title or "{%" in raw_title:
        t_ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            record=record,
            relations=relations,
        )
        resolved_title = await render_jinja_template(raw_title, t_ctx)
    else:
        resolved_title = resolve_template(raw_title, record, relations)

    if "{{" in raw_desc or "{%" in raw_desc:
        t_ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            record=record,
            relations=relations,
        )
        resolved_desc = await render_jinja_template(raw_desc, t_ctx)
    else:
        resolved_desc = resolve_template(raw_desc, record, relations)

    resolved_img = resolve_template(raw_img, record, relations) or None

    breadcrumbs = _build_breadcrumbs(
        parents=parents,
        current_title=resolved_title,
        current_path=current_path,
        record=record,
        relations=relations,
    )

    template_str = (node.get("template") or "").strip()
    if template_str:
        ctx = build_template_context(
            db=db,
            crud_engine=crud_engine,
            guest_permissions=guest_permissions,
            record=record,
            relations=relations,
            breadcrumbs=breadcrumbs,
            extra={
                "title": resolved_title,
                "description": resolved_desc,
                "current_path": current_path,
                "extracted_params": extracted_params,
            },
        )
        try:
            body_html = await render_jinja_template(template_str, ctx)
        except Exception as exc:
            logger.error("[SEO Tree] Ошибка рендеринга Jinja2 шаблона: %s", exc)
            body_html = f'<div class="seo-template-error">Ошибка шаблона: {html.escape(str(exc))}</div>'
    else:
        builder = HtmlBuilder()
        builder.h1(resolved_title)
        if record.get("author_name") or record.get("author"):
            builder.p(f"Автор: {record.get('author_name') or record.get('author')}")
        if resolved_desc:
            builder.p(resolved_desc)
        if resolved_img:
            builder.img(resolved_img, alt=resolved_title)
        body_html = builder.to_html()

    return SeoPageData(
        title=resolved_title,
        description=resolved_desc,
        canonical_url=current_path,
        og_image=resolved_img,
        schema_type=node.get("schema_type") or "Article",
        breadcrumbs=breadcrumbs,
        body_html=body_html,
    )


async def match_and_render_site_tree(
    path: str,
    *,
    db: Database,
    crud_engine: CrudEngine,
    guest_permissions: frozenset[str] | None = None,
) -> SeoPageData | None:
    """
    Проверяет, соответствует ли запрошенный ботом путь какому-либо узлу дерева сайта,
    и отдает семантический HTML со ссылками.
    """
    tree = get_cached_site_tree()
    all_nodes = flatten_tree_nodes(tree)
    clean_path = path if path == "/" else path.rstrip("/")

    for node, parents in all_nodes:
        pattern = node.get("url_pattern", "")
        if not pattern:
            continue

        compiled, keys = compile_pattern_to_regex(pattern)
        m = compiled.match(clean_path)
        if not m:
            continue

        extracted_params = m.groupdict()
        node_type = node.get("node_type", "static")

        try:
            res: SeoPageData | None = None
            if node_type == "static":
                res = await render_static_node(
                    node,
                    parents,
                    clean_path,
                    db=db,
                    crud_engine=crud_engine,
                    guest_permissions=guest_permissions,
                )
            elif node_type == "collection":
                res = await render_collection_node(
                    node,
                    parents,
                    clean_path,
                    extracted_params,
                    keys,
                    db=db,
                    crud_engine=crud_engine,
                    guest_permissions=guest_permissions,
                )
            elif node_type == "detail":
                res = await render_detail_node(
                    node,
                    parents,
                    clean_path,
                    extracted_params,
                    keys,
                    db=db,
                    crud_engine=crud_engine,
                    guest_permissions=guest_permissions,
                )
            if res is not None:
                return res
        except Exception as exc:
            logger.error("[SEO Tree] Ошибка рендеринга узла %s (%s): %s", node.get("title"), pattern, exc)

    return None


async def collect_site_tree_sitemap_urls(
    *,
    db: Database | None = None,
    crud_engine: CrudEngine | None = None,
    guest_permissions: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Автоматически собирает полный список URL для `sitemap.xml`,
    рекурсивно обходя дерево сайта и выгружая разрешенные для `guest` динамические записи.
    """
    tree = get_cached_site_tree()
    all_nodes = flatten_tree_nodes(tree)
    collected: list[dict[str, Any]] = []

    for node, _parents in all_nodes:
        if not node.get("sitemap_enabled", True):
            continue

        pattern = node.get("url_pattern", "")
        priority = float(node.get("sitemap_priority", 0.7))
        changefreq = node.get("sitemap_changefreq", "daily")

        node_type = node.get("node_type")
        if not node_type:
            if node.get("model_key"):
                node_type = "detail" if "{" in pattern else "collection"
            else:
                node_type = "static"

        if node_type in ("static", "collection") and "{" not in pattern and "}" not in pattern:
            if pattern:
                collected.append({
                    "loc": pattern,
                    "priority": priority,
                    "changefreq": changefreq,
                })
        elif db is not None and crud_engine is not None:
            model_key = node.get("model_key")
            spec = _get_allowed_spec(crud_engine, model_key, guest_permissions)
            if spec is None:
                continue

            async with db.session() as session:
                model_cls = spec.model_cls
                stmt = select(model_cls).limit(50_000)
                rows = (await session.execute(stmt)).scalars().all()
                for r in rows:
                    rec = serialize_safe_record(r, spec)
                    relations: dict[str, dict[str, Any]] = {}
                    for f in spec.fields:
                        if f.foreign_key_table or f.name.endswith("_id"):
                            fk_val = rec.get(f.name)
                            if fk_val is None:
                                continue
                            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                            t_spec = resolve_foreign_target_spec(crud_engine, f.name, f.foreign_key_table)
                            if t_spec and is_model_allowed_for_seo(t_spec, guest_permissions):
                                t_cls = t_spec.model_cls
                                r_row = (
                                    await session.execute(select(t_cls).where(t_cls.id == fk_val))
                                ).scalar_one_or_none()
                                if r_row:
                                    r_dict = serialize_safe_record(r_row, t_spec)
                                    relations[rel_name] = r_dict
                                    relations["parent"] = r_dict

                    loc = resolve_template(pattern, rec, relations)
                    if loc and "{" not in loc and "}" not in loc and not re.search(r"(?<!:)//", loc):
                        collected.append({
                            "loc": loc,
                            "priority": priority,
                            "changefreq": changefreq,
                            "lastmod": rec.get("updated_at") or rec.get("created_at"),
                        })

    return collected
