# -*- coding: utf-8 -*-
"""
CLI-утилита администрирования pyferro.
Позволяет создавать первого администратора системы:
    python -m pyferro createsuperuser
"""

from __future__ import annotations
import asyncio
import argparse
import sys
import getpass
from sqlalchemy import select

from pyferro.core.constants import ADMIN_ROLE, GUEST_ROLE, ADM_HELP_ROLE, SEO_ROLE
from pyferro.db import system_db_session, Base, engine
from pyferro.auth.models import User, Role
from pyferro.auth.discovery import sync_rpc_permissions


async def ensure_system_roles_exist(db) -> tuple[None, Role, None, None]:
    """Гарантирует наличие обязательной встроенной роли guest."""
    stmt_roles = select(Role).where(Role.name == GUEST_ROLE)
    guest_role = (await db.execute(stmt_roles)).scalar_one_or_none()
    if not guest_role:
        guest_role = Role(name=GUEST_ROLE, description="Гость / Неавторизованный посетитель")
        db.add(guest_role)
        await db.commit()
        await db.refresh(guest_role)
    return None, guest_role, None, None


async def async_create_superuser(username: str, password: str, email: str = None) -> None:
    """Асинхронно создает пользователя с правами суперадминистратора."""
    # Гарантируем создание таблиц
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with system_db_session() as db:
        stmt_user = select(User).where(User.login == username)
        user = (await db.execute(stmt_user)).scalar_one_or_none()

        pwd_hash = User._hash_password(password)
        if user:
            user.password_hash = pwd_hash
            user.is_superadmin = True
            if email:
                user.email = email
            print(f"[OK] Пользователь '{username}' обновлен и наделен правами суперадминистратора (is_superadmin=True).")
        else:
            user = User(
                login=username,
                name=username,
                email=email,
                password_hash=pwd_hash,
                is_superadmin=True,
            )
            db.add(user)
            print(f"[OK] Суперадминистратор '{username}' успешно создан.")

        await db.commit()

    # Синхронизируем базовые роли и RPC
    await sync_rpc_permissions()


async def async_set_password(login: str = "admin", password: str = None) -> str:
    """Обновляет пароль пользователя в существующей БД и наделяет правами суперадминистратора."""
    import secrets
    import string
    if not password:
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(secrets.choice(chars) for _ in range(16))
    async with system_db_session() as db:
        stmt = select(User).where(User.login == login)
        user = (await db.execute(stmt)).scalar_one_or_none()
        if not user:
            raise ValueError(
                f"Пользователь с логином '{login}' не найден в базе данных. "
                "Схема данных и пользователи должны быть предварительно инициализированы приложением."
            )

        user.is_superadmin = True
        user.password_hash = User._hash_password(password)
        await db.commit()
        return password

def main():
    parser = argparse.ArgumentParser(description="pyferro CLI management tool")
    subparsers = parser.add_subparsers(dest="command", help="Команда для выполнения")

    passwd_parser = subparsers.add_parser("set-admin-password", help="Установить или сгенерировать пароль администратора в существующей БД")
    passwd_parser.add_argument("--login", "-l", type=str, default="admin", help="Логин пользователя (по умолчанию admin)")
    passwd_parser.add_argument("--password", "-p", type=str, help="Новый пароль (если не указан, будет сгенерирован автоматически)")

    create_parser = subparsers.add_parser("createsuperuser", help="Создать администратора системы (admin)")
    create_parser.add_argument("--username", "-u", type=str, help="Имя пользователя (логин)")
    create_parser.add_argument("--password", "-p", type=str, help="Пароль администратора")
    create_parser.add_argument("--email", "-e", type=str, help="Email (опционально)")

    sync_parser = subparsers.add_parser("sync-rpc", help="Синхронизировать RPC методы с базой данных")

    migrate_parser = subparsers.add_parser("migrate", help="Управление миграциями схемы базы данных")
    migrate_sub = migrate_parser.add_subparsers(dest="migrate_action", help="Действие миграции")

    migrate_sub.add_parser("status", help="Показать статус примененных и ожидающих миграций")

    up_parser = migrate_sub.add_parser("up", help="Накатить ожидающие миграции схемы БД")
    up_parser.add_argument("--target", "-t", type=str, help="Целевая версия для остановки")
    up_parser.add_argument("--no-backup", action="store_true", help="Не создавать резервный снимок SQLite")

    rollback_parser = migrate_sub.add_parser("rollback", help="Откатить последнюю примененную миграцию")
    rollback_parser.add_argument("--steps", "-s", type=int, default=1, help="Количество шагов для отката (по умолчанию 1)")

    stamp_parser = migrate_sub.add_parser("stamp", help="Пометить версию как примененную без выполнения upgrade()")
    stamp_parser.add_argument("version", type=str, help="Версия для фиксации")

    help_parser = subparsers.add_parser("help-ui", aliases=["showcase"], help="Запустить интерактивную справку и API эксплорер PyFerro (/admin/help)")
    help_parser.add_argument("--port", "-p", type=int, default=8080, help="Порт сервера (по умолчанию 8080)")
    help_parser.add_argument("--host", "-H", type=str, default="127.0.0.1", help="Хост сервера (по умолчанию 127.0.0.1)")

    args = parser.parse_args()

    if args.command == "set-admin-password":
        try:
            pwd = asyncio.run(async_set_password(login=args.login, password=args.password))
            print("=" * 64)
            print(" 🛡️  pyferro: Пароль успешно обновлен в базе данных!")
            print(f" 👤 Логин:       {args.login}")
            print(f" 🔑 Пароль:      {pwd}")
            print("=" * 64)
            print(" 👉 Войдите через форму авторизации вашего приложения.")
        except Exception as e:
            print(f"❌ Ошибка смены пароля: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "createsuperuser":
        username = args.username
        password = args.password
        email = args.email

        if not username:
            try:
                username = input("Имя пользователя (login): ").strip()
            except (KeyboardInterrupt, EOFError):
                sys.exit(1)

        if not username:
            print("Ошибка: имя пользователя не может быть пустым.", file=sys.stderr)
            sys.exit(1)

        if not password:
            try:
                password = getpass.getpass("Пароль: ")
                password_confirm = getpass.getpass("Подтверждение пароля: ")
                if password != password_confirm:
                    print("Ошибка: пароли не совпадают.", file=sys.stderr)
                    sys.exit(1)
            except (KeyboardInterrupt, EOFError):
                sys.exit(1)

        if not password or len(password) < 6:
            print("Ошибка: пароль должен содержать минимум 6 символов.", file=sys.stderr)
            sys.exit(1)

        asyncio.run(async_create_superuser(username, password, email))

    elif args.command == "sync-rpc":
        asyncio.run(sync_rpc_permissions())
        print("[OK] Синхронизация RPC-методов успешно завершена.")

    elif args.command == "migrate":
        from pyferro.migrations import (
            get_migration_status,
            run_migrations,
            rollback_migration,
            stamp_version,
            LegacyDatabaseError,
            MigrationError,
        )

        action = getattr(args, "migrate_action", None) or "status"

        if action == "status":
            try:
                status = asyncio.run(get_migration_status())
                print("=" * 64)
                print(" 🧭 Статус миграций PyFerro:")
                print("=" * 64)
                fw_ver = status.get("framework_version", "0.7.0")
                db_ver = status.get("db_app_version", fw_ver)
                print(f" Пакет PyFerro:        v{fw_ver}")
                print(f" Версия схемы в БД:    v{db_ver}")
                if status.get("is_patch_compatible"):
                    print(" Инвариант SemVer:     Патч-релиз (схема БД инвариантна, даунтайм = 0)")
                print("-" * 64)
                applied = status["applied"]
                pending = status["pending"]
                print(f" Применено миграций:   {len(applied)}")
                for a in applied:
                    print(f"  ✓ {a['version']:<35} [{a['applied_at']}] ({a['execution_time_ms']} ms)")
                if pending:
                    print(f"\n Ожидают наката ({len(pending)}):")
                    for p in pending:
                        print(f"  ⏳ {p['version']:<35} - {p['description']}")
                    print("\n 👉 Выполните 'python -m pyferro migrate up' для применения.")
                else:
                    print("\n ✨ Схема базы данных полностью актуальна!")
                print("=" * 64)
            except LegacyDatabaseError as e:
                print(f"\n{e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"❌ Ошибка проверки статуса миграций: {e}", file=sys.stderr)
                sys.exit(1)

        elif action == "up":
            try:
                print("=" * 64)
                print(" 🚀 Запуск наката миграций PyFerro...")
                print("=" * 64)
                applied = asyncio.run(
                    run_migrations(
                        target_version=getattr(args, "target", None),
                        create_backup=not getattr(args, "no_backup", False),
                    )
                )
                if applied:
                    print("=" * 64)
                    print(f" ✅ Успешно применены миграции ({len(applied)}):")
                    for ver in applied:
                        print(f"  ✓ {ver}")
                    print("=" * 64)
                else:
                    print(" ✨ Все миграции уже применены, база актуальна.")
            except LegacyDatabaseError as e:
                print(f"\n{e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"❌ Сбой выполнения миграций: {e}", file=sys.stderr)
                sys.exit(1)

        elif action == "rollback":
            try:
                print("=" * 64)
                print(" ⏪ Откат миграций PyFerro...")
                print("=" * 64)
                rolled = asyncio.run(rollback_migration(steps=args.steps))
                if rolled:
                    print(f" ⏪ Успешно откатано шагов ({len(rolled)}):")
                    for ver in rolled:
                        print(f"  ↺ {ver}")
                else:
                    print(" ⚠️  Нет доступных миграций для отката.")
                print("=" * 64)
            except Exception as e:
                print(f"❌ Ошибка отката миграций: {e}", file=sys.stderr)
                sys.exit(1)

        elif action == "stamp":
            try:
                asyncio.run(stamp_version(args.version))
                print(f" [OK] Версия '{args.version}' зафиксирована в pf_schema_migrations.")
            except Exception as e:
                print(f"❌ Ошибка фиксации версии: {e}", file=sys.stderr)
                sys.exit(1)

    elif args.command in ("help-ui", "showcase"):
        import os
        help_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples", "admin_help"))
        if not os.path.exists(help_dir):
            help_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples", "showcase"))
        print("=" * 64)
        print(" 🚀 Запуск PyFerro Admin Help (Интерактивная справка и API)...")
        print(f" 🌐 Адрес: http://{args.host}:{args.port}/admin/help")
        print("=" * 64)
        try:
            from granian import Granian
            from granian.constants import Interfaces
            sys.path.insert(0, help_dir)
            os.chdir(help_dir)
            server = Granian(
                "server:app",
                address=args.host,
                port=args.port,
                interface=Interfaces.RSGI,
                workers=1,
            )
            server.serve()
        except ImportError:
            print("❌ Granian не установлен в окружении.", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
