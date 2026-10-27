# PyFerro 2.0 — Руководство разработчика и Архитектура

**PyFerro 2.0** — сверхбыстрый асинхронный RPC/CRUD веб-фреймворк на базе чистого RSGI (Rust Server-Gateway Interface), SQLAlchemy 2.0 и JSON-RPC 2.0 поверх WebSocket/HTTP.

---

## 1. Ключевые принципы архитектуры

1. **Минимум сущностей — ноль дублирования**:
   - В системе существует **единое понятие метода `Плашка.метод`** (например `Book.create`, `Book.read`, `Book.transfer`).
   - Имя метода всегда берется напрямую из объявления класса/модуля и функции Python (`class Book: async def transfer`) — никаких ручных строк `name="..."`.
2. **Нулевая рефлексия в рантайме**:
   - `inspect.signature` и `sqlalchemy.inspect` вызываются **строго 1 раз при старте сервера**.
   - Все проверки ролей и разрешений выполняются в оперативной памяти за **O(1) (~15 нс)** через `frozenset`.
3. **Ленивая база данных (Lazy DB)**:
   - Сессия `db: AsyncSession` открывается из пула **только** для тех методов, которые явно объявили аргумент `db` в своей сигнатуре.
4. **Два чекбокса на любой метод в админке (`/pyferro_admin`)**:
   - В панели управления все прикладные методы группируются по точке в карточки-плашки (`Book`, `Article`, `files`), а напротив каждого метода доступны две галочки: **«Разрешено»** (`Плашка.метод`) и **«Только свои»** (`Плашка.метод_own`).

---

## 2. Быстрый старт (приложение в 30 строк)

```python
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

Или запуск через CLI **Granian**:
```bash
granian --interface rsgi --host 0.0.0.0 --port 8000 main:app
```

---

## 3. Виды RPC-методов и Smart DI

Декоратор `@rpc_method` поддерживает 3 режима:

```python
from pyferro2.core import Session, SessionData, admRole
from pyferro2.rpc import rpc_method

class catalog:
    # 1. Публичный метод (доступен всем без настройки в БД)
    @rpc_method(public=True)
    async def status() -> str:
        return "ok"

    # 2. Прикладной метод (catalog.export) — настраивается чекбоксами в /pyferro_admin
    @rpc_method
    async def export(session_data: SessionData) -> dict:
        return {"user": session_data.username}

    # 3. Системный метод (доступен только указанным административным ролям admRole)
    @rpc_method(role=[admRole.adm_settings])
    async def rebuild_index() -> bool:
        return True
```

### Мультиретурн (`async def ... yield`) и уведомления (`session.notify`)
Если функция использует `yield`, роутер автоматически отправляет каждый элемент клиенту с тем же `id` запроса. При смене прав пользователя сервер мгновенно закрывает активные `yield`-генераторы и переподключает клиента:

```python
class feed:
    @rpc_method
    async def subscribe(session: Session):
        await session.notify("feed.started", {"ok": True})
        for tick in range(1, 4):
            yield {"tick": tick}
```

---

## 4. Файловая подсистема (2PC) и проксирование (Nginx / Angie / Caddy)

Загрузка файлов выполняется в 2 фазы (без буферизации в RAM):
1. Вызов RPC `files.init_upload` -> возвращает `folder_hash` и `upload_url`.
2. Потоковая отправка `POST /upload?folder=<folder_hash>&filename=<name>`.
3. Вызов RPC `files.commit(folder_hash=..., is_public=True)` -> атомарный перенос в постоянное хранилище (`os.replace`) и запись в `pf_file_metadata`.

Раздача защищенных файлов осуществляется через заголовок `X-Accel-Redirect` без прогона байт через Python.

> [!TIP]
> **Боевые конфигурации Nginx, Angie и Caddy v2**, архитектура потокового отсечения неавторизованных загрузок (Fail-Fast) и раздачи статики подробно описаны в [NGINX.md](NGINX.md).

---

## 5. Маршруты сервера (`PyFerroApp`)

| Маршрут | Назначение |
| :--- | :--- |
| `WS /ws` | Полнодуплексный JSON-RPC 2.0, мультиретурн (`yield`), серверные уведомления `session.notify` |
| `POST /rpc` | Синхронный вызов JSON-RPC 2.0 поверх HTTP |
| `POST /upload` | Потоковая закачка файлов во временную транзакцию (`O(1)` RAM) |
| `GET /files/<folder>/<name>` | Защищенная раздача файлов (поддержка `X-Accel-Redirect` и файловых JWT) |
| `GET /pyferro_admin` | Встроенная панель управления RBAC и CRUD (маршрут `/admin` свободен для вашего приложения) |

---

## 6. Табличная пагинация и сжатие трафика ($tabular)

PyFerro 2.0 включает высокопроизводительную подсистему пагинации для SQLAlchemy и фронтенда:

- **Бэкенд:** `paginate_tabular(db, Model, **params)` — выполняет поиск, фильтры, сортировку, умный `count(*)` и пакует ответ в сжатый протокол `$tabular` за **1 строчку кода**.
- **Фронтенд:** `createPaginator("Model.read")` + компонент `<Pagination />` — полностью берут на себя состояние, номера страниц `[1, '...', 4, 5, 6, '...', 25]`, стрелки «Назад/Вперед» и живой поиск.
- **Подробное руководство:** см. [PAGINATION.md](PAGINATION.md).
