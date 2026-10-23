# -*- coding: utf-8 -*-
"""
Main entry point for the Showcase demonstration server (PyFerro).
Run:
    python server.py
    or
    granian --rsgi server:app --host 127.0.0.1 --port 8080 --workers 1

Server available at: http://127.0.0.1:8080
"""

import os
import sys
import asyncio
from datetime import datetime, timezone

# Ensure framework root and showcase directory are importable
SHOWCASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK_ROOT = os.path.abspath(os.path.join(SHOWCASE_DIR, "..", ".."))

if os.path.isdir(os.path.join(FRAMEWORK_ROOT, "pyferro")) and FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, FRAMEWORK_ROOT)
if SHOWCASE_DIR not in sys.path:
    sys.path.insert(0, SHOWCASE_DIR)

# Framework core imports
from pyferro import FerroApp
from pyferro.core.logger import setup_logging, logger
from pyferro.db import engine, Base, async_session
from pyferro.smart_cache import version_registry
from pyferro.plugins.crud import ModelRegistry


# Static directory and SQLite DB path
PUBLIC_DIR = os.path.join(SHOWCASE_DIR, "public")
DB_PATH = os.path.join(SHOWCASE_DIR, "showcase.db")

# Create FerroApp application instance (SQLite + Zero-Copy Granian Static)
# auto_auth_ws=True (по умолчанию): сокеты автоматически авторизуются по Cookie
# auto_auth_models=True (по умолчанию): User, Role, RpcPermission регистрируются в CRUD автоматически
app = FerroApp(
    secret_key="showcase-demo-secret-key-1234567890-secure-seed",
    database_url=f"sqlite+aiosqlite:///{DB_PATH}",
    login_rpc="",  # Public access for interactive showcase
    static_dir=PUBLIC_DIR,
    index_file="index.html",
    cors=True,
    enable_seo=True
)

# Регистрация бизнес-моделей в CRUD
from models import Task, Document
ModelRegistry.register(Task)
ModelRegistry.register(Document)

# Регистрация RPC-хендлеров и плагинов
import handlers  # noqa: F401
import pyferro.plugins.files  # Registers HTTP /upload and RPC files.*
import pyferro.plugins.crud as crud  # noqa: F401
import pyferro.plugins.help as help_plugin  # noqa: F401

# Initialize logging
setup_logging()


@app.on_startup
async def init_database():
    """Asynchronously creates SQLite database tables and seeds demo data on server startup."""
    from pyferro.db import system_bypass
    from pyferro.auth import User, Role, RolePermission, UserDelegation
    from sqlalchemy import select, func

    with system_bypass():
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

                # Автоматическая синхронизация отсутствующих колонок в SQLite таблицах (например, team_id в RowSecureModel)
                def _sync_sqlite_columns(connection):
                    for table_name, table in Base.metadata.tables.items():
                        try:
                            res = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
                            existing_cols = {row[1] for row in res}
                            if not existing_cols:
                                continue
                            for col in table.columns:
                                if col.name not in existing_cols:
                                    col_type = col.type.compile(connection.dialect)
                                    logger.info(f"[Showcase] Adding missing column '{col.name}' ({col_type}) to table '{table_name}'")
                                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}")
                        except Exception as sync_err:
                            logger.warning(f"[Showcase] Column sync warning for {table_name}: {sync_err}")

                await conn.run_sync(_sync_sqlite_columns)
            logger.info("[Showcase] SQLite database schema initialized successfully.")

            # Initialize Smart Cache tag version registry
            await version_registry.initialize()

            # Seed initial demo dataset if database is fresh
            async with async_session() as db:
                count_users = (await db.execute(select(func.count(User.id)))).scalar_one()
                if count_users == 0:
                    # 1. Seed or retrieve demo roles
                    stmt_roles = select(Role).where(Role.name.in_(["admin", "guest", "editor", "reader", "adm-seo", "adm-help"]))
                    existing_roles = {r.name: r for r in (await db.execute(stmt_roles)).scalars().all()}

                    role_admin = existing_roles.get("admin") or Role(name="admin", description="Full administrator access")
                    role_guest = existing_roles.get("guest") or Role(name="guest", description="Guest public access")
                    role_adm_help = existing_roles.get("adm-help") or Role(name="adm-help", description="Admin Help & API Explorer")
                    role_editor = existing_roles.get("editor") or Role(name="editor", description="Content editor with task access")
                    role_reader = existing_roles.get("reader") or Role(name="reader", description="Content reader")
                    role_adm_seo = existing_roles.get("adm-seo") or Role(name="adm-seo", description="SEO Section Administrator")

                    for r in (role_admin, role_guest, role_adm_help, role_editor, role_reader, role_adm_seo):
                        if r.name not in existing_roles:
                            db.add(r)
                    await db.flush()

                    # 2. Seed default users
                    u_admin = User(
                        login="admin",
                        name="Administrator",
                        first_name="Admin",
                        last_name="System",
                        email="admin@example.com",
                        password_hash=User._hash_password("admin123"),
                        roles=[role_admin],
                    )
                    u_alice = User(
                        login="alice",
                        name="Alice Wonderland",
                        first_name="Alice",
                        last_name="Wonderland",
                        email="alice@example.com",
                        password_hash=User._hash_password("user123"),
                        roles=[role_editor],
                    )
                    u_bob = User(
                        login="bob",
                        name="Bob Builder",
                        first_name="Bob",
                        last_name="Builder",
                        email="bob@example.com",
                        password_hash=User._hash_password("bob123"),
                        roles=[role_editor, role_reader],
                    )
                    u_seo = User(
                        login="seo",
                        name="SEO Manager",
                        first_name="Sergey",
                        last_name="Optimizator",
                        email="seo@example.com",
                        password_hash=User._hash_password("seo123"),
                        roles=[role_adm_seo],
                    )
                    db.add_all([u_admin, u_alice, u_bob, u_seo])
                    await db.flush()

                    # 3. Seed Granular Permissions for role 'editor' on 'Task'
                    perm_task = RolePermission(
                        role_id=role_editor.id,
                        model_name="Task",
                        can_create=True,
                        can_read=True,
                        can_update=True,
                        can_delete=True,
                        read_global=True,    # Пользователи видят ВСЕ задачи
                        update_global=False, # Изменяют ТОЛЬКО СВОИ или ДЕЛЕГИРОВАННЫЕ
                        delete_global=False, # Удаляют ТОЛЬКО СВОИ или ДЕЛЕГИРОВАННЫЕ
                    )
                    db.add(perm_task)

                    # 4. Seed demo delegation (Bob delegates Task rights to Alice)
                    demo_delegation = UserDelegation(
                        from_user_id=u_bob.id,
                        to_user_id=u_alice.id,
                        model_name="Task",
                        is_active=True,
                    )
                    db.add(demo_delegation)

                    # 5. Seed demo tasks
                    demo_tasks = [
                        Task(title="Start PyFerro showcase server (Admin)", priority="high", completed=True, creator_id=u_admin.id, owner_id=u_admin.id),
                        Task(title="Inspect traffic savings with RFC 0002 ($tabular) (Alice)", priority="high", completed=False, creator_id=u_alice.id, owner_id=u_alice.id),
                        Task(title="Test Smart Cache tag invalidation across tabs (Alice)", priority="normal", completed=False, creator_id=u_alice.id, owner_id=u_alice.id),
                        Task(title="Run multi-return streaming task with live chunks (Bob)", priority="normal", completed=False, creator_id=u_bob.id, owner_id=u_bob.id),
                        Task(title="Trigger symmetric Reverse RPC call from server (Bob)", priority="low", completed=False, creator_id=u_bob.id, owner_id=u_bob.id),
                    ]
                    db.add_all(demo_tasks)

                    # 6. Seed demo documents
                    demo_docs = [
                        Document(title="PyFerro Architecture Manifesto", category="architecture", views=142, content="Granian RSGI + JSON-RPC 2.0 full duplex"),
                        Document(title="RFC 0002 Tabular Compression Specification", category="specs", views=98, content="40-70% wire traffic reduction"),
                        Document(title="Universal Reactive CRUD Guide", category="guides", views=64, content="Declarative class Crud: mapping"),
                    ]
                    db.add_all(demo_docs)

                    # 7. Seed demo forum categories & topics (pf_showcase_...)
                    from pyferro.plugins.help.models import ForumCategory, ForumTopic, ForumPost
                    c_dev = ForumCategory(
                        parent_id=None,
                        name="Разработка и Архитектура",
                        slug="development",
                        description="Вопросы веб-разработки, архитектуры бэкенда и системной безопасности",
                        icon="code",
                        display_order=1
                    )
                    c_mkt = ForumCategory(
                        parent_id=None,
                        name="Продвижение и Маркетинг",
                        slug="marketing",
                        description="Поисковая оптимизация, привлечение аудитории и продвижение веб-проектов",
                        icon="trending-up",
                        display_order=2
                    )
                    db.add_all([c_dev, c_mkt])
                    await db.flush()

                    c_arch = ForumCategory(
                        parent_id=c_dev.id,
                        name="Архитектура и WebSockets",
                        slug="architecture",
                        description="Обсуждение RSGI, Granian, WebSocket и протокола WSRPC",
                        icon="server",
                        display_order=1
                    )
                    c_sec = ForumCategory(
                        parent_id=c_dev.id,
                        name="Безопасность и RBAC",
                        slug="security",
                        description="Авторизация, роли, делегирование и безопасность на уровне строк (RLS)",
                        icon="shield",
                        display_order=2
                    )
                    c_seo = ForumCategory(
                        parent_id=c_mkt.id,
                        name="SEO и Индексация",
                        slug="seo",
                        description="Dynamic Rendering для роботов, Schema.org, OpenGraph и IndexNow",
                        icon="search",
                        display_order=1
                    )
                    db.add_all([c_arch, c_sec, c_seo])
                    await db.flush()
                    t1 = ForumTopic(
                        category_id=c_arch.id,
                        title="Как устроен WSRPC в PyFerro по сравнению со стандартным REST?",
                        slug="wsrpc-vs-rest-comparison",
                        author_name="Алексей Смирнов",
                        views_count=328,
                        replies_count=12,
                        first_post_text="В отличие от классического REST, WSRPC исключает постоянный TCP/TLS handshake оверхед, работает по единому сокету и поддерживает стриминг данных.",
                    )
                    t2 = ForumTopic(
                        category_id=c_sec.id,
                        title="Row-Level Security (RLS) без сложной возни в SQL",
                        slug="row-level-security-guide",
                        author_name="Елена Васильева",
                        views_count=195,
                        replies_count=5,
                        first_post_text="Модели, наследующие RowSecureModel, автоматически получают атрибуты creator_id, owner_id и team_id. Права на уровне строк фильтруются контекстом сессии.",
                    )
                    t3 = ForumTopic(
                        category_id=c_seo.id,
                        title="Почему мы отказались от тяжелого SSR в пользу Dynamic Rendering для ботов",
                        slug="dynamic-rendering-vs-ssr",
                        author_name="Дмитрий Ковалев",
                        views_count=412,
                        replies_count=19,
                        first_post_text="Тяжелый Node.js SSR увеличивает потребление памяти в 5-10 раз. PyFerro обслуживает людей как быстрое SPA, а ботам на лету отдает семантический HTML с микроразметкой JSON-LD.",
                    )
                    db.add_all([t1, t2, t3])
                    await db.flush()

                    p1 = ForumPost(
                        topic_id=t1.id,
                        author_name="Максим Архитектор",
                        content="Полностью поддерживаю, задержки упали с 45мс до 1.5мс в реальных сценариях!"
                    )
                    db.add(p1)

                    await db.commit()
                    logger.info("[Showcase] Fresh database initialized and seeded successfully.")
                else:
                    from pyferro.plugins.help.models import ForumCategory
                    has_dev = (await db.execute(select(ForumCategory).where(ForumCategory.slug == "development"))).scalar_one_or_none()
                    if not has_dev:
                        from sqlalchemy import delete
                        from pyferro.plugins.help.models import ForumTopic, ForumPost
                        await db.execute(delete(ForumPost))
                        await db.execute(delete(ForumTopic))
                        await db.execute(delete(ForumCategory))
                        await db.flush()

                        c_dev = ForumCategory(parent_id=None, name="Разработка и Архитектура", slug="development", description="Вопросы веб-разработки, архитектуры бэкенда и системной безопасности", icon="code", display_order=1)
                        c_mkt = ForumCategory(parent_id=None, name="Продвижение и Маркетинг", slug="marketing", description="Поисковая оптимизация, привлечение аудитории и продвижение веб-проектов", icon="trending-up", display_order=2)
                        db.add_all([c_dev, c_mkt])
                        await db.flush()

                        c_arch = ForumCategory(parent_id=c_dev.id, name="Архитектура и WebSockets", slug="architecture", description="Обсуждение RSGI, Granian, WebSocket и протокола WSRPC", icon="server", display_order=1)
                        c_sec = ForumCategory(parent_id=c_dev.id, name="Безопасность и RBAC", slug="security", description="Авторизация, роли, делегирование и безопасность на уровне строк (RLS)", icon="shield", display_order=2)
                        c_seo = ForumCategory(parent_id=c_mkt.id, name="SEO и Индексация", slug="seo", description="Dynamic Rendering для роботов, Schema.org, OpenGraph и IndexNow", icon="search", display_order=1)
                        db.add_all([c_arch, c_sec, c_seo])
                        await db.flush()

                        t1 = ForumTopic(category_id=c_arch.id, title="Как устроен WSRPC в PyFerro по сравнению со стандартным REST?", slug="wsrpc-vs-rest-comparison", author_name="Алексей Смирнов", views_count=328, replies_count=12, first_post_text="В отличие от классического REST, WSRPC исключает постоянный TCP/TLS handshake оверхед, работает по единому сокету и поддерживает стриминг данных.")
                        t2 = ForumTopic(category_id=c_sec.id, title="Row-Level Security (RLS) без сложной возни в SQL", slug="row-level-security-guide", author_name="Елена Васильева", views_count=195, replies_count=5, first_post_text="Модели, наследующие RowSecureModel, автоматически получают атрибуты creator_id, owner_id и team_id. Права на уровне строк фильтруются контекстом сессии.")
                        t3 = ForumTopic(category_id=c_seo.id, title="Почему мы отказались от тяжелого SSR в пользу Dynamic Rendering для ботов", slug="dynamic-rendering-vs-ssr", author_name="Дмитрий Ковалев", views_count=412, replies_count=19, first_post_text="Тяжелый Node.js SSR увеличивает потребление памяти в 5-10 раз. PyFerro обслуживает людей как быстрое SPA, а ботам на лету отдает семантический HTML с микроразметкой JSON-LD.")
                        db.add_all([t1, t2, t3])
                        await db.flush()

                        p1 = ForumPost(topic_id=t1.id, author_name="Максим Архитектор", content="Полностью поддерживаю, задержки упали с 45мс до 1.5мс в реальных сценариях!")
                        db.add(p1)
                        await db.commit()
                        logger.info("[Showcase] Forum categories upgraded to 2-level hierarchy.")
                    else:
                        logger.info("[Showcase] Database already populated, skipping initial seed.")
        except Exception as e:
            logger.error(f"[Showcase] Database initialization error: {e}", exc_info=True)


@app.route("/health", ["GET"])
async def health_handler(scope, proto):
    """Healthcheck endpoint."""
    proto.response_str(
        status=200,
        headers=[("content-type", "application/json")],
        body='{"status":"ok","framework":"PyFerro","showcase":"ready","database":"sqlite"}'
    )


def find_available_port(preferred_host: str, preferred_port: int) -> int:
    """Probes if preferred_port is available; if blocked or occupied, finds a free alternative."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((preferred_host, preferred_port))
            return preferred_port
        except OSError:
            pass

    # Common alternative development ports
    candidate_ports = [8000, 8081, 8088, 3000, 5000, 8888] + list(range(8082, 8100))
    for p in candidate_ports:
        if p == preferred_port:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((preferred_host, p))
                return p
            except OSError:
                continue

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((preferred_host, 0))
        return s.getsockname()[1]


def get_local_ip() -> str:
    """Определяет локальный IP-адрес машины в сети."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    if app.handle_cli():
        sys.exit(0)

    import argparse
    from granian import Granian

    parser = argparse.ArgumentParser(description="PyFerro Showcase Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8333, help="Port to bind (default: 8333)")
    args, _ = parser.parse_known_args()

    host = args.host
    requested_port = args.port
    port = find_available_port(host, requested_port)
    lan_ip = get_local_ip()

    print("=" * 70)
    print(" ⚡ PyFerro Admin Help & API Explorer (/admin/help)")
    if port != requested_port:
        print(f" [!] Notice: Port {requested_port} is busy or restricted by OS.")
        print(f" [!] Automatically selected available port: {port}")
    print(f" 🌐 Web UI (Local): http://127.0.0.1:{port}/")
    if host in ("0.0.0.0", "::"):
        print(f" 🌐 Web UI (LAN):   http://{lan_ip}:{port}/")
        print(f" 🗄️  Admin Panel:   http://{lan_ip}:{port}/admin/")
    else:
        print(f" 🗄️  Admin Panel:   http://{host}:{port}/admin/")
    print(f" 🔌 WSRPC Socket:   ws://{host}:{port}/")
    print(f" 💾 Database:       SQLite ({DB_PATH})")
    print(" 📖 Press Ctrl+C to stop the server")
    print("=" * 70)

    # Канонический запуск приложения PyFerro
    app.run(
        host=host,
        port=port,
        workers=1,
    )
