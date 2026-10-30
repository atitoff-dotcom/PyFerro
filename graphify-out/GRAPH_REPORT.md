# Graph Report - pyferro2  (2026-10-30)

## Corpus Check
- 109 files · ~62,436 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 3, .css 1, .ini 1)

## Summary
- 1468 nodes · 3357 edges · 85 communities (51 shown, 34 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 419 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `dcbef6a9`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.svelte
- Database
- sqlalchemy
- .notify
- PermissionsView.svelte
- seo/__init__.py
- rpc/__init__.py
- RpcRouter
- server/app.py
- auth/models.py
- asyncio
- SeoView.svelte
- package.json
- test_server_and_files.py
- SessionData
- .transfer
- jinja_engine.py
- seo/__init__.py
- UsersView.svelte
- ModelQueryWrapper
- index.js
- .call
- PaginationDemo.svelte
- paginate_tabular
- RpcError
- Session
- CrudEngine
- release.py
- Any
- forum/rpc.py
- HelpView.svelte
- 🗺️ 2. Поэтапный план реализации
- TestRegistrationAndCompilation
- .test_multireturn_yield_over_websocket
- release.py
- PyFerroApp
- .rpc_method
- 🏛️ 7 Ключевых Правил Архитектуры GUI
- sitemap.py
- TokenManager
- Database
- register_help_rpc
- FileStorage
- rpc.js
- 🏛️ PyFerro Project Rules & Architecture Guidelines
- pyferro
- TestSessionData
- core/__init__.py
- seed_system_roles
- MockRSGIWebsocketProtocol
- storage.py
- server/__init__.py
- pagination.py
- MockRSGIHTTPProtocol
- RowSecureModel
- .text
- Role
- migration_v2_0_0.py
- TTLCache
- Руководство для разработчиков: Быстрый старт
- Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)
- .transfer
- register_auth_rpc
- test_core_contracts.py
- .test_upload_fail_fast_content_length_and_slowloris_protection
- User
- Pagination.svelte
- .test_site_tree_guest_permissions_and_bot_rendering
- renderer.py
- TestForumE2E
- TestSession
- TestBotDetector
- RPC-маршрутизация и права доступа
- theme.svelte.js
- _format_tabular_rows
- Base
- _find_model_class
- base.py
- extract_token_from_scope
- .test_class_nesting_creates_plaque_method
- Enum
- _validate_tree_security

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 93 edges
2. `CrudEngine` - 60 edges
3. `Session` - 59 edges
4. `Database` - 51 edges
5. `PyFerroApp` - 51 edges
6. `RpcRouter` - 50 edges
7. `RpcError` - 32 edges
8. `register_seo_rpc()` - 32 edges
9. `ForbiddenError` - 31 edges
10. `Base` - 27 edges

## Surprising Connections (you probably didn't know these)
- `Защита от Disk Exhaustion DoS и Slowloris` --references--> `FileStorage`  [INFERRED]
  NGINX.md → src/pyferro2/files/storage.py
- `📂 Что входит в пример: SEO-Форум` --references--> `list_topics()`  [INFERRED]
  docs/help/04_demo_and_examples.md → examples/pyferro-demo/src/pyferro_demo/forum/rpc.py
- `📦 5. Сетевой формат `$tabular`` --references--> `unpackTabular()`  [INFERRED]
  PAGINATION.md → frontend/src/rpc.js
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `Role`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `User`  [INFERRED]
  ROADMAP_V2.md → src/pyferro2/auth/models.py

## Import Cycles
- None detected.

## Communities (85 total, 34 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.08
Nodes (34): activeTab, confirmSidebarTabSwitch(), createModelRow(), deleteModelRow(), doSwitchTab(), errorMsg, handleLoginSubmit(), helpSlug (+26 more)

### Community 1 - "Database"
Cohesion: 0.08
Nodes (20): build_template_context(), is_model_allowed_for_seo(), _generator(), render_jinja_template(), resolve_foreign_target_spec(), serialize_safe_record(), SeoPageData, HtmlBuilder (+12 more)

### Community 3 - ".notify"
Cohesion: 0.05
Nodes (32): createPaginator(), 1. Загрузка файлов (Upload): Потоковый Fail-Fast (RSGI), 2. Скачивание файлов (Download): `X-Accel-Redirect` и защита от XSS, 3. WebSocket и мультиретурн (`yield`), 4. Полная боевая конфигурация Nginx / Angie, 5. Конфигурация Caddy v2 (`Caddyfile`), 🏛️ Архитектурный паттерн: «Золотая середина», Двухфазная загрузка (2PC) в PyFerro: (+24 more)

### Community 4 - "PermissionsView.svelte"
Cohesion: 0.05
Nodes (38): ACTION_LABELS, allMethods, allowedCards, allowedMethodsCount, collapsedMap, disallowedCards, discardAndSwitchRole(), editableRoles (+30 more)

### Community 5 - "seo/__init__.py"
Cohesion: 0.08
Nodes (22): InvalidParamsError, enqueue_indexnow_urls(), flush_indexnow_queue(), notify_indexnow(), _post_indexnow_sync(), _send_indexnow_background(), configure_seo(), get_seo_config() (+14 more)

### Community 6 - "rpc/__init__.py"
Cohesion: 0.20
Nodes (4): Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`), JsonRpcErrorCode, MethodNotFoundError, check_rpc_access()

### Community 7 - "RpcRouter"
Cohesion: 0.10
Nodes (3): register_crud_rpc(), RpcRouter, router()

### Community 9 - "auth/models.py"
Cohesion: 0.20
Nodes (3): hash_password(), verify_password(), TestPasswords

### Community 10 - "asyncio"
Cohesion: 0.11
Nodes (3): TestParamsValidationAndRawWireProtocol, TestSmartDIAndLazyDatabase, TestThreeStepAccessControl

### Community 11 - "SeoView.svelte"
Cohesion: 0.06
Nodes (40): activeField, addChildNode(), applyPreset(), availableModels, availablePresets, botRoutes, currentNode, currentParents (+32 more)

### Community 12 - "package.json"
Cohesion: 0.13
Nodes (18): dependencies, tailwindcss@^4.3.3, @tailwindcss/vite@^4.3.3, devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0, name (+10 more)

### Community 16 - "jinja_engine.py"
Cohesion: 0.15
Nodes (4): get_jinja_env(), validate_jinja_template(), validate_template(), TestRendererAndTemplateValidation

### Community 17 - "seo/__init__.py"
Cohesion: 0.11
Nodes (11): extract_cookies(), extract_header(), extract_query_params(), is_bot(), get_cached(), set_cached(), bot_page(), decorator() (+3 more)

### Community 18 - "UsersView.svelte"
Cohesion: 0.06
Nodes (25): activeAdminCount, activeCustomUserCount, adminRoles, assignableRoles, customUserRoles, errorMsg, handleCreateUser(), handleSaveRoles() (+17 more)

### Community 19 - "ModelQueryWrapper"
Cohesion: 0.13
Nodes (3): is_sensitive_field(), ModelQueryWrapper, RecordWrapper

### Community 20 - "index.js"
Cohesion: 0.08
Nodes (18): @lucide/svelte@^1.61.0, {
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
  } (+10 more)

### Community 21 - ".call"
Cohesion: 0.17
Nodes (4): _bind_user_params(), encode_error(), RpcMethodSpec, _run_stream()

### Community 22 - "PaginationDemo.svelte"
Cohesion: 0.17
Nodes (9): hasNext, hasPrev, limit, mockPaginator, page, pageNumbers, { total = 250, pageSize = 10, currentPage = 1 }, totalCount (+1 more)

### Community 23 - "paginate_tabular"
Cohesion: 0.29
Nodes (9): unpack_tabular(), paginate_tabular(), test_count_false_mode(), test_cursor_pagination(), test_custom_select_and_column_projection(), test_offset_pagination_first_page(), test_offset_pagination_last_page(), test_offset_pagination_second_page() (+1 more)

### Community 24 - "RpcError"
Cohesion: 0.17
Nodes (9): Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`), register_file_rpc(), commit(), delete(), get_download_token(), list_my(), rollback(), ForbiddenError (+1 more)

### Community 26 - "CrudEngine"
Cohesion: 0.06
Nodes (12): CrudEngine, _create(), _delete(), _read(), _update(), _serialize_instance(), compile_model_spec(), FieldSpec (+4 more)

### Community 27 - "release.py"
Cohesion: 0.10
Nodes (9): build_help_bundle(), _file_to_slug_and_order(), HelpDocParser, _highlight_code(), main(), parse_markdown_doc(), _parse_widget_props(), _slugify() (+1 more)

### Community 29 - "forum/rpc.py"
Cohesion: 0.07
Nodes (26): 🚀 PyFerro Showcase & Demo (pyferro-demo), 🛡️ Безопасность и архитектурная изоляция, ⚡ Быстрый старт, 💡 Использование как шаблона, Установка и запуск в 1 команду:, 📂 Что входит в пример: SEO-Форум, 1. Установка из PyPI:, 2. Запуск приложения: (+18 more)

### Community 30 - "HelpView.svelte"
Cohesion: 0.11
Nodes (19): activeArticle, articleLoading, articles, createSnippet(), { currentSlug = '', onNavigate = null }, errorMsg, escapeHtml(), escapeRegex() (+11 more)

### Community 31 - "🗺️ 2. Поэтапный план реализации"
Cohesion: 0.20
Nodes (10): 🏛️ 1. Архитектурные принципы PyFerro 2.0, 🗺️ 2. Поэтапный план реализации, 🚀 Дорожная карта реализации PyFerro 2.0: Архитектурный план, ⚡ Закон минимального потребления CPU и Zero-Boilerplate:, 🎯 Результат выполнения плана:, Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`), Этап 6: Интерфейс панели управления (`pyferro2/frontend/`, маршрут `/pyferro_admin`) (+2 more)

### Community 34 - "release.py"
Cohesion: 0.14
Nodes (13): main(), build_and_upload_pypi(), build_frontend(), build_help(), ensure_migration_for_release(), get_current_version(), git_commit_and_push(), is_minor_release() (+5 more)

### Community 35 - "PyFerroApp"
Cohesion: 0.11
Nodes (3): main(), _granian_target_loader(), PyFerroApp

### Community 36 - ".rpc_method"
Cohesion: 0.32
Nodes (3): _compile_method_spec(), _resolve_method_name(), _decorator()

### Community 37 - "🏛️ 7 Ключевых Правил Архитектуры GUI"
Cohesion: 0.11
Nodes (18): 1. Zero Hardcoded Colors (Только токены системы), 1. Поверхности и фоны, 2. Theme Invariant (Запрет утилиты `dark:`), 2. Границы и разделители, 3. Типографика, 3. Фотометрическая эргономика (Защита зрения), 4. Закон эшелонирования слоев (Elevation Law), 4. Статусы и Акценты (+10 more)

### Community 38 - "sitemap.py"
Cohesion: 0.16
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

### Community 47 - "core/__init__.py"
Cohesion: 0.21
Nodes (3): apply_tabular_result(), is_tabular(), pack_tabular()

### Community 48 - "seed_system_roles"
Cohesion: 0.13
Nodes (5): ensure_admin_user(), load_guest_session_data(), seed_system_roles(), _run(), app()

### Community 50 - "storage.py"
Cohesion: 0.11
Nodes (4): StoredFile, FileMaxSizeExceededError, sanitize_filename(), UploadTransaction

### Community 51 - "server/__init__.py"
Cohesion: 0.14
Nodes (5): call_rsgi_http(), make_ws_close(), make_ws_message(), MockRSGIScope, TestMultiReturnAndGracefulDisconnect

### Community 52 - "pagination.py"
Cohesion: 0.20
Nodes (3): decode_cursor(), encode_cursor(), test_cursor_encode_decode()

### Community 54 - "RowSecureModel"
Cohesion: 0.15
Nodes (9): CRUD Engine и спецификации моделей, Автоматическая валидация, Интерактивный пример, Определение модели, RowSecureModel, Category, Crud, Product (+1 more)

### Community 55 - ".text"
Cohesion: 0.33
Nodes (3): downgrade(), upgrade(), generate()

### Community 56 - "Role"
Cohesion: 0.18
Nodes (3): _prevent_system_role_deletion(), _prevent_system_role_modification(), Role

### Community 59 - "Руководство для разработчиков: Быстрый старт"
Cohesion: 0.25
Nodes (7): Архитектура системы, Быстрый старт полноценного приложения, Интерактивный компонент: Пагинация, Полезные ссылки, Простейшее приложение, Руководство для разработчиков: Быстрый старт, Установка

### Community 60 - "Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)"
Cohesion: 0.17
Nodes (4): Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`), RolePermission, db(), SampleArticle

### Community 62 - "register_auth_rpc"
Cohesion: 0.22
Nodes (6): Золотые правила чистоты:, UnauthorizedError, register_auth_rpc(), login(), me(), serialize_session_data()

### Community 65 - "User"
Cohesion: 0.18
Nodes (3): User, create_user(), app()

### Community 66 - "Pagination.svelte"
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

### Community 68 - "renderer.py"
Cohesion: 0.29
Nodes (3): _format_datetime(), render_404_html(), render_seo_page()

### Community 72 - "RPC-маршрутизация и права доступа"
Cohesion: 0.50
Nodes (3): RPC-маршрутизация и права доступа, Регистрация метода, Системные роли `adm_*`

### Community 73 - "theme.svelte.js"
Cohesion: 0.33
Nodes (5): currentTheme, initTheme(), isDark(), setTheme(), toggleTheme()

### Community 75 - "_format_tabular_rows"
Cohesion: 0.33
Nodes (3): _extract_item_value(), _format_tabular_rows(), _serialize_val()

### Community 77 - "Base"
Cohesion: 0.40
Nodes (3): Base, db_session(), DemoBook

## Knowledge Gaps
- **2 isolated node(s):** `pyferro-demo`, `pyferro`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 700 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **34 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `paginate_tabular()` connect `paginate_tabular` to `.notify`, `seo/__init__.py`, `_format_tabular_rows`, `Base`, `_find_model_class`, `pagination.py`?**
  _High betweenness centrality (0.331) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `SessionData` (e.g. with `register_forum_rpc()` and `TestForumE2E`) actually correct?**
  _`SessionData` has 39 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pyferro-demo`, `pyferro` to the rest of the system?**
  _2 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.07804878048780488 - nodes in this community are weakly interconnected._
- **Why does `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)` connect `.notify` to `rpc.js`, `paginate_tabular`?**
  _High betweenness centrality (0.320) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `CrudEngine` (e.g. with `Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`)` and `Role`) actually correct?**
  _`CrudEngine` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Should `Database` be split into smaller, more focused modules?**
  _Cohesion score 0.08020050125313283 - nodes in this community are weakly interconnected._