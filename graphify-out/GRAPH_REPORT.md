# Graph Report - pyferro2  (2026-11-06)

## Corpus Check
- 107 files · ~68,458 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .ini 1)

## Summary
- 1581 nodes · 3699 edges · 82 communities (56 shown, 26 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 476 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9df57e94`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.svelte
- Database
- sqlalchemy
- .notify
- PermissionsView.svelte
- register_seo_rpc
- rpc/router.py
- RpcRouter
- server/app.py
- auth/models.py
- asyncio
- SeoView.svelte
- package.json
- test_server_and_files.py
- .transfer
- get_jinja_env
- handle_bot_http
- UsersView.svelte
- ModelQueryWrapper
- index.js
- .call
- PaginationDemo.svelte
- pagination.py
- RpcError
- OAuthView.svelte
- CrudEngine
- release.py
- Any
- 🚀 PyFerro Showcase & Demo (pyferro-demo)
- HelpView.svelte
- 🗺️ 2. Поэтапный план реализации
- UnauthorizedError
- .test_multireturn_yield_over_websocket
- register_oauth_rpc
- PyFerroApp
- seo/__init__.py
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
- test_oauth_and_registration.py
- app
- MockRSGIWebsocketProtocol
- storage.py
- server/__init__.py
- sitemap.py
- MockRSGIHTTPProtocol
- CRUD Engine и спецификации моделей
- .text
- Role
- migration_v2_0_0.py
- TTLCache
- Руководство для разработчиков: Быстрый старт
- test_db_and_auth_models.py
- oauth/rpc.py
- ForbiddenError
- test_core_contracts.py
- crud/rpc.py
- User
- ._dispatch_ws_frame
- .test_site_tree_guest_permissions_and_bot_rendering
- renderer.py
- orjson
- Session
- compile_model_spec
- RPC-маршрутизация и права доступа
- manager.py
- EmailVerificationStore
- bot_page
- app
- site_tree.py
- CrudEngine

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 93 edges
2. `Session` - 66 edges
3. `PyFerroApp` - 61 edges
4. `CrudEngine` - 60 edges
5. `RpcRouter` - 51 edges
6. `Database` - 50 edges
7. `ForbiddenError` - 38 edges
8. `register_oauth_rpc()` - 36 edges
9. `RpcError` - 33 edges
10. `register_seo_rpc()` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Определение модели` --references--> `RowSecureModel`  [INFERRED]
  docs/help/02_crud_engine.md → src/pyferro2/db/base.py
- `Защита от Disk Exhaustion DoS и Slowloris` --references--> `FileStorage`  [INFERRED]
  NGINX.md → src/pyferro2/files/storage.py
- `📦 5. Сетевой формат `$tabular`` --references--> `unpackTabular()`  [INFERRED]
  PAGINATION.md → frontend/src/rpc.js
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `RolePermission`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `Role`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py

## Import Cycles
- None detected.

## Communities (82 total, 26 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.06
Nodes (47): activeTab, authMode, confirmSidebarTabSwitch(), createModelRow(), deleteModelRow(), doSwitchTab(), errorMsg, finishOAuthLogin() (+39 more)

### Community 1 - "Database"
Cohesion: 0.10
Nodes (11): render_jinja_template(), HtmlBuilder, preview_node(), _build_breadcrumbs(), _coerce_column_value(), flatten_tree_nodes(), match_and_render_site_tree(), render_collection_node() (+3 more)

### Community 2 - "sqlalchemy"
Cohesion: 0.10
Nodes (5): Category, Crud, Product, Crud, test_full_application_lifecycle()

### Community 3 - ".notify"
Cohesion: 0.09
Nodes (19): 1. Загрузка файлов (Upload): Потоковый Fail-Fast (RSGI), 2. Скачивание файлов (Download): `X-Accel-Redirect` и защита от XSS, 3. WebSocket и мультиретурн (`yield`), 4. Полная боевая конфигурация Nginx / Angie, 5. Конфигурация Caddy v2 (`Caddyfile`), 🏛️ Архитектурный паттерн: «Золотая середина», Двухфазная загрузка (2PC) в PyFerro:, Защита от Disk Exhaustion DoS и Slowloris (+11 more)

### Community 4 - "PermissionsView.svelte"
Cohesion: 0.05
Nodes (38): ACTION_LABELS, allMethods, allowedCards, allowedMethodsCount, collapsedMap, disallowedCards, discardAndSwitchRole(), editableRoles (+30 more)

### Community 5 - "register_seo_rpc"
Cohesion: 0.13
Nodes (13): validate_jinja_template(), SeoConfigRecord, register_seo_rpc(), apply_preset(), get_tree(), save_tree(), toggle_guest_read(), validate_template() (+5 more)

### Community 6 - "rpc/router.py"
Cohesion: 0.15
Nodes (7): JsonRpcErrorCode, MethodNotFoundError, check_rpc_access(), _compile_method_spec(), _resolve_method_name(), RpcMethodSpec, _decorator()

### Community 10 - "asyncio"
Cohesion: 0.08
Nodes (5): router(), TestClassNestingAndRouterInclude, TestParamsValidationAndRawWireProtocol, TestSmartDIAndLazyDatabase, TestThreeStepAccessControl

### Community 11 - "SeoView.svelte"
Cohesion: 0.06
Nodes (40): activeField, addChildNode(), applyPreset(), availableModels, availablePresets, botRoutes, currentNode, currentParents (+32 more)

### Community 12 - "package.json"
Cohesion: 0.11
Nodes (22): dependencies, @lucide/svelte@^1.61.0, tailwindcss@^4.3.3, @tailwindcss/vite@^4.3.3, devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0 (+14 more)

### Community 13 - "test_server_and_files.py"
Cohesion: 0.11
Nodes (6): make_ws_close(), make_ws_message(), MockRSGIWebsocketProtocol, TestMultiReturnAndGracefulDisconnect, app(), TestHttpAndWebSocketTransport

### Community 15 - ".transfer"
Cohesion: 0.12
Nodes (4): Book, Crud, Book, Crud

### Community 17 - "handle_bot_http"
Cohesion: 0.17
Nodes (6): extract_cookies(), extract_header(), extract_query_params(), is_bot(), handle_bot_http(), TestBotDetector

### Community 18 - "UsersView.svelte"
Cohesion: 0.06
Nodes (25): activeAdminCount, activeCustomUserCount, adminRoles, assignableRoles, customUserRoles, errorMsg, handleCreateUser(), handleSaveRoles() (+17 more)

### Community 19 - "ModelQueryWrapper"
Cohesion: 0.12
Nodes (5): build_template_context(), is_sensitive_field(), ModelQueryWrapper, RecordWrapper, serialize_safe_record()

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
Cohesion: 0.16
Nodes (3): Database, _bind_user_params(), db_session()

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
Nodes (35): createPaginator(), 🚀 1. Быстрый старт: Бэкенд за 1 строчку, 1. Два режима пагинации «под капотом»:, 2. Авто-трансляция фильтров и поиска в SQL:, 🧰 2. Возможности бэкенда (`paginate_tabular`), 🎨 3. Быстрый старт: Фронтенд (JS / Svelte), 3. Оптимизация Zero-Hydration:, 🛠️ 4. Методы и свойства `createPaginator` (+27 more)

### Community 24 - "RpcError"
Cohesion: 0.22
Nodes (7): Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`), register_file_rpc(), commit(), delete(), get_download_token(), list_my(), rollback()

### Community 25 - "OAuthView.svelte"
Cohesion: 0.05
Nodes (27): accounts, accountToDelete, allowRegistration, appLogoSvg, appTitle, executeDelete(), filterProvider, isDeleting (+19 more)

### Community 26 - "CrudEngine"
Cohesion: 0.09
Nodes (9): RolePermission, _create(), _delete(), _read(), _update(), _serialize_instance(), InvalidParamsError, clear_seo_cache() (+1 more)

### Community 27 - "release.py"
Cohesion: 0.06
Nodes (21): build_help_bundle(), _file_to_slug_and_order(), HelpDocParser, _highlight_code(), main(), parse_markdown_doc(), _parse_widget_props(), _slugify() (+13 more)

### Community 29 - "🚀 PyFerro Showcase & Demo (pyferro-demo)"
Cohesion: 0.29
Nodes (6): 🚀 PyFerro Showcase & Demo (pyferro-demo), 🛡️ Безопасность и архитектурная изоляция, ⚡ Быстрый старт, 💡 Использование как шаблона, Установка и запуск в 1 команду:, 📂 Что входит в пример: SEO-Форум

### Community 30 - "HelpView.svelte"
Cohesion: 0.13
Nodes (17): activeArticle, articleLoading, articles, createSnippet(), { currentSlug = '', onNavigate = null }, errorMsg, escapeHtml(), escapeRegex() (+9 more)

### Community 31 - "🗺️ 2. Поэтапный план реализации"
Cohesion: 0.13
Nodes (13): 🏛️ 1. Архитектурные принципы PyFerro 2.0, 🗺️ 2. Поэтапный план реализации, 🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план, ⚡ Закон минимального потребления CPU и Zero-Boilerplate:, Золотые правила чистоты:, 🎯 Результат выполнения плана:, Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`) (+5 more)

### Community 32 - "UnauthorizedError"
Cohesion: 0.15
Nodes (10): async_http_json(), _sync_http_request(), BaseProvider, ExternalUserProfile, GoogleProvider, TelegramProvider, VkProvider, YandexProvider (+2 more)

### Community 34 - "register_oauth_rpc"
Cohesion: 0.14
Nodes (14): send_email(), get_or_create_config(), seed_auth_configs(), register_oauth_rpc(), admin_delete(), admin_get_all_configs(), admin_test_smtp(), admin_update_config() (+6 more)

### Community 35 - "PyFerroApp"
Cohesion: 0.24
Nodes (3): main(), _granian_target_loader(), PyFerroApp

### Community 36 - "seo/__init__.py"
Cohesion: 0.18
Nodes (7): enqueue_indexnow_urls(), flush_indexnow_queue(), notify_indexnow(), get_seo_config(), SeoConfig, ping_indexnow(), register_sitemap_provider()

### Community 37 - "🏛️ 7 Ключевых Правил Архитектуры GUI"
Cohesion: 0.11
Nodes (18): 1. Zero Hardcoded Colors (Только токены системы), 1. Поверхности и фоны, 2. Theme Invariant (Запрет утилиты `dark:`), 2. Границы и разделители, 3. Типографика, 3. Фотометрическая эргономика (Защита зрения), 4. Закон эшелонирования слоев (Elevation Law), 4. Статусы и Акценты (+10 more)

### Community 38 - "sitemap.py"
Cohesion: 0.21
Nodes (6): build_sitemap_xml(), _format_lastmod(), handle_sitemap_http(), _render_sitemapindex_xml(), _render_urlset_xml(), _send_xml()

### Community 40 - "Database"
Cohesion: 0.18
Nodes (5): ensure_admin_user(), load_guest_session_data(), seed_system_roles(), _run(), TestDatabaseAndModels

### Community 41 - "register_help_rpc"
Cohesion: 0.11
Nodes (8): register_help_rpc(), get_article(), get_search_index(), get_tree(), search_index(), tree(), _resolve_bundle_path(), RpcError

### Community 43 - "rpc.js"
Cohesion: 0.19
Nodes (11): authState, loginAdmin(), logoutAdmin(), client, getStoredToken(), rpc, RpcClient, rpcFn() (+3 more)

### Community 46 - "SessionData"
Cohesion: 0.09
Nodes (3): SessionData, TestSessionData, TestHelpRpcIntegration

### Community 47 - "test_oauth_and_registration.py"
Cohesion: 0.16
Nodes (8): test_oauth_admin_api(), test_oauth_get_auth_url_providers(), test_oauth_login_telegram_flow(), test_oauth_login_telegram_invalid_hash(), test_oauth_login_vk_flow(), test_public_config_and_branding(), test_registration_direct_flow(), test_registration_with_email_verification()

### Community 50 - "storage.py"
Cohesion: 0.13
Nodes (3): StoredFile, FileMaxSizeExceededError, sanitize_filename()

### Community 51 - "server/__init__.py"
Cohesion: 0.11
Nodes (4): call_rsgi_http(), MockRSGIScope, extract_token_from_scope(), TestCoreFileSubsystem

### Community 54 - "CRUD Engine и спецификации моделей"
Cohesion: 0.40
Nodes (4): CRUD Engine и спецификации моделей, Автоматическая валидация, Интерактивный пример, Определение модели

### Community 55 - ".text"
Cohesion: 0.15
Nodes (6): downgrade(), upgrade(), downgrade(), upgrade(), generate(), TestMigrationV210

### Community 56 - "Role"
Cohesion: 0.15
Nodes (3): _prevent_system_role_deletion(), _prevent_system_role_modification(), Role

### Community 58 - "TTLCache"
Cohesion: 0.15
Nodes (3): get_cached(), set_cached(), TTLCache

### Community 59 - "Руководство для разработчиков: Быстрый старт"
Cohesion: 0.25
Nodes (7): Архитектура системы, Быстрый старт полноценного приложения, Интерактивный компонент: Пагинация, Полезные ссылки, Простейшее приложение, Руководство для разработчиков: Быстрый старт, Установка

### Community 61 - "oauth/rpc.py"
Cohesion: 0.16
Nodes (3): AuthConfig, OAuthAccount, _utc_now()

### Community 62 - "ForbiddenError"
Cohesion: 0.16
Nodes (7): login(), ForbiddenError, register_auth_rpc(), login(), logout(), me(), serialize_session_data()

### Community 64 - "crud/rpc.py"
Cohesion: 0.18
Nodes (4): hash_password(), register_crud_rpc(), create_user(), TestPasswords

### Community 65 - "User"
Cohesion: 0.36
Nodes (4): User, register(), verify_email_code(), test_oauth_login_seamless_linking_by_email()

### Community 67 - ".test_site_tree_guest_permissions_and_bot_rendering"
Cohesion: 0.17
Nodes (3): configure_seo(), TestRendererAndTemplateValidation, TestSeoSiteTreeRpcAndHttpIntegration

### Community 68 - "renderer.py"
Cohesion: 0.21
Nodes (5): SeoPageData, _format_datetime(), render_404_html(), render_seo_page(), custom_landing()

### Community 71 - "compile_model_spec"
Cohesion: 0.22
Nodes (3): compile_model_spec(), FieldSpec, _map_sa_type()

### Community 72 - "RPC-маршрутизация и права доступа"
Cohesion: 0.50
Nodes (3): RPC-маршрутизация и права доступа, Регистрация метода, Системные роли `adm_*`

### Community 73 - "manager.py"
Cohesion: 0.25
Nodes (4): find_available_username(), get_auth_config(), link_or_create_oauth_user(), sanitize_username()

### Community 75 - "bot_page"
Cohesion: 0.24
Nodes (4): bot_page(), decorator(), BotRoute, _send_html()

### Community 79 - "site_tree.py"
Cohesion: 0.11
Nodes (4): Base, RowSecureModel, _utc_now(), compile_pattern_to_regex()

### Community 83 - "CrudEngine"
Cohesion: 0.11
Nodes (11): Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`), CrudEngine, ModelSpec, is_model_allowed_for_seo(), _generator(), resolve_foreign_target_spec(), _validate_tree_security(), collect_site_tree_sitemap_urls() (+3 more)

## Knowledge Gaps
- **1 isolated node(s):** `pyferro`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 759 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `paginate_tabular()` connect `pagination.py` to `sqlalchemy`, `seo/__init__.py`, `site_tree.py`?**
  _High betweenness centrality (0.337) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `SessionData` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`SessionData` has 40 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pyferro` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.057912457912457915 - nodes in this community are weakly interconnected._
- **Why does `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)` connect `pagination.py` to `rpc.js`, `.notify`?**
  _High betweenness centrality (0.334) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `Session` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`Session` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Should `Database` be split into smaller, more focused modules?**
  _Cohesion score 0.10099573257467995 - nodes in this community are weakly interconnected._