# Graph Report - pyferro2  (2026-10-25)

## Corpus Check
- 42 files · ~22,888 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 1 file(s) not represented in the graph (top: .css 1)

## Summary
- 696 nodes · 1374 edges · 43 communities (18 shown, 25 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 269 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- App.svelte
- PyFerroApp
- test_crud_and_multireturn.py
- .transfer
- CrudEngine
- FileStorage
- RpcError
- register_crud_rpc
- typing
- Database
- Session
- package.json
- SessionData
- TokenManager
- ModelSpec
- asyncio
- Role
- Base
- hash_password
- ._prepare_call
- User
- tabular.py
- RpcRouter
- ._bind_model_rpc
- storage.py
- _compile_method_spec
- TestSessionData
- app
- register_auth_rpc
- TestRegistrationAndCompilation
- .test_session_notify_and_lazy_db_injection

## God Nodes (most connected - your core abstractions)
1. `SessionData` - 61 edges
2. `PyFerroApp` - 41 edges
3. `Session` - 40 edges
4. `CrudEngine` - 35 edges
5. `RpcRouter` - 35 edges
6. `Database` - 24 edges
7. `RpcError` - 23 edges
8. `FileStorage` - 20 edges
9. `ForbiddenError` - 19 edges
10. `User` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `Role`  [INFERRED]
  ROADMAP_V2.md → auth/models.py
- `Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`)` --references--> `User`  [INFERRED]
  ROADMAP_V2.md → auth/models.py
- `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` --references--> `Session`  [INFERRED]
  ROADMAP_V2.md → core/session.py
- `Этап 1: Фундамент и строгие контракты (`pyferro2/core/`)` --references--> `Session`  [INFERRED]
  ROADMAP_V2.md → core/session.py
- `⚡ Закон минимального потребления CPU и Zero-Boilerplate:` --references--> `SessionData`  [INFERRED]
  ROADMAP_V2.md → core/session_data.py

## Import Cycles
- None detected.

## Communities (43 total, 25 thin omitted)

### Community 0 - "App.svelte"
Cohesion: 0.05
Nodes (48): activeTab, allMethods, createCustomRole(), createModelRow(), createNewUser(), deleteCustomRole(), deleteModelRow(), errorMsg (+40 more)

### Community 1 - "PyFerroApp"
Cohesion: 0.05
Nodes (11): encode_error(), _granian_target_loader(), _iter_request_chunks(), PyFerroApp, _run_stream(), _read_full_body(), _send_json_bytes(), extract_token_from_scope() (+3 more)

### Community 2 - "test_crud_and_multireturn.py"
Cohesion: 0.06
Nodes (9): SampleArticle, TestConstants, router(), call_asgi_http(), receive(), send(), TestCoreFileSubsystem, TestHttpAndWebSocketTransport (+1 more)

### Community 3 - ".transfer"
Cohesion: 0.06
Nodes (17): 1. Ключевые принципы архитектуры, 2. Быстрый старт (приложение в 30 строк), 3. Виды RPC-методов и Smart DI, 4. Файловая подсистема (2PC) и конфиги прокси (Nginx / Angie / Caddy), 5. Маршруты сервера (`PyFerroApp`), PyFerro 2.0 — Руководство разработчика и Архитектура, Конфигурация Caddy v2 (`Caddyfile`), Мультиретурн (`async def ... yield`) и уведомления (`session.notify`) (+9 more)

### Community 4 - "CrudEngine"
Cohesion: 0.14
Nodes (5): CrudEngine, _create(), _delete(), _read(), _serialize_instance()

### Community 5 - "FileStorage"
Cohesion: 0.09
Nodes (3): StoredFile, FileStorage, UploadTransaction

### Community 6 - "RpcError"
Cohesion: 0.16
Nodes (14): JsonRpcErrorCode, register_file_rpc(), commit(), delete(), get_download_token(), list_my(), rollback(), Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`) (+6 more)

### Community 7 - "register_crud_rpc"
Cohesion: 0.09
Nodes (10): admRole, WsCloseCode, register_crud_rpc(), schemas(), 🗺️ 2. Поэтапный план реализации, Этап 1: Фундамент и строгие контракты (`pyferro2/core/`), Этап 3: Диспетчер JSON-RPC 2.0 и авторизация RPC (`pyferro2/rpc/`), Этап 6: Интерфейс панели управления (`pyferro2/frontend/`, маршрут `/pyferro_admin`) (+2 more)

### Community 9 - "Database"
Cohesion: 0.18
Nodes (4): load_guest_session_data(), seed_system_roles(), Database, TestDatabaseAndModels

### Community 12 - "package.json"
Cohesion: 0.14
Nodes (15): devDependencies, svelte@^5.0.0, @sveltejs/vite-plugin-svelte@^5.0.3, vite@^6.0.0, name, private, scripts, build (+7 more)

### Community 15 - "ModelSpec"
Cohesion: 0.15
Nodes (6): compile_model_spec(), FieldSpec, _map_sa_type(), ModelSpec, RowSecureModel, Этап 5: Декларативный движок CRUD, RLS и единая модель `Плашка.метод` (`pyferro2/crud/`)

### Community 18 - "Role"
Cohesion: 0.18
Nodes (3): _prevent_system_role_deletion(), _prevent_system_role_modification(), Role

### Community 19 - "Base"
Cohesion: 0.16
Nodes (5): RolePermission, Base, Золотые правила чистоты:, Этап 2: База данных и чистые модели (`pyferro2/db/`, `pyferro2/auth/`), db()

### Community 20 - "hash_password"
Cohesion: 0.26
Nodes (3): hash_password(), verify_password(), TestPasswords

### Community 22 - "User"
Cohesion: 0.18
Nodes (3): User, create_user(), app()

### Community 23 - "tabular.py"
Cohesion: 0.27
Nodes (4): apply_tabular_result(), is_tabular(), pack_tabular(), unpack_tabular()

### Community 28 - "_compile_method_spec"
Cohesion: 0.28
Nodes (3): _compile_method_spec(), _resolve_method_name(), _decorator()

### Community 31 - "register_auth_rpc"
Cohesion: 0.29
Nodes (4): register_auth_rpc(), logout(), me(), serialize_session_data()

## Knowledge Gaps
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SessionData` connect `SessionData` to `PyFerroApp`, `.transfer`, `CrudEngine`, `FileStorage`, `RpcError`, `register_crud_rpc`, `Database`, `Session`, `TokenManager`, `asyncio`, `Base`, `User`, `pyferro2_core_constants`, `_compile_method_spec`, `TestSessionData`, `register_auth_rpc`, `.guest`, `.__init__`, `.resolve_token`?**
  _High betweenness centrality (0.182) - this node is a cross-community bridge._
- **Are the 31 inferred relationships involving `SessionData` (e.g. with `User` and `load_guest_session_data()`) actually correct?**
  _`SessionData` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Should `App.svelte` be split into smaller, more focused modules?**
  _Cohesion score 0.05423728813559322 - nodes in this community are weakly interconnected._
- **Why does `PyFerroApp` connect `PyFerroApp` to `test_crud_and_multireturn.py`, `.transfer`, `CrudEngine`, `FileStorage`, `RpcError`, `register_crud_rpc`, `Database`, `Session`, `app.py`, `SessionData`, `TokenManager`, `User`, `RpcRouter`, `app`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `PyFerroApp` (e.g. with `5. Маршруты сервера (`PyFerroApp`)` and `Этап 4: Сервер, Аутентификация и Файловое ядро (`pyferro2/server/`, `pyferro2/files/`)`) actually correct?**
  _`PyFerroApp` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Should `PyFerroApp` be split into smaller, more focused modules?**
  _Cohesion score 0.054354178842782 - nodes in this community are weakly interconnected._
- **Why does `Session` connect `Session` to `PyFerroApp`, `.test_session_notify_and_lazy_db_injection`, `.transfer`, `.guest`, `test_crud_and_multireturn.py`, `.__init__`, `register_crud_rpc`, `SessionData`, `asyncio`, `._prepare_call`, `RpcRouter`, `pyferro2_core_constants`, `_compile_method_spec`, `register_auth_rpc`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._