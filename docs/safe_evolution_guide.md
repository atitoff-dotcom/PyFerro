# Specification: PyFerro Safe Evolution Engine (Version Upgrades)

> **Key Axiom:** The client is careless, updates are inherently dangerous. Every operation must be transactional, reversible, and shielded against human error. The application must never lose data or become trapped in an unrecoverable state.

---

## 1. Concept and Philosophy

Database schema and environment upgrades carry maximum operational risk:
* Clients rarely read Release Notes.
* Backups are frequently omitted before running updates.
* Upgrades can be interrupted abruptly (`Ctrl+C`, power failure, network drops).
* Users often skip multiple major releases (e.g., from `0.1.0` straight to `0.5.0`).
* Applications may run across multi-worker setups (`granian --workers 4`).

Accordingly, PyFerro's version upgrade architecture adheres to **Zero-Trust Defensive Upgrades**.

---

## 2. System State Machine

On server startup, PyFerro checks the installed library version (`pyferro.__version__`) against the schema version recorded in `_ferro_migrations`:

```
                    ┌────────────────────────┐
                    │      Server Start      │
                    └───────────┬────────────┘
                                │
               ┌────────────────┴────────────────┐
               ▼                                 ▼
      [Versions Match]                 [db_ver < app_ver]
               │                                 │
               ▼                                 ▼
          NORMAL Mode                 RECOVERY_REQUIRED Mode
     (Standard operations)             (Safe upgrade gatekeeper)
                                                 │
                                                 ├── Public traffic: 503 Maintenance
                                                 └── /crud admin: Upgrade Wizard
```

1. **`NORMAL` Mode:** Standard startup; all routes and WSRPC endpoints function normally.
2. **`RECOVERY_REQUIRED` Mode:**
   - Public HTTP requests receive `503 Service Unavailable` (`Retry-After: 60`).
   - WSRPC business requests return RPC error `-32050 ("Scheduled maintenance in progress")`.
   - Logging into `/crud` with the master admin password displays the GUI upgrade wizard.

---

## 3. Pre-flight Audit & Shadow Snapshots

Before executing any upgrade code, the system initiates pre-flight protection:

### 3.1. Native Physical Snapshot via `VACUUM INTO` (SQLite)
Instead of copying files while WAL journals are active, SQLite's native command is invoked:
```python
# Creates an atomic, defragmented snapshot live without locking active readers
snapshot_path = f".ferro_snapshots/snapshot_{from_ver}_{timestamp}.db"
await session.execute(text(f"VACUUM INTO '{snapshot_path}'"))
```
* **Snapshot Retention:** Stores the last 3 snapshots (FIFO), automatically pruning older ones.

### 3.2. Disk Space Guard
* Verifies available disk capacity before creating backups.
* If `available_space < db_size * 2`, the upgrade is **blocked**.

### 3.3. Safety-Linter
Validates the version script prior to execution:
* ❌ Prohibits adding `NOT NULL` columns without a `DEFAULT` value.
* ❌ Prohibits dropping columns without prior deprecation (Expand & Contract pattern).
* ❌ Enforces required functions: `pre_check()`, `upgrade()`, `downgrade()`.

---

## 4. Version Script Contract (`pyferro/migrations/v0_5_0.py`)

Each version script is isolated and follows the **Expand & Contract** principle:

```python
"""
Version: 0.5.0
Title: RPC Permission Matrix Optimization
"""

VERSION = "0.5.0"
TITLE = "Add metadata summary and optimize permission lookups"
CHANGELOG = [
    "Add summary column to auth_rpc_permission",
    "Create composite index (role_id, method_name)",
    "Sync system seeds for built-in RPC methods"
]

async def pre_check(ctx) -> bool:
    """Phase 1: Inspection (read-only verification)."""
    return await ctx.has_table("auth_rpc_permission")


async def upgrade(ctx):
    """Phase 2: Execution with live GUI progress streaming."""
    
    # Step 1: Check and add column
    await ctx.report_progress(20, "Inspecting permissions schema...")
    if not await ctx.has_column("auth_rpc_permission", "summary"):
        await ctx.report_progress(40, "Adding summary column...")
        await ctx.add_column(
            table="auth_rpc_permission",
            column="summary",
            col_type="VARCHAR(255)",
            nullable=True
        )

    # Step 2: Index creation
    await ctx.report_progress(70, "Creating index...")
    await ctx.create_index(
        name="ix_role_method",
        table="auth_rpc_permission",
        columns=["role_id", "method_name"],
        if_not_exists=True
    )

    # Step 3: Python data transformation
    await ctx.report_progress(90, "Syncing system permissions...")

    await ctx.report_progress(100, "Version 0.5.0 applied successfully!")


async def downgrade(ctx):
    """Phase 3: Rollback."""
    await ctx.report_progress(50, "Dropping index ix_role_method...")
    await ctx.drop_index("ix_role_method", if_exists=True)
    
    if await ctx.has_column("auth_rpc_permission", "summary"):
        await ctx.drop_column("auth_rpc_permission", "summary")
```

---

## 5. Background Task Manager & GUI (WSRPC Stream)

### 5.1. Decoupled Task Manager
* Upgrades run inside a standalone server-side `UpgradeTaskManager`.
* If the admin closes the browser, reboots their machine, or loses Wi-Fi connectivity, the background task completes or safely aborts on the server.
* Reopening `/crud` immediately reconnects the socket to the ongoing task.

### 5.2. WSRPC API
1. `system.updates.status`: Returns status (`NORMAL`, `RECOVERY_REQUIRED`, `IN_PROGRESS`) and pending versions.
2. `system.updates.apply(stream: true)`: Streams progress `0..100%`, steps, and log messages to Svelte 5 via `session.send_stream_chunk()`.
3. `system.updates.rollback`: Triggers atomic rollback or restores physical snapshot.

---

## 6. Disaster Recovery Engine

If an error or interrupt occurs during `upgrade()`:
1. `await engine.dispose()` tears down active connections.
2. `app.db` is immediately overwritten with the `VACUUM INTO` snapshot from `.ferro_snapshots/`.
3. The database engine reinitializes against the restored files.
4. Data loss: **0 bytes**; Recovery time: **< 1 second**.

---

## 7. Metadata Audit Table (`_ferro_migrations`)

```sql
CREATE TABLE IF NOT EXISTS _ferro_migrations (
    version VARCHAR(32) PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_by VARCHAR(64),
    execution_time_ms INTEGER,
    checksum VARCHAR(64),
    snapshot_path VARCHAR(255)
);
```
