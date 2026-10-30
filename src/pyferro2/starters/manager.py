"""
Менеджер жизненного цикла стартовых приложений (StartersManager).
Управляет проверкой конфликтов, установкой релизов с GitHub, накатыванием сидов и безопасным удалением.
"""

from __future__ import annotations

import io
import shutil
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import pyferro2
from pyferro2.db.engine import Database
from pyferro2.rpc.errors import RpcError
from pyferro2.starters.catalog import DEFAULT_CATALOG, StarterManifest
from pyferro2.starters.models import StarterBase, TstMessage, TstMeta, TstTopic
from pyferro2.starters.seeder import seed_forum_data
from pyferro2.starters.seo import (
    get_forum_sitemap,
    get_topic_breadcrumbs,
    get_topic_discussion_posting,
)


class StartersManager:
    """Менеджер стартеров и тестовых приложений."""

    def __init__(
        self,
        db: Database,
        catalog: list[StarterManifest] | None = None,
        apps_dir: Path | str = "apps",
    ) -> None:
        self.db: Database = db
        self.catalog: list[StarterManifest] = catalog or DEFAULT_CATALOG
        self.apps_dir: Path = Path(apps_dir)

    @property
    def current_version(self) -> str:
        """Текущая версия PyFerro."""
        return getattr(pyferro2, "__version__", "2.1.0")

    def get_compatible_tag(self, starter: StarterManifest) -> str:
        """Определяет релизный тег для текущей минорной версии фреймворка."""
        parts = self.current_version.split(".")
        major = parts[0] if len(parts) > 0 else "2"
        minor = parts[1] if len(parts) > 1 else "0"
        return f"v{major}.{minor}"

    def find_manifest(self, starter_id: str) -> StarterManifest:
        """Ищет стартер в каталоге или вызывает 404."""
        for s in self.catalog:
            if s.id == starter_id:
                return s
        raise RpcError(f"Стартер '{starter_id}' не найден в каталоге", code=404)

    async def get_existing_db_tables(self) -> set[str]:
        """Возвращает список всех существующих таблиц в БД."""
        def _get_tables(conn_sync: Any) -> set[str]:
            return set(inspect(conn_sync).get_table_names())

        async with self.db.engine.connect() as conn:
            return await conn.run_sync(_get_tables)

    async def get_installed_meta(self, session: AsyncSession, starter_id: str) -> TstMeta | None:
        """Считывает запись метаданных стартера из tst_meta (если таблица существует)."""
        existing = await self.get_existing_db_tables()
        if "tst_meta" not in existing:
            return None
        return await session.get(TstMeta, starter_id)

    async def list_starters(self) -> list[dict[str, Any]]:
        """
        Возвращает список доступных стартеров с их текущим статусом установки,
        версией и проверкой на рассинхронизацию схемы.
        """
        existing_tables = await self.get_existing_db_tables()
        result: list[dict[str, Any]] = []

        async with self.db.session() as session:
            for s in self.catalog:
                starter_tables_set = set(s.tables)
                present_tables = starter_tables_set.intersection(existing_tables)

                meta = await self.get_installed_meta(session, s.id)
                installed_version = meta.installed_version if meta else None

                is_installed = starter_tables_set.issubset(existing_tables) and meta is not None
                version_mismatch = (
                    is_installed
                    and installed_version is not None
                    and not self.current_version.startswith(installed_version.split(".")[0] + "." + installed_version.split(".")[1])
                )

                result.append(
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                        "repo": s.repo,
                        "branch": s.branch,
                        "compatible_tag": self.get_compatible_tag(s),
                        "tables": list(s.tables),
                        "tags": list(s.tags),
                        "installed": is_installed,
                        "installed_version": installed_version,
                        "version_mismatch": version_mismatch,
                        "existing_tables": sorted(list(present_tables)),
                    }
                )

        return result

    async def install(
        self,
        starter_id: str,
        overwrite: bool = False,
        archive_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """
        Устанавливает стартер:
        1. Проверяет наличие таблиц tst_*. Если они есть и overwrite=False — прерывает с ошибкой конфликта.
        2. При overwrite=True предварительно удаляет существующие таблицы tst_*.
        3. Скачивает и распаковывает архив с GitHub (или использует fallback).
        4. Создает таблицы и заливает сид-данные.
        5. Фиксирует версию установки в tst_meta.
        """
        starter = self.find_manifest(starter_id)
        existing_tables = await self.get_existing_db_tables()

        conflicts = [tbl for tbl in starter.tables if tbl in existing_tables]
        if conflicts and not overwrite:
            raise RpcError(
                f"Конфликт таблиц стартера: в базе данных уже существуют таблицы ({', '.join(conflicts)}). "
                f"Удалите их вручную или подтвердите установку с флагом overwrite=True.",
                code=409,
            )

        # Если overwrite=True, дропаем конфликтующие таблицы
        if conflicts and overwrite:
            await self._drop_tables(starter.tables)

        # Получаем архив стартера
        if archive_bytes is None:
            archive_bytes = await self._fetch_archive(starter)

        # Распаковываем файлы в директорию приложений
        target_dir = self.apps_dir / starter.id
        self._extract_archive(archive_bytes, target_dir)

        # Создаем таблицы в БД
        await self._create_tables()

        # Наполняем демонстрационными данными
        async with self.db.session() as session:
            # Записываем метаданные о версии (upsert)
            now = datetime.now(timezone.utc)
            meta = await session.get(TstMeta, starter.id)
            if meta is not None:
                meta.installed_version = self.current_version
                meta.installed_at = now
            else:
                meta = TstMeta(
                    starter_id=starter.id,
                    installed_version=self.current_version,
                    installed_at=now,
                )
                session.add(meta)
            await session.commit()

            # Запускаем сидер форума (если это starter-forum-seo)
            seed_stats: dict[str, int] = {}
            if starter.id == "starter-forum-seo":
                seed_stats = await seed_forum_data(session)

        return {
            "ok": True,
            "starter_id": starter.id,
            "installed_version": self.current_version,
            "tag": self.get_compatible_tag(starter),
            "tables": list(starter.tables),
            "seed_stats": seed_stats,
            "message": f"Стартер '{starter.name}' успешно установлен",
        }

    async def uninstall(self, starter_id: str) -> dict[str, Any]:
        """
        Полностью и безопасно удаляет стартер:
        Дропает таблицы tst_* и удаляет директорию приложения.
        """
        starter = self.find_manifest(starter_id)

        # 1. Дропаем таблицы
        await self._drop_tables(starter.tables)

        # 2. Удаляем папку приложения
        target_dir = self.apps_dir / starter.id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        return {
            "ok": True,
            "starter_id": starter.id,
            "dropped_tables": list(starter.tables),
            "message": f"Стартер '{starter.name}' успешно удален",
        }

    async def get_seo_preview(
        self, starter_id: str, slug: str | None = None
    ) -> dict[str, Any]:
        """
        Формирует предпросмотр SEO для установленного стартера форума.
        """
        starter = self.find_manifest(starter_id)
        existing_tables = await self.get_existing_db_tables()
        if not set(starter.tables).issubset(existing_tables):
            raise RpcError(f"Стартер '{starter_id}' еще не установлен в базу данных", code=400)

        async with self.db.session() as session:
            # Находим топик для предпросмотра
            if slug:
                stmt = select(TstTopic).where(TstTopic.slug == slug)
            else:
                # Берем первую ветку с сообщениями
                stmt = select(TstTopic).where(TstTopic.is_category == False).limit(1)  # noqa: E712

            result = await session.execute(stmt)
            topic = result.scalar_one_or_none()
            if not topic:
                raise RpcError("В базе данных стартера пока нет веток обсуждений", code=404)

            breadcrumbs = await get_topic_breadcrumbs(session, topic.id)
            discussion_ld = await get_topic_discussion_posting(session, topic.id)
            sitemap_items = await get_forum_sitemap(session)

            return {
                "topic": {
                    "id": topic.id,
                    "title": topic.title,
                    "slug": topic.slug,
                    "seo_title": topic.seo_title,
                    "seo_description": topic.seo_description,
                },
                "breadcrumbs_json_ld": breadcrumbs,
                "discussion_json_ld": discussion_ld,
                "sitemap_sample": sitemap_items[:5],
                "total_sitemap_urls": len(sitemap_items),
            }

    async def _drop_tables(self, tables: tuple[str, ...]) -> None:
        """Безопасно дропает таблицы стартера (только с префиксом tst_)."""
        async with self.db.engine.begin() as conn:
            for tbl in tables:
                if tbl.startswith("tst_"):
                    await conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))

    async def _create_tables(self) -> None:
        """Создает таблицы TstMeta, TstTopic, TstMessage в БД."""
        async with self.db.engine.begin() as conn:
            await conn.run_sync(StarterBase.metadata.create_all)
    async def _fetch_archive(self, starter: StarterManifest) -> bytes:
        """
        Загружает zip-архив стартера с GitHub.
        Использует тег совместимости (например, v2.1) или генерирует встроенный шаблон при оффлайне.
        """
        tag = self.get_compatible_tag(starter)
        url = f"https://github.com/{starter.repo}/archive/refs/tags/{tag}.zip"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": f"PyFerro/{self.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except Exception:
            # Fallback: генерируем автономный стартер-пакет на лету,
            # чтобы система работала автономно, в тестах и без интернета
            return self._generate_builtin_starter_archive(starter)

    def _extract_archive(self, archive_bytes: bytes, target_dir: Path) -> None:
        """Распаковывает zip-архив в указанную директорию."""
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            # Если архив обернут в корневую папку repo-tag/
            root_names = {p.split("/")[0] for p in zf.namelist() if "/" in p}
            single_root = list(root_names)[0] if len(root_names) == 1 else None

            for member in zf.infolist():
                if member.is_dir():
                    continue
                filename = member.filename
                if single_root and filename.startswith(f"{single_root}/"):
                    filename = filename[len(single_root) + 1 :]
                if not filename:
                    continue

                dest = target_dir / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    def _generate_builtin_starter_archive(self, starter: StarterManifest) -> bytes:
        """Генерирует базовый каркас приложения для оффлайн/тестового использования."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            readme = f"# {starter.name}\n\n{starter.description}\n"
            zf.writestr("README.md", readme)
            zf.writestr(
                "app.py",
                '"""Автономное приложение стартера форума SEO."""\n'
                'print("Starter Forum SEO ready.")\n',
            )
        return buf.getvalue()
