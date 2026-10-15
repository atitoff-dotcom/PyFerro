# AI Agent Guide: Разработка на фреймворке `PyFerro`

> **Инструкция для ИИ-ассистентов (Cursor, Antigravity, Claude, ChatGPT, Windsurf, Copilot)**  
> Этот документ содержит актуальные контракты, архитектурные правила и анти-паттерны для генерации кода на базе фреймворка `PyFerro`.

---

## 1. Концепция и Архитектура

`PyFerro` — высокопроизводительный реактивный Python-фреймворк:
- **Сетевой уровень:** Rust RSGI сервер **Granian** (не ASGI и не WSGI!).
- **Протокол:** Симметричный **JSON-RPC 2.0 (WSRPC)** поверх постоянного WebSocket-соединения + опциональный HTTP.
- **Сжатие данных:** Табличный формат **RFC 0002 (Tabular Data Compression)** — экономит 40–70% трафика в списках.
- **Безопасность:** По умолчанию гостям разрешены только методы `login.*`. Доступ к остальным требует авторизации или явного флага `public=True`.
- **Эталонный пример:** Живой интерактивный стенд со всеми плагинами находится в [examples/showcase](file:///home/alex/PyFerro/examples/showcase).

---

## 2. Быстрый старт: Приложение (`server.py`)

```python
import os
from pyferro import FerroApp, rpc_method, tabular_response, RPCError
from pyferro.broadcast import broadcast, broadcast_notification

# 1. Инициализация приложения со всеми настройками (Code-First)
app = FerroApp(
    secret_key=os.getenv("SECRET_KEY", "dev-secret-key-change-in-production"),
    database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///app.db"),
    static_dir="./public",       # Раздача статики через нативный Rust Zero-Copy (proto.response_file)
    index_file="index.html",     # Автоматическая отдача на GET /
    login_rpc="login.",          # Гостям открыты методы с префиксом login. и методы с is_public в БД
    cors=True
)

# 2. Публичный метод (доступен неавторизованным гостям, настраивается в БД auth_rpc_permission)
@app.rpc("system.ping")
async def ping():
    return {"status": "pong"}

# 3. Метод с авто-распаковкой kwargs и табличным сжатием
@app.rpc("tasks.list")
@tabular_response(fields=["id", "title", "completed"])
async def list_tasks(limit: int = 100):
    return [
        {"id": 1, "title": "Купить хлеб", "completed": False},
        {"id": 2, "title": "Написать тесты", "completed": True},
    ]

# 4. Защищенный метод (права доступа привязываются к ролям в БД через CRUD)
@app.rpc("admin.cleanup")
async def admin_cleanup():
    await broadcast_notification("system.alert", {"msg": "База очищена"})
    return {"status": "ok"}

# 5. Запуск сервера (workers=1 рекомендуется для in-memory backplane)
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, workers=1)
```

Запуск через CLI:
```bash
granian --rsgi server:app --host 127.0.0.1 --port 8080 --workers 1
```

---

## 3. Правила и контракты объявления RPC-методов

### 3.1. Декоратор `@rpc_method` / `@app.rpc`
```python
from pyferro.core.session import rpc_method, RPCError

@rpc_method("items.create")
async def create_item(session, title: str, count: int = 1):
    # session: текущая сессия сокета (AuthSession при авторизации)
    # Права доступа настраиваются исключительно в БД (auth_rpc_permission)
    # Именованные аргументы автоматически извлекаются из JSON-RPC params
    if not title:
        raise RPCError(-32602, "Название не может быть пустым")
    return {"id": 42, "title": title, "count": count}
```

### 3.2. Сигнатуры хендлеров (поддерживаются все варианты):
1. `async def fn(session, params: dict)` — прямой доступ к объекту сессии и словарю параметров.
2. `async def fn(session, title: str, priority: int = 1)` — авто-маппинг kwargs + `session`.
3. `async def fn(title: str, priority: int = 1)` — только именованные параметры из `params`.
4. `async def fn()` — метод без аргументов.

### 3.3. Обработка ошибок (JSON-RPC 2.0 Error)
Для возврата ошибки клиенту используйте `raise RPCError(code, message)`:
- `raise RPCError("Текст ошибки")` → код `-32000` (Server Error).
- `raise RPCError(-32602, "Неверные параметры")` → стандартный код ошибки JSON-RPC.

### 3.4. Стандарт оформления Docstring для RPC-методов
Каждый RPC-метод **обязан** иметь качественный docstring. Отсутствие docstring считается анти-паттерном и логируется предупреждением `[Discovery] ⚠️ RPC-метод '...' не имеет docstring!`.

**Правила оформления:**
1. **Строка 1 (Краткое резюме):** 3–10 слов, четко описывающих действие на основном языке проекта (без технических клише вроде *"Обертка для..."* или *"RPC handler"*). Первая строка автоматически извлекается системой Discovery и отображается под именем метода в матрице прав и настройках доступа гостей:
   ```python
   @app.rpc("documents.list")
   async def list_docs(limit: int = 50):
       """Просмотр архива документов и сформированных отчетов.
       
       Возвращает список документов с пагинацией и правами доступа.
       
       :param limit: Максимальное количество записей (по умолчанию 50).
       :return: Табличный список метаданных документов.
       """
   ```
2. **Строки 2+ (Подробная документация):** Полное описание параметров, бизнес-логики и возвращаемых структур. Отображается администраторам во всплывающем окне справки (кнопка `ℹ️` в интерфейсе управления правами).
3. **Параметр `description`:** При необходимости можно явно переопределить краткое описание: `@app.rpc("tasks.get", description="Получение задачи по ID")`.

---

## 4. Табличное сжатие (RFC 0002)

Всегда используйте `@tabular_response` для списков однотипных объектов:
```python
from pyferro.core.tabular import tabular_response

@rpc_method("users.get_all")
@tabular_response(fields=["id", "username", "email", "role"])
async def get_users():
    # Возвращает список словарей или ORM-моделей
    return await fetch_users_from_db()
```
*Эффект:* Превращает `[{"id":1, ...}, {"id":2, ...}]` в `{"$tabular": true, "fields": [...], "rows": [[1, ...], [2, ...]]}`. Клиентский TS/JS SDK распаковывает это прозрачно на лету через `unpackTabular()`.

---

## 5. Smart Cache и инвалидация тегов (RFC 0001)

Для реактивной инвалидации кэша на клиентах при мутациях используйте `@invalidates`:
```python
from pyferro.smart_cache import invalidates

@rpc_method("topics.delete")
@invalidates(tags=["forum.topics", "forum.category.{category_id}", "forum.topic.{topic_id}"])
async def delete_topic(topic_id: int, category_id: int):
    # Теги со строковыми шаблонами разрешаются автоматически из params/kwargs и result
    return {"status": "ok"}
```
Сервер монотонно увеличивает версию тегов в памяти/БД и рассылает сокетам событие `cache.invalidate`.

---

## 6. Multi-return Потоковый Стриминг (`stream: true`)

Для длительных задач отправляйте промежуточный прогресс без блокировки сокета:
```python
from pyferro.core.session import current_rpc_id_ctx

@app.rpc("analytics.generate")
async def generate_report(session):
    rpc_id = current_rpc_id_ctx.get()
    
    # Отправка промежуточных чанков прогресса
    await session.send_stream_chunk(rpc_id, {"progress": 30, "step": "Сканирование БД"})
    await session.send_stream_chunk(rpc_id, {"progress": 70, "step": "Сжатие"})
    
    # Финальный ответ завершает RPC-запрос
    return {"progress": 100, "report_url": "/reports/12.pdf"}
```

---

## 7. Полнодуплексный Reverse RPC (Сервер &rarr; Клиент)

WSRPC симметричен: сервер может сам отправить запрос клиенту и дождаться ответа:
```python
@app.rpc("client.inspect")
async def inspect_client(session):
    # Сервер отправляет JSON-RPC запрос в браузер
    client_response = await session.send_request("client.get_env", timeout=3.0)
    return {"browser_info": client_response}
```

---

## 8. Рассылки реального времени (Broadcast)

Неблокирующая O(1) рассылка уведомлений всем подключенным сокетам:
```python
from pyferro.broadcast import broadcast, broadcast_notification

# Сериализация происходит 1 раз в память, после чего фрейм отправляется всем сокетам
await broadcast_notification("order.updated", {"order_id": 105, "status": "shipped"})
```

---

## 9. Загрузка файлов (Двухфазный коммит 2PC)

Загрузка больших файлов без буферизации в RAM через RSGI HTTP стриминг:
1. `POST /upload?folder_hash=...` — чанки пишутся сразу на диск с O(1) памяти.
2. Проверка прав: эндпоинт `/auth-check-upload` валидирует JWT в заголовке `Authorization: Bearer <JWT>`.
3. Фиксация: WSRPC метод `files.commit(folder_hash="...")` атомарно переносит файлы в постоянное хранилище.

---

## 10. Универсальный реактивный CRUD (`pyferro.plugins.crud`)

Авто-генерация API и встроенная панель управления на `/crud`:
1. Регистрация моделей:
   ```python
   from pyferro.plugins.crud import ModelRegistry
   ModelRegistry.register(Task)
   # или ModelRegistry.auto_discover(Base)
   ```
2. Декларативное описание модели (`class Crud:`):
   ```python
   class Item(Base):
       __tablename__ = "items"
       id: Mapped[int] = mapped_column(Integer, primary_key=True)
       title: Mapped[str] = mapped_column(String(100), info={"label": "Название"})
       class Crud:
           verbose_name = "Элемент"
           verbose_name_plural = "Элементы"
           hidden = {"secret_col"}
           readonly = {"created_at"}
           protected = {"owner_id"}
   ```
3. Контракт методов WSRPC: `crud.schema`, `crud.list` ($tabular), `crud.get`, `crud.create`, `crud.update_cell`, `crud.bulk_update`, `crud.delete`.
4. ⚠️ **Безопасность панели (Zero-Leakage 404):**
   - Переход на `http://localhost:8080/crud` вернет **404 Not Found**, если в запросе нет Cookie сессии администратора (`ferro_crud_session` или `ferro_session`). Это защитная мера, а не ошибка роутинга!
   - **Управление паролем администратора:** утилита командной строки `python server.py --set-admin-password [пароль] --login admin` безопасно обновляет пароль в БД (строго DML, PBKDF2-SHA256).
   - **В приложении:** сокеты и панель управления нативно авторизуются по Cookie/JWT (`auto_auth_ws=True`), а при сторонней авторизации поддерживается `set_crud_session_validator(func)`.
   - Подробное руководство: [docs/crud_panel_guide.md](docs/crud_panel_guide.md).
5. **Стандарты разработки GUI и компонентов интерфейса:**
   - **Компонентная модель Svelte 5:** все элементы управления (кнопки, инпуты, селекты, чекбоксы, модальные окна, бейджи) оформляются исключительно как переиспользуемые компоненты Svelte 5.
   - **Типографика и шрифты:** многообразия шрифтов и их размеров быть не должно. Используются стандартный системный шрифт + моноширинный для технических данных и не более 3–4 фиксированных размеров. Наклонный шрифт (курсив) допустим только при крайней необходимости.

---

## 11. SEO & Dynamic Rendering (`pyferro.plugins.seo`)

Автоматическое определение краулеров и отдача SSR HTML с мета-тегами:
```python
from pyferro.plugins.seo import bot_page, render_seo_page

@bot_page("/articles/{slug}")
async def article_seo(slug: str):
    article = await get_article(slug)
    return render_seo_page(
        title=article.title,
        description=article.summary,
        og_image=article.cover_url
    )
```

---

## 12. Аутентификация и управление паролями (Frontend & Backend)

Подробное руководство: [docs/auth_guide.md](file:///home/alex/PyFerro/docs/auth_guide.md).

1. **Формат хэширования паролей в БД:**
   - Канонический стандарт: **PBKDF2-SHA256** с Base64 кодированием соли и ключа:
     `pbkdf2_sha256$<iterations>$<salt_b64>$<key_b64>`
   - Любые отклонения (хранение в hex, двоеточие `:` вместо `$`, сырой текст) приводят к ошибке «пароль не совпадает».
   - Утилита командной строки: `python server.py --set-admin-password [пароль] --login admin`.
2. **Контракт RPC-методов (Default Deny):**
   - Все методы с префиксом `login.` (`login.submit`, `login.get_key`, `login.refresh`, `login.whoami`) автоматически открыты неавторизованным гостям.
   - Любые кастомные методы вроде `auth.login` или `user.login` **обязаны** иметь `@app.rpc("auth.login", public=True)`, иначе гость получит `RPCError(-32000, "Permission Denied")`.
3. **Авторизация сокета и сессия:**
   - При успешном входе хендлер устанавливает `session.data = AuthSession(...)` (или через `current_transport_ctx.get().data`).
   - Для администраторов обязательно вызывать `create_crud_session(user_info, token=token)` для открытия `/crud`.
   - При реконнекте сервер автоматически авторизует сокет по Cookie (`auto_auth_ws=True`).
4. **Фронтенд и шлюз `authInterceptor` (Gatekeeper):**
   - В клиенте `client/wsrpc.ts` настроен шлюз `authInterceptor`. Он удерживает отправку бизнес-запросов до восстановления сессии.
   - Токен сессии обязательно сохраняется в `document.cookie` (`ferro_session`, `ferro_crud_session`) для HTTP/SSO и в `localStorage` (`refresh_token`).

---

## 13. Работа с базой данных и системными операциями (`pyferro.db`)

Подсистема базы данных экспортирует `engine`, `Base`, `async_session`, а также высокоуровневые контекстные менеджеры для выполнения системных запросов, кронов, миграций и фоновых задач в обход Row-Level Security (RLS):

```python
from pyferro import system_db_session, system_bypass
from sqlalchemy import select

# 1. Автономная асинхронная сессия БД со встроенным системным обходом RLS:
@app.rpc("tasks.cleanup")
async def tasks_cleanup():
    async with system_db_session() as db:
        stmt = select(Task).where(Task.status == "archived")
        tasks = (await db.execute(stmt)).scalars().all()
        # Изменения сохраняются штатно
        await db.commit()
    return {"status": "ok"}

# 2. Обход RLS для блока кода в уже открытой сессии:
with system_bypass():
    user = await User.get_permissions_by_id(db, user_id)
```

⚠️ **Анти-паттерн:** Ручное управление `token = system_bypass_ctx.set(True) ... try / finally: system_bypass_ctx.reset(token)`. Всегда используйте `system_db_session()` или `with system_bypass():`.

---

## 14. 🚫 КРИТИЧЕСКИЕ АНТИ-ПАТТЕРНЫ (Anti-Hallucination Guardrails)

1. ❌ **НЕ ИМПОРТИРУЙТЕ `fastapi`, `starlette` или ASGI-модули.**
   - Сервер работает на **Granian RSGI**, где `scope.proto` — `"http"` или `"websocket"`.
2. ❌ **НЕ ПИШИТЕ `await ws.send_json(...)` или `await ws.send_bytes(...)`.**
   - В WSRPC хендлеры просто делают `return dict_or_list`! Фреймворк сам упакует результат в JSON-RPC 2.0 response.
   - Если нужно отправить сообщение в сокет напрямую, используйте безопасный метод `await session.send_str(payload_str)`.
3. ❌ **НЕ ДЕЛАЙТЕ синхронный блокирующий I/O в async-функциях.**
   - Для тяжелых синхронных вызовов (хэширование, RSA, чтение файлов) используйте `await asyncio.to_thread(...)`.
4. ❌ **НЕ ЗАПУСКАЙТЕ `workers > 1` без распределенного бэкплейна.**
   - In-memory структуры (активные сокеты `ACTIVE_SESSIONS_SET`, кэш-версии) изолированы в процессах ОС. Для масштабирования используйте шину `BaseBackplane` (Redis/Postgres).
5. ❌ **НЕ ИСПОЛЬЗУЙТЕ устаревший `asyncio.iscoroutinefunction`.**
   - Используйте `inspect.iscoroutinefunction(func)` (совместимо с Python 3.11–3.14+).
6. ❌ **НЕ ЗАБЫВАЙТЕ про `public=True` для публичных методов.**
   - Если метод должен быть доступен неавторизованному гостю и не начинается с `login.`, всегда указывайте `@rpc_method("name", public=True)`.
7. ❌ **НЕ ЗАБЫВАЙТЕ `@functools.wraps(func)` в кастомных декораторах хендлеров.**
   - При создании декораторов всегда используйте `@wraps(func)`, чтобы механизм unwrapping и auto-mapping сигнатур корректно извлекал параметры.
8. ❌ **КОСТЫЛИ И MONKEY-PATCHING НЕДОПУСТИМЫ НИКОГДА.**
   - Категорически запрещено делать обходные заплатки в прикладном коде или примерах (`_orig = Cls.method; Cls.method = _hack`).
   - Любая проблема (роутинг, протокол, контракты интерфейсов) должна решаться **системно и нативно** в кодовой базе самой библиотеки с последующим бампом версии.
   - Код в `examples/` обязан быть эталонно чистым, лаконичным и идиоматичным.
9. 🎯 **ПОЛНОТА И НАГЛЯДНОСТЬ ПРИМЕРОВ (Showcase Completeness).**
   - Любая функциональность, реализованная во фреймворке (разделение доступа RLS, 2PC-загрузка файлов, Smart Cache, динамические роли и права в БД, стриминг, Reverse RPC), **обязана быть доходчиво, интерактивно и наглядно представлена в `examples/showcase`**.
   - Если фича есть в коде библиотеки, но её нельзя опробовать на демонстрационном стенде в браузере в один клик — реализация считается неполной. Стенд — это живая спецификация платформы.
10. 📦 **ОБЯЗАТЕЛЬНЫЙ РЕЛИЗ НА PYPI ПРИ ИЗМЕНЕНИИ БИБЛИОТЕКИ.**
   - Если изменен код самой библиотеки (`pyferro/`), **всегда обязательно бампится версия (`pyproject.toml`, `pyferro/__init__.py`) и публикуется новый релиз на PyPI**. Пользователь должен всегда иметь актуальную версию пакета без рассинхрона между репозиторием и PyPI.
11. 📋 **ВЕДЕНИЕ И ОБЯЗАТЕЛЬНОЕ ЧТЕНИЕ БЭКЛОГА (`NEXT_RELEASE.md`).**
   - Любые выявленные задачи на следующий релиз (рефакторинг, удаление рудиментов, новые фичи) немедленно заносятся в [NEXT_RELEASE.md](NEXT_RELEASE.md).
   - **Перед каждым бампом версии и публикацией пакета в PyPI агент ОБЯЗАН прочитать `NEXT_RELEASE.md`** и учесть/закрыть запланированные пункты перед релизом.
12. 🛑 **ЕСТЬ ДИССОНАНС, ЗНАЧИТ МЫ НЕ НА САМОМ ВЕРНОМ ПУТИ. ПОЭТОМУ СПРАШИВАЙ!**
   - Если при взгляде на задачу, код или ошибку возникает малейший внутренний диссонанс, ощущение «что-то тут не так» или противоречие между архитектурой и кодом — **это 100% сигнал, что мы не на самом верном пути**.
   - Категорически запрещено глушить диссонанс, действовать на автопилоте или замазывать проблему локальными заплатками / костылями.
   - **Поэтому спрашивай:** немедленно остановись, честно изложи пользователю сомнения и диссонанс, и спроси перед тем, как совершать действия.
13. 🚫 **НЕ РЕДАКТИРОВАТЬ БИБЛИОТЕЧНЫЕ ФАЙЛЫ СПОНТАННО / КОГДА ЗАХОЧЕТСЯ.**
   - Костылей не делать, но и библиотечные файлы (`pyferro/`, `client/`) запрещено редактировать бесконтрольно, спонтанно или на скорую руку.
   - Всегда проверять, нет ли уже готового канонического инструмента в репозитории (например, канонический клиент `client/wsrpc.ts` вместо создания ad-hoc дубликатов).
   - Любые изменения в кодовой базе библиотеки должны быть осознанными, системными и архитектурно выверенными.
14. ❌ **НЕ ГОВОРИТЕ О ТОМ, ЧЕГО НЕТ В КОДЕ.**
   - Запрещено выдумывать несуществующие параметры и роуты (вроде `dev_admin=True` или `/dev-admin` — их нет в проекте). Опирайтесь строго на то, что реально реализовано в кодовой базе.
15. 📚 **СТАНДАРТЫ ДОКУМЕНТАЦИИ: SINGLE SOURCE OF TRUTH И ПРИНЦИП БЛИЗНЕЦОВ.**
   - Каждая сущность (клиент `client/wsrpc.ts`, плагин, протокол) имеет **ровно один канонический документ**. Запрещено дублировать простыни кода и API в другие документы — используйте краткую выжимку и прямую ссылку.
   - Разделение зон ответственности: клиентские руководства пишутся для UI-разработчиков (TS/JS, Svelte, React, Vue, DOM) без бэкенд-кишок (DML, SQLAlchemy, RSGI); серверные — для бэкендеров.
   - Принцип близнецов: вся документация ведется строго синхронно в `docs/` (EN) и `docs_ru/` (RU) с идентичной структурой файлов.
16. 🤖 **ОБЯЗАТЕЛЬНЫЙ ИИ-ПРОМТ МИГРАЦИИ ДЛЯ КАЖДОГО РЕЛИЗА (AI Migration Prompt).**
   - При каждом релизе, затрагивающем схему БД, модели или контракты фреймворка, создается готовый структурированный промт для ИИ-ассистентов (Cursor, Antigravity, Claude, Copilot).
   - Промт содержит пошаговый алгоритм: аудит кода, бэкап БД, миграции DDL/DML, правки моделей и проверку работоспособности. Разработчик прикладного проекта должен иметь возможность скопировать этот промт в свой ИИ и обновить приложение в один клик.





