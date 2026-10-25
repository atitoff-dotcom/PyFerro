# PyFerro 2.0 — Руководство разработчика и Архитектура

**PyFerro 2.0** — сверхбыстрый асинхронный RPC/CRUD веб-фреймворк на базе чистого ASGI, SQLAlchemy 2.0 и JSON-RPC 2.0 поверх WebSocket/HTTP.

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
granian --interface asgi --host 0.0.0.0 --port 8000 main:app
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

## 4. Файловая подсистема (2PC) и конфиги прокси (Nginx / Angie / Caddy)

Загрузка файлов выполняется в 2 фазы (без буферизации в RAM):
1. Вызов RPC `files.init_upload` -> возвращает `folder_hash` и `upload_url`.
2. Потоковая отправка `POST /upload?folder=<folder_hash>&filename=<name>`.
3. Вызов RPC `files.commit(folder_hash=..., is_public=True)` -> атомарный перенос в постоянное хранилище (`os.replace`) и запись в `pf_file_metadata`.

### Полная боевая конфигурация Nginx / Angie для Granian (`WS /ws` + `2PC Files`)

Для корректной работы **Granian** за Nginx/Angie важно:
1. Выделить `location /ws` с отключенной буферизацией (`proxy_buffering off`) и длинным `proxy_read_timeout`, чтобы Nginx не обрывал живые WebSocket-соединения и долгие мультиретурн-стримы (`yield`) каждые 60 секунд.
2. В `location /upload` отключить буферизацию запроса (`proxy_request_buffering off`), чтобы файлы стримились чанками напрямую в Granian за `O(1)` памяти.
3. В `location /internal_files/` включить `internal;` для прямой раздачи файлов с диска по заголовку `X-Accel-Redirect`.

```nginx
# В секции http { ... } определяем корректный заголовок Connection для WebSocket и Keep-Alive:
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream granian_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}

server {
    listen 80;
    server_name example.com;

    # 1. WebSocket JSON-RPC 2.0 и мультиретурн (yield) для Granian
    location /ws {
        proxy_pass http://granian_backend/ws;
        proxy_http_version 1.1;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Отключаем буферизацию для мгновенной доставки пакетов yield и session.notify
        proxy_buffering off;
        # Держим соединение для долгих подписок (24 часа; heartbeat ping/pong поддерживает активность)
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # 2. Потоковая закачка файлов напрямую в Granian без двойной буферизации на диске Nginx
    location /upload {
        client_max_body_size 2G;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_pass http://granian_backend/upload;
    }

    # 3. Внутренняя раздача файлов с диска мимо Python (по заголовку X-Accel-Redirect от PyFerroApp)
    location /internal_files/ {
        internal;
        alias /var/lib/pyferro/storage/;
    }

    # 4. Остальные HTTP-маршруты (/rpc, /files/..., /pyferro_admin)
    location / {
        proxy_pass http://granian_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Конфигурация Caddy v2 (`Caddyfile`)
Caddy понимает тот же самый заголовок `X-Accel-Redirect` через `handle_response`:

```caddyfile
example.com {
    reverse_proxy 127.0.0.1:8000 {
        @accel header X-Accel-Redirect *
        handle_response @accel {
            root * /var/lib/pyferro/storage
            rewrite * {rp.header.X-Accel-Redirect}
            uri strip_prefix /internal_files
            file_server
        }
    }
}
```

---

## 5. Маршруты сервера (`PyFerroApp`)

| Маршрут | Назначение |
| :--- | :--- |
| `WS /ws` | Полнодуплексный JSON-RPC 2.0, мультиретурн (`yield`), серверные уведомления `session.notify` |
| `POST /rpc` | Синхронный вызов JSON-RPC 2.0 поверх HTTP |
| `POST /upload` | Потоковая закачка файлов во временную транзакцию (`O(1)` RAM) |
| `GET /files/<folder>/<name>` | Защищенная раздача файлов (поддержка `X-Accel-Redirect` и файловых JWT) |
| `GET /pyferro_admin` | Встроенная панель управления RBAC и CRUD (маршрут `/admin` свободен для вашего приложения) |
