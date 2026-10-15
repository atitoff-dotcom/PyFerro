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
    cors=True
)

# Регистрация бизнес-моделей в CRUD
from models import Task, Document
ModelRegistry.register(Task)
ModelRegistry.register(Document)

# Регистрация RPC-хендлеров и плагинов
import handlers  # noqa: F401
import pyferro.plugins.files  # Registers HTTP /upload and RPC files.*
import pyferro.plugins.crud as crud  # noqa: F401

# Initialize logging
setup_logging()


@app.on_startup
async def init_database():
    """Asynchronously creates SQLite database tables and seeds demo data on server startup."""
    from pyferro.db import system_bypass
    from pyferro.auth import User, Role, RolePermission, UserDelegation
    from sqlalchemy import select, func, update, text

    with system_bypass():
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # Safe migration for existing SQLite database if creator_id/owner_id/updated_at columns are absent
                for col_ddl in [
                    "ALTER TABLE showcase_tasks ADD COLUMN creator_id INTEGER",
                    "ALTER TABLE showcase_tasks ADD COLUMN owner_id INTEGER",
                    "ALTER TABLE showcase_tasks ADD COLUMN updated_at DATETIME",
                    "ALTER TABLE auth_role_permission ADD COLUMN read_global BOOLEAN DEFAULT 0",
                    "ALTER TABLE auth_role_permission ADD COLUMN update_global BOOLEAN DEFAULT 0",
                    "ALTER TABLE auth_role_permission ADD COLUMN delete_global BOOLEAN DEFAULT 0",
                    "ALTER TABLE auth_user_permission ADD COLUMN read_global BOOLEAN DEFAULT 0",
                    "ALTER TABLE auth_user_permission ADD COLUMN update_global BOOLEAN DEFAULT 0",
                    "ALTER TABLE auth_user_permission ADD COLUMN delete_global BOOLEAN DEFAULT 0",
                ]:
                    try:
                        await conn.execute(text(col_ddl))
                    except Exception:
                        pass
            logger.info("[Showcase] SQLite database schema initialized successfully.")

            # Initialize Smart Cache tag version registry
            await version_registry.initialize()

            # Seed initial demo tasks, documents, roles and delegations
            async with async_session() as db:
                # 1. Update existing tasks creator_id & owner_id if NULL
                await db.execute(update(Task).where(Task.id == 1, Task.creator_id == None).values(creator_id=1, owner_id=1))
                await db.execute(update(Task).where(Task.id.in_([2, 3]), Task.creator_id == None).values(creator_id=2, owner_id=2))
                await db.execute(update(Task).where(Task.id >= 4, Task.creator_id == None).values(creator_id=3, owner_id=3))
                await db.execute(update(Task).where(Task.owner_id == None).values(owner_id=Task.creator_id))

                count_tasks = (await db.execute(select(func.count(Task.id)))).scalar_one()
                if count_tasks == 0:
                    demo_tasks = [
                        Task(title="Start PyFerro showcase server (Admin)", priority="high", completed=True, creator_id=1, owner_id=1),
                        Task(title="Inspect traffic savings with RFC 0002 ($tabular) (Alice)", priority="high", completed=False, creator_id=2, owner_id=2),
                        Task(title="Test Smart Cache tag invalidation across tabs (Alice)", priority="normal", completed=False, creator_id=2, owner_id=2),
                        Task(title="Run multi-return streaming task with live chunks (Bob)", priority="normal", completed=False, creator_id=3, owner_id=3),
                        Task(title="Trigger symmetric Reverse RPC call from server (Bob)", priority="low", completed=False, creator_id=3, owner_id=3),
                    ]
                    db.add_all(demo_tasks)

                count_docs = (await db.execute(select(func.count(Document.id)))).scalar_one()
                if count_docs == 0:
                    demo_docs = [
                        Document(title="PyFerro Architecture Manifesto", category="architecture", views=142, content="Granian RSGI + JSON-RPC 2.0 full duplex"),
                        Document(title="RFC 0002 Tabular Compression Specification", category="specs", views=98, content="40-70% wire traffic reduction"),
                        Document(title="Universal Reactive CRUD Guide", category="guides", views=64, content="Declarative class Crud: mapping"),
                    ]
                    db.add_all(demo_docs)

                # 2. Seed demo roles and users
                count_roles = (await db.execute(select(func.count(Role.id)))).scalar_one()
                if count_roles == 0:
                    role_admin = Role(name="admin", description="Full administrator access")
                    role_user = Role(name="user", description="Regular user with granular RLS access")
                    role_editor = Role(name="editor", description="Content editor")
                    db.add_all([role_admin, role_user, role_editor])
                    await db.flush()

                r_admin = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
                r_user = (await db.execute(select(Role).where(Role.name == "user"))).scalar_one_or_none()

                # Seed Granular Permissions for role 'user' on 'Task' if missing
                if r_user:
                    perm_check = (await db.execute(select(RolePermission).where(
                        RolePermission.role_id == r_user.id,
                        RolePermission.model_name == "Task"
                    ))).scalar_one_or_none()
                    if not perm_check:
                        perm_task = RolePermission(
                            role_id=r_user.id,
                            model_name="Task",
                            can_create=True,
                            can_read=True,
                            can_update=True,
                            can_delete=True,
                            read_global=True,    # Пользователи видят ВСЕ задачи
                            update_global=False, # Изменяют ТОЛЬКО СВОИ или ДЕЛЕГИРОВАННЫЕ
                            delete_global=False, # Удаляют ТОЛЬКО СВОИ или ДЕЛЕГИРОВАННЫЕ
                            row_level_only=True,
                        )
                        db.add(perm_task)

                count_users = (await db.execute(select(func.count(User.id)))).scalar_one()
                if count_users == 0:
                    user_admin = User(login="admin", name="Administrator", first_name="Admin", last_name="System", email="admin@example.com", password_hash=User._hash_password("admin123"))
                    user_alice = User(login="alice", name="Alice Wonderland", first_name="Alice", last_name="Wonderland", email="alice@example.com", password_hash=User._hash_password("user123"))
                    user_bob = User(login="bob", name="Bob Builder", first_name="Bob", last_name="Builder", email="bob@example.com", password_hash=User._hash_password("bob123"))
                    db.add_all([user_admin, user_alice, user_bob])
                    await db.flush()

                    if r_admin:
                        user_admin.roles.append(r_admin)
                    if r_user:
                        user_alice.roles.append(r_user)
                        user_bob.roles.append(r_user)

                # 3. Seed demo delegation (Bob delegates Task rights to Alice)
                count_delegations = (await db.execute(select(func.count(UserDelegation.id)))).scalar_one()
                if count_delegations == 0:
                    demo_delegation = UserDelegation(
                        from_user_id=3,  # Bob
                        to_user_id=2,    # Alice
                        model_name="Task",
                        is_active=True,
                    )
                    db.add(demo_delegation)

                await db.commit()
                logger.info("[Showcase] Initial demo records and permissions seeded successfully.")

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
    print(" ⚡ PyFerro Showcase: Interactive Demo & Living Documentation")
    if port != requested_port:
        print(f" [!] Notice: Port {requested_port} is busy or restricted by OS.")
        print(f" [!] Automatically selected available port: {port}")
    print(f" 🌐 Web UI (Local): http://127.0.0.1:{port}/")
    if host in ("0.0.0.0", "::"):
        print(f" 🌐 Web UI (LAN):   http://{lan_ip}:{port}/")
        print(f" 🗄️  CRUD Admin:    http://{lan_ip}:{port}/crud")
    else:
        print(f" 🗄️  CRUD Admin:    http://{host}:{port}/crud")
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
