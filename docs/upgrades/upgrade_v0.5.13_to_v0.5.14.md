# 🤖 AI Application Migration Prompt: PyFerro v0.5.13 ➔ v0.5.14

> **Developer Instructions:**  
> Copy the markdown prompt block below and feed it to your AI coding assistant (Cursor, Antigravity, Claude Code, Windsurf, Copilot) in your project root. The AI will handle the project audit, database backup, schema migration, and model code adaptation.

---

```markdown
You are a Lead Software Engineer migrating an application to PyFerro v0.5.14.
Your objective is to safely upgrade this project, its database schema, and application models to the v0.5.14 contracts without downtime or data loss.

Context of v0.5.14 changes:
1. Granular CRUD Permission Scopes: system tables `auth_role_permissions` and `auth_user_permissions` now feature explicit columns `read_global`, `update_global`, and `delete_global` (replacing the single binary `row_level_only` flag).
2. Author vs. Owner Separation in RLS: `RowSecureModel` now includes an `owner_id` column (current responsible owner). The existing `creator_id` is now immutable creation audit data.
3. Authority Delegation Subsystem: introduces the `auth_user_delegation` table.

Execute the migration strictly following these steps:

### STEP 1. Project & Model Audit (Read-Only)
1. Locate dependency manifests (`requirements.txt`, `pyproject.toml`, or `Pipfile`) and update `pyferro` to `^0.5.14`.
2. Find all SQLAlchemy models inheriting from `RowSecureModel` (or having `creator_id`).
3. Note down the table names for these models (e.g., `tasks`, `documents`, `orders`).

### STEP 2. Database Backup (Zero-Data-Loss)
Before executing any DDL/DML, perform a reliable backup:
- SQLite: execute `VACUUM INTO 'backup_pre_v0514.db'` or copy the database file.
- PostgreSQL: ensure a transaction block or execute a snapshot/dump.

### STEP 3. Database Migration (DDL & DML)
Execute the following migrations (via custom migration script or Alembic):

1. **Update System Permission Tables (`auth_role_permissions` and `auth_user_permissions`):**
   - Add columns:
     - `read_global BOOLEAN NOT NULL DEFAULT 0`
     - `update_global BOOLEAN NOT NULL DEFAULT 0`
     - `delete_global BOOLEAN NOT NULL DEFAULT 0`
   - Backfill permissions (DML):
     ```sql
     -- If previously global access was allowed (row_level_only = 0), grant global scopes
     UPDATE auth_role_permissions 
     SET read_global = 1, update_global = 1, delete_global = 1 
     WHERE row_level_only = 0 OR row_level_only IS NULL;

     UPDATE auth_user_permissions 
     SET read_global = 1, update_global = 1, delete_global = 1 
     WHERE row_level_only = 0 OR row_level_only IS NULL;
     ```

2. **Create Authority Delegation Table (`auth_user_delegation`):**
   ```sql
   CREATE TABLE IF NOT EXISTS auth_user_delegation (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       from_user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
       to_user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
       model_name VARCHAR(100),
       valid_from DATETIME,
       valid_to DATETIME,
       is_active BOOLEAN NOT NULL DEFAULT 1,
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP
   );
   CREATE INDEX IF NOT EXISTS ix_auth_delegation_lookup 
   ON auth_user_delegation (to_user_id, is_active);
   ```

3. **Update Application Tables (`RowSecureModel`):**
   For each model table inheriting from `RowSecureModel` (identified in Step 1):
   - Add the `owner_id` column:
     ```sql
     ALTER TABLE <table_name> ADD COLUMN owner_id INTEGER REFERENCES auth_users(id);
     CREATE INDEX IF NOT EXISTS ix_<table_name>_owner_id ON <table_name> (owner_id);
     ```
   - Populate `owner_id` with `creator_id` for all existing rows:
     ```sql
     UPDATE <table_name> SET owner_id = creator_id WHERE owner_id IS NULL;
     ```

### STEP 4. Application Code Adaptation (Python)
1. Inspect business logic and handlers:
   - If ownership transfer previously mutated `item.creator_id = new_user_id`, change it to `item.owner_id = new_user_id` (`creator_id` is now immutable).
   - If direct checks like `perm.row_level_only` exist, replace them with `perm.read_global`, `perm.update_global`, or `perm.delete_global`.
2. Ensure all `@app.rpc` methods have a descriptive docstring (first line provides concise action summary for the permissions matrix).

### STEP 5. Verification
1. Run test suite (`pytest`).
2. Start the application server:
   - Log into `/crud` as admin.
   - Open Role Permissions modal and verify tri-state selectors: `Forbidden` | `Own Only 👤` | `All 🌐`.
   - Verify console logs show no missing column or table warnings.
```
