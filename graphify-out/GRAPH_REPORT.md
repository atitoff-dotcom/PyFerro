# Graph Report - pyferro2  (2026-10-30)

## Corpus Check
- 106 files · ~64,758 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .ini 1)

## Summary
- 1532 nodes · 3526 edges · 77 communities (46 shown, 31 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 448 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6a249578`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.svelte
- Database
- sqlalchemy
- PyFerro 2.0 — Руководство разработчика и Архитектура
- PermissionsView.svelte
- get_seo_config
- RpcRouter
- admRole
- app.py
- auth/models.py
- asyncio
- SeoView.svelte
- package.json
- test_server_and_files.py
- SessionData
- .transfer
- seo/rpc.py
- seo/__init__.py
- UsersView.svelte
- ModelQueryWrapper
- index.js
- .call
- PaginationDemo.svelte
- pagination.py
- ForbiddenError
- Session
- CrudEngine
- release.py
- Any
- manager.py
- HelpView.svelte
- 🗺️ 2. Поэтапный план реализации
- TestRegistrationAndCompilation
- .test_multireturn_yield_over_websocket
- StartersManager
- PyFerroApp
- register_starters_rpc
- 🏛️ 7 Ключевых Правил Архитектуры GUI
- sitemap.py
- 2. Единые стандарты для примеров и стартеров
- StartersView.svelte
- register_help_rpc
- FileStorage
- rpc.js
- 🏛️ PyFerro Project Rules & Architecture Guidelines
- pyferro
- StarterManifest
- core/__init__.py
- db
- MockRSGIWebsocketProtocol
- storage.py
- test_full_application_lifecycle
- 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian
- MockRSGIHTTPProtocol
- RowSecureModel
- .text
- .get_seo_preview
- migration_v2_0_0.py
- TTLCache
- Руководство для разработчиков: Быстрый старт
- .notify
- .transfer
- serialize_session_data
- test_core_contracts.py
- .test_upload_fail_fast_content_length_and_slowloris_protection
- FileMaxSizeExceededError
- .test_site_tree_guest_permissions_and_bot_rendering
- TestStartersLifecycle
- TestBotDetector
- RPC-маршрутизация и права доступа
- router

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 92 edges
2. `CrudEngine` - 60 edges
3. `Database` - 59 edges
4. `Session` - 57 edges
5. `RpcRouter` - 53 edges
6. `PyFerroApp` - 50 edges
7. `RpcError` - 38 edges
8. `StartersManager` - 37 edges
9. `ForbiddenError` - 32 edges
10. `register_seo_rpc()` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Защита от Disk Exhaustion DoS и Slowloris` --references--> `FileStorage`  [INFERRED]
  NGINX.md → src/pyferro2/files/storage.py
- `📦 5. Сетевой формат `$tabular`` --references--> `unpackTabular()`  [INFERRED]
  PAGINATION.md → frontend/src/rpc.js
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `User`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py
- `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)` --references--> `admRole`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/core/constants.py
- `Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`)` --references--> `admRole`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/core/constants.py

## Import Cycles
- None detected.

## Communities (77 total, 31 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.07
Nodes (34): activeTab, confirmSidebarTabSwitch(), createModelRow(), deleteModelRow(), doSwitchTab(), errorMsg, handleLoginSubmit(), helpSlug (+26 more)

### Community 1 - "Database"
Cohesion: 0.08
Nodes (18): Database, render_jinja_template(), SeoConfigRecord, SeoPageData, HtmlBuilder, _build_breadcrumbs(), _coerce_column_value(), collect_site_tree_sitemap_urls() (+10 more)

### Community 3 - "PyFerro 2.0 — Руководство разработчика и Архитектура"
Cohesion: 0.18
Nodes (10): 1. Ключевые принципы архитектуры, 2. Быстрый старт (приложение в 30 строк), 3. Виды RPC-методов и Smart DI, 4. Файловая подсистема (2PC) и проксирование (Nginx / Angie / Caddy), 5. Маршруты сервера (`PyFerroApp`), 6. Табличная пагинация и сжатие трафика ($tabular), PyFerro 2.0 — Руководство разработчика и Архитектура, Мультиретурн (`async def ... yield`) и уведомления (`session.notify`) (+2 more)

### Community 4 - "PermissionsView.svelte"
Cohesion: 0.05
Nodes (38): ACTION_LABELS, allMethods, allowedCards, allowedMethodsCount, collapsedMap, disallowedCards, discardAndSwitchRole(), editableRoles (+30 more)

### Community 5 - "get_seo_config"
Cohesion: 0.07
Nodes (13): enqueue_indexnow_urls(), flush_indexnow_queue(), notify_indexnow(), _post_indexnow_sync(), _send_indexnow_background(), configure_seo(), get_seo_config(), SeoConfig (+5 more)

### Community 6 - "RpcRouter"
Cohesion: 0.13
Nodes (7): JsonRpcErrorCode, InvalidParamsError, MethodNotFoundError, RpcError, UnauthorizedError, RpcRouter, TestStartersRpcSecurity

### Community 7 - "admRole"
Cohesion: 0.12
Nodes (7): User, ensure_admin_user(), load_guest_session_data(), seed_system_roles(), admRole, register_crud_rpc(), create_user()

### Community 9 - "auth/models.py"
Cohesion: 0.05
Nodes (11): Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`), _prevent_system_role_deletion(), _prevent_system_role_modification(), Role, RolePermission, hash_password(), verify_password(), SampleArticle (+3 more)

### Community 10 - "asyncio"
Cohesion: 0.10
Nodes (4): TestClassNestingAndRouterInclude, TestParamsValidationAndRawWireProtocol, TestSmartDIAndLazyDatabase, TestThreeStepAccessControl

### Community 11 - "SeoView.svelte"
Cohesion: 0.06
Nodes (40): activeField, addChildNode(), applyPreset(), availableModels, availablePresets, botRoutes, currentNode, currentParents (+32 more)

### Community 12 - "package.json"
Cohesion: 0.11
Nodes (22): dependencies, @lucide/svelte@^1.61.0, tailwindcss@^4.3.3, @tailwindcss/vite@^4.3.3, devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0 (+14 more)

### Community 14 - "SessionData"
Cohesion: 0.07
Nodes (4): Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), SessionData, TestSessionData, TestHybridTokenManager

### Community 16 - "seo/rpc.py"
Cohesion: 0.09
Nodes (15): get_jinja_env(), is_model_allowed_for_seo(), resolve_foreign_target_spec(), validate_jinja_template(), register_seo_rpc(), apply_preset(), get_tree(), preview_node() (+7 more)

### Community 17 - "seo/__init__.py"
Cohesion: 0.12
Nodes (11): extract_cookies(), extract_header(), extract_query_params(), is_bot(), get_cached(), set_cached(), bot_page(), decorator() (+3 more)

### Community 18 - "UsersView.svelte"
Cohesion: 0.07
Nodes (25): activeAdminCount, activeCustomUserCount, adminRoles, assignableRoles, customUserRoles, errorMsg, handleCreateUser(), handleSaveRoles() (+17 more)

### Community 19 - "ModelQueryWrapper"
Cohesion: 0.12
Nodes (6): build_template_context(), is_sensitive_field(), ModelQueryWrapper, _generator(), RecordWrapper, serialize_safe_record()

### Community 20 - "index.js"
Cohesion: 0.08
Nodes (16): {
    variant = "default",
    children,
    class: customClass = "",
    ...restProps
  }, variantClasses, {
    title = "",
    headerExtra,
    children,
    class: customClass = "",
    ...restProps
  }, {
    checked = $bindable(),
    disabled = false,
    label = "",
    id = "",
    children,
    class: customClass = "",
    ...restProps
  }, elementId, {
    value = $bindable(),
    type = "text",
    disabled = false,
    error = false,
    class: customClass = "",
    ...restProps
  }, {
    open = false,
    onclose = () => {},
    title = "",
    children,
    footer,
    class: customClass = "",
    maxWidth = "max-w-xl",
  }, addToast() (+8 more)

### Community 21 - ".call"
Cohesion: 0.10
Nodes (8): Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`), _bind_user_params(), check_rpc_access(), encode_error(), RpcMethodSpec, _run_stream(), db_session(), DemoBook

### Community 22 - "PaginationDemo.svelte"
Cohesion: 0.09
Nodes (14): { paginator, showLimitSelect = true, showTotal = true }, sizeClasses, {
    variant = "primary",
    size = "md",
    type = "button",
    disabled = false,
    children,
    class: customClass = "",
    ...restProps
  }, variantClasses, {
    value = $bindable(),
    disabled = false,
    options = [],
    error = false,
    children,
    class: customClass = "",
    ...restProps
  }, hasNext, hasPrev, limit (+6 more)

### Community 23 - "pagination.py"
Cohesion: 0.07
Nodes (31): createPaginator(), 🚀 1. Быстрый старт: Бэкенд за 1 строчку, 1. Два режима пагинации «под капотом»:, 2. Авто-трансляция фильтров и поиска в SQL:, 🧰 2. Возможности бэкенда (`paginate_tabular`), 🎨 3. Быстрый старт: Фронтенд (JS / Svelte), 3. Оптимизация Zero-Hydration:, 🛠️ 4. Методы и свойства `createPaginator` (+23 more)

### Community 24 - "ForbiddenError"
Cohesion: 0.12
Nodes (12): Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`), register_file_rpc(), commit(), delete(), get_download_token(), list_my(), rollback(), ForbiddenError (+4 more)

### Community 25 - "Session"
Cohesion: 0.14
Nodes (3): Session, TestSession, TestHelpRpcIntegration

### Community 26 - "CrudEngine"
Cohesion: 0.07
Nodes (13): CrudEngine, _create(), _delete(), _read(), _update(), _serialize_instance(), compile_model_spec(), FieldSpec (+5 more)

### Community 27 - "release.py"
Cohesion: 0.06
Nodes (21): build_help_bundle(), _file_to_slug_and_order(), HelpDocParser, _highlight_code(), main(), parse_markdown_doc(), _parse_widget_props(), _slugify() (+13 more)

### Community 28 - "Any"
Cohesion: 0.10
Nodes (3): _iter_rsgi_chunks(), _set_scope_session_data(), extract_token_from_scope()

### Community 29 - "manager.py"
Cohesion: 0.14
Nodes (6): _now_utc(), StarterBase, TstMessage, TstMeta, TstTopic, seed_forum_data()

### Community 30 - "HelpView.svelte"
Cohesion: 0.13
Nodes (17): activeArticle, articleLoading, articles, createSnippet(), { currentSlug = '', onNavigate = null }, errorMsg, escapeHtml(), escapeRegex() (+9 more)

### Community 31 - "🗺️ 2. Поэтапный план реализации"
Cohesion: 0.15
Nodes (9): 🏛️ 1. Архитектурные принципы PyFerro 2.0, 🗺️ 2. Поэтапный план реализации, 🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план, Золотые правила чистоты:, 🎯 Результат выполнения плана:, Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`), Этап 6: Интерфейс панели управления (`pyferro2/frontend/`, маршрут `/pyferro_admin`), Этап 7: Сквозное тестирование и документация (`pyferro2/tests/`) (+1 more)

### Community 35 - "PyFerroApp"
Cohesion: 0.12
Nodes (4): main(), _granian_target_loader(), PyFerroApp, _run()

### Community 36 - "register_starters_rpc"
Cohesion: 0.12
Nodes (4): _compile_method_spec(), _resolve_method_name(), _decorator(), register_starters_rpc()

### Community 37 - "🏛️ 7 Ключевых Правил Архитектуры GUI"
Cohesion: 0.11
Nodes (18): 1. Zero Hardcoded Colors (Только токены системы), 1. Поверхности и фоны, 2. Theme Invariant (Запрет утилиты `dark:`), 2. Границы и разделители, 3. Типографика, 3. Фотометрическая эргономика (Защита зрения), 4. Закон эшелонирования слоев (Elevation Law), 4. Статусы и Акценты (+10 more)

### Community 38 - "sitemap.py"
Cohesion: 0.17
Nodes (8): build_sitemap_xml(), collect_all_sitemap_urls(), _format_lastmod(), handle_sitemap_http(), register_sitemap_provider(), _render_sitemapindex_xml(), _render_urlset_xml(), _send_xml()

### Community 39 - "2. Единые стандарты для примеров и стартеров"
Cohesion: 0.11
Nodes (16): 1. Философия и цели, 2.1. Изоляция базы данных: префикс `tst_*`, 2.2. Защита при инсталляции (Conflict Detection), 2.3. Политика дистрибуции: исключение из PyPI и версионирование по GitHub Releases, 2.4. Решение проблемы миграций при обновлении PyFerro, 2.5. Механизм доставки и установки (Download Flow), 2. Единые стандарты для примеров и стартеров, 3.1. Структура базы данных (всего 2 таблицы + метаданные) (+8 more)

### Community 40 - "StartersView.svelte"
Cohesion: 0.12
Nodes (13): conflictMessage, handleInstall(), handleUninstall(), isActionRunning, isLoading, loadStarters(), { onnotify = () => {} }, seoPreviewData (+5 more)

### Community 41 - "register_help_rpc"
Cohesion: 0.15
Nodes (7): register_help_rpc(), get_article(), get_search_index(), get_tree(), search_index(), tree(), _resolve_bundle_path()

### Community 43 - "rpc.js"
Cohesion: 0.18
Nodes (12): authState, loginAdmin(), logoutAdmin(), refreshSession(), client, getStoredToken(), rpc, RpcClient (+4 more)

### Community 47 - "core/__init__.py"
Cohesion: 0.21
Nodes (4): WsCloseCode, apply_tabular_result(), is_tabular(), pack_tabular()

### Community 50 - "storage.py"
Cohesion: 0.23
Nodes (3): StoredFile, sanitize_filename(), UploadTransaction

### Community 51 - "test_full_application_lifecycle"
Cohesion: 0.21
Nodes (3): call_rsgi_http(), MockRSGIScope, test_full_application_lifecycle()

### Community 52 - "🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian"
Cohesion: 0.18
Nodes (8): 1. Загрузка файлов (Upload): Потоковый Fail-Fast (RSGI), 2. Скачивание файлов (Download): `X-Accel-Redirect` и защита от XSS, 4. Полная боевая конфигурация Nginx / Angie, 5. Конфигурация Caddy v2 (`Caddyfile`), 🏛️ Архитектурный паттерн: «Золотая середина», Двухфазная загрузка (2PC) в PyFerro:, Защита от Disk Exhaustion DoS и Slowloris, 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian

### Community 54 - "RowSecureModel"
Cohesion: 0.20
Nodes (7): CRUD Engine и спецификации моделей, Автоматическая валидация, Интерактивный пример, Определение модели, RowSecureModel, Category, Crud

### Community 55 - ".text"
Cohesion: 0.22
Nodes (4): downgrade(), upgrade(), generate(), TestMigrationV210

### Community 56 - ".get_seo_preview"
Cohesion: 0.29
Nodes (3): get_forum_sitemap(), get_topic_breadcrumbs(), get_topic_discussion_posting()

### Community 59 - "Руководство для разработчиков: Быстрый старт"
Cohesion: 0.25
Nodes (7): Архитектура системы, Быстрый старт полноценного приложения, Интерактивный компонент: Пагинация, Полезные ссылки, Простейшее приложение, Руководство для разработчиков: Быстрый старт, Установка

### Community 62 - "serialize_session_data"
Cohesion: 0.29
Nodes (3): logout(), me(), serialize_session_data()

### Community 72 - "RPC-маршрутизация и права доступа"
Cohesion: 0.50
Nodes (3): RPC-маршрутизация и права доступа, Регистрация метода, Системные роли `adm_*`

## Knowledge Gaps
- **1 isolated node(s):** `pyferro`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 739 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `paginate_tabular()` connect `pagination.py` to `sqlalchemy`, `CrudEngine`, `get_seo_config`?**
  _High betweenness centrality (0.335) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `SessionData` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`SessionData` has 39 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pyferro` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.07195121951219512 - nodes in this community are weakly interconnected._
- **Why does `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)` connect `pagination.py` to `rpc.js`, `🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian`?**
  _High betweenness centrality (0.332) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `CrudEngine` (e.g. with `Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`)` and `Role`) actually correct?**
  _`CrudEngine` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Should `Database` be split into smaller, more focused modules?**
  _Cohesion score 0.0803633822501747 - nodes in this community are weakly interconnected._