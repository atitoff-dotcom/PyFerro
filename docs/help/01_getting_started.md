# Руководство для разработчиков: Быстрый старт

Добро пожаловать в панель управления PyFerro 2.0. Это интерактивная документация, в которой теоретические разделы дополнены живыми компонентами интерфейса и песочницами.

## Архитектура системы

PyFerro 2.0 построен на трех ключевых концепциях:
1. **Rust RSGI (Granian)** — высокопроизводительный асинхронный сервер сетевых шлюзов.
2. **WSRPC (JSON-RPC 2.0)** — симметричный протокол поверх WebSocket и HTTP POST `/rpc`.
3. **ORM SQLAlchemy**, поддержка PostgreSQL, MySQL и MariaDB, SQLite, Oracle, Microsoft SQL Server, причем без БД фреймворк полноценно не работает, для простых решений вполне достаточно простого файлового SQLite

## Установка

```bash
pip install pyferro
```

## Простейшее приложение

```python
from pyferro2.core.session_data import SessionData
from pyferro2.rpc import rpc_method


@rpc_method
async def test(data: SessionData):
return  {"test": 3}

app = PyFerroApp(secret_key="replace-with-32-byte-production-secret-key!")

if __name__ == "__main__":
    # Прямой запуск на Rust-сервере Granian:
    app.run(host="0.0.0.0", port=8000)
      
```


## Быстрый старт полноценного приложения

```python
"""
Быстрый старт PyFerro 2.0 (RSGI).
Пример из README.md: модель Book, права RLS, кастомный RPC-метод Book.transfer и регистрация в CRUD.
"""

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.core import SessionData
from pyferro2.db import Database, RowSecureModel
from pyferro2.rpc import ForbiddenError, rpc_method
from pyferro2.server import PyFerroApp


class Book(RowSecureModel):
    """Таблица книг. Наследование от RowSecureModel автоматически добавляет id и creator_id."""

    __tablename__ = "books"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str] = mapped_column(String(120), nullable=False)

    class Crud:
        title = "Книги"
        searchable = ("title", "author")
        readonly = ()
        hidden = ()

    @rpc_method
    async def transfer(
        book_id: int,
        new_owner_id: int,
        session_data: SessionData,
        db: AsyncSession,
    ) -> dict:
        """Кастомный метод Book.transfer (автоматически появится в плашке Book в /pyferro_admin)."""
        book = await db.get(Book, book_id)
        if not book:
            raise ForbiddenError("Книга не найдена")

        # Если в админке включена галочка «Только свои» (Book.transfer_own):
        if session_data.is_own_only("Book.transfer") and book.creator_id != session_data.user_id:
            raise ForbiddenError("Можно передавать только свои книги")

        book.creator_id = new_owner_id
        await db.commit()
        return {"id": book.id, "creator_id": book.creator_id}


db = Database("sqlite+aiosqlite:///./app.db")
app = PyFerroApp(db=db, secret_key="replace-with-32-byte-production-secret-key!")

# Регистрирует Book.create, Book.read, Book.update, Book.delete и кастомный Book.transfer:
app.crud.register(Book)

if __name__ == "__main__":
    # Прямой запуск на Rust-сервере Granian:
    app.run(host="0.0.0.0", port=8000)
```






## Интерактивный компонент: Пагинация

Ниже представлен реальный рабочий компонент `Pagination.svelte`, используемый в таблицах админки. Вы можете кликать по страницам и менять их размер:

```widget:PaginationDemo
total: 250
pageSize: 10
currentPage: 1
```

## Полезные ссылки

Используйте меню слева для навигации между статьями документации. Каждая статья имеет прямой постоянный URL вида `/pyferro_admin/help/<slug>`.
