# Graph Report - pyferro2  (2026-11-10)

## Corpus Check
- 115 files · ~85,909 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .ini 1)

## Summary
- 1809 nodes · 4209 edges · 101 communities (67 shown, 34 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 539 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `06669c84`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.svelte
- Database
- orjson
- 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian
- PermissionsView.svelte
- CacheView.svelte
- RpcError
- TestRegistrationAndCompilation
- app.py
- cache/rpc.py
- asyncio
- SeoView.svelte
- package.json
- test_server_and_files.py
- .transfer
- PyFerro 2.0 — Руководство разработчика и Архитектура
- handle_bot_http
- UsersView.svelte
- ModelQueryWrapper
- index.js
- .call
- PaginationDemo.svelte
- pagination.py
- CacheManager
- OAuthView.svelte
- CrudEngine
- release.py
- PyFerroApp
- 🚀 PyFerro Showcase & Demo (pyferro-demo)
- HelpView.svelte
- 🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план
- UnauthorizedError
- .test_multireturn_yield_over_websocket
- register_oauth_rpc
- finishOAuthLogin
- site_tree.py
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
- ensure_admin_user
- MockRSGIWebsocketProtocol
- test_seo.py
- server/__init__.py
- mailer.py
- MockRSGIHTTPProtocol
- CRUD Engine и спецификации моделей
- .text
- auth/models.py
- migration_v2_0_0.py
- TTLCache
- Руководство для разработчиков: Быстрый старт
- .transfer
- oauth/rpc.py
- cache/manager.py
- RpcRouter
- register_crud_rpc
- User
- .notify
- seo/__init__.py
- orjson
- Session
- core/__init__.py
- 3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile)
- ModelSpec
- EmailVerificationStore
- bot_page
- app
- render_markdown_filter
- ⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)
- cache/models.py
- _extract_from_clause_tables
- Pagination.svelte
- Base
- Глава 5: Автоматическое кеширование, Offline-First и Медиа-кеш (IndexedDB)
- Any
- @lucide/svelte
- TestSessionData
- .rpc_method
- db
- .guest
- .test_session_notify_and_lazy_db_injection
- auth.svelte.js
- 🧰 2. Возможности бэкенда (`paginate_tabular`)
- CacheConfig
- .test_admin_settings_and_manifest
- TestConstants
- TestBotDetector
- TestRendererAndTemplateValidation

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 97 edges
2. `Session` - 75 edges
3. `PyFerroApp` - 67 edges
4. `CrudEngine` - 62 edges
5. `RpcRouter` - 59 edges
6. `Database` - 52 edges
7. `ForbiddenError` - 38 edges
8. `register_oauth_rpc()` - 36 edges
9. `Base` - 34 edges
10. `RpcError` - 33 edges

## Surprising Connections (you probably didn't know these)
- `Определение модели` --references--> `RowSecureModel`  [INFERRED]
  docs/help/02_crud_engine.md → src/pyferro2/db/base.py
- `Защита от Disk Exhaustion DoS и Slowloris` --references--> `FileStorage`  [INFERRED]
  NGINX.md → src/pyferro2/files/storage.py
- `3.1. Статический анализ Scope (`public` vs `user`)` --references--> `RpcMethodSpec`  [INFERRED]
  docs/help/05_caching_and_offline.md → src/pyferro2/rpc/router.py
- `📦 5. Сетевой формат `$tabular`` --references--> `unpackTabular()`  [INFERRED]
  PAGINATION.md → frontend/src/rpc.js
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `User`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py

## Import Cycles
- None detected.

## Communities (101 total, 34 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.06
Nodes (30): activeTab, authMode, createModelRow(), deleteModelRow(), errorMsg, helpSlug, isOAuthLoading, loadModelRows() (+22 more)

### Community 1 - "Database"
Cohesion: 0.11
Nodes (10): render_jinja_template(), HtmlBuilder, preview_node(), _build_breadcrumbs(), _coerce_column_value(), match_and_render_site_tree(), render_collection_node(), render_detail_node() (+2 more)

### Community 3 - "🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian"
Cohesion: 0.25
Nodes (8): 1. Загрузка файлов (Upload): Потоковый Fail-Fast (RSGI), 2. Скачивание файлов (Download): `X-Accel-Redirect` и защита от XSS, 4. Полная боевая конфигурация Nginx / Angie, 5. Конфигурация Caddy v2 (`Caddyfile`), 🏛️ Архитектурный паттерн: «Золотая середина», Двухфазная загрузка (2PC) в PyFerro:, Защита от Disk Exhaustion DoS и Slowloris, 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian

### Community 4 - "PermissionsView.svelte"
Cohesion: 0.04
Nodes (46): ACTION_LABELS, allMethods, allowedCards, allowedMethodsCount, collapsedMap, currentVerifyMethod, currentVerifyRole, disallowedCards (+38 more)

### Community 5 - "CacheView.svelte"
Cohesion: 0.08
Nodes (18): buildSnapshot(), collapsedMap, config, filterMode, groupedCards, hasUnsavedChanges, isLoading, isPurging (+10 more)

### Community 6 - "RpcError"
Cohesion: 0.11
Nodes (10): 3.2. Авто-трекинг таблиц SQLAlchemy (`db/engine.py`), Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`), register_file_rpc(), commit(), delete(), get_download_token(), list_my(), rollback() (+2 more)

### Community 8 - "app.py"
Cohesion: 0.11
Nodes (3): admRole, JsonRpcErrorCode, StoredFile

### Community 9 - "cache/rpc.py"
Cohesion: 0.15
Nodes (11): 2.3. Системные RPC-методы управления (`cache.*`), load_cache_from_db(), purge_all_cache(), save_cache_to_db(), CacheConfigRecord, infer_method_cache_scope(), is_app_cacheable_method(), register_cache_rpc() (+3 more)

### Community 10 - "asyncio"
Cohesion: 0.09
Nodes (4): TestClassNestingAndRouterInclude, TestDryRunAccessCheck, TestParamsValidationAndRawWireProtocol, TestThreeStepAccessControl

### Community 11 - "SeoView.svelte"
Cohesion: 0.06
Nodes (41): activeField, addChildNode(), allowedModels, availableModels, botRoutes, currentNode, currentParents, currentSelection (+33 more)

### Community 12 - "package.json"
Cohesion: 0.14
Nodes (16): @tailwindcss/vite@^4.3.3, devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0, name, private, scripts (+8 more)

### Community 13 - "test_server_and_files.py"
Cohesion: 0.12
Nodes (5): make_ws_close(), make_ws_message(), MockRSGIWebsocketProtocol, app(), TestHttpAndWebSocketTransport

### Community 16 - "PyFerro 2.0 — Руководство разработчика и Архитектура"
Cohesion: 0.22
Nodes (6): 2. Быстрый старт (приложение в 30 строк), 3. Виды RPC-методов и Smart DI, 4. Файловая подсистема (2PC) и проксирование (Nginx / Angie / Caddy), 6. Табличная пагинация и сжатие трафика ($tabular), PyFerro 2.0 — Руководство разработчика и Архитектура, Мультиретурн (`async def ... yield`) и уведомления (`session.notify`)

### Community 17 - "handle_bot_http"
Cohesion: 0.24
Nodes (4): extract_cookies(), extract_header(), extract_query_params(), is_bot()

### Community 18 - "UsersView.svelte"
Cohesion: 0.07
Nodes (25): activeAdminCount, activeCustomUserCount, adminRoles, assignableRoles, customUserRoles, errorMsg, handleCreateUser(), handleSaveRoles() (+17 more)

### Community 19 - "ModelQueryWrapper"
Cohesion: 0.08
Nodes (9): build_template_context(), get_jinja_env(), is_sensitive_field(), ModelQueryWrapper, _generator(), RecordWrapper, serialize_safe_record(), validate_jinja_template() (+1 more)

### Community 20 - "index.js"
Cohesion: 0.10
Nodes (15): {
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
  }, addToast(), getToasts() (+7 more)

### Community 21 - ".call"
Cohesion: 0.12
Nodes (6): MethodNotFoundError, _bind_user_params(), check_rpc_access(), encode_error(), RpcMethodSpec, _run_stream()

### Community 22 - "PaginationDemo.svelte"
Cohesion: 0.17
Nodes (9): hasNext, hasPrev, limit, mockPaginator, page, pageNumbers, { total = 250, pageSize = 10, currentPage = 1 }, totalCount (+1 more)

### Community 23 - "pagination.py"
Cohesion: 0.09
Nodes (18): unpack_tabular(), decode_cursor(), encode_cursor(), _extract_item_value(), _find_model_class(), _format_tabular_rows(), _is_entity_select(), paginate_tabular() (+10 more)

### Community 25 - "OAuthView.svelte"
Cohesion: 0.06
Nodes (27): accounts, accountToDelete, allowRegistration, appLogoSvg, appTitle, executeDelete(), filterProvider, isDeleting (+19 more)

### Community 26 - "CrudEngine"
Cohesion: 0.09
Nodes (9): CrudEngine, _create(), _delete(), _read(), _update(), _serialize_instance(), clear_seo_cache(), set_cached_site_tree() (+1 more)

### Community 27 - "release.py"
Cohesion: 0.06
Nodes (21): build_help_bundle(), _file_to_slug_and_order(), HelpDocParser, _highlight_code(), main(), parse_markdown_doc(), _parse_widget_props(), _slugify() (+13 more)

### Community 28 - "PyFerroApp"
Cohesion: 0.08
Nodes (6): main(), _granian_target_loader(), _iter_rsgi_chunks(), PyFerroApp, _run(), _set_scope_session_data()

### Community 29 - "🚀 PyFerro Showcase & Demo (pyferro-demo)"
Cohesion: 0.29
Nodes (6): 🚀 PyFerro Showcase & Demo (pyferro-demo), 🛡️ Безопасность и архитектурная изоляция, ⚡ Быстрый старт, 💡 Использование как шаблона, Установка и запуск в 1 команду:, 📂 Что входит в пример: SEO-Форум

### Community 30 - "HelpView.svelte"
Cohesion: 0.13
Nodes (17): activeArticle, articleLoading, articles, createSnippet(), { currentSlug = '', onNavigate = null }, errorMsg, escapeHtml(), escapeRegex() (+9 more)

### Community 31 - "🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план"
Cohesion: 0.33
Nodes (5): 🏛️ 1. Архитектурные принципы PyFerro 2.0, 🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план, ⚡ Закон минимального потребления CPU и Zero-Boilerplate:, Золотые правила чистоты:, 🎯 Результат выполнения плана:

### Community 32 - "UnauthorizedError"
Cohesion: 0.11
Nodes (12): async_http_json(), _sync_http_request(), BaseProvider, ExternalUserProfile, GoogleProvider, TelegramProvider, VkProvider, YandexProvider (+4 more)

### Community 34 - "register_oauth_rpc"
Cohesion: 0.15
Nodes (14): send_email(), get_auth_config(), get_or_create_config(), seed_auth_configs(), AuthConfig, register_oauth_rpc(), admin_delete(), admin_get_all_configs() (+6 more)

### Community 35 - "finishOAuthLogin"
Cohesion: 0.25
Nodes (16): confirmSidebarTabSwitch(), doSwitchTab(), finishOAuthLogin(), handleLoginSubmit(), handleOAuthMessage(), handleRegisterSubmit(), handleVerifySubmit(), loadActiveTab() (+8 more)

### Community 36 - "site_tree.py"
Cohesion: 0.10
Nodes (17): InvalidParamsError, resolve_foreign_target_spec(), SeoConfigRecord, register_seo_rpc(), apply_preset(), get_tree(), ping_indexnow(), save_tree() (+9 more)

### Community 37 - "🏛️ 7 Ключевых Правил Архитектуры GUI"
Cohesion: 0.11
Nodes (18): 1. Zero Hardcoded Colors (Только токены системы), 1. Поверхности и фоны, 2. Theme Invariant (Запрет утилиты `dark:`), 2. Границы и разделители, 3. Типографика, 3. Фотометрическая эргономика (Защита зрения), 4. Закон эшелонирования слоев (Elevation Law), 4. Статусы и Акценты (+10 more)

### Community 38 - "sitemap.py"
Cohesion: 0.17
Nodes (8): build_sitemap_xml(), collect_all_sitemap_urls(), _format_lastmod(), handle_sitemap_http(), register_sitemap_provider(), _render_sitemapindex_xml(), _render_urlset_xml(), _send_xml()

### Community 40 - "Database"
Cohesion: 0.18
Nodes (3): Database, TestDatabaseAndModels, TestMigrationV210

### Community 41 - "register_help_rpc"
Cohesion: 0.16
Nodes (6): register_help_rpc(), get_search_index(), get_tree(), search_index(), tree(), _resolve_bundle_path()

### Community 43 - "rpc.js"
Cohesion: 0.10
Nodes (11): canonicalParamsString(), client, extractMediaUrls(), generateUuid(), idbStorage, PyFerroIndexedDB, rpc, RpcClient (+3 more)

### Community 47 - "theme.svelte.js"
Cohesion: 0.33
Nodes (5): currentTheme, initTheme(), isDark(), setTheme(), toggleTheme()

### Community 48 - "ensure_admin_user"
Cohesion: 0.11
Nodes (7): ensure_admin_user(), seed_system_roles(), cache_app(), add_crop(), app(), TestSeoSiteTreeRpcAndHttpIntegration, custom_landing()

### Community 50 - "test_seo.py"
Cohesion: 0.11
Nodes (7): FileMaxSizeExceededError, sanitize_filename(), UploadTransaction, Category, Crud, Product, Crud

### Community 51 - "server/__init__.py"
Cohesion: 0.11
Nodes (5): call_rsgi_http(), MockRSGIScope, extract_token_from_scope(), TestCoreFileSubsystem, test_full_application_lifecycle()

### Community 54 - "CRUD Engine и спецификации моделей"
Cohesion: 0.40
Nodes (4): CRUD Engine и спецификации моделей, Автоматическая валидация, Интерактивный пример, Определение модели

### Community 55 - ".text"
Cohesion: 0.15
Nodes (6): downgrade(), upgrade(), downgrade(), upgrade(), downgrade(), upgrade()

### Community 56 - "auth/models.py"
Cohesion: 0.08
Nodes (10): Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`), _prevent_system_role_deletion(), _prevent_system_role_modification(), Role, RolePermission, hash_password(), verify_password(), load_guest_session_data() (+2 more)

### Community 58 - "TTLCache"
Cohesion: 0.15
Nodes (3): get_cached(), set_cached(), TTLCache

### Community 59 - "Руководство для разработчиков: Быстрый старт"
Cohesion: 0.25
Nodes (7): Архитектура системы, Быстрый старт полноценного приложения, Интерактивный компонент: Пагинация, Полезные ссылки, Простейшее приложение, Руководство для разработчиков: Быстрый старт, Установка

### Community 62 - "cache/manager.py"
Cohesion: 0.20
Nodes (4): compute_etag(), record_read_table(), start_table_tracking(), stop_table_tracking()

### Community 63 - "RpcRouter"
Cohesion: 0.15
Nodes (6): 3.1. Статический анализ Scope (`public` vs `user`), 3.3. Протокол ETag (`$if_none_match` и `$not_modified`), 3.4. Защита от дублей для Offline Outbox (`$idempotency_key`), 3. Архитектура серверного движка (`src/pyferro2/cache/`), RpcRouter, router()

### Community 64 - "register_crud_rpc"
Cohesion: 0.15
Nodes (7): 🗺️ 2. Поэтапный план реализации, Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`), Этап 6: Интерфейс панели управления (`pyferro2/frontend/`, маршрут `/pyferro_admin`), Этап 7: Сквозное тестирование и документация (`pyferro2/tests/`), register_crud_rpc(), schemas()

### Community 65 - "User"
Cohesion: 0.10
Nodes (14): User, find_available_username(), link_or_create_oauth_user(), sanitize_username(), login(), register(), verify_email_code(), ForbiddenError (+6 more)

### Community 68 - "seo/__init__.py"
Cohesion: 0.14
Nodes (7): configure_seo(), get_seo_config(), SeoConfig, SeoPageData, _format_datetime(), render_404_html(), render_seo_page()

### Community 69 - "orjson"
Cohesion: 0.18
Nodes (5): enqueue_indexnow_urls(), flush_indexnow_queue(), notify_indexnow(), _post_indexnow_sync(), _send_indexnow_background()

### Community 70 - "Session"
Cohesion: 0.09
Nodes (10): Session, test_oauth_admin_api(), test_oauth_get_auth_url_providers(), test_oauth_login_telegram_flow(), test_oauth_login_telegram_invalid_hash(), test_oauth_login_vk_flow(), test_public_config_and_branding(), test_registration_direct_flow() (+2 more)

### Community 71 - "core/__init__.py"
Cohesion: 0.21
Nodes (4): WsCloseCode, apply_tabular_result(), is_tabular(), pack_tabular()

### Community 72 - "3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile)"
Cohesion: 0.25
Nodes (7): 1. Регистрация RPC-методов на бэкенде, 2. Системные роли безопасности, 3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile), RPC-маршрутизация и авторизация, 🌐 Подключение по WebSocket (`/ws`), 🔑 Хранение токена и работа с Cookie, ⚠️ Частые архитектурные ошибки и их решение

### Community 73 - "ModelSpec"
Cohesion: 0.19
Nodes (5): Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`), ModelSpec, is_model_allowed_for_seo(), _validate_tree_security(), _get_allowed_spec()

### Community 75 - "bot_page"
Cohesion: 0.19
Nodes (5): bot_page(), decorator(), BotRoute, handle_bot_http(), _send_html()

### Community 78 - "render_markdown_filter"
Cohesion: 0.18
Nodes (5): render_markdown_filter(), _flush_para(), _flush_table(), _format_inline(), TestMarkdownFilterAndQueryRouting

### Community 79 - "⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)"
Cohesion: 0.20
Nodes (11): 1.1. Бэкенд (Python) — Чистая бизнес-логика, 1.2. Фронтенд (Svelte / JS) — Стандартные вызовы `rpc`, 1. Как это выглядит для прикладного разработчика, createPaginator(), 🚀 1. Быстрый старт: Бэкенд за 1 строчку, 🎨 3. Быстрый старт: Фронтенд (JS / Svelte), 🛠️ 4. Методы и свойства `createPaginator`, Вариант А: Передача модели (Zero-SQL) (+3 more)

### Community 81 - "_extract_from_clause_tables"
Cohesion: 0.22
Nodes (6): _extract_from_clause_tables(), _extract_statement_tables(), _on_session_after_commit(), _on_session_after_flush(), _on_session_after_rollback(), _on_session_orm_execute()

### Community 82 - "Pagination.svelte"
Cohesion: 0.20
Nodes (5): { paginator, showLimitSelect = true, showTotal = true }, sizeClasses, {
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
  }

### Community 83 - "Base"
Cohesion: 0.11
Nodes (9): compile_model_spec(), FieldSpec, _map_sa_type(), Base, RowSecureModel, _utc_now(), SampleArticle, db_session() (+1 more)

### Community 84 - "Глава 5: Автоматическое кеширование, Offline-First и Медиа-кеш (IndexedDB)"
Cohesion: 0.18
Nodes (8): 2.1. Глобальные настройки (`pf_cache_config`), 2.2. Правила для методов по Плашкам (`pf_cache_rules`), 2. Управление кешированием в Админке (`CacheView.svelte`), 4.1. Схема базы `IndexedDB` (`pyferro2_storage`, version `1`), 4.2. Алгоритм работы `rpc.call(method, params, options)`, 4.3. Кеширование и раздача картинок (`Media Prefetcher` + `Service Worker`), 4. Архитектура клиентского движка (`IndexedDB` `pyferro2_storage`), Глава 5: Автоматическое кеширование, Offline-First и Медиа-кеш (IndexedDB)

### Community 86 - "@lucide/svelte"
Cohesion: 0.22
Nodes (5): dependencies, @lucide/svelte@^1.61.0, tailwindcss@^4.3.3, {
    open = false,
    onclose = () => {},
    title = "",
    children,
    footer,
    class: customClass = "",
    maxWidth = "max-w-xl",
  }, @lucide/svelte

### Community 88 - ".rpc_method"
Cohesion: 0.32
Nodes (3): _compile_method_spec(), _resolve_method_name(), _decorator()

### Community 89 - "db"
Cohesion: 0.29
Nodes (4): 1. Ключевые принципы архитектуры, db(), Article, Crud

### Community 92 - "auth.svelte.js"
Cohesion: 0.47
Nodes (4): authState, loginAdmin(), logoutAdmin(), setStoredToken()

### Community 93 - "🧰 2. Возможности бэкенда (`paginate_tabular`)"
Cohesion: 0.40
Nodes (5): 1. Два режима пагинации «под капотом»:, 2. Авто-трансляция фильтров и поиска в SQL:, 🧰 2. Возможности бэкенда (`paginate_tabular`), 3. Оптимизация Zero-Hydration:, Сигнатура функции:

## Knowledge Gaps
- **1 isolated node(s):** `pyferro`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 862 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **34 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `createPaginator()` connect `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)` to `rpc.js`?**
  _High betweenness centrality (0.277) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `SessionData` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`SessionData` has 42 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pyferro` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.06306306306306306 - nodes in this community are weakly interconnected._
- **Why does `Глава 5: Автоматическое кеширование, Offline-First и Медиа-кеш (IndexedDB)` connect `Глава 5: Автоматическое кеширование, Offline-First и Медиа-кеш (IndexedDB)` to `CrudEngine`, `RpcRouter`, `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `Session` (e.g. with `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` and `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)`) actually correct?**
  _`Session` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Should `Database` be split into smaller, more focused modules?**
  _Cohesion score 0.10793650793650794 - nodes in this community are weakly interconnected._