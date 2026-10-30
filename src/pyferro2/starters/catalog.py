"""
Реестр и манифесты стартовых приложений (Starter Apps).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StarterManifest:
    """Манифест описания стартового приложения."""

    id: str
    name: str
    description: str
    repo: str
    branch: str = "main"
    tables: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    min_pyferro_version: str = "2.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Базовый каталог проверенных стартеров
DEFAULT_CATALOG: list[StarterManifest] = [
    StarterManifest(
        id="starter-forum-seo",
        name="SEO Tree Forum",
        description="Древовидный форум на 2-х таблицах (tst_topics, tst_messages): эталонная микроразметка Schema.org (BreadcrumbList, DiscussionForumPosting), ЧПУ-слаги и sitemap.xml с dynamic lastmod.",
        repo="pyferro/starter-forum-seo",
        branch="main",
        tables=("tst_topics", "tst_messages", "tst_meta"),
        tags=("seo", "forum", "tree", "json-ld", "sitemap"),
        min_pyferro_version="2.0.0",
    ),
]
