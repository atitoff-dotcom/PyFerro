"""
Модели данных и структуры памяти для подсистемы SEO и Dynamic Rendering в PyFerro 2.0 (`pyferro2/seo/models.py`).

Хранит конфигурацию и «Живое дерево сайта» (Site Tree) непосредственно в базе данных (`pf_seo_config`)
с горячим кэшем в оперативной памяти (`SeoRuntimeState`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.db.base import Base


class SeoConfigRecord(Base):
    """
    Таблица конфигурации SEO и структуры дерева сайта (`pf_seo_config`).
    Хранит единственную запись (`id = 1`) как единый источник правды.
    """

    __tablename__ = "pf_seo_config"

    site_url: Mapped[str] = mapped_column(
        String(255), default="http://localhost:8080", server_default="http://localhost:8080", nullable=False
    )
    site_name: Mapped[str] = mapped_column(
        String(255), default="PyFerro 2.0 Application", server_default="PyFerro 2.0 Application", nullable=False
    )
    default_title: Mapped[str] = mapped_column(
        String(255), default="PyFerro 2.0 Application", server_default="PyFerro 2.0 Application", nullable=False
    )
    default_description: Mapped[str] = mapped_column(
        Text,
        default="Современное реактивное веб-приложение на базе PyFerro 2.0",
        server_default="Современное реактивное веб-приложение на базе PyFerro 2.0",
        nullable=False,
    )
    default_og_image: Mapped[str] = mapped_column(
        String(512), default="", server_default="", nullable=False
    )
    default_lang: Mapped[str] = mapped_column(
        String(16), default="ru", server_default="ru", nullable=False
    )
    indexnow_key: Mapped[str] = mapped_column(
        String(128), default="", server_default="", nullable=False
    )
    sitemap_ttl: Mapped[int] = mapped_column(
        Integer, default=3600, server_default="3600", nullable=False
    )
    tree_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default="{}", nullable=False
    )


@dataclass(slots=True)
class SeoConfig:
    """Актуальное состояние конфигурации SEO в оперативной памяти."""

    site_url: str = "http://localhost:8080"
    site_name: str = "PyFerro 2.0 Application"
    default_title: str = "PyFerro 2.0 Application"
    default_description: str = "Современное реактивное веб-приложение на базе PyFerro 2.0"
    default_og_image: str | None = None
    default_lang: str = "ru"
    indexnow_key: str | None = None
    sitemap_ttl: int = 3600
    enable_sitemap: bool = True
    sitemap_max_urls_per_file: int = 50_000
    extra_bot_patterns: list[str] = field(default_factory=list)
    custom_detector: Callable[[Any], bool | None] | None = None
    indexnow_queue_file: str | None = None
    indexnow_flush_interval: int = 1800
    indexnow_max_queue_size: int = 1000


@dataclass(slots=True)
class SeoPageData:
    """
    Структура данных для рендеринга семантической HTML-страницы поисковым ботам,
    социальным сетям (OpenGraph / Twitter Cards) и ИИ-индексаторам (JSON-LD).
    """

    title: str
    description: str = ""
    canonical_url: str | None = None
    og_image: str | None = None
    og_type: str = "website"              # "website", "article", "profile", etc.
    schema_type: str = "WebPage"          # "Article", "DiscussionForumPosting", "Product", etc.
    schema_data: dict[str, Any] | None = None
    body_html: str = ""                   # Основной семантический контент (h1, p, article, nav)
    lang: str = "ru"
    published_time: datetime | None = None
    modified_time: datetime | None = None
    author: str | None = None
    breadcrumbs: list[tuple[str, str]] | None = None  # [("Главная", "/"), ("Статьи", "/articles")]
    robots: str = "index, follow"


_CURRENT_SEO_CONFIG: SeoConfig = SeoConfig()


def get_seo_config() -> SeoConfig:
    """Возвращает текущую in-memory конфигурацию SEO."""
    return _CURRENT_SEO_CONFIG


def configure_seo(
    *,
    site_url: str | None = None,
    site_name: str | None = None,
    default_title: str | None = None,
    default_description: str | None = None,
    default_og_image: str | None = None,
    default_lang: str | None = None,
    indexnow_key: str | None = None,
    sitemap_ttl: int | None = None,
    enable_sitemap: bool | None = None,
    sitemap_max_urls_per_file: int | None = None,
    extra_bot_patterns: list[str] | None = None,
    custom_detector: Callable[[Any], bool | None] | None = None,
    indexnow_queue_file: str | None = ...,  # type: ignore[assignment]
    indexnow_flush_interval: int | None = None,
    indexnow_max_queue_size: int | None = None,
) -> SeoConfig:
    """Программная настройка SEO-конфигурации в памяти."""
    cfg = _CURRENT_SEO_CONFIG
    if site_url is not None:
        cfg.site_url = site_url.rstrip("/")
    if site_name is not None:
        cfg.site_name = site_name
    if default_title is not None:
        cfg.default_title = default_title
    if default_description is not None:
        cfg.default_description = default_description
    if default_og_image is not None:
        cfg.default_og_image = default_og_image or None
    if default_lang is not None:
        cfg.default_lang = default_lang
    if indexnow_key is not None:
        cfg.indexnow_key = indexnow_key or None
    if sitemap_ttl is not None:
        cfg.sitemap_ttl = int(sitemap_ttl)
    if enable_sitemap is not None:
        cfg.enable_sitemap = bool(enable_sitemap)
    if sitemap_max_urls_per_file is not None:
        cfg.sitemap_max_urls_per_file = int(sitemap_max_urls_per_file)
    if extra_bot_patterns is not None:
        cfg.extra_bot_patterns = list(extra_bot_patterns)
    if custom_detector is not None:
        cfg.custom_detector = custom_detector
    if indexnow_queue_file is not ...:
        cfg.indexnow_queue_file = indexnow_queue_file
    if indexnow_flush_interval is not None:
        cfg.indexnow_flush_interval = int(indexnow_flush_interval)
    if indexnow_max_queue_size is not None:
        cfg.indexnow_max_queue_size = int(indexnow_max_queue_size)
    return cfg
