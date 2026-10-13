# План задач к следующему обновлению (NEXT_RELEASE.md)

> **Внимание ИИ-ассистентов и разработчиков:**  
> Этот файл является обязательным бэклогом задач для следующего релиза.  
> **ПЕРЕД ЛЮБЫМ БАМПОМ ВЕРСИИ И ПУБЛИКАЦИЕЙ В PYPI ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ ЭТОТ ФАЙЛ**, реализовать запланированные в нем задачи или учесть их. Новые задачи и идеи по рефакторингу/улучшениям сразу заносятся сюда.

---

## 📌 Запланировано к следующему релизу (Backlog)
> Подробный концептуальный манифест и спецификация: [docs_ru/roadmap_future_architecture.md](docs_ru/roadmap_future_architecture.md) ([EN](docs/roadmap_future_architecture.md)).

* [ ] **v0.6.0: Автогенерация TypeScript-типов (`pyferro codegen`) и CLI разработчика (`pyferro cli`):**
  - **`pyferro codegen [app] -o [path]`**: автоматическая генерация `ferro.d.ts` со схемами моделей SQLAlchemy (`ModelRegistry`), строгой типизацией вызовов `rpc.call(method, params)` и распаковкой `@tabular_response`.
  - **Консольный CLI `pyferro` в `[project.scripts]`**: команды `pyferro rpc list` (аудит ролей, CASL и docstrings), `pyferro models list`, `pyferro admin create/set-password`.
* [ ] **v0.6.1: Декларативные хуки в моделях (`@crud_hook`) и In-Memory тестировщик (`FerroTestClient`):**
  - **Хуки жизненного цикла в CRUD**: поддержка `before_create`, `after_create`, `before_update`, `before_delete` в `class Crud` моделей без необходимости переопределять обработчики вручную.
  - **Легковесный `FerroTestClient(app)`**: тестирование RPC-методов, middleware, CASL и сессий в памяти без сетевого оверхеда со скоростью >10 000 req/sec.
* [ ] **v0.6.2: Декоратор `@transactional` с авто-откатом при дисконнекте:**
  - Автоматическое управление `AsyncSession` (commit/rollback) и интеграция с `session.register_on_close` для мгновенного отката транзакций при обрыве соединения сокета клиентом.
* [ ] **v0.6.3: Движок безопасных версионных обновлений (Safe Evolution Engine & GUI Upgrade Wizard):**
  - **Спецификация:** [docs_ru/safe_evolution_guide.md](docs_ru/safe_evolution_guide.md) ([EN](docs/safe_evolution_guide.md)).
  - **Нативный теневой снимок через `VACUUM INTO`**: мгновенный бэкап SQLite без блокировки читателей перед выполнением любых миграций.
  - **Аварийный откат (Instant Disaster Recovery)**: физическая подмена файла за <1 сек при любых ошибках, падении питания или Ctrl+C.
  - **State Machine и Recovery Safe-Mode**: автоматический переход в `RECOVERY_REQUIRED` при расхождении версий, отдача 503 гостям и открытие мастера обновления в `/crud`.
  - **WSRPC Streaming & Task Manager**: фоновый `UpgradeTaskManager`, неубиваемый при закрытии вкладки или потере Wi-Fi, со стримингом прогресса 0..100% в админку Svelte 5.
  - **Контракт версионных скриптов**: функции `pre_check()`, `upgrade()` (Expand & Contract) и зеркальный `downgrade()`.

---

## ✅ Выполнено в текущем релизе / подготовке:
* [x] **v0.5.13: Security Hardening, Code Optimization & Zero-Vulnerability Core Hotfix:**
  - **Защита CRUD и предотвращение эскалации привилегий:** системные модели безопасности (`User`, `Role`, `RpcPermission`) закрыты от изменения через CRUD для не-суперпользователей; Many-to-Many связи в `crud.update_cell` и `crud.create` теперь строго валидируются через RLS scope и `protected_fields`; метод `crud.lookup` переведен на строгую проверку прав чтения модели и RLS-скоупинг.
  - **Исправление `login.secure` (RSA-вход):** добавлен недостающий `import base64` в `pyferro/core/security.py`, полностью устраняющий `NameError` при расшифровке паролей.
  - **Оптимизация PBKDF2 в Asyncio:** тяжелые вычисления хэшей паролей (600,000 итераций) в `verify_password` и регистрации перенесены в рабочий поток `asyncio.to_thread(...)`, исключая зависания event loop; добавлена фиктивная проверка для защиты от атак по времени (timing enumeration).
  - **Защита эндпоинта `/upload` (Defense in Depth):** встроенная строгая проверка JWT-аутентификации из заголовков `Authorization: Bearer` или защищенных сессионных кук отсекает неавторизованные потоки и заполнение диска до начала стриминга тела; корректно проставляется `owner_id`.
  - **Default Deny для авторизованных сессий:** в `JsonRpcSession._check_permissions` установлен запретительный дефолт `has_perm = False` для любых сессионных данных без явных списков прав.
  - **Надежность WebSocket-сессий:** предотвращен `UnboundLocalError` при сбоях в рукопожатии; блок `finally: if session: await session.close()` гарантирует очистку сессий из `ACTIVE_SESSIONS_SET` при любых исключениях; добавлена валидация типа `rpc_id` для предотвращения `TypeError: unhashable type`.
  - **Корректный отзыв сессий при `auth.logout`:** обеспечено считывание `session_db_id` как из `session.data`, так и напрямую из `session`, что гарантирует удаление привязанных записей `ActiveSession` и `RefreshToken` из базы данных при выходе.
  - **XSS-санитизация в SEO JSON-LD:** экранирование символа `<` (`\u003c`) в `orjson.dumps` предотвращает выход за пределы тега `<script type="application/ld+json">`.
  - **Строгий Lifecycle Startup:** исключения в `run_startup_callbacks` больше не глушатся, а пробрасываются наружу, гарантируя остановку старта воркера Granian при сбоях миграций БД или схемы.
  - **Сокращение кода и ликвидация бойлерплейта (`system_bypass`, `system_db_session`):** введены чистые контекстные менеджеры в `pyferro.db` (`system_db_session()` и `system_bypass()`), устранившие десятки строк ручного управления токенами `system_bypass_ctx.set(...)` и громоздких блоков `try/finally` по всему проекту (`pyferro/auth`, `pyferro/plugins/crud`, `pyferro/cli.py`, `pyferro/app.py`, `pyferro/core/lifecycle.py`).
  - **Интеграция и исправление RSGI Scope в `raw_ws`:** исправлено обращение к атрибуту пути `scope.path` в `dispatch_raw_ws` (для нативных объектов `Scope` Granian), добавлена нативная диспетчеризация маршрутов `RAW_WS_ROUTES` в `FerroApp._handle_websocket`.

* [x] **v0.5.12: Чистая архитектура первого уровня и полное удаление легаси-прокси плагинов (Zero Technical Debt):**
  - **Полное удаление устаревших прокси-каталогов `pyferro.plugins.{db,auth,broadcast,smart_cache}`:** исключен легаси-балласт и паразитное дублирование импортов.
  - **Единый стандарт ядра:** все базовые подсистемы теперь импортируются строго из первоуровневых модулей (`pyferro.db`, `pyferro.auth`, `pyferro.broadcast`, `pyferro.smart_cache`).
  - **Каталог `pyferro.plugins` очищен:** содержит только прикладные специализированные расширения-инкубаторы (`crud`, `files`, `seo`, `raw_ws`).

* [x] **v0.5.11: Поддержка OAuth-провайдеров, nullable-полей БД и универсальных UI-алиасов в `client/wsrpc.ts`:**
  - **Поддержка `email?: string | null` в `AuthUser`:** устранена ошибка строгой типизации TypeScript при возврате `null` из SQL-баз данных при регистрации через OAuth/телефон.
  - **Публичный метод `auth.setSession(res)`:** удобная идиоматичная фиксация сессии при альтернативных сценариях входа (OAuth 2.0, VK ID, Яндекс ID, Google, Telegram Login Widget, SMS, Passkeys). Атомарно сохраняет Cookies (`ferro_session`, `ferro_crud_session`, `rpc_jwt`), обновляет `localStorage` и реактивный `userStore`.
  - **Универсальные алиасы идентификаторов и профиля (`id`, `uid`, `avatar`, `photo_url`):** нормализация данных пользователя через метод `normalizeUser()` гарантирует совместимость с UI-библиотеками (Svelte, React, Vue), роутерами и таблицами как при первичном входе, так и при автоматическом восстановлении сессии по Cookie (`restoreSession` / `login.whoami`).
  - **Синхронизация документации:** обновлены руководства `docs/client_guide.md` и `docs_ru/client_guide.md` с наглядными примерами интеграции сторонних методов авторизации.
  - **Безопасный спавн воркеров Granian в `app.run()` (`_granian_target_loader`):** устранена ошибка `TypeError: expected string or bytes-like object, got 'FerroApp'` при запуске сервера через `app.run()`. Granian в `server.serve(target_loader=...)` теперь получает канонический загрузчик, прозрачно поддерживающий как готовый экземпляр `FerroApp`, так и строковый путь цели.
  - **Атомарное создание сущностей с Many-to-Many связями в `crud.create`:** устранена ошибка `(sqlalchemy.exc.MissingGreenlet) greenlet_spawn has not been called` при создании записей (например, `User` с ролями). M2M-объекты теперь разрешаются и связываются с транзиентной сущностью до добавления в сессию и `db.flush()`, а идентификатор записи считывается без избыточного вызова `db.refresh(obj)`.
  - **Промоушен базовых подсистем в модули первого уровня (`pyferro.db`, `pyferro.auth`, `pyferro.broadcast`, `pyferro.smart_cache`):** зрелые универсальные подсистемы переведены из `plugins/` в ядро фреймворка первого уровня (Django-style architecture). Добавлен нативный метод `await app.broadcast(...)`. Устаревшие прокси-папки `pyferro.plugins.{db,auth,broadcast,smart_cache}` полностью удалены для чистоты архитектуры (Zero Tech Debt). Плагинами остаются только специализированные расширения (`crud`, `files`, `seo`, `raw_ws`).

* [x] **v0.5.10: Zero-Boilerplate Client Auth (`client/wsrpc.ts`), реструктуризация документации (Single Source of Truth) и очистка устаревших RFC:**
  - **Встроенная подсистема `AuthStore<TUser>` в канонический клиент `BinaryWSRPC`:** больше не требуется копировать отдельный файл `auth.ts` на 470 строк в клиентские проекты.
  - **Экспортируемый синглтон `auth`:** прямое использование `import { rpc, auth } from './wsrpc'` или `rpc.auth`.
  - **Атомарная синхронизация сессии:** автоматическая запись и очистка Cookies (`ferro_session`, `ferro_crud_session`, `rpc_jwt`) и `localStorage.refresh_token`.
  - **Безопасный вход `auth.loginSecure()`:** нативное шифрование пароля через Web Crypto API (RSA-OAEP, SHA-256) без единой внешней NPM-зависимости.
  - **Session Gatekeeper и Auto-Reconnect Sync:** прозрачное удержание бизнес-запросов до восстановления сессии и автоматическая фоновая синхронизация при повторном открытии сокета (`onConnect`).
  - **Реактивность и строгая типизация:** поддержка Svelte store contract (`$auth`, `onChange`), React external store, Vue и параметризация кастомными моделями `BinaryWSRPC<CustomUser>`.
  - **Регламент и стандарты документации:** принят `.agents/rules/documentation_standards.md` и правило 15 в `AGENTS.md`.
  - **Каноническое руководство по клиенту:** созданы близнецы `docs/client_guide.md` (EN) и `docs_ru/client_guide.md` (RU).
  - **Очистка каталога RFC:** удалены 22 файла черновиков и фантомов из `docs/rfc/` и `docs_ru/rfc/`, исключая рассинхрон с кодом; очищены `docs/auth_guide.md` и `docs_ru/auth_guide.md` от дублирования.

* [x] **v0.5.9: Конфигурируемый `session_prefix` в `FerroApp`, полная обратная совместимость кук (`rsgi_*`, `rpc_jwt`) и прозрачная SSO-авторизация администратора в `/crud`:**
  - **Конфигурируемый `session_prefix` в `FerroApp` (по умолчанию `'ferro'`):**
    - В `FerroApp(session_prefix='ferro')` и `configure(session_prefix=...)` добавлен параметр префикса сессионных кук для изоляции приложений на одном хосте/домене.
    - Имена кук на выдачу: `{prefix}_session`, `{prefix}_crud_session`, `{prefix}_jwt`.
  - **Универсальное извлечение кук с обратной совместимостью (`Robustness Principle`):**
    - Реализованы утилиты `extract_cookies`, `get_session_cookie_names`, `extract_session_token` в `pyferro.core.http`.
    - Сервер проверяет сначала сконфигурированный префикс, а затем автоматически подхватывает исторические и универсальные токены: `ferro_crud_session`, `ferro_session`, `ferro_jwt`, `rsgi_crud_session`, `rsgi_session`, `rsgi_jwt`, `rpc_jwt`, `token`.
    - Устранен ложный `404 Not Found` на `/crud` при логине из существующих клиентских приложений.
  - **Автоматическая регистрация администратора в CRUD-сессиях:**
    - При входе через `login.submit` (`pyferro.plugins.auth.handlers`) администратор автоматически регистрируется в реестре `create_crud_session` как по `jwt_token`, так и по `rt_obj.token`.
  - **Информативная отладка Zero-Leakage:**
    - В обработчик `/crud` добавлено детальное логирование `logger.debug` с указанием причины отклонения (токен, роль, полученные куки).
  - **Тесты:**
    - Расширены тесты в `tests/suites/test_crud.py` с проверкой всех вариантов кук (`rsgi_crud_session`, `rsgi_session`, `rpc_jwt`).

* [x] **v0.5.8: Масштабирование GUI (+25%), высококонтрастный фокус кнопок, отказоустойчивость сессий администратора в Cockpit:**
  - **Фирменный стиль и официальный логотип PyFerro (Ferro Brick Red):**
    - Создан векторный SVG-логотип PyFerro (монохромный кирпично-красный `Ferro` + верхняя плашка `Py`).
    - Создан компонент `PyFerroLogo.svelte` и применен в шапках CRUD Mission Control (вместо эмодзи `🛡️`) и витрины Showcase (вместо `⚡`).
    - Сгенерирован и подключен адаптивный векторный фавикон `favicon.svg` для браузерных вкладок на `/` и `/crud`.
    - Фирменный кирпично-красный цвет `#b83a28` (светлая тема) и `#c94432` (темная тема) установлен как базовый `primary` акцент интерфейса, кнопок и активных состояний.
  - **Масштабирование и эргономика интерфейса панели управления (+25%):**
    - Пропорциональное увеличение шрифтов, отступов, таблиц и инпутов на 25% через `html { font-size: 125%; }` в `app.css`.
    - Высококонтрастное выделение активных вкладок и кнопок в CRUD и Mission Control Cockpit: зарегистрированы цветовые токены `@theme` в Tailwind v4 (`bg-primary text-primary-foreground font-bold shadow-sm`).
    - Устранены ошибки типизации Svelte 5 / TS в IDE (`svelte.config.js`, `tsconfig.json`).
  - **Отказоустойчивость проверки прав администратора (`_ensure_admin`):**
    - Исправлена ошибка в `pyferro/plugins/crud/admin_handlers.py`, возникавшая когда в RPC-хендлер первым аргументом приходил уже сам объект данных `AuthSession` / `DemoSessionData`, не имеющий вложенного `.data`.
    - Унифицирована проверка прав администратора для сокет-сессий `JsonRpcSession` и объектов контекста `AuthSession` / `DemoSessionData` / `dict`.
    - Точная идентификация текущей сессии (`is_current: true`) в `list_active_sessions` и `kill_session` через `current_transport_ctx.get()`.
  - **Надежная SSO-авторизация и JWT-сессии в демонстраторе (`examples/showcase`):**
    - В методе `auth_login` токен теперь генерируется как криптографический JWT (`create_access_token`) с подписью `SECRET_KEY`, обеспечивая сохранение авторизации администратора в Cookie даже при перезапусках сервера.
    - В `DemoSessionData` добавлены геттеры `role`, `roles` и проверка `has_rpc_permission`.
  - **Информативная диагностика ошибок в Cockpit (`SystemCockpit.svelte`):**
    - Корректное извлечение строковых сообщений об ошибках из JSON-RPC ответа клиента (`wsrpc`).
    - При возникновении ошибок доступа `Unauthorized` отображается понятная плашка с подсказкой о необходимости повторного входа.
    - Исправлен бейдж во вкладке Smart Cache (устранено ошибочное отображение `✅` при сбоях).
    - Пересобран продакшен-бандл GUI в `pyferro/plugins/crud/static/`.
  - **Завершение ребрендинга и зачистка рудиментов `rsgi-wsrpc`:**
    - Все оставшиеся упоминания старого рабочего имени `rsgi-wsrpc` и `rsgi_wsrpc` заменены на канонический `PyFerro` / `pyferro` в докстрингах и комментариях всех официальных модулей (`core/`, `plugins/crud`, `plugins/auth`, `plugins/db`, `plugins/seo`, `plugins/smart_cache`).
    - Исправлен и переведен на `pyferro` пример `examples/seo_app.py` (импорты, HTML-заголовки, баннер запуска).
    - Обновлен заголовок User-Agent `pyferro-auth/1.0` в `pyferro/plugins/auth/handlers.py`.
    - Обновлен `package.json` админки (`pyferro-crud-frontend`), скрипты бенчмарков (`scripts/benchmark.py`), аудита безопасности (`scripts/security_audit.py`), генерации документации (`scripts/build_docs.py`), тесты (`tests/suites/test_raw_ws.py`), `docs/security_and_performance.md` и `LICENSE`.
* [x] **v0.5.7: Расширение панели управления: Витрина плагинов ядра (Plugin Matrix) и Оперативный пульт горячего управления в GUI (Live Hot-Apply):**
  - **Витрина плагинов платформы (Plugin Matrix Dashboard):**
    - Новый RPC-метод `system.plugin_matrix`: опрашивает и возвращает полную карту состояния официальных плагинов (`db`, `smart_cache`, `crud`, `files`, `seo`, `broadcast`, `auth`).
    - В GUI вкладка «Конфигурация» преобразована в «Параметры и плагины» со стильными карточками модулей, индикаторами активности (🟢 `Активен` / ⚪ `Не подключен`), метриками и быстрыми переходами.
  - **Оперативный пульт горячего управления (Live Hot-Apply):**
    - Новый RPC-метод `system.update_hot_config`: безопасное переключение параметров на лету в оперативной памяти без перезапуска сервера и без обрыва постоянных WebSocket-соединений.
    - Мгновенное переключение уровня логирования (`DEBUG` / `INFO` / `WARNING` / `ERROR`) через `set_runtime_log_level()`.
    - Мгновенное переключение вывода SQL-запросов (SQL Echo) в текущем пуле SQLAlchemy через `set_db_echo()`.
    - Динамическая настройка таймаутов неактивности гостей/пользователей и флага гостевого доступа с валидацией (защита от ошибок).
    - В GUI добавлен интерактивный пульт с бейджами 🟢 *«Hot-Apply (Мгновенно)»* и тост-подтверждением применения.
  - **Инспекция инфраструктуры (Code-First):**
    - Отображение версий Python, ОС, сетевого сервера Granian (Rust RSGI) и протокола WSRPC в режиме Read-Only, предотвращающее случайные сбои запуска сервиса.
  - **Тесты и бандл:**
    - Покрытие новыми тестами в `tests/suites/test_admin_cockpit.py` (89 тестов успешно проходят).
    - Пересобран продакшен-бандл GUI в `pyferro/plugins/crud/static/`.

* [x] **v0.5.6: Ребрендинг в PyFerro (`pyferro` / `FerroApp`), стандартизация Docstring CRUD-методов, защита прав роли Admin и SPA Best Practices:**
  - **Официальный ребрендинг фреймворка в `pyferro`:**
    - Имя пакета на PyPI: `pyferro`.
    - Корневой класс приложения переименован в `FerroApp` (`from pyferro import FerroApp`).
    - Базовый модуль: `pyferro` вместо `rsgi_wsrpc`.
    - Системные cookie обновлены на `ferro_session` и `ferro_crud_session`.
    - Все примеры витрины `examples/showcase` и документация полностью переведены на PyFerro.
  - **Docstrings для всех RPC-методов CRUD (`crud.*`):**
    - Добавлены стандартизированные docstrings (AGENTS.md 3.4) для `crud.schema`, `crud.get`, `crud.list`, `crud.create`, `crud.update_cell`, `crud.bulk_update`, `crud.delete`, `crud.lookup` в `pyferro/plugins/crud/handlers.py`.
    - Полностью устранены предупреждения Service Discovery о методах без docstring.
  - **Защита прав системной роли `admin` в панели управления (CRUD Admin UI):**
    - В таблице ролей для роли `admin` кнопка настройки прав заменена на некликабельный бейдж `🛡️ Полный доступ` (`Full Access`).
    - Устранена иллюзия настройки прав, интерфейс полностью согласован с бэкендовым правилом неизменяемости (`is_immutable=True`).
    - Функция `openPermissions` защищена от открытия модалки для роли `admin`.
    - Пересобран статический бандл автономной панели управления `pyferro/plugins/crud/static/`.
  - **Документация: Руководство по авторизации и разрешению Race Condition в SPA (`docs/auth_guide.md`):**
    - Добавлены разделы 4.5–4.7: анатомия гонок при реконнекте в SPA (Layout vs Child Pages), идиоматичный UI-барьер в лейауте (`{#if isSessionReady}`), сетевой шлюз `authInterceptor` и настройка Vite Dev-Server Proxy (`vite.config.ts`) для прозрачной авто-авторизации сокетов через куки (`auto_auth_ws=True`).

* [x] **v0.5.5: Совместимость с Python 3.14 и Granian multiprocessing spawn (Pickle-safe App):**
  - **Устранение `TypeError: cannot pickle 'itertools.count'`:**
    - Заменен несериализуемый C-объект `itertools.count()` на picklable класс `_SessionCounter` в `pyferro/app.py`.
    - `FerroApp` теперь гарантированно и прозрачно сериализуется через `pickle` / `multiprocessing.reduction.ForkingPickler`, что обеспечивает полную совместимость со стандартной моделью `spawn` в Python 3.14, macOS, Windows и многопроцессным режимом Granian (`workers > 1` / `mp`).
  - **Тесты:**
    - Добавлен автоматический тест сериализуемости `test_app_picklability` в `tests/suites/test_dx_improvements.py`.

* [x] **v0.5.4: Исключение бэкдоров, 100% Code-First конфигурация и CLI-управление администратором:**
  - **Безопасность: Полное удаление `/dev-admin` бэкдора:**
    - Полностью удален роут `/dev-admin` и аргумент `dev_admin` из ядра `FerroApp`. Исключены риски утечки авторизации через небезопасный контекст (HTTP) и сбоев многопроцессного режима.
  - **CLI-утилита смены пароля администратора (`--set-admin-password`):**
    - Реализована встроенная утилита командной строки: `python server.py --set-admin-password [ПАРОЛЬ] [--login ЛОГИН]`.
    - Поддерживает безопасный интерактивный ввод пароля через `getpass` с подтверждением или генерацию криптографически стойкого пароля, а также аргумент для CI/CD.
    - Работает строго на уровне DML (`password_hash` по стандарту PBKDF2-SHA256) без опасных DDL-мутаций (`create_all` исключен), предотвращая версионные конфликты схем данных.
    - Добавлен метод `app.handle_cli()` и CLI-команда `PyFerro set-admin-password`.
  - **100% Code-First архитектура без рассинхронизации окружения:**
    - Полностью исключены неявные обращения к переменным окружения (`os.getenv`, `os.environ`) в ядре, модуле конфигурации `pyferro/core/lib/config.py`, плагине БД `plugins/db/session.py` и витрине `showcase/server.py`.
    - Все настройки задаются строго явно и прозрачно в Python-коде приложения, исключая скрытые конфликты окружений (systemd vs SSH/cron).
  - **Очистка легаси-рудиментов:**
    - Из `DEFAULT_SYSTEM_BLACKLIST` в `pyferro/plugins/crud/registry.py` удален устаревший класс `PrefixBankEvent`.
  - **Тесты и документация:**
    - Актуализированы тесты в `tests/suites/test_dx_improvements.py` и руководство `docs/crud_panel_guide.md`.
    - 86 тестов успешно проходят за 1.34s.

* [x] **v0.5.3: Единый системный стандарт эндпоинта WebSocket (`/ws`):**
  - **Канонический WebSocket эндпоинт (`/ws`):**
    - В [client/wsrpc.ts](file:///home/alex/PyFerro/client/wsrpc.ts) унифицирована функция `getWsUrl()`: теперь соединение всегда направляется на `/ws` единообразно во всех окружениях (HTTP, HTTPS, Vite dev-сервер, Nginx reverse proxy).
    - Устранена рассинхронизация с Nginx: ранее при открытии админки по HTTP запрос уходил на `ws://host/` вместо `ws://host/ws`, что приводило к ошибке при наличии директивы `location /ws`.
    - Добавлен механизм явного переопределения URL сокета через `window.__WSRPC_URL__`.
    - Пересобраны автономная панель управления ([pyferro/plugins/crud/static](file:///home/alex/PyFerro/pyferro/plugins/crud/static)) и интерактивная витрина ([examples/showcase/public](file:///home/alex/PyFerro/examples/showcase/public)).
    - Скрипты нагрузочного тестирования и аудита безопасности ([scripts/benchmark.py](file:///home/alex/PyFerro/scripts/benchmark.py), [scripts/security_audit.py](file:///home/alex/PyFerro/scripts/security_audit.py)) и тестовый конфиг ([tests/framework/config.py](file:///home/alex/PyFerro/tests/framework/config.py)) обновлены для использования пути `/ws`.

## ✅ Выполнено в предыдущих релизах
* [x] **v0.5.2:**
  - **Единый Mission Control Cockpit (`/admin`):**
    - Подраздел **`📊 Данные (CRUD)`**: управление зарегистрированными бизнес-моделями и матрицей прав доступа.
    - Подраздел **`⚙️ Система (System Cockpit)`**:
      - `admin.sessions_list` & `admin.session_kill`: мониторинг открытых дуплексных WebSocket-соединений и отключение клиентов (Kick).
      - `system.cache_stats` & `system.cache_invalidate`: инспекция монотонных версий тегов Smart Cache (RFC 0001) и ручная инвалидация.
      - `system.broadcast`: O(1) Zero-Copy рассылка системных уведомлений без блокировки сокетов.
      - `system.recent_logs`: кольцевой буфер оперативного журнала событий сервера в памяти с авто-обновлением (Live Log Streamer).
      - `system.get_config`: инспекция Runtime Config с маскированием секретных ключей.
  - **Теплая бежево-коричневая палитра оформления:**
    - **Светлая тема:** строго 80% от самого светлого в теплых бежевых тонах (`#dcd3c6` / `#e8e0d4` / `#2d221a`).
    - **Темная тема:** строго 20% от самого светлого в теплых коричневатых тонах (`#33241b` / `#3d2c22` / `#ece5dc`).
  - **Системная надежность ядра:**
    - Поддержка проверки `CloseMessage` по `__class__.__name__` для нативных RSGI-фреймов Granian и тестовых сокетов.
* [x] **v0.5.1:**

  - **Zero-Boilerplate DX (Developer Experience):**
    - `auto_auth_ws=True` (по умолчанию включено): автоматическая авторизация WebSocket-сессий по Cookie (`ferro_crud_session`, `ferro_session`, `rpc_jwt`, `token`) без необходимости писать ручной код в `@app.on_connect`.
    - Режим быстрой локальной разработки `dev_admin=True` в `FerroApp`: автоматическая регистрация `/dev-admin` с установкой Cookie и безопасный сидинг пользователя `admin`/`admin123`.
    - Бесшовная интеграция `plugins.crud` и `plugins.auth`: `get_crud_session` нативно валидирует JWT-токены фреймворка и защищен от циклической рекурсии.
    - Динамический ре-бинд базы данных (`AsyncEngineProxy` и `configure_db`): параметры `database_url` и `db_echo` в `FerroApp` и `configure()` прозрачно переконфигурируют движок и `async_session` независимо от порядка импортов в коде.
    - Алиас `send_stream_chunk` в `AuthSession` для соответствия контракту потокового стриминга.
    - Автоматическая регистрация моделей безопасности (`User`, `Role`, `RpcPermission`) в `ModelRegistry.register_auth_models()`.
* [x] **v0.5.0:**
  - **Новый GUI управления доступом и разрешениями (CRUD + RPC):** разделение прав на данные (CRUD-матрица для моделей) и процедурных прав (RPC), персональные разрешения поверх ролевых, модалка `PermissionsModal.svelte`.
  - **Навигация субъектов доступа (Гости, Пользователи, Роли):** поддержка `target_type = "guest"`, Zero-Noise скрытие кнопки при `allow_guests=False`.
  - **Стандартизация Docstring RPC-методов и интерактивная справка (Help Modal):** сохранение оригинальных docstrings в `@rpc_method`, auto-healing шаблонных записей в БД при discovery, компонент `RpcHelpModal.svelte` с кнопкой `ℹ️`.
  - **Очистка CRUD Admin от визуального и технического шума:** скрытие технических связующих моделей (`is_internal = True`), компактное форматирование времени, исправление инлайн-редактирования Many-to-Many ячеек.
  - **Showcase как единый источник правды (SSOT) и двуязычная документация:** манифест `showcase_docs.json`, скрипт `build_docs.py`, фронтенд Showcase на Svelte 5.
* [x] **v0.4.9:**
  - Поддержка связей Many-to-Many в CRUD Admin: отображение бейджей/тегов, множественный выбор чекбоксами в модалке создания и инлайн-редактирование ячеек.
  - Декларативные модели связей первого класса `UserRole`, `UserTeam`, `RoleRpcPermission` в реестре CRUD с сохранением обратной совместимости.
  - Новый RPC-метод `crud.lookup` для динамической подгрузки вариантов Foreign Key и Many-to-Many.
  - Информативные цветные логи `[WSRPC]` на клиенте и автоматическая поддержка подключения по локальному IP (LAN).
  - Кнопки быстрых действий (Action Buttons) и таски VS Code для запуска Showcase на `0.0.0.0:8080` и сборки UI CRUD.
* [x] **v0.4.8:**
  - Полноценная мультиязычность (RU / EN) в CRUD-панели на Svelte 5 с переключателем языка `🌐 RU / EN`.
  - Мультиязычность витрины `examples/showcase` (RU / EN).
  - Интеграция системных моделей безопасности `RpcPermission`, `Role`, `User` в панель CRUD (`ModelRegistry`).
  - Окончательное удаление рудимента `/crud/login` и HTML-формы входа; полный переход на SSO и Zero-Leakage 404.
* [x] **v0.4.7:** Экспорт `set_crud_session_validator` в публичный интерфейс `plugins/crud`.
* [x] **v0.4.6:** Безопасное извлечение `user_name` в системном логгере без `AttributeError`.
* [x] **v0.4.5:** Zero-Leakage (404 Not Found) для админки CRUD и бесшовный SSO-мост с приложением.
* [x] **v0.4.4:** Динамические роли в БД, Service Discovery RPC-методов, типизированный `FerroApp`.
