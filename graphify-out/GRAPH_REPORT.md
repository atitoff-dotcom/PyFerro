# Graph Report - pyferro2  (2026-10-25)

## Corpus Check
- 54 files · ~29,191 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .ini 1)

## Summary
- 838 nodes · 1649 edges · 34 communities (19 shown, 15 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 301 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6e0e267a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.svelte
- PyFerroApp
- test_crud_and_multireturn.py
- .notify
- CrudEngine
- FileStorage
- RpcError
- JsonRpcErrorCode
- app.py
- Database
- Session
- server/__init__.py
- package.json
- MockRSGIHTTPProtocol
- SessionData
- .transfer
- TokenManager
- RpcRouter
- ._bind_model_rpc
- hash_password
- .call
- Pagination.svelte
- paginate_tabular
- migration_v2_0_0.py
- .run
- ModelSpec
- release.py
- extract_token_from_scope
- Base
- TestRegistrationAndCompilation
- .test_multireturn_yield_over_websocket
- 🏛️ PyFerro Project Rules & Architecture Guidelines
- pyferro

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 65 edges
2. `PyFerroApp` - 43 edges
3. `Session` - 40 edges
4. `CrudEngine` - 35 edges
5. `RpcRouter` - 35 edges
6. `Database` - 25 edges
7. `RpcError` - 23 edges
8. `paginate_tabular()` - 22 edges
9. `FileStorage` - 20 edges
10. `ForbiddenError` - 20 edges

## Surprising Connections (you probably didn't know these)
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `Role`  [INFERRED]
  ROADMAP_V2.md → auth/models.py
- `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)` --references--> `admRole`  [INFERRED]
  ROADMAP_V2.md → core/constants.py
- `Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`)` --references--> `admRole`  [INFERRED]
  ROADMAP_V2.md → core/constants.py
- `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` --references--> `Session`  [INFERRED]
  ROADMAP_V2.md → core/session.py
- `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)` --references--> `Session`  [INFERRED]
  ROADMAP_V2.md → core/session.py

## Import Cycles
- None detected.

## Communities (34 total, 15 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.05
Nodes (49): activeTab, allMethods, createCustomRole(), createModelRow(), createNewUser(), deleteCustomRole(), deleteModelRow(), errorMsg (+41 more)

### Community 1 - "PyFerroApp"
Cohesion: 0.12
Nodes (3): _iter_rsgi_chunks(), PyFerroApp, _set_scope_session_data()

### Community 2 - "test_crud_and_multireturn.py"
Cohesion: 0.08
Nodes (6): Book, Crud, SampleArticle, TestConstants, router(), test_full_application_lifecycle()

### Community 3 - ".notify"
Cohesion: 0.05
Nodes (31): createPaginator(), 🚀 1. Быстрый старт: Бэкенд за 1 строчку, 1. Два режима пагинации «под капотом»:, 2. Авто-трансляция фильтров и поиска в SQL:, 🧰 2. Возможности бэкенда (`paginate_tabular`), 🎨 3. Быстрый старт: Фронтенд (JS / Svelte), 3. Оптимизация Zero-Hydration:, 🛠️ 4. Методы и свойства `createPaginator` (+23 more)

### Community 4 - "CrudEngine"
Cohesion: 0.14
Nodes (4): CrudEngine, _read(), _serialize_instance(), InvalidParamsError

### Community 5 - "FileStorage"
Cohesion: 0.09
Nodes (3): StoredFile, FileStorage, UploadTransaction

### Community 6 - "RpcError"
Cohesion: 0.19
Nodes (9): register_file_rpc(), commit(), delete(), get_download_token(), list_my(), rollback(), Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`), ForbiddenError (+1 more)

### Community 7 - "JsonRpcErrorCode"
Cohesion: 0.14
Nodes (5): admRole, JsonRpcErrorCode, WsCloseCode, MethodNotFoundError, UnauthorizedError

### Community 9 - "Database"
Cohesion: 0.05
Nodes (11): _prevent_system_role_deletion(), _prevent_system_role_modification(), Role, ensure_admin_user(), load_guest_session_data(), seed_system_roles(), Database, _run() (+3 more)

### Community 10 - "Session"
Cohesion: 0.06
Nodes (5): Session, TestSession, TestParamsValidationAndRawWireProtocol, TestSmartDIAndLazyDatabase, TestThreeStepAccessControl

### Community 12 - "package.json"
Cohesion: 0.14
Nodes (15): devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0, name, private, scripts, build (+7 more)

### Community 13 - "MockRSGIHTTPProtocol"
Cohesion: 0.06
Nodes (9): call_rsgi_http(), make_ws_close(), make_ws_message(), MockRSGIHTTPProtocol, MockRSGIScope, MockRSGIWebsocketProtocol, MockRSGIWebsocketTransport, TestCoreFileSubsystem (+1 more)

### Community 19 - "._bind_model_rpc"
Cohesion: 0.29
Nodes (3): _create(), _delete(), _update()

### Community 20 - "hash_password"
Cohesion: 0.16
Nodes (4): hash_password(), verify_password(), create_user(), TestPasswords

### Community 21 - ".call"
Cohesion: 0.08
Nodes (11): Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`), _bind_user_params(), check_rpc_access(), _compile_method_spec(), encode_error(), _resolve_method_name(), RpcMethodSpec, _decorator() (+3 more)

### Community 23 - "paginate_tabular"
Cohesion: 0.06
Nodes (22): apply_tabular_result(), is_tabular(), pack_tabular(), unpack_tabular(), _utc_now(), decode_cursor(), encode_cursor(), _extract_item_value() (+14 more)

### Community 26 - "ModelSpec"
Cohesion: 0.13
Nodes (4): compile_model_spec(), FieldSpec, _map_sa_type(), ModelSpec

### Community 27 - "release.py"
Cohesion: 0.16
Nodes (11): build_and_upload_pypi(), build_frontend(), ensure_migration_for_release(), get_current_version(), git_commit_and_push(), is_minor_release(), main(), run_cmd() (+3 more)

### Community 31 - "Base"
Cohesion: 0.10
Nodes (16): RolePermission, User, schemas(), Base, RowSecureModel, 🗺️ 2. Поэтапный план реализации, Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`) (+8 more)

## Knowledge Gaps
- **1 isolated node(s):** `pyferro`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 361 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `paginate_tabular()` connect `paginate_tabular` to `.notify`, `Base`?**
  _High betweenness centrality (0.209) - this node is a cross-community bridge._
- **Are the 33 inferred relationships involving `SessionData` (e.g. with `User` and `load_guest_session_data()`) actually correct?**
  _`SessionData` has 33 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pyferro` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.053005464480874315 - nodes in this community are weakly interconnected._
- **Why does `⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)` connect `.notify` to `App.svelte`, `paginate_tabular`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `PyFerroApp` (e.g. with `main()` and `5. Маршруты сервера (`PyFerroApp`)`) actually correct?**
  _`PyFerroApp` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Should `PyFerroApp` be split into smaller, more focused modules?**
  _Cohesion score 0.1206896551724138 - nodes in this community are weakly interconnected._