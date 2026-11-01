"""
CLI утилита запуска pyferro-demo.
"""

from __future__ import annotations

import argparse
import os
import sys

from granian import Granian


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
        "--host", default="0.0.0.0", help="Хост сервера (по умолчанию 0.0.0.0 — все интерфейсы)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Порт сервера (по умолчанию 8080)"
    )
    parser.add_argument(
        "--db", default="demo.db", help="Путь к SQLite базе данных (по умолчанию demo.db)"
    )

    args = parser.parse_args()

    os.environ["PYFERRO_DEMO_DB"] = args.db

    print("=" * 60)
    print(" 🚀 Запуск PyFerro Showcase & Demo Application")
    print(f" 📦 База данных: {args.db}")
    print(f" 🌐 Адрес:       http://{args.host}:{args.port}")
    print(f" 🛡️  Админка:     http://{args.host}:{args.port}/pyferro_admin/")
    print(" 🔑 Логин:       admin / Пароль: admin")
    print("=" * 60)
    print("=" * 60)

    server = Granian(
        "pyferro_demo.app:app",
        address=args.host,
        port=args.port,
        interface="rsgi",
        workers=1,
    )
    server.serve()


if __name__ == "__main__":
    main()
