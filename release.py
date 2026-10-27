#!/usr/bin/env python3
"""
release.py — Инструмент автоматизации релизов PyFerro.

Возможности:
1. Прогон тестов (pytest) и сборка фронтенда (npm run build).
2. Бамп версии в pyproject.toml и __init__.py.
3. Проверка/генерация шаблона миграции БД при минорном релизе (x.Y.0).
4. Git коммит, тег и пуш в GitHub.
5. Сборка wheel/sdist (python -m build) и выгрузка на PyPI (twine upload).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"
INIT_PATH = ROOT_DIR / "src" / "pyferro2" / "__init__.py"
MIGRATIONS_DIR = ROOT_DIR / "src" / "pyferro2" / "migrations"


def run_cmd(cmd: list[str] | str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cwd = cwd or ROOT_DIR
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    print(f"  👉 [RUN] {cmd_str}")
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"❌ Ошибка выполнения команды: {cmd_str}\n")
        if res.stdout:
            print("--- STDOUT ---")
            print(res.stdout[-1500:])
        if res.stderr:
            print("--- STDERR ---")
            print(res.stderr[-1500:])
        sys.exit(res.returncode)
    return res


def get_current_version() -> str:
    if INIT_PATH.exists():
        content = INIT_PATH.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    if PYPROJECT_PATH.exists():
        content = PYPROJECT_PATH.read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return "2.0.0"


def update_version(new_version: str) -> None:
    print(f"\n📝 Обновление версии до {new_version}...")
    if INIT_PATH.exists():
        text = INIT_PATH.read_text(encoding="utf-8")
        new_text = re.sub(
            r'__version__\s*=\s*["\']([^"\']+)["\']',
            f'__version__ = "{new_version}"',
            text,
        )
        INIT_PATH.write_text(new_text, encoding="utf-8")
        print("  ✓ Обновлен __init__.py")

    if PYPROJECT_PATH.exists():
        text = PYPROJECT_PATH.read_text(encoding="utf-8")
        new_text = re.sub(
            r'(version\s*=\s*["\'])([^"\']+)(["\'])',
            rf'\g<1>{new_version}\g<3>',
            text,
            count=1,
        )
        PYPROJECT_PATH.write_text(new_text, encoding="utf-8")
        print("  ✓ Обновлен pyproject.toml")


def is_minor_release(version: str) -> bool:
    """Определяет, является ли релиз мажорным или минорным (требующим миграции)."""
    parts = version.split(".")
    if len(parts) >= 2:
        # e.g. 2.1.0 или 2.1
        patch = parts[2] if len(parts) > 2 else "0"
        return patch == "0"
    return False


def ensure_migration_for_release(version: str) -> None:
    """
    Правило проекта: новый минорный релиз (x.Y.0) обязательно требует миграции БД.
    Генерирует шаблон миграции, если он еще не создан.
    """
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    slug = version.replace(".", "_")
    migration_file = MIGRATIONS_DIR / f"migration_v{slug}.py"

    if not migration_file.exists():
        print(f"\n📦 [Правило проекта] Минорный релиз v{version} требует миграции БД.")
        template = f'''"""
Миграция схемы БД для PyFerro v{version}.
Сгенерировано автоматически релиз-скриптом.
"""

from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger("pyferro.migrations")


async def upgrade(session: AsyncSession) -> None:
    """
    Применяет изменения схемы или данных для версии {version}.
    """
    logger.info("Applying migration for v{version}...")
    # TODO: Добавьте DDL или миграционные SQL-запросы здесь
    await session.commit()


async def downgrade(session: AsyncSession) -> None:
    """
    Откат изменений схемы для версии {version}.
    """
    logger.info("Reverting migration for v{version}...")
    # TODO: Добавьте откат DDL запросов здесь
    await session.commit()
'''
        migration_file.write_text(template, encoding="utf-8")
        print(f"  ✨ Сгенерирован шаблон миграции: {migration_file.relative_to(ROOT_DIR)}")
    else:
        print(f"  ✓ Миграция {migration_file.name} уже существует.")

def build_help() -> None:
    generator = ROOT_DIR / "generate_help.py"
    if generator.exists():
        print("\n📚 Компиляция документации (generate_help.py)...")
        python_bin = ROOT_DIR / ".venv" / "bin" / "python"
        py = str(python_bin) if python_bin.exists() else sys.executable
        run_cmd([py, str(generator), "--frontend-dist"])
        print("  ✓ Документация успешно скомпилирована в help/help_data.json!")


def run_tests() -> None:
    print("\n🧪 Запуск тестов бэкенда (pytest)...")
    venv_pytest = ROOT_DIR / ".venv" / "bin" / "pytest"
    cmd = [str(venv_pytest) if venv_pytest.exists() else "pytest"]
    run_cmd(cmd)
    print("  ✓ Все тесты успешно пройдены!")


def build_frontend() -> None:
    frontend_dir = ROOT_DIR / "frontend"
    if (frontend_dir / "package.json").exists():
        npm_bin = shutil.which("npm")
        if not npm_bin:
            if (frontend_dir / "dist").exists():
                print("\n⚠️  npm не найден в PATH. Используется уже собранный frontend/dist.")
                return
            else:
                print("\n❌ npm не найден в системе и директория frontend/dist отсутствует!")
                sys.exit(1)
        print("\n🔨 Сборка фронтенда админки (npm run build)...")
        run_cmd([npm_bin, "run", "build"], cwd=frontend_dir)
        print("  ✓ Фронтенд успешно собран!")

    dist_src = ROOT_DIR / "frontend" / "dist"
    dist_dst = ROOT_DIR / "src" / "pyferro2" / "frontend" / "dist"
    if dist_src.exists():
        dist_dst.parent.mkdir(parents=True, exist_ok=True)
        if dist_dst.exists():
            shutil.rmtree(dist_dst)
        shutil.copytree(dist_src, dist_dst)
        print("  ✓ frontend/dist скопирован в src/pyferro2/frontend/dist для упаковки в PyPI")

def update_graphify() -> None:
    print("\n🕸️  Обновление графа знаний архитектуры (graphify)...")
    graphify_bin = ROOT_DIR / ".venv" / "bin" / "graphify"
    if graphify_bin.exists():
        cmd = [str(graphify_bin), "update", ".", "--force"]
    elif shutil.which("graphify"):
        cmd = ["graphify", "update", ".", "--force"]
    else:
        python_bin = ROOT_DIR / ".venv" / "bin" / "python"
        py = str(python_bin) if python_bin.exists() else sys.executable
        cmd = [py, "-m", "graphify", "update", ".", "--force"]

    res = run_cmd(cmd, check=False)
    if res.returncode == 0:
        print("  ✓ Граф знаний graphify успешно актуализирован!")
    else:
        print("  ⚠️ Не удалось обновить graphify (пропущено).")



def git_commit_and_push(version: str | None, message: str, dry_run: bool = False) -> None:
    print("\n🐙 Выполнение Git-операций...")
    run_cmd(["git", "add", "."])

    # Проверка наличия изменений
    status = run_cmd(["git", "status", "--porcelain"])
    if not status.stdout.strip() and not version:
        print("  ℹ️ Нет изменений для коммита.")
        return

    commit_title = f"release: v{version} - {message}" if version else message
    if status.stdout.strip():
        run_cmd(["git", "commit", "-m", commit_title])
        print(f"  ✓ Коммит создан: {commit_title}")
    else:
        print("  ℹ️ Рабочая директория чиста.")

    tag_name = f"v{version}" if version else None
    if tag_name:
        # Проверяем, существует ли уже такой тег
        existing_tags = run_cmd(["git", "tag", "-l", tag_name]).stdout.strip()
        if existing_tags:
            print(f"  ⚠️ Тег {tag_name} уже существует.")
        else:
            run_cmd(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}: {message}"])
            print(f"  ✓ Создан тег {tag_name}")

    if dry_run:
        print("  🔍 [DRY-RUN] Пропуск git push.")
        return

    print("  🚀 Отправка в GitHub (origin main)...")
    push_cmd = ["git", "push", "origin", "main"]
    if tag_name:
        push_cmd.append("--tags")
    run_cmd(push_cmd)
    print("  ✓ Успешно отправлено в GitHub!")


def build_and_upload_pypi(dry_run: bool = False) -> None:
    print("\n📦 Сборка и публикация пакета в PyPI...")
    dist_dir = ROOT_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    python_bin = ROOT_DIR / ".venv" / "bin" / "python"
    py = str(python_bin) if python_bin.exists() else sys.executable

    # Build
    run_cmd([py, "-m", "build"])
    print("  ✓ Пакет успешно собран в dist/")

    # Twine check
    run_cmd([py, "-m", "twine", "check", "dist/*"])
    print("  ✓ Проверка twine check пройдена!")

    if dry_run:
        print("  🔍 [DRY-RUN] Пропуск twine upload в PyPI.")
        return

    # Twine upload
    print("  🚀 Загрузка дистрибутива на PyPI...")
    run_cmd([py, "-m", "twine", "upload", "dist/*"])
    print("  🎉 Релиз успешно опубликован на PyPI!")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="release",
        description="🚀 Инструмент автоматизации Git-коммитов и релизов PyFerro на GitHub и PyPI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # 1. Быстрый коммит и пуш в GitHub с авто-прогоном тестов:
  python release.py -m "Поправил авторизацию в админке"

  # 2. Полный релиз версии (Git + GitHub Tag + PyPI):
  python release.py 2.0.0 -m "Релиз PyFerro 2.0 на Granian RSGI"

  # 3. Минорный релиз с автогенерацией миграции БД:
  python release.py 2.1.0 -m "Новый функционал потокового RPC"

  # 4. Проверка без отправки на серверы (--dry-run):
  python release.py 2.0.0 -m "Тестовый прогон" --dry-run
        """,
    )

    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="Номер версии релиза (например, 2.0.0 или 2.1.0). Если не указан — выполняется обычный git commit & push.",
    )
    parser.add_argument(
        "-m",
        "--message",
        required=True,
        help="Сообщение коммита / описание релиза (обязательный аргумент).",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Пропустить запуск тестов pytest перед релизом.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Пропустить сборку фронтенда npm run build.",
    )
    parser.add_argument(
        "--skip-graphify",
        action="store_true",
        help="Пропустить обновление графа знаний graphify.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Выполнить проверки и сборку, но не пушить в GitHub и не публиковать в PyPI.",
    )

    args = parser.parse_args()

    current_ver = get_current_version()
    print("=" * 65)
    print(" 🛡️  PyFerro 2.0 Release Automation Tool")
    print(f" 📌 Текущая версия: {current_ver}")
    if args.version:
        print(f" 🎯 Целевая версия: {args.version}")
    print(f" 💬 Сообщение:      {args.message}")
    if args.dry_run:
        print(" ⚠️  РЕЖИМ:          DRY-RUN (без публикации)")
    print("=" * 65)
    # 0. Сборка документации
    build_help()

    # 1. Тесты
    if not args.skip_tests:
        run_tests()

    # 2. Сборка фронтенда
    if not args.skip_build:
        build_frontend()

    # 3. Обновление графа знаний архитектуры (graphify)
    if not args.skip_graphify:
        update_graphify()

    # 4. Версионирование и миграции
    if args.version:
        if is_minor_release(args.version):
            ensure_migration_for_release(args.version)
        update_version(args.version)

    # 4. Git коммит и пуш
    git_commit_and_push(args.version, args.message, dry_run=args.dry_run)

    # 5. Публикация в PyPI (только если указана версия)
    if args.version:
        build_and_upload_pypi(dry_run=args.dry_run)

    print("\n" + "=" * 65)
    if args.version:
        print(f" 🎉 Релиз v{args.version} успешно завершен!")
    else:
        print(" ✅ Изменения успешно отправлены в репозиторий!")
    print("=" * 65)


if __name__ == "__main__":
    main()
