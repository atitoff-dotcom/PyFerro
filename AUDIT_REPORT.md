# Аудит ядра PyFerro 0.5.12

Метка: ✅ = подтверждено запуском кода (PoC), 📖 = по чтению кода.
Код `PL3_3` и `examples/` не аудировались. Исправления в код не вносились.

## CRITICAL

### 1. ✅ Эскалация привилегий user → admin через CRUD
- **Где:** `pyferro/plugins/crud/handlers.py`: `handle_crud_update_cell` (m2m-ветка ~L377-405) и `handle_crud_create` (~L611-662). `identity.py:160-165` `DefaultIdentityProvider.has_permission` разрешает любые действия любому авторизованному. `registry.py` `register_auth_models()` публикует `User`/`Role`/`RpcPermission`.
- **Сценарий:** пользователь с RPC-правом `crud.update_cell` шлёт `{model:"User", id:<свой>, field:"roles", value:["admin"]}`. В PoC роли стали `['admin']`. `crud.create User roles:["admin"]` создал нового админа.
- **Фикс:**
  - в m2m-ветке вызвать `policy.scope(ctx, meta, "update", db)`, как в обычной ветке;
  - `has_permission` сделать default-deny;
  - `User.roles`, `Role.*`, `RpcPermission.*` добавить в `protected` и закрыть модели для не-админов.

### 2. ✅ `crud.lookup` без проверки прав и RLS
- **Где:** `handlers.py:682-711`.
- **Сценарий:** не-админ получает список всех логинов (PoC-D). Работает для любой зарегистрированной модели.
- **Фикс:** применить тот же `policy.scope(..., "read", ...)` и проверку `has_permission`, что и в `crud.list`.

### 3. 📖 Известный `secret_key` по умолчанию
- **Где:** `core/lib/config.py:87`, `core/security.py:14-29`: fallback `"dev-insecure-secret-key-change-in-production"`, только warning.
- **Сценарий:** любой подделывает JWT с `roles:["admin"]` → `/crud` и WS superadmin (`allowed_rpc_methods={"*"}`).
- **Фикс:** без явного ключа в проде не стартовать. Минимум: `secrets.token_urlsafe(48)` на процесс.

### 4. ✅ `login.secure` полностью сломан: нет `import base64`
- **Где:** `core/security.py` (`decrypt_rsa`, `hash_password`).
- **Сценарий:** любой RSA-логин даёт `NameError`, обработчик превращает его в «Ошибка расшифровки пароля» (PoC-A).
- **Фикс:** `import base64` + тест.

### 5. ✅ Logout ничего не отзывает
- **Где:** `auth/handlers.py:433-454` `handle_logout`: `getattr(session,"data")`, но в хендлер приходит `AuthSession` без `.data`, так что `db_id=None`. JWT без привязки (`jti` отбрасывается). `app.py:255-330` `_auto_authenticate_ws` не проверяет отзыв и не перечитывает роли из БД.
- **Сценарий:** после `auth.logout` refresh-токен остался в БД, `login.refresh` им успешен, JWT валиден (PoC-E). Украденная кука жива до TTL.
- **Фикс:**
  - брать `session_db_id` из `AuthSession`;
  - удалять refresh-токен;
  - хранить `jti` в `ActiveSession` и проверять в `_auto_authenticate_ws`;
  - ротировать refresh-токен при использовании.

### 6. ✅ PBKDF2 (600k) синхронно в event loop
- **Где:** `auth/handlers.py:310` (`verify_password`), `:519` (регистрация), `models.py:403-448`.
- **Сценарий:** ≈108 мс на проверку, 5 проверок = 0.54 с, лаг цикла ~99 мс. Один сокет шлёт 30 `login.submit`/с и сервер встаёт. Лимитов на перебор нет. Неизвестный логин отвечает быстрее известного (user enumeration).
- **Фикс:** `await asyncio.to_thread(...)`. Для неизвестного пользователя всё равно считать dummy-хэш. Добавить простой лимит попыток на IP/логин.

### 7. 📖 `/upload` без аутентификации
- **Где:** `plugins/files/upload.py:390-515`, `files/handlers.py` (`files.init_upload/commit/rollback` — `public=True`), `/auth-check-upload` читает только куку `rpc_jwt`, роль не проверяет. `current_user_ctx` для HTTP не выставляется.
- **Сценарий:** аноним заполняет диск по 250 МБ за запрос (CORS `*`). Ошибка отдаёт `f"Upload failed: {str(e)}"` (L510).
- **Фикс:** валидировать JWT внутри `upload_handler`. Убрать `public=True` у init/commit/rollback. Вместо `str(e)` отдавать общий текст.

## HIGH

### 8. ✅ `_handle_websocket`: `UnboundLocalError` и утечка сессии
- **Где:** `app.py:501-531`. `JsonRpcSession.__init__` кладёт сессию в `ACTIVE_SESSIONS_SET`.
- **Сценарий:** если `accept()`/`_auto_authenticate_ws` бросит исключение, `except` обращается к непривязанной `session` и падает. `start()` не вызывается, `close()` тоже: сессия остаётся в `ACTIVE_SESSIONS_SET` и получает рассылки.
- **Фикс:** `session = None` до `try` и `finally: if session: await session.close()`. Либо регистрировать в `start()`.

### 9. ✅ Каждый `login.*` на сокете плодит ActiveSession и колбэки
- **Где:** `auth/handlers.py`, `register_on_close(cleanup_app_session)`.
- **Сценарий:** 5 refresh на одном сокете = 5 колбэков, после закрытия в БД остаётся 4 строки `ActiveSession` (PoC-F). Утечка строк, сессии «навсегда» онлайн.
- **Фикс:** хранить один db_id на сессию. Перед созданием новой удалять старую и не регистрировать колбэк повторно.

### 10. ✅ Клиентский `response` с unhashable `id`
- **Где:** `core/session.py`, обработка ответа клиента (`_pending_requests.pop(id)`).
- **Сценарий:** пока висит reverse-RPC, клиент шлёт `{"id":[1],"result":1}` → `TypeError`, `start()` падает, сессия умирает (PoC-G). Без pending-запросов не воспроизводится.
- **Фикс:** `if not isinstance(id_, (str,int)): ignore/-32600` перед `pop`.

### 11. 📖 Конфиги не доходят до кода
- **Где:** `FerroApp(max_message_size=...)` кладёт значение в `settings.max_message_size`, а `session.py:244` читает `settings.security.get("max_message_size")`. Аналогично `max_upload_size` (хардкод 262144000).
- **Сценарий:** админ ограничил размер, а действует 10 МБ. GUI показывает неверное значение.
- **Фикс:** читать из одного места. Лимит сообщения проверять до `json.loads`.

### 12. ✅ XSS в SEO JSON-LD
- **Где:** `plugins/seo/renderer.py:131-132`.
- **Сценарий:** `title="</script><script>alert(1)</script>"` попадает в `<script type="application/ld+json">` без экранирования.
- **Фикс:** `.replace("<", "\\u003c")` у результата `orjson.dumps`. `body_html` вставляется как есть (задокументировать).

### 13. 📖 `has_perm=True` по умолчанию (fail-open)
- **Где:** `core/session.py:331-353`. Если у данных сессии нет ни `has_rpc_permission`, ни `allowed_rpc_methods`, доступ остаётся открытым.
- **Сценарий:** кастомный `session.data` (сторонняя авторизация) получает доступ ко всем методам.
- **Фикс:** начальное значение `has_perm=False`.

### 14. 📖 Нет проверки `Origin` у WebSocket (CSWSH)
- **Где:** `app.py` `_handle_websocket`; кука автоматически авторизует сокет (`auto_auth_ws`).
- **Сценарий:** вредоносная страница открывает WS на ваш хост, браузер прикладывает куку (при `SameSite=None`/старых браузерах). Дальше RPC от имени жертвы.
- **Фикс:** сверять `Origin` с `cors_origins`/хостом до `accept()`. Куки ставить с `SameSite=Lax/Strict`.

### 15. 📖 Старт с полуинициализированным состоянием
- **Где:** `core/lifecycle.py` `run_startup_callbacks` глотает исключения. `sys.exit(1)` в `_rsgi_init_handler` не срабатывает. `on_startup/on_shutdown` дедуплицируются по `__name__`+`__qualname__`, различные функции из разных модулей молча теряются (probe-1).
- **Сценарий:** упала миграция, а сервер поднялся. Это блокер для Safe Evolution Engine (v0.6.3).
- **Фикс:** пробрасывать исключение из startup. Дедуплицировать по `id(func)`/модулю.

## MEDIUM

| # | Где | Проблема | Фикс |
|---|---|---|---|
| 16 📖 | `auth/handlers.py:307` | `or_(login==x, email==x)` + `scalar_one_or_none()`; регистрация `email="alice"` ломает вход «alice» (`MultipleResultsFound`) | валидировать email, уникальность login∪email, `.first()` |
| 17 📖 | OAuth, `oauth_auto_link_email=True` | автопривязка по email без подтверждения; `state` на сервере не проверяется | требовать verified email, проверять `state` |
| 18 📖 | `models.py:425-432` | unsalted SHA-256 fallback, не constant-time, без апгрейда | `hmac.compare_digest` + перехэшировать после входа |
| 19 📖 | `models.py:335` | `is_superadmin` = `role.id==1 or name=="admin"` | только по флагу/имени |
| 20 📖 | `files/service.py:169`, `crud/auth.py:75`, `app.py:283` | JWT разных типов с одним секретом и без `typ/aud`; нечисловой `sub` → `uid=1` | claim `typ`, при ошибке `sub` отклонять |
| 21 📖 | `crud/auth.py:12` | `_ACTIVE_CRUD_SESSIONS` без TTL и вытеснения, роли «заморожены»; refresh-токен регистрируется как CRUD-токен (`handlers.py:209-211`) | TTL/LRU, не регистрировать refresh |
| 22 📖 | `crud/events.py` `notify_crud_change` | `cache.patch` с моделью, id и `by_user` уходит всем, включая гостей | рассылать только авторизованным с правом на модель |
| 23 📖 | `smart_cache/engine.py` | `_persist_versions` — `create_task` без ссылки, версии в БД могут идти назад; `sqlite_insert` для всех БД; `initialize` глотает ошибки и версии сбрасываются в 1; теги из params не ограничены | хранить задачи, `GREATEST`/upsert по диалекту, лимит тегов |
| 24 📖 | `core/session.py` | `_handler_tasks` на сокет не ограничен, пул PG 5+3 (`db/session.py:68-75`) | `Semaphore` на сокет (например 16) |
| 25 📖 | `core/session.py` | `max_message_size` проверяется после `receive()`, считает символы; `send_request` ждёт весь timeout при ошибке отправки; исключения `_close_tasks` не забираются | проверять размер раньше, ловить ошибку отправки, `gather(return_exceptions=True)` |
| 26 📖 | `files/service.py:41-83` | `commit_upload`: сначала ФС, потом БД; ошибка БД глотается, RPC отвечает `committed`; `cleanup_stale` нигде не вызывается; запись чанков синхронная в loop | сначала БД, ошибки наружу, периодическая очистка, `to_thread` |
| 27 📖 | refresh-токены | хранятся в открытом виде, без ротации | хранить `sha256(token)`, ротировать |
| 28 📖 | `crud/identity.py` | `is_superuser` берётся из куки транспорта, а не из `session.data` | брать только из `session.data` |

## LOW

- `crud/static_handler.py:104` — `startswith` без разделителя пути (соседняя `static_*` проходит).
- `app.py` CORS: список `cors_origins` склеивается через ", " (невалидный ACAO). `index.html` отдаётся с `max-age=3600`.
- Логирование пользовательского ввода без экранирования (log injection). `db_echo` пишет параметры запросов.
- `--set-admin-password <pwd>` виден в `ps`; читать из `getpass`/stdin.
- `asyncio.create_task` без ссылки: `notify_session_change`, `MemoryBackplane.publish`, `_persist_versions`.
- `plugins/raw_ws/manager.py` использует `scope.get("path")` на объекте Scope Granian (вероятно не работает), нет лимитов.
- `backplane_url` и `MemoryBackplane` в broadcast не используются (мёртвый код).

## Рекомендуемый порядок
1. **Однострочники:** `import base64` (#4), экранирование JSON-LD (#12), `session=None` + `finally` (#8), проверка типа `id` (#10), `has_perm=False` (#13).
2. **Безопасность CRUD и auth:** #1, #2, #5, #6, #3.
3. **Upload и лимиты:** #7, #11, #24.
4. **Lifecycle (#15):** до Safe Evolution Engine.

> [!NOTE]
> Правки в `pyferro/` требуют по AGENTS.md: прочитать `NEXT_RELEASE.md`, поднять версию (`pyproject.toml`, `pyferro/__init__.py`) и выпустить на PyPI.
