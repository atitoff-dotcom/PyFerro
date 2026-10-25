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
