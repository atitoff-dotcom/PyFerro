# -*- coding: utf-8 -*-
"""
pyferro.plugins.seo.dynamic_rules: Движок No-Code динамических SEO-правил для моделей.
Позволяет связывать таблицы БД (товары, статьи, форумы) с шаблонами URL,
метатегами, хлебными крошками и Schema.org разметкой без написания кода.
"""

import re
import html
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import select

from pyferro.core.logger import logger
from pyferro.db import async_session
from pyferro.plugins.crud import ModelRegistry
from .schemas import SeoPageData
from .renderer import HtmlBuilder

PARAM_RE = re.compile(r"\{([a-zA-Z0-9_.]+)(?::([a-zA-Z_]+))?\}")


def resolve_template(template: str, record: Dict[str, Any], relations: Dict[str, Dict[str, Any]]) -> str:
    """
    Подставляет значения колонок и связей по внешним ключам в шаблон строки.
    Поддерживает:
      {title} -> record['title']
      {category.name} -> relations['category']['name']
      {category.slug} -> relations['category']['slug']
    """
    if not template:
        return ""

    def replace_match(m):
        full_key = m.group(1)
        if "." in full_key:
            rel_name, field_name = full_key.split(".", 1)
            rel_obj = relations.get(rel_name)
            if isinstance(rel_obj, dict):
                val = rel_obj.get(field_name)
                return str(val) if val is not None else ""
            return ""
        else:
            val = record.get(full_key)
            return str(val) if val is not None else ""

    return PARAM_RE.sub(replace_match, template)


def get_model_schema_for_seo(model_key: str) -> Dict[str, Any]:
    """
    Возвращает схему полей и связей модели для отображения подсказок/чипсов в GUI админки.
    """
    meta = ModelRegistry.get(model_key)
    if not meta:
        return {"fields": [], "relations": []}

    fields = []
    for f in meta.get_column_fields():
        fields.append({
            "name": f.name,
            "type": f.type,
            "label": f.label or f.name,
            "primary_key": f.primary_key,
        })

    relations = []
    for f in meta.get_column_fields():
        if f.foreign_key or f.name.endswith("_id"):
            target_key = f.target_model
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            target_meta = ModelRegistry.get(target_key) if target_key else None

            # Если target_meta не найдена по имени, пробуем найти по имени таблицы внешнего ключа
            if not target_meta and f.foreign_key and isinstance(f.foreign_key, dict):
                target_table = f.foreign_key.get("target_table")
                if target_table:
                    target_meta = ModelRegistry.get(target_table)

            rel_fields = []
            if target_meta:
                for tf in target_meta.get_column_fields():
                    rel_fields.append({
                        "name": tf.name,
                        "chip": f"{rel_name}.{tf.name}",
                        "label": f"{target_meta.verbose_name or rel_name}: {tf.label or tf.name}",
                        "type": tf.type,
                    })

            relations.append({
                "relation_name": rel_name,
                "fk_field": f.name,
                "target_model": target_meta.verbose_name if target_meta else (target_key or rel_name),
                "fields": rel_fields,
            })

    return {
        "key": meta.key,
        "table_name": meta.table_name,
        "verbose_name": meta.verbose_name or meta.key,
        "fields": fields,
        "relations": relations,
    }


async def preview_model_rule(model_key: str, rule: Dict[str, Any], sample_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Генерирует живое превью метаданных для симулятора в админке.
    Если sample_id передан, берет реальную запись из БД, иначе первую доступную или мок-данные.
    """
    meta = ModelRegistry.get(model_key)
    record: Dict[str, Any] = {}
    relations: Dict[str, Dict[str, Any]] = {}

    if meta:
        async with async_session() as db:
            try:
                model_cls = meta.model_cls
                stmt = select(model_cls)
                if sample_id is not None:
                    # Ищем по первичному ключу
                    pk_col = getattr(model_cls, "id", None)
                    if pk_col is not None:
                        stmt = stmt.where(pk_col == sample_id)
                stmt = stmt.limit(1)
                res = (await db.execute(stmt)).scalars().first()
                if res:
                    if hasattr(res, "to_dict"):
                        record = res.to_dict()
                    else:
                        record = {col.name: getattr(res, col.name, None) for col in meta.model_cls.__table__.columns}

                    # Подгружаем связанные записи по FK
                    for f in meta.get_column_fields():
                        if f.foreign_key or f.name.endswith("_id"):
                            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                            target_meta = ModelRegistry.get(f.target_model) if f.target_model else None
                            if not target_meta and f.foreign_key and isinstance(f.foreign_key, dict):
                                target_meta = ModelRegistry.get(f.foreign_key.get("target_table"))
                            if target_meta:
                                fk_val = record.get(f.name)
                                if fk_val is not None:
                                    target_cls = target_meta.model_cls
                                    target_pk = getattr(target_cls, "id", None)
                                    if target_pk is not None:
                                        t_stmt = select(target_cls).where(target_pk == fk_val).limit(1)
                                        t_res = (await db.execute(t_stmt)).scalars().first()
                                        if t_res:
                                            relations[rel_name] = (
                                                t_res.to_dict()
                                                if hasattr(t_res, "to_dict")
                                                else {c.name: getattr(t_res, c.name, None) for c in target_cls.__table__.columns}
                                            )
            except Exception as e:
                logger.warning(f"[SEO Preview] Ошибка загрузки записи {model_key}: {e}")

    # Если в базе нет записей, подставляем говорящие демонстрационные мок-данные
    if not record:
        record = {
            "id": 42,
            "title": "Как устроен WSRPC в PyFerro по сравнению со стандартным REST?",
            "name": "Флагманский смартфон Pro Edition 256GB",
            "slug": "wsrpc-vs-rest-comparison",
            "author_name": "Алексей Смирнов",
            "price": "89 990",
            "views_count": 328,
            "replies_count": 12,
            "description": "Подробный разбор архитектуры и замера задержек при передаче данных через постоянное WebSocket-соединение.",
            "first_post_text": "В отличие от классического REST, WSRPC исключает постоянный TCP/TLS handshake оверхед.",
            "content": "Полный текст статьи с примерами кода и графиками производительности.",
            "created_at": "2026-10-22",
            "image_url": "https://picsum.photos/seed/pyferro/1200/630",
        }
        relations = {
            "category": {
                "id": 1,
                "name": "Архитектура и WebSockets",
                "slug": "architecture",
                "description": "Раздел обсуждения архитектурных паттернов",
            }
        }

    # Резолвим поля
    resolved_url = resolve_template(rule.get("url_pattern", "/{slug}"), record, relations)
    resolved_title = resolve_template(rule.get("title_template", "{title}"), record, relations)
    resolved_description = resolve_template(rule.get("description_template", "{description}"), record, relations)
    resolved_og_image = resolve_template(rule.get("og_image_template", ""), record, relations) or "https://picsum.photos/seed/pyferro/1200/630"

    # Резолвим цепочку хлебных крошек
    raw_breadcrumbs = rule.get("breadcrumbs") or [
        {"title": "Главная", "url": "/"},
        {"title": "{category.name}", "url": "/forum/{category.slug}"},
        {"title": "{title}", "url": ""},
    ]

    breadcrumbs = []
    for b in raw_breadcrumbs:
        b_title = resolve_template(b.get("title", ""), record, relations)
        b_url = resolve_template(b.get("url", ""), record, relations)
        if b_title:
            breadcrumbs.append({"title": b_title, "url": b_url})

    schema_type = rule.get("schema_type", "WebPage")
    author_val = record.get("author_name") or record.get("author") or "Автор"

    # Формируем Schema.org JSON-LD
    schema_data: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": resolved_title,
        "description": resolved_description,
    }

    if schema_type == "DiscussionForumPosting":
        schema_data.update({
            "headline": resolved_title,
            "articleBody": resolved_description,
            "author": {"@type": "Person", "name": author_val},
            "interactionStatistic": {
                "@type": "InteractionCounter",
                "interactionType": "https://schema.org/ReplyAction",
                "userInteractionCount": record.get("replies_count", 0),
            },
        })
    elif schema_type == "Product":
        price_val = str(record.get("price", "999")).replace(" ", "")
        schema_data.update({
            "image": resolved_og_image,
            "offers": {
                "@type": "Offer",
                "price": price_val,
                "priceCurrency": "RUB",
                "availability": "https://schema.org/InStock",
            },
        })
    elif schema_type == "Article":
        schema_data.update({
            "headline": resolved_title,
            "author": {"@type": "Person", "name": author_val},
            "image": resolved_og_image,
        })

    # Семантический HTML для роботов
    html_b = HtmlBuilder()
    html_b.h1(resolved_title)
    if author_val:
        html_b.p(f"Автор: {author_val}")
    if resolved_description:
        html_b.p(resolved_description)
    if resolved_og_image:
        html_b.img(resolved_og_image, alt=resolved_title)

    return {
        "url": resolved_url,
        "title": resolved_title,
        "description": resolved_description,
        "og_image": resolved_og_image,
        "schema_type": schema_type,
        "schema_data": schema_data,
        "breadcrumbs": breadcrumbs,
        "body_html": html_b.to_html(),
        "record_id": record.get("id"),
    }


def compile_pattern_to_regex(pattern: str) -> Tuple[Any, List[str]]:
    """Компилирует URL шаблон вида /forum/{category_slug}/{slug} в regex."""
    keys: List[str] = []
    regex_pattern = "^"
    last_idx = 0

    for match in PARAM_RE.finditer(pattern):
        start, end = match.span()
        regex_pattern += re.escape(pattern[last_idx:start])
        full_key = match.group(1)
        # На случай если ключ содержит точку {category.slug}
        clean_key = full_key.replace(".", "__")
        keys.append((full_key, clean_key))
        regex_pattern += f"(?P<{clean_key}>[^/]+)"
        last_idx = end

    regex_pattern += re.escape(pattern[last_idx:]) + "$"
    return re.compile(regex_pattern), keys


async def match_and_render_model_rule(path: str, model_rules: List[Dict[str, Any]]) -> Optional[SeoPageData]:
    """
    Проверяет, соответствует ли запрошенный ботом путь одному из динамических правил моделей.
    Если да — извлекает запись из БД и возвращает SeoPageData.
    """
    for rule in model_rules:
        pattern = rule.get("url_pattern")
        if not pattern:
            continue

        compiled, keys = compile_pattern_to_regex(pattern)
        m = compiled.match(path)
        if not m:
            continue

        extracted_params = m.groupdict()
        model_key = rule.get("model_key")
        meta = ModelRegistry.get(model_key)
        if not meta:
            continue

        # Формируем запрос к БД
        model_cls = meta.model_cls
        async with async_session() as db:
            try:
                stmt = select(model_cls)
                for full_key, clean_key in keys:
                    val = extracted_params.get(clean_key)
                    if "." in full_key:
                        # Фильтр по связанной таблице
                        rel_name, field_name = full_key.split(".", 1)
                        # Ищем FK поле
                        fk_field = getattr(model_cls, f"{rel_name}_id", None)
                        if fk_field is not None:
                            # Получаем модель связи
                            for f in meta.get_column_fields():
                                if f.name == f"{rel_name}_id" and f.target_model:
                                    t_meta = ModelRegistry.get(f.target_model)
                                    if t_meta:
                                        t_cls = t_meta.model_cls
                                        col = getattr(t_cls, field_name, None)
                                        if col is not None:
                                            stmt = stmt.join(t_cls).where(col == val)
                    else:
                        col = getattr(model_cls, full_key, None)
                        if col is not None:
                            stmt = stmt.where(col == val)

                stmt = stmt.limit(1)
                res = (await db.execute(stmt)).scalars().first()
                if not res:
                    return None

                # Генерируем превью по найденному объекту
                item_id = getattr(res, "id", None)
                preview = await preview_model_rule(model_key, rule, sample_id=item_id)

                bc_tuples = [(b["title"], b["url"]) for b in preview.get("breadcrumbs", [])]

                return SeoPageData(
                    title=preview["title"],
                    description=preview["description"],
                    canonical_url=preview["url"],
                    og_image=preview["og_image"],
                    og_type="article" if rule.get("schema_type") in ("Article", "DiscussionForumPosting") else "website",
                    schema_type=preview["schema_type"],
                    schema_data=preview["schema_data"],
                    body_html=preview["body_html"],
                    breadcrumbs=bc_tuples,
                )
            except Exception as e:
                logger.error(f"[Dynamic SEO] Ошибка выборки для {path}: {e}", exc_info=True)
                return None

    return None