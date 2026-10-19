# 🧭 PROJECT_STATE.md — Архитектурный канон PyFerro (Cold-Start Guide)

> **Назначение:** Единая точка входа для быстрого старта ИИ-агента (читается за 1 вызов `agentbox view PROJECT_STATE.md --start 1 --end 80`).

## 1. Профиль и стек
- **Проект:** `PyFerro` (текущая версия в `pyproject.toml` / `pyferro/__init__.py`: `0.7.0`).
- **Сетевой слой:** Rust RSGI сервер **Granian** (`interface=rsgi`, не ASGI/WSGI).
- **Протокол:** Симметричный **JSON-RPC 2.0 (WSRPC)** поверх WebSocket + HTTP роутинг + табличное сжатие **RFC 0002 (`$tabular`)**.
- **Данные и UI:** SQLAlchemy 2.0 Async (`aiosqlite` / `asyncpg`) + встроенная админ-панель **Svelte 5** (`/crud`).

## 2. Карта репозитория
- `pyferro/app.py` — главный класс `FerroApp` (точка входа RSGI, конфигурация, статика Zero-Copy, WebSocket, CLI-перехват).
- `pyferro/core/` — ядро протокола:
  - `session.py` — `JsonRpcSession`, декоратор `@rpc_method`, `RPCError`, реестр `RPC_REGISTRY`, `ACTIVE_SESSIONS_SET`, `ContextVar`-контексты.
  - `http.py`, `router.py`, `tabular.py`, `security.py`, `lifecycle.py`, `logger.py`, `constants.py`, `lib/config.py` (`Settings`, `configure`).
- `pyferro/db/` — `Base`, `engine` (`AsyncEngineProxy`), `async_session`, `system_db_session()`, `system_bypass()`, `naming.py` (префикс системных таблиц).
- `pyferro/auth/` — `RowSecureModel`, `AuthSession`, модели (`User`, `Role`, `Team`, `RpcPermission`, `RolePermission`, `UserPermission`, `UserDelegation`, `ActiveSession`, `RefreshToken`, `OAuthAccount`), RLS-перехватчики (`security.py`), `discovery.py` (авто-синк RPC и кэш гостя), `handlers.py` (`login.*`, OAuth VK/Yandex), `permission_handlers.py` (`permissions.*`).
- `pyferro/smart_cache/` — реактивная инвалидация кэша по тегам (`@invalidates`, `version_registry`, `cache.invalidate` / `cache.patch`).
- `pyferro/broadcast.py` — рассылки `broadcast_notification`, `send_to_user`, `send_to_role`.
- `pyferro/plugins/` — прикладные расширения:
  - `crud/` — движок авто-админки (`ModelRegistry`, `handlers.py`, `admin_handlers.py`, `policy.py`, `identity.py`, `frontend/` на Svelte 5 и скомпилированный `static/`).
  - `files/` — двухфазная (2PC) потоковая загрузка файлов (`upload.py`, `service.py`, `handlers.py`).
  - `seo/` — SSR для поисковых ботов (`@bot_page`, `sitemap.xml`, `IndexNow`).
  - `raw_ws/` — нативные бинарные/текстовые WebSocket-потоки в обход JSON-RPC (`@raw_ws_route`).
- `client/` — канонический TypeScript-клиент `wsrpc.ts` (включая `AuthStore`) и `smartCache.ts`.
- `examples/showcase/` — живой эталонный стенд со всеми подсистемами.
- `docs/` (EN) и `docs_ru/` (RU) — документация по принципу близнецов (строго 1-в-1).

## 3. Ключевые архитектурные инварианты
1. **Импорты первого уровня:** базовые подсистемы импортируются напрямую из `pyferro.{db, auth, broadcast, smart_cache}` (старые прокси в `pyferro.plugins.*` и `pyferro/compat.py` удалены).
2. **Изоляция системных таблиц (`pf_`):** все 17 таблиц фреймворка имеют префикс `pf_` по умолчанию (`pf_auth_user`, `pf_auth_role`, `pf_cache_tag_versions`, `pf_file_metadata` и т.д.). Настраивается через `FerroApp(table_prefix=pf_)` и `pyferro/db/naming.py`. `ModelRegistry.get()` резолвит модели как по имени класса (`User`), так и по `pf_auth_user` / `auth_user`.
3. **Роль `guest` и Default Deny (Zero Special Cases):** параметр `public=True` и колонка `is_public` упразднены. Неавторизованный сокет имеет системную роль `guest`. На чистой БД гостю открыты только `login.*`. Остальные RPC и чтение таблиц открываются через роль `guest` в БД (кэшируются в `GUEST_ALLOWED_RPC_METHODS` и `GUEST_ALLOWED_CRUD_MODELS`).
4. **CQRS для гостей в CRUD:** гостям разрешены только `crud.schema`, `crud.list`, `crud.get` для таблиц с `can_read=True` у роли `guest`. Любые мутации (`create`/`update`/`delete`) для гостей аппаратно заблокированы (`-32003`).
5. **Гранулярный RLS и Делегирование:** в `RowSecureModel` поле `creator_id` — неизменяемый автор, `owner_id` — текущий ответственный. Права задаются флагами `read_global`, `update_global`, `delete_global` (вместо удаленного `row_level_only`). Модель `UserDelegation` дает временный доступ заместителю к записям замещаемого без `UPDATE` самих записей.
6. **Системный обход RLS:** любые внутренние/служебные запросы фреймворка к БД выполняются строго внутри `async with system_db_session() as db:` (или `with system_bypass():`).

## 4. Тестирование и сборка
- **In-memory unit-сьюты (`tests/suites/`):** автономные тесты ядра (`test_app.py`, `test_crud.py`, `test_crud_granular_and_delegation.py`, `test_dx_improvements.py`, `test_guest_cqrs_crud.py`, `test_http_utils.py`, `test_raw_ws.py`, `test_rpc_permissions.py`, `test_seo.py`, `test_session_features.py`, `test_table_prefix.py`, `test_admin_cockpit.py`).
- **E2E раннер (`python tests/run.py`):** сьюты `auth`, `forum`, `smart_cache`, `load` требуют запущенного сервера на `127.0.0.1:8080`.
- **Сборка фронтенда админки:** `npm --prefix pyferro/plugins/crud/frontend run build` (обновляет бандл в `pyferro/plugins/crud/static/`).

## 5. Обязательные регламенты
- [AGENTS.md](AGENTS.md) — контракты `@rpc_method`, стандарт docstrings, запрет костылей/monkey-patching, синхронность `docs/` и `docs_ru/`, публикация в PyPI.
- [NEXT_RELEASE.md](NEXT_RELEASE.md) — бэклог и чеклист задач (обязателен к чтению перед бампом версии).