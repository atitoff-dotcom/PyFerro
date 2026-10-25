"""
Тесты для системы пагинации PyFerro 2.0 (paginate_tabular, encode_cursor, decode_cursor).
"""

from datetime import datetime, timezone
from enum import Enum
import uuid

import pytest
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.core.tabular import unpack_tabular
from pyferro2.db.base import Base
from pyferro2.db.engine import Database
from pyferro2.db.pagination import decode_cursor, encode_cursor, paginate_tabular


class BookGenre(str, Enum):
    FICTION = "fiction"
    SCIENCE = "science"
    FANTASY = "fantasy"


class DemoBook(Base):
    __tablename__ = "demo_books"

    title: Mapped[str] = mapped_column(String(100), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    genre: Mapped[str] = mapped_column(String(50), default=BookGenre.FICTION.value)
    price: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


@pytest.fixture
async def db_session():
    db = Database("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db.session() as session:
        # Наполняем тестовыми данными (5 книг)
        books = [
            DemoBook(title="Book Alpha", author="Author 1", genre=BookGenre.FICTION.value, price=100),
            DemoBook(title="Book Beta", author="Author 2", genre=BookGenre.SCIENCE.value, price=200),
            DemoBook(title="Book Gamma", author="Author 1", genre=BookGenre.FICTION.value, price=150),
            DemoBook(title="Book Delta", author="Author 3", genre=BookGenre.FANTASY.value, price=300),
            DemoBook(title="Book Epsilon", author="Author 2", genre=BookGenre.SCIENCE.value, price=250),
        ]
        session.add_all(books)
        await session.commit()
        yield session

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_offset_pagination_first_page(db_session):
    res = await paginate_tabular(db_session, DemoBook, page=1, limit=2)
    assert res["$tabular"] is True
    assert res["total"] == 5
    assert res["pages"] == 3
    assert res["page"] == 1
    assert res["limit"] == 2
    assert res["has_next"] is True
    assert res["has_prev"] is False
    assert len(res["rows"]) == 2
    assert "title" in res["fields"]
    assert res["next_cursor"] is not None

    unpacked = unpack_tabular(res)
    assert len(unpacked["items"]) == 2
    # По умолчанию сортировка id.desc()
    assert unpacked["items"][0]["title"] == "Book Epsilon"
    assert unpacked["items"][1]["title"] == "Book Delta"


@pytest.mark.asyncio
async def test_offset_pagination_second_page(db_session):
    res = await paginate_tabular(db_session, DemoBook, page=2, limit=2)
    assert res["page"] == 2
    assert res["has_next"] is True
    assert res["has_prev"] is True
    assert len(res["rows"]) == 2

    unpacked = unpack_tabular(res)
    assert unpacked["items"][0]["title"] == "Book Gamma"
    assert unpacked["items"][1]["title"] == "Book Beta"


@pytest.mark.asyncio
async def test_offset_pagination_last_page(db_session):
    res = await paginate_tabular(db_session, DemoBook, page=3, limit=2)
    assert res["page"] == 3
    assert res["has_next"] is False
    assert res["has_prev"] is True
    assert len(res["rows"]) == 1

    unpacked = unpack_tabular(res)
    assert unpacked["items"][0]["title"] == "Book Alpha"


@pytest.mark.asyncio
async def test_cursor_pagination(db_session):
    # Страница 1 (Offset с получением next_cursor)
    p1 = await paginate_tabular(db_session, DemoBook, page=1, limit=2)
    cursor = p1["next_cursor"]
    assert cursor is not None

    # Страница 2 по курсору
    p2 = await paginate_tabular(db_session, DemoBook, cursor=cursor, limit=2)
    assert p2["$tabular"] is True
    assert p2["total"] is None  # В режиме курсора count(*) не вызывается!
    assert p2["has_next"] is True
    assert p2["has_prev"] is True
    assert len(p2["rows"]) == 2

    unpacked2 = unpack_tabular(p2)
    assert unpacked2["items"][0]["title"] == "Book Gamma"
    assert unpacked2["items"][1]["title"] == "Book Beta"

    # Страница 3 по следующему курсору
    cursor2 = p2["next_cursor"]
    p3 = await paginate_tabular(db_session, DemoBook, cursor=cursor2, limit=2)
    assert p3["has_next"] is False
    assert len(p3["rows"]) == 1
    unpacked3 = unpack_tabular(p3)
    assert unpacked3["items"][0]["title"] == "Book Alpha"


@pytest.mark.asyncio
async def test_search_and_filters(db_session):
    # Поиск по подстроке
    res_search = await paginate_tabular(db_session, DemoBook, search="Gamma")
    assert res_search["total"] == 1
    unpacked = unpack_tabular(res_search)
    assert unpacked["items"][0]["title"] == "Book Gamma"

    # Фильтрация по жанру
    res_filter = await paginate_tabular(
        db_session, DemoBook, filters={"genre": BookGenre.SCIENCE.value}
    )
    assert res_filter["total"] == 2
    unpacked_filter = unpack_tabular(res_filter)
    genres = {item["genre"] for item in unpacked_filter["items"]}
    assert genres == {BookGenre.SCIENCE.value}


@pytest.mark.asyncio
async def test_custom_select_and_column_projection(db_session):
    # Передаем готовый Select с проекцией колонок
    stmt = select(DemoBook.id, DemoBook.title).where(DemoBook.price > 150)
    res = await paginate_tabular(db_session, stmt, limit=10)

    assert res["$tabular"] is True
    assert res["fields"] == ["id", "title"]
    assert res["total"] == 3
    assert len(res["rows"]) == 3


@pytest.mark.asyncio
async def test_count_false_mode(db_session):
    # Режим без COUNT (для бесконечного скролла)
    res = await paginate_tabular(db_session, DemoBook, page=1, limit=2, count=False)
    assert res["total"] is None
    assert res["pages"] is None
    assert res["has_next"] is True
    assert len(res["rows"]) == 2


@pytest.mark.asyncio
def test_cursor_encode_decode():
    token = encode_cursor(42, col="id", direction="desc")
    decoded = decode_cursor(token)
    assert decoded["v"] == 42
    assert decoded["c"] == "id"
    assert decoded["d"] == "desc"
