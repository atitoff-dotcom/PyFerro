"""
CLI утилита запуска pyferro-demo.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pyferro_demo.app import create_demo_app


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pyferro-demo",
        description="🚀 Запуск демонстрационного приложения PyFerro (Форум, JSON-RPC, Granian RSGI)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run"],
        help="Команда (по умолчанию run)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Хост сервера (по умолчанию 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Порт сервера (по умолчанию 8080)"
    )
    parser.add_argument(
        "--db", default="demo.db", help="Путь к SQLite базе данных (по умолчанию demo.db)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print(" 🚀 Запуск PyFerro Showcase & Demo Application")
    print(f" 📦 База данных: {args.db}")
    print(f" 🌐 Адрес:       http://{args.host}:{args.port}")
    print(f" 🛡️  Админка:     http://{args.host}:{args.port}/pyferro_admin/")
    print(" 🔑 Логин:       admin / Пароль: admin")
    print("=" * 60)

    db_url = f"sqlite+aiosqlite:///{args.db}"
    app = asyncio.run(create_demo_app(db_url=db_url))
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
