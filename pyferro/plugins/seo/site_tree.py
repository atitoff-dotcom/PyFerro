# -*- coding: utf-8 -*-
"""
pyferro.plugins.seo.site_tree: Универсальный движок «Живого дерева сайта» для SEO и Dynamic Rendering в PyFerro.

Обеспечивает:
1. 100% универсальную модель структуры сайта (Главная -> Разделы -> Категории -> Карточки).
2. Поддержку универсального родительского контекста `{parent.slug}`, `{parent.title}`, `{parent.id}`.
3. Автоматическую генерацию семантических ссылок <a href="..."> для ботов на каждом уровне.
4. Автоматическую сборку хлебных крошек (Breadcrumbs) снизу вверх по родительским узлам.
5. Автоматическую сборку Sitemap.xml прямо из обхода дерева.
6. Персистентное хранение структуры в data/seo_tree.json с горячим обновлением и пресетами.
"""

import json
import os
import re
import html
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone
from sqlalchemy import select

from pyferro.core.logger import logger
from pyferro.db import async_session
from pyferro.plugins.crud import ModelRegistry
from .schemas import SeoPageData
from .renderer import HtmlBuilder
from .dynamic_rules import resolve_template, compile_pattern_to_regex, PARAM_RE

SEO_TREE_FILE = os.getenv("SEO_TREE_FILE", "data/seo_tree.json")


def _get_model_meta(model_key: Optional[str]):
    """Универсально находит метаданные модели в реестре, подгружая плагины при необходимости."""
    if not model_key:
        return None
    meta = ModelRegistry.get(model_key)
    if not meta:
        try:
            import pyferro.plugins.help
            meta = ModelRegistry.get(model_key)
        except Exception:
            pass
    return meta


def _resolve_relation_meta(f):
    """Определяет целевую модель связи по полю внешнего ключа."""
    fk_dict = f.foreign_key if isinstance(f.foreign_key, dict) else {}
    target_key = f.target_model or fk_dict.get("target_table") or fk_dict.get("target_model")
    return _get_model_meta(target_key)


# Универсальные шаблоны структуры для быстрого старта любого типа проекта
STRUCTURE_PRESETS: Dict[str, Dict[str, Any]] = {
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
                    "schema_type": "WebPage",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.6,
                    "sitemap_changefreq": "monthly",
                    "children": []
                },
                {
                    "id": "contacts",
                    "title": "Контакты",
                    "url_pattern": "/contacts",
                    "node_type": "static",
                    "meta_title": "Контакты и обратная связь",
                    "meta_description": "Свяжитесь с нами удобным способом: телефон, электронная почта, адрес.",
                    "og_image": "",
                    "schema_type": "WebPage",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.5,
                    "sitemap_changefreq": "monthly",
                    "children": []
                }
            ]
        }
    },
    "ecommerce": {
        "title": "Интернет-магазин (Каталог ➔ Разделы ➔ Товары)",
        "description": "Идеально для каталогов, магазинов и витрин товаров со вложенными категориями",
        "icon": "🛒",
        "tree": {
            "id": "root",
            "title": "Главная страница",
            "url_pattern": "/",
            "node_type": "static",
            "meta_title": "Интернет-магазин товаров",
            "meta_description": "Широкий ассортимент качественных товаров, выгодные цены и быстрая доставка.",
            "og_image": "",
            "schema_type": "WebPage",
            "sitemap_enabled": True,
            "sitemap_priority": 1.0,
            "sitemap_changefreq": "daily",
            "children": [
                {
                    "id": "catalog_hub",
                    "title": "Каталог (Разделы)",
                    "url_pattern": "/catalog",
                    "node_type": "collection",
                    "model_key": None,
                    "meta_title": "Каталог товаров — Все категории",
                    "meta_description": "Выберите интересующий раздел каталога для просмотра товаров.",
                    "og_image": "",
                    "schema_type": "CollectionPage",
                    "item_link_pattern": "/catalog/{slug}",
                    "item_title_pattern": "{title}",
                    "item_desc_pattern": "{description}",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.9,
                    "sitemap_changefreq": "daily",
                    "children": [
                        {
                            "id": "category_page",
                            "title": "Раздел каталога (Товары)",
                            "url_pattern": "/catalog/{parent.slug}",
                            "node_type": "collection",
                            "model_key": None,
                            "meta_title": "{parent.title} — Товары раздела",
                            "meta_description": "Купить товары в категории {parent.title} по выгодной цене с гарантией.",
                            "og_image": "",
                            "schema_type": "CollectionPage",
                            "item_link_pattern": "/catalog/{parent.slug}/{slug}",
                            "item_title_pattern": "{title}",
                            "item_desc_pattern": "{description}",
                            "filter_field": "category_id",
                            "filter_parent_param": "parent.id",
                            "sitemap_enabled": True,
                            "sitemap_priority": 0.8,
                            "sitemap_changefreq": "daily",
                            "children": [
                                {
                                    "id": "product_detail",
                                    "title": "Карточка товара",
                                    "url_pattern": "/catalog/{parent.slug}/{slug}",
                                    "node_type": "detail",
                                    "model_key": None,
                                    "meta_title": "{title} — купить в интернет-магазине",
                                    "meta_description": "{description}",
                                    "og_image": "{image}",
                                    "schema_type": "Product",
                                    "sitemap_enabled": True,
                                    "sitemap_priority": 0.8,
                                    "sitemap_changefreq": "weekly",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    },
    "blog": {
        "title": "Блог и Публикации (Лента ➔ Статьи)",
        "description": "Подходит для контентных проектов, новостных изданий, медиа и личных блогов",
        "icon": "📰",
        "tree": {
            "id": "root",
            "title": "Главная страница",
            "url_pattern": "/",
            "node_type": "static",
            "meta_title": "{site_name} — Новости и статьи",
            "meta_description": "Актуальные публикации, экспертные материалы и полезные статьи.",
            "og_image": "",
            "schema_type": "WebPage",
            "sitemap_enabled": True,
            "sitemap_priority": 1.0,
            "sitemap_changefreq": "daily",
            "children": [
                {
                    "id": "blog_hub",
                    "title": "Блог (Все статьи)",
                    "url_pattern": "/blog",
                    "node_type": "collection",
                    "model_key": None,
                    "meta_title": "Блог — Все статьи и публикации",
                    "meta_description": "Читайте последние статьи, обзоры и практические руководства.",
                    "og_image": "",
                    "schema_type": "CollectionPage",
                    "item_link_pattern": "/blog/{slug}",
                    "item_title_pattern": "{title}",
                    "item_desc_pattern": "{description}",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.8,
                    "sitemap_changefreq": "daily",
                    "children": [
                        {
                            "id": "article_detail",
                            "title": "Статья блога",
                            "url_pattern": "/blog/{slug}",
                            "node_type": "detail",
                            "model_key": None,
                            "meta_title": "{title} — Читать статью в блоге",
                            "meta_description": "{description}",
                            "og_image": "{image}",
                            "schema_type": "Article",
                            "sitemap_enabled": True,
                            "sitemap_priority": 0.8,
                            "sitemap_changefreq": "weekly",
                            "children": []
                        }
                    ]
                }
            ]
        }
    },
    "forum": {
        "title": "Сообщество и Форум (Разделы ➔ Подразделы ➔ Темы)",
        "description": "Многоуровневая структура: главные разделы, вложенные подразделы и карточки тем",
        "icon": "💬",
        "tree": {
            "id": "root",
            "title": "Главная страница",
            "url_pattern": "/",
            "node_type": "static",
            "meta_title": "PyFerro Platform — современное реактивное веб-приложение",
            "meta_description": "Высокопроизводительное SPA-приложение с реактивными WebSocket-каналами, No-Code SEO и мгновенным откликом.",
            "og_image": "",
            "schema_type": "WebPage",
            "model_key": None,
            "sitemap_enabled": True,
            "sitemap_priority": 1.0,
            "sitemap_changefreq": "daily",
            "children": [
                {
                    "id": "forum_hub",
                    "title": "Форум (Главные разделы)",
                    "url_pattern": "/forum",
                    "node_type": "collection",
                    "model_key": "ForumCategory",
                    "meta_title": "Форум сообщества — Главные разделы",
                    "meta_description": "Обсуждения, анонсы, обмен опытом и техническая поддержка сообщества.",
                    "og_image": "",
                    "schema_type": "CollectionPage",
                    "template": """<h1>{{ title }}</h1>
<p>{{ description }}</p>

<h2>Разделы форума:</h2>
<ul>
{% for c in ForumCategory.where(parent_id=None) %}
  <li>
    <a href="/forum/{{ c.slug }}"><strong>{{ c.name }}</strong></a>
    {% if c.description %} — <span>{{ c.description }}</span>{% endif %}
  </li>
{% endfor %}
</ul>

<h2>Свежие темы обсуждений:</h2>
<ul>
{% for t in ForumTopic[:5] %}
  <li>
    <a href="/forum/{{ t.category.slug or 'general' }}/{{ t.slug }}"><strong>{{ t.title }}</strong></a>
    {% if t.author_name %} (автор: {{ t.author_name }}){% endif %}
  </li>
{% endfor %}
</ul>""",
                    "item_link_pattern": "/forum/{slug}",
                    "item_title_pattern": "{name}",
                    "item_desc_pattern": "{description}",
                    "filter_field": "parent_id",
                    "filter_is_null": True,
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.9,
                    "sitemap_changefreq": "daily",
                    "children": [
                        {
                            "id": "category_root",
                            "title": "Главный раздел (Список подразделов)",
                            "url_pattern": "/forum/{slug}",
                            "node_type": "collection",
                            "model_key": "ForumCategory",
                            "meta_title": "Раздел «{{ record.name }}» — Подразделы форума",
                            "meta_description": "{{ record.description }}",
                            "og_image": "",
                            "schema_type": "CollectionPage",
                            "template": """<h1>Раздел: {{ record.name }}</h1>
{% if record.description %}<p>{{ record.description }}</p>{% endif %}

<h2>Подразделы:</h2>
<ul>
{% for sub in ForumCategory.where(parent_id=record.id) %}
  <li>
    <a href="/forum/{{ record.slug }}/{{ sub.slug }}"><strong>{{ sub.name }}</strong></a>
    {% if sub.description %} — <span>{{ sub.description }}</span>{% endif %}
  </li>
{% endfor %}
</ul>""",
                            "item_link_pattern": "/forum/{parent.slug}/{slug}",
                            "item_title_pattern": "{name}",
                            "item_desc_pattern": "{description}",
                            "filter_field": "parent_id",
                            "filter_parent_param": "id",
                            "sitemap_enabled": True,
                            "sitemap_priority": 0.85,
                            "sitemap_changefreq": "daily",
                            "children": [
                                {
                                    "id": "topic_detail",
                                    "title": "Тема форума (Карточка)",
                                    "url_pattern": "/forum/{parent.slug}/{slug}",
                                    "node_type": "detail",
                                    "model_key": "ForumTopic",
                                    "meta_title": "{{ record.title }} — {{ parent.name }} | Форум",
                                    "meta_description": "{{ record.first_post_text }}",
                                    "og_image": "",
                                    "schema_type": "DiscussionForumPosting",
                                    "template": """<h1>{{ record.title }}</h1>
<p class="topic-meta">
  {% if record.author_name %}Автор: <strong>{{ record.author_name }}</strong> | {% endif %}
  Просмотров: {{ record.views_count or 0 }} | Ответов: {{ record.replies_count or 0 }}
</p>
<div class="topic-body">
  <p>{{ record.first_post_text }}</p>
</div>""",
                                    "sitemap_enabled": True,
                                    "sitemap_priority": 0.8,
                                    "sitemap_changefreq": "weekly",
                                    "children": []
                                },
                                {
                                    "id": "category_sub",
                                    "title": "Подраздел форума (Список тем)",
                                    "url_pattern": "/forum/{parent.slug}/{slug}",
                                    "node_type": "collection",
                                    "model_key": "ForumCategory",
                                    "meta_title": "Подраздел «{{ record.name or title }}» — Темы",
                                    "meta_description": "{{ record.description or description }}",
                                    "og_image": "",
                                    "schema_type": "CollectionPage",
                                    "template": """<h1>Подраздел: {{ record.name or title }}</h1>
{% if record.description %}<p>{{ record.description }}</p>{% endif %}

<h2>Темы обсуждения:</h2>
<ul>
{% for t in ForumTopic.where(category_id=record.id) %}
  <li>
    <a href="/forum/{{ parent.slug }}/{{ record.slug }}/{{ t.slug }}"><strong>{{ t.title }}</strong></a>
    {% if t.author_name %} (автор: {{ t.author_name }}){% endif %}
  </li>
{% endfor %}
</ul>""",
                                    "item_link_pattern": "/forum/{root.slug}/{parent.slug}/{slug}",
                                    "item_title_pattern": "{title}",
                                    "item_desc_pattern": "{first_post_text}",
                                    "filter_field": "category_id",
                                    "filter_parent_param": "id",
                                    "sitemap_enabled": True,
                                    "sitemap_priority": 0.75,
                                    "sitemap_changefreq": "daily",
                                    "children": [
                                        {
                                            "id": "topic_detail_sub",
                                            "title": "Тема в подразделе (Карточка)",
                                            "url_pattern": "/forum/{root.slug}/{parent.slug}/{slug}",
                                            "node_type": "detail",
                                            "model_key": "ForumTopic",
                                            "meta_title": "{{ record.title }} — {{ parent.name }} | Форум",
                                            "meta_description": "{{ record.first_post_text }}",
                                            "og_image": "",
                                            "schema_type": "DiscussionForumPosting",
                                            "template": """<h1>{{ record.title }}</h1>
<p class="topic-meta">
  {% if record.author_name %}Автор: <strong>{{ record.author_name }}</strong> | {% endif %}
  Просмотров: {{ record.views_count or 0 }} | Ответов: {{ record.replies_count or 0 }}
</p>
<div class="topic-body">
  <p>{{ record.first_post_text }}</p>
</div>""",
                                            "sitemap_enabled": True,
                                            "sitemap_priority": 0.7,
                                            "sitemap_changefreq": "weekly",
                                            "children": []
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": "about_page",
                    "title": "О проекте",
                    "url_pattern": "/about",
                    "node_type": "static",
                    "meta_title": "О нашем проекте — Миссия и технологии",
                    "meta_description": "Узнайте больше о нашей платформе, команде и архитектуре на базе PyFerro WSRPC.",
                    "og_image": "",
                    "schema_type": "WebPage",
                    "sitemap_enabled": True,
                    "sitemap_priority": 0.5,
                    "sitemap_changefreq": "monthly",
                    "children": []
                }
            ]
        }
    }
}


def _get_default_tree() -> Dict[str, Any]:
    """Возвращает дерево по умолчанию (сначала проверяем модели проекта, иначе форум или минимальный сайт)."""
    # Если в проекте уже есть зарегистрированные ForumCategory/Topic, отдаем forum пресет
    meta_fc = _get_model_meta("ForumCategory")
    if meta_fc:
        return STRUCTURE_PRESETS["forum"]["tree"]
    return STRUCTURE_PRESETS["clean"]["tree"]


_CACHED_TREE: Optional[Dict[str, Any]] = None


def load_site_tree() -> Dict[str, Any]:
    """Загружает структуру дерева сайта из файла конфигурации или возвращает дефолтную."""
    global _CACHED_TREE
    if _CACHED_TREE is not None:
        return _CACHED_TREE

    if os.path.exists(SEO_TREE_FILE):
        try:
            with open(SEO_TREE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "id" in data:
                    _CACHED_TREE = data
                    return _CACHED_TREE
        except Exception as e:
            logger.warning(f"[SEO Tree] Ошибка чтения {SEO_TREE_FILE}: {e}. Используем дерево по умолчанию.")

    _CACHED_TREE = _get_default_tree()
    return _CACHED_TREE


def save_site_tree(tree_data: Dict[str, Any]) -> None:
    """Сохраняет структуру дерева сайта в файл и инвалидирует кэш."""
    global _CACHED_TREE
    _CACHED_TREE = tree_data

    dir_name = os.path.dirname(SEO_TREE_FILE)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with open(SEO_TREE_FILE, "w", encoding="utf-8") as f:
        json.dump(tree_data, f, ensure_ascii=False, indent=2)

    logger.info(f"[SEO Tree] Конфигурация дерева сайта успешно сохранена в {SEO_TREE_FILE}")

    try:
        from .sitemap import invalidate_sitemap_cache
        invalidate_sitemap_cache()
    except Exception:
        pass


def flatten_tree_nodes(node: Dict[str, Any], parent_chain: Optional[List[Dict[str, Any]]] = None) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Рекурсивно разворачивает дерево в плоский список пар (узел, цепочка_родителей)."""
    if parent_chain is None:
        parent_chain = []
    result = [(node, parent_chain)]
    new_chain = parent_chain + [node]
    for child in node.get("children", []):
        result.extend(flatten_tree_nodes(child, new_chain))
    return result


async def match_and_render_site_tree(path: str) -> Optional[SeoPageData]:
    """
    Основной перехватчик: проверяет, соответствует ли запрошенный ботом путь
    какому-либо узлу дерева сайта, и отдает богатый семантический HTML со ссылками.
    """
    tree = load_site_tree()
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
            res = None
            if node_type == "static":
                res = await _render_static_node(node, parents, clean_path)
            elif node_type == "collection":
                res = await _render_collection_node(node, parents, clean_path, extracted_params, keys)
            elif node_type == "detail":
                res = await _render_detail_node(node, parents, clean_path, extracted_params, keys)
            if res is not None:
                return res
        except Exception as e:
            logger.error(f"[SEO Tree] Ошибка рендеринга узла {node.get('title')} ({pattern}): {e}", exc_info=True)
    return None


async def _render_static_node(
    node: Dict[str, Any],
    parents: List[Dict[str, Any]],
    current_path: str
) -> SeoPageData:
    """Рендерит статический узел (например, главную страницу или /about) со ссылками на детей."""
    title = node.get("meta_title") or node.get("title", "")
    description = node.get("meta_description", "")
    og_image = node.get("og_image") or None
    schema_type = node.get("schema_type") or "WebPage"

    # Хлебные крошки
    breadcrumbs = []
    for p in parents:
        breadcrumbs.append((p.get("title", ""), p.get("url_pattern", "/")))
    if current_path != "/":
        breadcrumbs.append((node.get("title", ""), current_path))

    template_str = (node.get("template") or "").strip()
    if template_str:
        from .jinja_engine import build_template_context, render_jinja_template
        ctx = build_template_context(
            breadcrumbs=breadcrumbs,
            site_url=current_path,
            site_name=title,
            extra={"title": title, "description": description, "current_path": current_path}
        )
        try:
            body_html = await render_jinja_template(template_str, ctx)
        except Exception as e:
            logger.error(f"[SEO Tree] Ошибка рендеринга Jinja2 шаблона для {node.get('title')}: {e}")
            body_html = f'<div class="seo-template-error">Ошибка шаблона: {html.escape(str(e))}</div>'
    else:
        builder = HtmlBuilder()
        builder.h1(title)
        if description:
            builder.p(description)

        # Выводим ссылки на непосредственные дочерние разделы
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
                    builder.raw(f'  <li><a href="{html.escape(u, quote=True)}"><strong>{html.escape(t)}</strong></a>{desc_span}</li>')
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
        body_html=body_html
    )


async def _render_collection_node(
    node: Dict[str, Any],
    parents: List[Dict[str, Any]],
    current_path: str,
    extracted_params: Dict[str, str],
    keys: List[Tuple[str, str]]
) -> Optional[SeoPageData]:
    """
    Рендерит хаб/раздел коллекций (например, /catalog или /catalog/{parent.slug}).
    Извлекает записи из БД и генерирует живой HTML-список <a href="..."> для краулера.
    """
    model_key = node.get("model_key")
    meta = _get_model_meta(model_key)
    if not meta:
        return await _render_static_node(node, parents, current_path)

    # 1. Если узел параметризован (например, /catalog/{parent.slug}), находим родительскую запись
    parent_record = {}
    parent_relations = {}

    if keys:
        for full_key, clean_key in keys:
            val = extracted_params.get(clean_key)
            if not val:
                continue
            if "." in full_key:
                rel_name, field_name = full_key.split(".", 1)
                for f in meta.get_column_fields():
                    # Сопоставляем универсальный parent, root или имя связи
                    if rel_name in ("parent", "root", "grandparent") or f.name.startswith(rel_name) or (f.foreign_key and rel_name in f.name):
                        target_meta = _resolve_relation_meta(f)
                        if target_meta:
                            async with async_session() as db:
                                t_cls = target_meta.model_cls
                                col = getattr(t_cls, field_name, None)
                                if col is not None:
                                    row = (await db.execute(select(t_cls).where(col == val))).scalar_one_or_none()
                                    if row:
                                        p_dict = row.to_dict() if hasattr(row, "to_dict") else {c.name: getattr(row, c.name, None) for c in t_cls.__table__.columns}
                                        parent_relations[rel_name] = p_dict
                                        if rel_name == "parent":
                                            parent_record.update(p_dict)
                                        # Если у найденной сущности есть parent_id (дедушка / корневой раздел)
                                        if hasattr(t_cls, "parent_id") and getattr(row, "parent_id", None):
                                            gp_row = (await db.execute(select(t_cls).where(t_cls.id == getattr(row, "parent_id")))).scalar_one_or_none()
                                            if gp_row:
                                                gp_dict = gp_row.to_dict() if hasattr(gp_row, "to_dict") else {c.name: getattr(gp_row, c.name, None) for c in t_cls.__table__.columns}
                                                parent_relations["root"] = gp_dict
                                                parent_relations["grandparent"] = gp_dict
                                        break
            else:
                # full_key без точки: параметр самого раздела (например /forum/{slug})
                async with async_session() as db:
                    resolved_in_rel = False
                    for f in meta.get_column_fields():
                        if f.foreign_key or f.name.endswith("_id"):
                            t_meta = _resolve_relation_meta(f)
                            if t_meta:
                                t_cls = t_meta.model_cls
                                col = getattr(t_cls, full_key, None)
                                if col is not None:
                                    row = (await db.execute(select(t_cls).where(col == val))).scalar_one_or_none()
                                    if row:
                                        p_dict = row.to_dict() if hasattr(row, "to_dict") else {c.name: getattr(row, c.name, None) for c in t_cls.__table__.columns}
                                        parent_relations["parent"] = p_dict
                                        parent_record.update(p_dict)
                                        if hasattr(t_cls, "parent_id") and getattr(row, "parent_id", None):
                                            gp_row = (await db.execute(select(t_cls).where(t_cls.id == getattr(row, "parent_id")))).scalar_one_or_none()
                                            if gp_row:
                                                gp_dict = gp_row.to_dict() if hasattr(gp_row, "to_dict") else {c.name: getattr(gp_row, c.name, None) for c in t_cls.__table__.columns}
                                                parent_relations["root"] = gp_dict
                                                parent_relations["grandparent"] = gp_dict
                                        resolved_in_rel = True
                                        break
                    if not resolved_in_rel:
                        t_cls = meta.model_cls
                        col = getattr(t_cls, full_key, None)
                        if col is not None:
                            row = (await db.execute(select(t_cls).where(col == val))).scalar_one_or_none()
                            if row:
                                p_dict = row.to_dict() if hasattr(row, "to_dict") else {c.name: getattr(row, c.name, None) for c in t_cls.__table__.columns}
                                parent_relations["parent"] = p_dict
                                parent_record.update(p_dict)
                                if hasattr(t_cls, "parent_id") and getattr(row, "parent_id", None):
                                    gp_row = (await db.execute(select(t_cls).where(t_cls.id == getattr(row, "parent_id")))).scalar_one_or_none()
                                    if gp_row:
                                        gp_dict = gp_row.to_dict() if hasattr(gp_row, "to_dict") else {c.name: getattr(gp_row, c.name, None) for c in t_cls.__table__.columns}
                                        parent_relations["root"] = gp_dict
                                        parent_relations["grandparent"] = gp_dict
    # Если узел параметризован, но запись в базе не найдена — пропускаем узел для поиска других совпадений
    if keys and not parent_record:
        return None

    # Гарантируем, что {parent.xyz} всегда указывает на родительский контекст
    if parent_record and "parent" not in parent_relations:
        parent_relations["parent"] = parent_record

    raw_title = node.get("meta_title") or node.get("title", "")
    raw_desc = node.get("meta_description", "")
    if "{{" in raw_title or "{%" in raw_title:
        from .jinja_engine import build_template_context, render_jinja_template
        t_ctx = build_template_context(record=parent_record, relations=parent_relations)
        resolved_title = await render_jinja_template(raw_title, t_ctx)
    else:
        resolved_title = resolve_template(raw_title, parent_record, parent_relations)

    if "{{" in raw_desc or "{%" in raw_desc:
        from .jinja_engine import build_template_context, render_jinja_template
        t_ctx = build_template_context(record=parent_record, relations=parent_relations)
        resolved_desc = await render_jinja_template(raw_desc, t_ctx)
    else:
        resolved_desc = resolve_template(raw_desc, parent_record, parent_relations)
    # 2. Выполняем выборку элементов текущего раздела из базы данных
    items = []
    async with async_session() as db:
        model_cls = meta.model_cls
        stmt = select(model_cls)

        filter_field = node.get("filter_field")
        filter_parent_param = node.get("filter_parent_param")
        filter_is_null = node.get("filter_is_null")

        if filter_field and hasattr(model_cls, filter_field):
            if filter_is_null:
                stmt = stmt.where(getattr(model_cls, filter_field).is_(None))
            elif filter_parent_param:
                parent_val = None
                if "." in filter_parent_param:
                    r_name, f_name = filter_parent_param.split(".", 1)
                    parent_val = (parent_relations.get(r_name) or parent_relations.get("parent") or {}).get(f_name)
                else:
                    parent_val = parent_record.get(filter_parent_param)

                if parent_val is not None:
                    stmt = stmt.where(getattr(model_cls, filter_field) == parent_val)
        elif hasattr(model_cls, "parent_id") and not keys:
            stmt = stmt.where(getattr(model_cls, "parent_id").is_(None))
        stmt = stmt.limit(50)
        rows = (await db.execute(stmt)).scalars().all()
        for r in rows:
            items.append(r.to_dict() if hasattr(r, "to_dict") else {c.name: getattr(r, c.name, None) for c in model_cls.__table__.columns})

    # 3. Формируем хлебные крошки
    breadcrumbs = []
    for p in parents:
        p_url = resolve_template(p.get("url_pattern", "/"), parent_record, parent_relations)
        p_title = resolve_template(p.get("title", ""), parent_record, parent_relations)
        breadcrumbs.append((p_title, p_url))
    breadcrumbs.append((resolved_title, current_path))

    # 4. Собираем HTML (через Jinja2 шаблон или стандартный построитель)
    template_str = (node.get("template") or "").strip()
    if template_str:
        from .jinja_engine import build_template_context, render_jinja_template
        ctx = build_template_context(
            record=parent_record,
            relations=parent_relations,
            parent_chain=parents,
            breadcrumbs=breadcrumbs,
            extra={
                "title": resolved_title,
                "description": resolved_desc,
                "current_path": current_path,
                "extracted_params": extracted_params,
                "items": items,
            }
        )
        try:
            body_html = await render_jinja_template(template_str, ctx)
        except Exception as e:
            logger.error(f"[SEO Tree] Ошибка рендеринга Jinja2 шаблона: {e}")
            body_html = f'<div class="seo-template-error">Ошибка шаблона: {html.escape(str(e))}</div>'
    else:
        builder = HtmlBuilder()
        builder.h1(resolved_title)
        if resolved_desc:
            builder.p(resolved_desc)

        # Авто-подбор полей названия и ссылки для элемента, если шаблоны не заданы
        field_names = [f.name for f in meta.get_column_fields()]
        fallback_title_field = next((f for f in ["title", "name", "caption", "header"] if f in field_names), "title")
        fallback_desc_field = next((f for f in ["description", "first_post_text", "content", "summary", "text"] if f in field_names), "description")
        fallback_slug_field = next((f for f in ["slug", "code", "alias", "id"] if f in field_names), "id")

        item_link_tpl = node.get("item_link_pattern") or f"{current_path}/{{{fallback_slug_field}}}"
        item_title_tpl = node.get("item_title_pattern") or f"{{{fallback_title_field}}}"
        item_desc_tpl = node.get("item_desc_pattern") or f"{{{fallback_desc_field}}}"

        if items:
            builder.raw('<section class="seo-collection-items">')
            builder.h2("Содержимое раздела:")
            builder.raw("<ul>")
            for it in items:
                it_url = resolve_template(item_link_tpl, it, parent_relations)
                it_title = resolve_template(item_title_tpl, it, parent_relations) or it.get(fallback_title_field) or "Ссылка"
                it_desc = resolve_template(item_desc_tpl, it, parent_relations) or ""

                desc_part = f" — <span>{html.escape(str(it_desc)[:200])}</span>" if it_desc else ""
                builder.raw(f'  <li><a href="{html.escape(it_url, quote=True)}"><strong>{html.escape(str(it_title))}</strong></a>{desc_part}</li>')
            builder.raw("</ul>")
            builder.raw("</section>")
        else:
            builder.raw('<p class="seo-empty text-muted">В данном разделе пока нет записей.</p>')
        body_html = builder.to_html()

    return SeoPageData(
        title=resolved_title,
        description=resolved_desc,
        canonical_url=current_path,
        og_image=node.get("og_image") or None,
        schema_type=node.get("schema_type") or "CollectionPage",
        breadcrumbs=breadcrumbs,
        body_html=body_html
    )


async def _render_detail_node(
    node: Dict[str, Any],
    parents: List[Dict[str, Any]],
    current_path: str,
    extracted_params: Dict[str, str],
    keys: List[Tuple[str, str]]
) -> Optional[SeoPageData]:
    """
    Рендерит детальную страницу записи (товар, статья, публикация, страница).
    Извлекает запись и родительские связи, формирует разметку Schema.org и крошки.
    """
    model_key = node.get("model_key")
    meta = _get_model_meta(model_key)
    if not meta:
        return None

    async with async_session() as db:
        model_cls = meta.model_cls
        stmt = select(model_cls)

        main_param_val = None
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

        if not main_param_val:
            return None

        col = getattr(model_cls, main_field, None)
        if col is None:
            return None

        try:
            if hasattr(col.type, "python_type") and col.type.python_type is int:
                main_param_val = int(main_param_val)
        except Exception:
            pass

        row = (await db.execute(stmt.where(col == main_param_val))).scalar_one_or_none()
        if not row:
            return None

        record = row.to_dict() if hasattr(row, "to_dict") else {c.name: getattr(row, c.name, None) for c in model_cls.__table__.columns}

        # Загружаем связанные сущности (Foreign Keys)
        relations = {}
        for f in meta.get_column_fields():
            if f.foreign_key or f.name.endswith("_id"):
                fk_val = record.get(f.name)
                if fk_val is None:
                    continue
                rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                target_meta = _resolve_relation_meta(f)
                if target_meta:
                    t_cls = target_meta.model_cls
                    rel_row = (await db.execute(select(t_cls).where(t_cls.id == fk_val))).scalar_one_or_none()
                    if rel_row:
                        r_dict = rel_row.to_dict() if hasattr(rel_row, "to_dict") else {c.name: getattr(rel_row, c.name, None) for c in t_cls.__table__.columns}
                        relations[rel_name] = r_dict
                        relations["parent"] = r_dict
                        # Если у родителя тоже есть parent_id (дедушка / корневой раздел)
                        if hasattr(t_cls, "parent_id") and getattr(rel_row, "parent_id", None):
                            gp_row = (await db.execute(select(t_cls).where(t_cls.id == getattr(rel_row, "parent_id")))).scalar_one_or_none()
                            if gp_row:
                                gp_dict = gp_row.to_dict() if hasattr(gp_row, "to_dict") else {c.name: getattr(gp_row, c.name, None) for c in t_cls.__table__.columns}
                                relations["root"] = gp_dict
                                relations["grandparent"] = gp_dict
                                relations["category_parent"] = gp_dict
    field_names = [f.name for f in meta.get_column_fields()]
    fallback_title_field = next((f for f in ["title", "name", "caption", "header"] if f in field_names), "title")
    fallback_desc_field = next((f for f in ["description", "first_post_text", "content", "summary", "text"] if f in field_names), "description")
    fallback_img_field = next((f for f in ["image", "og_image", "cover", "photo", "avatar"] if f in field_names), "")

    raw_title = node.get("meta_title") or f"{{{fallback_title_field}}}"
    raw_desc = node.get("meta_description") or f"{{{fallback_desc_field}}}"
    raw_img = node.get("og_image") or (f"{{{fallback_img_field}}}" if fallback_img_field else "")

    if "{{" in raw_title or "{%" in raw_title:
        from .jinja_engine import build_template_context, render_jinja_template
        t_ctx = build_template_context(record=record, relations=relations)
        resolved_title = await render_jinja_template(raw_title, t_ctx)
    else:
        resolved_title = resolve_template(raw_title, record, relations)

    if "{{" in raw_desc or "{%" in raw_desc:
        from .jinja_engine import build_template_context, render_jinja_template
        t_ctx = build_template_context(record=record, relations=relations)
        resolved_desc = await render_jinja_template(raw_desc, t_ctx)
    else:
        resolved_desc = resolve_template(raw_desc, record, relations)

    resolved_img = resolve_template(raw_img, record, relations) or None

    # Хлебные крошки
    breadcrumbs = []
    for p in parents:
        p_title = resolve_template(p.get("title", ""), record, relations)
        p_url = resolve_template(p.get("url_pattern", "/"), record, relations)
        breadcrumbs.append((p_title, p_url))
    breadcrumbs.append((resolved_title, current_path))

    template_str = (node.get("template") or "").strip()
    if template_str:
        from .jinja_engine import build_template_context, render_jinja_template
        ctx = build_template_context(
            record=record,
            relations=relations,
            parent_chain=parents,
            breadcrumbs=breadcrumbs,
            extra={
                "title": resolved_title,
                "description": resolved_desc,
                "current_path": current_path,
                "extracted_params": extracted_params,
            }
        )
        try:
            body_html = await render_jinja_template(template_str, ctx)
        except Exception as e:
            logger.error(f"[SEO Tree] Ошибка рендеринга Jinja2 шаблона: {e}")
            body_html = f'<div class="seo-template-error">Ошибка шаблона: {html.escape(str(e))}</div>'
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
        body_html=body_html
    )


async def collect_site_tree_sitemap_urls() -> List[Dict[str, Any]]:
    """
    Автоматически собирает полный список URL для sitemap.xml,
    рекурсивно обходя дерево сайта и выгружая динамические записи.
    """
    tree = load_site_tree()
    all_nodes = flatten_tree_nodes(tree)
    collected: List[Dict[str, Any]] = []

    for node, parents in all_nodes:
        if not node.get("sitemap_enabled", True):
            continue

        node_type = node.get("node_type", "static")
        pattern = node.get("url_pattern", "")
        priority = float(node.get("sitemap_priority", 0.7))
        changefreq = node.get("sitemap_changefreq", "daily")

        if node_type == "static":
            if pattern:
                collected.append({
                    "loc": pattern,
                    "priority": priority,
                    "changefreq": changefreq,
                })
        elif node_type == "collection":
            if "{" not in pattern:
                collected.append({
                    "loc": pattern,
                    "priority": priority,
                    "changefreq": changefreq,
                })
        elif node_type == "detail":
            model_key = node.get("model_key")
            meta = _get_model_meta(model_key)
            if not meta:
                continue

            async with async_session() as db:
                model_cls = meta.model_cls
                stmt = select(model_cls).limit(50000)
                rows = (await db.execute(stmt)).scalars().all()
                for r in rows:
                    rec = r.to_dict() if hasattr(r, "to_dict") else {c.name: getattr(r, c.name, None) for c in model_cls.__table__.columns}

                    relations = {}
                    for f in meta.get_column_fields():
                        if f.foreign_key or f.name.endswith("_id"):
                            fk_val = rec.get(f.name)
                            if fk_val is None:
                                continue
                            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                            t_meta = _resolve_relation_meta(f)
                            if t_meta:
                                t_cls = t_meta.model_cls
                                r_row = (await db.execute(select(t_cls).where(t_cls.id == fk_val))).scalar_one_or_none()
                                if r_row:
                                    r_dict = r_row.to_dict() if hasattr(r_row, "to_dict") else {c.name: getattr(r_row, c.name, None) for c in t_cls.__table__.columns}
                                    relations[rel_name] = r_dict
                                    relations["parent"] = r_dict

                    loc = resolve_template(pattern, rec, relations)
                    if loc and "{" not in loc:
                        collected.append({
                            "loc": loc,
                            "priority": priority,
                            "changefreq": changefreq,
                            "lastmod": rec.get("updated_at") or rec.get("created_at"),
                        })

    return collected
