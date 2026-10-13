# Архитектурный манифест и план развития PyFerro (Roadmap)

> **Статус документа:** Концептуальный архитектурный план будущих релизов  
> **Цель:** Переход от высокопроизводительного сокетного сервера к целостной fullstack-экосистеме с нулевым бойлерплейтом и идеальным опытом разработчика (Developer Experience, DX).

---

## 🧭 Содержание
1. [Введение и стратегический фокус](#1-введение-и-стратегический-фокус)
2. [Инициатива 1: Автогенерация TypeScript-типов (`pyferro codegen`)](#2-инициатива-1-автогенерация-typescript-типов-pyferro-codegen)
3. [Инициатива 2: Консольная CLI-утилита разработчика (`pyferro cli`)](#3-инициатива-2-консольная-cli-утилита-разработчика-pyferro-cli)
4. [Инициатива 3: Декларативные хуки жизненного цикла моделей (`@crud_hook`)](#4-инициатива-3-декларативные-хуки-жизненного-цикла-моделей-crud_hook)
5. [Инициатива 4: Встроенный In-Memory тестовый клиент (`FerroTestClient`)](#5-инициатива-4-встроенный-in-memory-тестовый-клиент-ferrotestclient)
6. [Инициатива 5: Декоратор `@transactional` с авто-откатом при дисконнекте](#6-инициатива-5-декоратор-transactional-с-авто-откатом-при-дисконнекте)
7. [Матрица приоритетов и этапы внедрения](#7-матрица-приоритетов-и-этапы-внедрения)

---

## 1. Введение и стратегический фокус

PyFerro уже решил ключевые задачи сетевого уровня и производительности:
* Сверхбыстрый RSGI транспорт на Rust (Granian);
* Симметричный полнодуплексный протокол WSRPC (JSON-RPC 2.0);
* Табличное сжатие списков RFC 0002 (экономия 40–70% трафика);
* Реактивный CRUD и панель управления с разграничением прав на уровне строк (RLS);
* Клиентский модуль `BinaryWSRPC` с реактивным `AuthStore`, Web Crypto RSA и Gatekeeper.

Следующий качественный шаг в эволюции фреймворка — **ликвидация трения между бэкендом и фронтендом, устранение рутинного бойлерплейта и эталонный инструментарий разработчика**.

---

## 2. Инициатива 1: Автогенерация TypeScript-типов (`pyferro codegen`)

### Проблема
В классических стеках (FastAPI, Django, Express) синхронизация контрактов между бэкендом и фронтендом требует громоздких схем OpenAPI, сторонних парсеров и ручного написания интерфейсов. Любое переименование поля в модели или изменение параметров RPC приводит к скрытым ошибкам во фронтенде в рантайме.

### Уникальное преимущество PyFerro
Вся метаинформация уже собрана в памяти приложения:
1. `ModelRegistry.all()` содержит метаданные моделей SQLAlchemy (`FieldMeta`): типы колонок, флаги `nullable`, `primary_key`, перечисления `enum`, связи Foreign Key.
2. `RPC_REGISTRY` содержит сигнатуры методов, аннотации типов параметров (`typing.get_type_hints`), декораторы `@tabular_response(fields=[...])` и docstrings.

### Концепция команды
```bash
pyferro codegen server:app --out frontend/src/lib/types/ferro.d.ts
```

### Генерируемый контракт (`ferro.d.ts`)
```typescript
/** Автоматически сгенерировано PyFerro Codegen. Не редактировать вручную. */

// 1. Интерфейсы моделей базы данных
export interface User {
    id: number;
    username: string;
    email: string | null;
    role: 'admin' | 'moderator' | 'user';
    is_active: boolean;
    created_at: string;
}

export interface ForumTopic {
    id: number;
    title: string;
    content: string;
    author_id: number;
    views_count: number;
}

// 2. Реестр вызовов RPC-методов
export interface RpcSchema {
    'forum.get_topic': {
        params: { id: number };
        response: ForumTopic;
    };
    'tasks.list': {
        params?: { limit?: number; offset?: number };
        response: Task[]; // распакованный @tabular_response
    };
    'admin.cleanup': {
        params?: void;
        response: { status: string; deleted_count: number };
    };
}
```

### Поддержка в клиенте `BinaryWSRPC`
```typescript
import { BinaryWSRPC } from './wsrpc';
import type { RpcSchema } from './types/ferro';

export const rpc = new BinaryWSRPC<AuthUser, RpcSchema>();

// Полный автокомплит в IDE: методы, аргументы и строгий тип возврата!
const topic = await rpc.call('forum.get_topic', { id: 10 }); 
// topic имеет тип ForumTopic, а не any! Опечатка в id подсвечивается компилятором TS.
```

---

## 3. Инициатива 2: Консольная CLI-утилита разработчика (`pyferro cli`)

### Проблема
Разработчику приходится держать в голове разрозненные команды: запуск через `granian`, сброс пароля через аргументы скрипта, ручной аудит зарегистрированных методов через код.

### Решение
Регистрация канонической консольной команды в `[project.scripts]` `pyproject.toml`:
```toml
[project.scripts]
pyferro = "pyferro.cli:main"
```

### Набор команд:
1. **`pyferro rpc list [app]`**:
   Выводит в терминал интерактивную таблицу всех зарегистрированных RPC-методов:
   - Имя метода;
   - Область доступа (`public`, `auth`, `admin`);
   - Права доступа CASL;
   - Наличие и статус docstring (с предупреждением ⚠️ для методов без документации согласно стандарту).
2. **`pyferro models list [app]`**:
   Сводная таблица CRUD-моделей: имя таблицы, количество колонок, скрытые поля, признак `is_internal`, наличие RLS-политик.
3. **`pyferro admin create [app] --login admin --password secret`**:
   Безопасное создание или обновление суперпользователя в БД (DML, PBKDF2-SHA256).
4. **`pyferro codegen [app] -o [path]`**:
   Генерация TypeScript-типов.

---

## 4. Инициатива 3: Декларативные хуки жизненного цикла моделей (`@crud_hook`)

### Проблема
В CRUD-плагине создание и обновление происходят автоматически. Но в реальных проектах на каждом шаге требуются сайд-эффекты:
- Очистить прикрепленные файлы при удалении;
- Отправить уведомление в сокет (`broadcast_notification`) при создании записи;
- Вычислить или нормализовать поле (например, `slug = slugify(title)`);
- Проверить дополнительные бизнес-правила перед записью.

Сейчас разработчик вынужден полностью отказываться от авто-методов `crud.*` и писать кастомные обработчики с нуля.

### Решение
Декларативные хуки жизненного цикла прямо внутри класса модели `class Crud`:
```python
class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    class Crud:
        verbose_name = "Тема форума"

        async def before_create(self, db_session: AsyncSession, current_user: AuthSession):
            """Автоматическая привязка автора перед сохранением."""
            self.author_id = current_user.user_id

        async def after_create(self, db_session: AsyncSession, current_user: AuthSession):
            """Уведомление подписчиков в реальном времени."""
            await broadcast_notification("forum.new_topic", {"id": self.id, "title": self.title})

        async def before_delete(self, db_session: AsyncSession, current_user: AuthSession):
            """Каскадная очистка связанных файлов на диске."""
            await delete_topic_files(self.id)
```

Встроенные хендлеры `crud_create`, `crud_update_cell`, `crud_delete` автоматически вызывают эти хуки в рамках активной транзакции БД.

---

## 5. Инициатива 4: Встроенный In-Memory тестовый клиент (`FerroTestClient`)

### Проблема
Для написания интеграционных тестов сокетов сейчас требуется либо громоздкое мокирование `MockAdminSession`, либо запуск реального сетевого сервера на случайном порту, что замедляет тесты и усложняет CI/CD.

### Решение
Легковесный эмулятор сокетного соединения в памяти:
```python
import pytest
from pyferro.testing import FerroTestClient
from server import app

@pytest.mark.asyncio
async def test_forum_workflow():
    async with FerroTestClient(app) as client:
        # 1. Гостевой вызов публичного метода
        pong = await client.rpc("system.ping")
        assert pong == {"status": "pong"}

        # 2. Неавторизованный доступ отклоняется
        with pytest.raises(RPCError) as exc:
            await client.rpc("topics.create", {"title": "Test"})
        assert exc.value.code == -32000

        # 3. Мгновенная смена контекста пользователя без сетевых оверхедов
        client.login_as(user_id=1, username="admin", role="admin")
        res = await client.rpc("topics.create", {"title": "Test"})
        assert res["id"] == 1

        # 4. Проверка прозрачной распаковки табличных данных
        topics = await client.rpc("topics.list")
        assert isinstance(topics, list)
```

### Преимущества:
* Тестирует полную цепочку: валидацию CASL/RLS, распаковку kwargs, `@tabular_response`, инвалидацию `@invalidates`.
* Скорость: более **10 000 вызовов в секунду** в одном процессе.
* Нулевые требования к сетевым портам.

---

## 6. Инициатива 5: Декоратор `@transactional` с авто-откатом при дисконнекте

### Проблема
1. Рутинный бойлерплейт: `async with async_session() as db: try: ... commit() except: rollback()`.
2. Если клиент оборвал соединение (закрыл вкладку браузера) посреди длительной асинхронной операции, открытая транзакция может удерживать блокировки строк в СУБД вплоть до истечения таймаута пула соединений.

### Решение
Декоратор `@transactional` (или `@app.transactional`):
```python
@app.rpc("orders.checkout")
@app.transactional
async def checkout_order(db: AsyncSession, session: JsonRpcSession, cart_id: int):
    # db — готовая сессия из настроенного async_sessionmaker приложения.
    # При успешном завершении вызывается db.commit().
    # При исключении вызывается db.rollback().
    ...
```

### Интеграция с обрывом сокета:
Декоратор автоматически регистрирует хук `session.register_on_close(cleanup)`:
* Если сокет закрывается до возврата результата из функции, транзакция **немедленно откатывается** (`await db.rollback()`), предотвращая утечки ресурсов и «зависшие» блокировки в БД.

---

## 7. Матрица приоритетов и этапы внедрения

| Инициатива | Направление | Полезность | Трудоемкость | Запланированный релиз |
|---|---|:---:|:---:|:---:|
| **1. `pyferro codegen`** | Frontend & DX | 🌟 10/10 | Средняя | **v0.6.0** |
| **2. `pyferro cli`** | Инструменты DX | ⚡ 9/10 | Низкая/Средняя | **v0.6.0** |
| **3. `@crud_hook`** | Модели и CRUD | 💎 9/10 | Низкая | **v0.6.1** |
| **4. `FerroTestClient`** | Тестирование | 🛡️ 8/10 | Средняя | **v0.6.1** |
| **5. `@transactional`** | Надежность БД | 🔒 8/10 | Низкая | **v0.6.2** |
