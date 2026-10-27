"""
CLI-точка входа для выполнения служебных команд PyFerro 2.0 (например, python -m pyferro2 --add-admin).
"""

from pyferro2.server.app import PyFerroApp


def main() -> None:
    app = PyFerroApp()
    if not app.handle_cli():
        print("Использование: python -m pyferro2 --add-admin [--username admin] [--password admin]")


if __name__ == "__main__":
    main()
