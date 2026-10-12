# План задач к следующему обновлению (NEXT_RELEASE.md)

> **Внимание ИИ-ассистентов и разработчиков:**  
> Этот файл является обязательным бэклогом задач для следующего релиза.  
> **ПЕРЕД ЛЮБЫМ БАМПОМ ВЕРСИИ И ПУБЛИКАЦИЕЙ В PYPI ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ ЭТОТ ФАЙЛ**, реализовать запланированные в нем задачи или учесть их. Новые задачи и идеи по рефакторингу/улучшениям сразу заносятся сюда.

---

## 📌 Запланировано к следующему релизу (Backlog)
* [ ] Задачи формируются по мере поступления.

---

## ✅ Выполнено в текущем релизе / подготовке:
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
