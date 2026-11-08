# Graph Report - pyferro2  (2026-11-08)

## Corpus Check
- 107 files · ~71,605 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .ini 1)

## Summary
- 1606 nodes · 3759 edges · 85 communities (53 shown, 32 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 486 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b034b68f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.svelte
- Database
- core/__init__.py
- 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian
- PermissionsView.svelte
- .test_site_tree_guest_permissions_and_bot_rendering
- server/__init__.py
- TestRegistrationAndCompilation
- app.py
- auth/models.py
- asyncio
- SeoView.svelte
- package.json
- test_server_and_files.py
- Session
- .transfer
- PyFerro 2.0 — Руководство разработчика и Архитектура
- handle_bot_http
- UsersView.svelte
- ModelQueryWrapper
- index.js
- .call
- PaginationDemo.svelte
- pagination.py
- loadData
- OAuthView.svelte
- CrudEngine
- release.py
- PyFerroApp
- 🚀 PyFerro Showcase & Demo (pyferro-demo)
- HelpView.svelte
- 🗺️ 2. Поэтапный план реализации
- UnauthorizedError
- .test_multireturn_yield_over_websocket
- register_oauth_rpc
- test_e2e_lifecycle.py
- register_seo_rpc
- 🏛️ 7 Ключевых Правил Архитектуры GUI
- sitemap.py
- TokenManager
- Database
- register_help_rpc
- FileStorage
- rpc.js
- 🏛️ PyFerro Project Rules & Architecture Guidelines
- pyferro
- SessionData
- theme.svelte.js
- seed_system_roles
- MockRSGIWebsocketProtocol
- storage.py
- server/__init__.py
- mailer.py
- MockRSGIHTTPProtocol
- RowSecureModel
- .text
- Role
- migration_v2_0_0.py
- TTLCache
- Руководство для разработчиков: Быстрый старт
- .transfer
- oauth/rpc.py
- .reset_to_guest
- ._bind_model_rpc
- register_crud_rpc
- User
- .notify
- StoredFile
- seo/__init__.py
- orjson
- test_core_contracts.py
- test_server_and_files.py
- 3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile)
- UploadTransaction
- EmailVerificationStore
- bot_page
- app
- extract_token_from_scope
- base.py
- isMethodAllowed
- isCollapsed
- CrudEngine

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 93 edges
2. `Session` - 66 edges
3. `CrudEngine` - 61 edges
4. `PyFerroApp` - 61 edges
5. `Database` - 51 edges
6. `RpcRouter` - 51 edges
7. `ForbiddenError` - 38 edges
8. `register_oauth_rpc()` - 36 edges
9. `RpcError` - 33 edges
10. `register_seo_rpc()` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Защита от Disk Exhaustion DoS и Slowloris` --references--> `FileStorage`  [INFERRED]
  NGINX.md → src/pyferro2/files/storage.py
- `📦 5. Сетевой формат `$tabular`` --references--> `unpackTabular()`  [INFERRED]
  PAGINATION.md → frontend/src/rpc.js
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `RolePermission`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `Role`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `User`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py

## Import Cycles
- None detected.

## Communities (85 total, 32 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.07
Nodes (47): activeTab, authMode, confirmSidebarTabSwitch(), createModelRow(), deleteModelRow(), doSwitchTab(), errorMsg, finishOAuthLogin() (+39 more)

### Community 1 - "Database"
Cohesion: 0.09
Nodes (13): render_jinja_template(), HtmlBuilder, _build_breadcrumbs(), _coerce_column_value(), collect_site_tree_sitemap_urls(), flatten_tree_nodes(), get_cached_site_tree(), get_default_tree() (+5 more)

### Community 2 - "core/__init__.py"
Cohesion: 0.12
Nodes (3): WsCloseCode, TestRendererAndTemplateValidation, TestSeoSiteTreeRpcAndHttpIntegration

### Community 3 - "🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian"
Cohesion: 0.18
Nodes (8): 1. Загрузка файлов (Upload): Потоковый Fail-Fast (RSGI), 2. Скачивание файлов (Download): `X-Accel-Redirect` и защита от XSS, 4. Полная боевая конфигурация Nginx / Angie, 5. Конфигурация Caddy v2 (`Caddyfile`), 🏛️ Архитектурный паттерн: «Золотая середина», Двухфазная загрузка (2PC) в PyFerro:, Защита от Disk Exhaustion DoS и Slowloris, 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian

### Community 4 - "PermissionsView.svelte"
Cohesion: 0.05
Nodes (25): ACTION_LABELS, allMethods, allowedMethodsCount, collapsedMap, editableRoles, groupedMethodCards, hasUnsavedChanges, isCreatingRole (+17 more)

### Community 5 - ".test_site_tree_guest_permissions_and_bot_rendering"
Cohesion: 0.16
Nodes (5): SeoConfigRecord, load_seo_from_db(), save_seo_to_db(), set_cached_site_tree(), custom_landing()

### Community 8 - "app.py"
Cohesion: 0.11
Nodes (5): admRole, JsonRpcErrorCode, MethodNotFoundError, UnauthorizedError, RpcRouter

### Community 9 - "auth/models.py"
Cohesion: 0.18
Nodes (3): hash_password(), verify_password(), TestPasswords

### Community 10 - "asyncio"
Cohesion: 0.08
Nodes (5): router(), TestClassNestingAndRouterInclude, TestParamsValidationAndRawWireProtocol, TestSmartDIAndLazyDatabase, TestThreeStepAccessControl

### Community 11 - "SeoView.svelte"
Cohesion: 0.06
Nodes (41): activeField, addChildNode(), allowedModels, availableModels, botRoutes, currentNode, currentParents, currentSelection (+33 more)

### Community 12 - "package.json"
Cohesion: 0.11
Nodes (22): dependencies, @lucide/svelte@^1.61.0, tailwindcss@^4.3.3, @tailwindcss/vite@^4.3.3, devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0 (+14 more)

### Community 14 - "Session"
Cohesion: 0.18
Nodes (3): Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), Session, TestHelpRpcIntegration

### Community 16 - "PyFerro 2.0 — Руководство разработчика и Архитектура"
Cohesion: 0.18
Nodes (10): 1. Ключевые принципы архитектуры, 2. Быстрый старт (приложение в 30 строк), 3. Виды RPC-методов и Smart DI, 4. Файловая подсистема (2PC) и проксирование (Nginx / Angie / Caddy), 5. Маршруты сервера (`PyFerroApp`), 6. Табличная пагинация и сжатие трафика ($tabular), PyFerro 2.0 — Руководство разработчика и Архитектура, Мультиретурн (`async def ... yield`) и уведомления (`session.notify`) (+2 more)

### Community 17 - "handle_bot_http"
Cohesion: 0.16
Nodes (5): extract_cookies(), extract_header(), extract_query_params(), is_bot(), TestBotDetector

### Community 18 - "UsersView.svelte"
Cohesion: 0.06
Nodes (25): activeAdminCount, activeCustomUserCount, adminRoles, assignableRoles, customUserRoles, errorMsg, handleCreateUser(), handleSaveRoles() (+17 more)

### Community 19 - "ModelQueryWrapper"
Cohesion: 0.07
Nodes (12): build_template_context(), get_jinja_env(), is_sensitive_field(), ModelQueryWrapper, _generator(), RecordWrapper, render_markdown_filter(), _flush_para() (+4 more)

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
Cohesion: 0.07
Nodes (11): Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`), _bind_user_params(), check_rpc_access(), _compile_method_spec(), encode_error(), _resolve_method_name(), RpcMethodSpec, _decorator() (+3 more)

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
Cohesion: 0.06
Nodes (34): createPaginator(), 🚀 1. Быстрый старт: Бэкенд за 1 строчку, 1. Два режима пагинации «под капотом»:, 2. Авто-трансляция фильтров и поиска в SQL:, 🧰 2. Возможности бэкенда (`paginate_tabular`), 🎨 3. Быстрый старт: Фронтенд (JS / Svelte), 3. Оптимизация Zero-Hydration:, 🛠️ 4. Методы и свойства `createPaginator` (+26 more)

### Community 24 - "loadData"
Cohesion: 0.29
Nodes (8): discardAndSwitchRole(), handleCreateRole(), handleDeleteRole(), handleRoleClick(), loadData(), saveAndSwitchRole(), savePermissions(), selectRole()

### Community 25 - "OAuthView.svelte"
Cohesion: 0.05
Nodes (27): accounts, accountToDelete, allowRegistration, appLogoSvg, appTitle, executeDelete(), filterProvider, isDeleting (+19 more)

### Community 26 - "CrudEngine"
Cohesion: 0.09
Nodes (15): Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`), _read(), _serialize_instance(), register_file_rpc(), commit(), delete(), get_download_token(), list_my() (+7 more)

### Community 27 - "release.py"
Cohesion: 0.06
Nodes (21): build_help_bundle(), _file_to_slug_and_order(), HelpDocParser, _highlight_code(), main(), parse_markdown_doc(), _parse_widget_props(), _slugify() (+13 more)

### Community 28 - "PyFerroApp"
Cohesion: 0.05
Nodes (14): main(), _granian_target_loader(), _iter_rsgi_chunks(), PyFerroApp, _run(), _set_scope_session_data(), test_oauth_admin_api(), test_oauth_get_auth_url_providers() (+6 more)

### Community 29 - "🚀 PyFerro Showcase & Demo (pyferro-demo)"
Cohesion: 0.29
Nodes (6): 🚀 PyFerro Showcase & Demo (pyferro-demo), 🛡️ Безопасность и архитектурная изоляция, ⚡ Быстрый старт, 💡 Использование как шаблона, Установка и запуск в 1 команду:, 📂 Что входит в пример: SEO-Форум

### Community 30 - "HelpView.svelte"
Cohesion: 0.13
Nodes (17): activeArticle, articleLoading, articles, createSnippet(), { currentSlug = '', onNavigate = null }, errorMsg, escapeHtml(), escapeRegex() (+9 more)

### Community 31 - "🗺️ 2. Поэтапный план реализации"
Cohesion: 0.13
Nodes (10): 🏛️ 1. Архитектурные принципы PyFerro 2.0, 🗺️ 2. Поэтапный план реализации, 🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план, Золотые правила чистоты:, 🎯 Результат выполнения плана:, Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`), Этап 6: Интерфейс панели управления (`pyferro2/frontend/`, маршрут `/pyferro_admin`), Этап 7: Сквозное тестирование и документация (`pyferro2/tests/`) (+2 more)

### Community 32 - "UnauthorizedError"
Cohesion: 0.15
Nodes (7): BaseProvider, ExternalUserProfile, GoogleProvider, TelegramProvider, VkProvider, YandexProvider, ValidationError

### Community 34 - "register_oauth_rpc"
Cohesion: 0.14
Nodes (14): get_auth_config(), get_or_create_config(), seed_auth_configs(), AuthConfig, register_oauth_rpc(), admin_delete(), admin_get_all_configs(), admin_update_config() (+6 more)

### Community 36 - "register_seo_rpc"
Cohesion: 0.15
Nodes (8): validate_jinja_template(), register_seo_rpc(), apply_preset(), ping_indexnow(), save_tree(), validate_template(), _validate_tree_security(), compile_pattern_to_regex()

### Community 37 - "🏛️ 7 Ключевых Правил Архитектуры GUI"
Cohesion: 0.11
Nodes (18): 1. Zero Hardcoded Colors (Только токены системы), 1. Поверхности и фоны, 2. Theme Invariant (Запрет утилиты `dark:`), 2. Границы и разделители, 3. Типографика, 3. Фотометрическая эргономика (Защита зрения), 4. Закон эшелонирования слоев (Elevation Law), 4. Статусы и Акценты (+10 more)

### Community 38 - "sitemap.py"
Cohesion: 0.15
Nodes (8): build_sitemap_xml(), collect_all_sitemap_urls(), _format_lastmod(), handle_sitemap_http(), register_sitemap_provider(), _render_sitemapindex_xml(), _render_urlset_xml(), _send_xml()

### Community 40 - "Database"
Cohesion: 0.21
Nodes (3): Database, TestDatabaseAndModels, TestMigrationV210

### Community 41 - "register_help_rpc"
Cohesion: 0.15
Nodes (7): register_help_rpc(), get_article(), get_search_index(), get_tree(), search_index(), tree(), _resolve_bundle_path()

### Community 43 - "rpc.js"
Cohesion: 0.25
Nodes (7): client, getStoredToken(), rpc, RpcClient, rpcFn(), unpackTabular(), 📦 5. Сетевой формат `$tabular`

### Community 47 - "theme.svelte.js"
Cohesion: 0.33
Nodes (5): currentTheme, initTheme(), isDark(), setTheme(), toggleTheme()

### Community 48 - "seed_system_roles"
Cohesion: 0.16
Nodes (4): ensure_admin_user(), load_guest_session_data(), seed_system_roles(), app()

### Community 52 - "mailer.py"
Cohesion: 0.27
Nodes (3): send_email(), _send_smtp_sync(), admin_test_smtp()

### Community 54 - "RowSecureModel"
Cohesion: 0.15
Nodes (9): CRUD Engine и спецификации моделей, Автоматическая валидация, Интерактивный пример, Определение модели, RowSecureModel, Category, Crud, Product (+1 more)

### Community 55 - ".text"
Cohesion: 0.18
Nodes (5): downgrade(), upgrade(), downgrade(), upgrade(), generate()

### Community 56 - "Role"
Cohesion: 0.13
Nodes (4): _prevent_system_role_deletion(), _prevent_system_role_modification(), Role, RolePermission

### Community 58 - "TTLCache"
Cohesion: 0.15
Nodes (3): get_cached(), set_cached(), TTLCache

### Community 59 - "Руководство для разработчиков: Быстрый старт"
Cohesion: 0.25
Nodes (7): Архитектура системы, Быстрый старт полноценного приложения, Интерактивный компонент: Пагинация, Полезные ссылки, Простейшее приложение, Руководство для разработчиков: Быстрый старт, Установка

### Community 63 - "._bind_model_rpc"
Cohesion: 0.29
Nodes (3): _create(), _delete(), _update()

### Community 64 - "register_crud_rpc"
Cohesion: 0.14
Nodes (5): register_crud_rpc(), create_user(), schemas(), register_auth_rpc(), login()

### Community 65 - "User"
Cohesion: 0.14
Nodes (10): User, find_available_username(), link_or_create_oauth_user(), sanitize_username(), login(), register(), verify_email_code(), me() (+2 more)

### Community 68 - "seo/__init__.py"
Cohesion: 0.14
Nodes (8): configure_seo(), get_seo_config(), SeoConfig, SeoPageData, _format_datetime(), render_404_html(), render_seo_page(), get_tree()

### Community 69 - "orjson"
Cohesion: 0.14
Nodes (7): async_http_json(), _sync_http_request(), enqueue_indexnow_urls(), flush_indexnow_queue(), notify_indexnow(), _post_indexnow_sync(), _send_indexnow_background()

### Community 72 - "3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile)"
Cohesion: 0.25
Nodes (7): 1. Регистрация RPC-методов на бэкенде, 2. Системные роли безопасности, 3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile), RPC-маршрутизация и авторизация, 🌐 Подключение по WebSocket (`/ws`), 🔑 Хранение токена и работа с Cookie, ⚠️ Частые архитектурные ошибки и их решение

### Community 75 - "bot_page"
Cohesion: 0.19
Nodes (5): bot_page(), decorator(), BotRoute, handle_bot_http(), _send_html()

### Community 80 - "isMethodAllowed"
Cohesion: 0.67
Nodes (3): allowedCards, disallowedCards, isMethodAllowed()

### Community 83 - "CrudEngine"
Cohesion: 0.08
Nodes (12): Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`), CrudEngine, compile_model_spec(), FieldSpec, _map_sa_type(), ModelSpec, Base, is_model_allowed_for_seo() (+4 more)

## Knowledge Gaps
- **1 isolated node(s):** `pyferro`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 769 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `paginate_tabular()` connect `pagination.py` to `core/__init__.py`, `CrudEngine`, `seo/__init__.py`?**
  _High betweenness centrality (0.347) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `SessionData` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`SessionData` has 40 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pyferro` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.06568832983927324 - nodes in this community are weakly interconnected._
- **Why does `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)` connect `pagination.py` to `rpc.js`, `🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian`?**
  _High betweenness centrality (0.344) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `Session` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`Session` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Should `Database` be split into smaller, more focused modules?**
  _Cohesion score 0.09082125603864734 - nodes in this community are weakly interconnected._