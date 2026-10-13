# Authentication Architecture & Security Guide (Backend & Security)

> **Standard for Developers and AI Assistants (Cursor, Antigravity, Claude, ChatGPT, Windsurf, Copilot)**  
> Comprehensive guide covering authentication workflows, password storage, session lifecycle, WebSocket Gatekeeper, and security configuration in the `PyFerro` framework.

---

## 🧭 Table of Contents

1. [Fundamental Authorization Model: WSRPC vs REST](#1-fundamental-authorization-model-wsrpc-vs-rest)
2. [Password Storage & Hashing: Why Passwords Mismatch](#2-password-storage--hashing-why-passwords-mismatch)
   - [Canonical PBKDF2-SHA256 Standard](#21-canonical-pbkdf2-sha256-standard)
   - [Anti-Patterns from Legacy Frameworks](#22-anti-patterns-from-legacy-frameworks)
   - [CLI Password Reset Utility](#23-cli-password-reset-utility)
3. [Backend: RPC Method Contracts & Sessions](#3-backend-rpc-method-contracts--sessions)
   - [The `login.` Prefix & `public=True` Rule (Default Deny)](#31-the-login-prefix--publictrue-rule-default-deny)
   - [Option A: Built-in `plugins.auth` Plugin](#32-option-a-built-in-pluginsauth-plugin)
   - [Automatic WebSocket Cookie Authentication (`auto_auth_ws`)](#33-automatic-websocket-cookie-authentication-auto_auth_ws)
4. [Frontend: Integration with `wsrpc.ts`](#4-frontend-integration-with-wsrpcts)
5. [CRUD Panel Security Integration (Zero-Leakage 404)](#5-crud-panel-security-integration-zero-leakage-404)
6. [Troubleshooting Guide](#6-troubleshooting-guide)

---

## 1. Fundamental Authorization Model: WSRPC vs REST

In traditional REST APIs, every HTTP query is stateless and passes an `Authorization: Bearer <JWT>` header. The server parses and cryptographically validates the token on every single request.

In **`PyFerro`**, the model is fundamentally different:
1. **Persistent Stateful Socket:** The client opens a single persistent full-duplex WebSocket connection.
2. **One-Time Authentication (O(1)):** Upon successful login, the socket session object is marked authenticated (`session.data = AuthSession(...)`).
3. **Sub-Microsecond In-Memory Permission Checks:** Subsequent RPC queries over the connection are validated in RAM in fractions of a microsecond without repetitive DB queries or JWT cryptographic overhead.
4. **Dual Circuit Architecture:**
   - **WebSocket Circuit:** Handles RPC methods, reactive server push, and data streaming.
   - **HTTP Circuit:** Serves static files, zero-copy file uploads (2PC `/upload`), and provides access to `/crud` via Cookies (`ferro_session`, `ferro_crud_session`).
5. **Seamless Reconnection (`auto_auth_ws=True`):** Upon reconnection, the server inspects handshake Cookies and restores the session in RAM **before** executing business requests.

---

## 2. Password Storage & Hashing: Why Passwords Mismatch

The most common issue during database migrations or initial setup is **password hash format mismatches**.

### 2.1. Canonical PBKDF2-SHA256 Standard

PyFerro enforces **PBKDF2 with HMAC-SHA256** using **Base64-encoded salt and derived key**.

The database `password_hash` string must follow this exact format:
```text
pbkdf2_sha256$<iterations>$<salt_b64>$<key_b64>
```

Where:
- `pbkdf2_sha256` — Algorithm identifier.
- `iterations` — Iteration count (default: `100000`).
- `salt_b64` — 16 random salt bytes encoded in Base64.
- `key_b64` — 32 derived key bytes encoded in Base64.
- Delimiter — Dollar sign `$` (NEVER colon `:`).

### 2.2. Anti-Patterns from Legacy Frameworks

| Invalid DB Format | Cause of Failure | Fix |
|---|---|---|
| `pbkdf2:sha256:10000$salt$hash` | Colon delimiter (legacy Flask/Werkzeug format) | Rehash using `pyferro.core.security.hash_password` |
| `salt$hash` (hex string) | Hexadecimal encoding instead of Base64 | Reset password using the CLI tool |
| Plain text or unsalted SHA256 | Insecure and incompatible signature | Reset administrator password via CLI |

### 2.3. CLI Password Reset Utility

To safely update a user's password without launching the server:

```bash
python server.py --set-admin-password "MyNewPassword" --login admin
```

Or programmatically:
```python
from pyferro.core.security import hash_password

new_hash = hash_password("new_password")
user.password_hash = new_hash
await db_session.commit()
```

---

## 3. Backend: RPC Method Contracts & Sessions

### 3.1. The `login.` Prefix & `public=True` Rule (Default Deny)

By default, PyFerro operates under a strict **Default Deny** policy: all RPC methods require authorization, except:
1. Methods prefixed with `login.` (e.g. `login.submit`, `login.get_key`, `login.refresh`, `login.whoami`).
2. Methods declared with `@app.rpc("auth.login", public=True)`.

### 3.2. Built-in `plugins.auth` Plugin

The `pyferro.plugins.auth` plugin provides standard RPC methods:
* `login.submit` — Standard username/password login.
* `login.get_key` — Generates an ephemeral RSA public key for client-side password encryption.
* `login.secure` — Receives encrypted password, decrypts via server private key, and authenticates.
* `login.whoami` — Returns current socket identity and permissions.
* `login.refresh` — Extends session lifetime via `refresh_token`.
* `auth.logout` — Revokes session and deletes token.

### 3.3. Automatic WebSocket Cookie Authentication (`auto_auth_ws`)

`FerroApp` enables `auto_auth_ws=True` by default. When a socket connects, the server inspects `ferro_session` / `ferro_crud_session` cookies during the WebSocket Upgrade and authenticates the connection before the first RPC call executes.

---

## 4. Frontend: Integration with `wsrpc.ts`

Client-side authentication, RSA encryption, token refresh, Cookie management, and Session Gatekeeper queuing are **fully built into** the official client [`client/wsrpc.ts`](../client/wsrpc.ts) via `rpc.auth` and the exported `auth` singleton.

> 📖 **Comprehensive Client SDK Guide:**  
> See [docs/client_guide.md](client_guide.md) for full documentation on networking, reactivity, streaming, events, and TypeScript generics.

### Quick Frontend Authentication Example:
```typescript
import { rpc, auth } from './wsrpc';

// 1. Standard login (or auth.loginSecure for RSA-encrypted passwords)
await auth.login({ username: 'alex', password: 'secret' });

// 2. Inspect session state
console.log(auth.user);     // AuthUser | null
console.log(auth.isValid);  // boolean

// 3. Reactive user subscription (Svelte $auth, React, Vue)
auth.onChange((user) => {
    console.log('Current user:', user?.username);
});

// 4. Logout (cleans socket, Cookies, and localStorage)
await auth.logout();
```

---

## 5. CRUD Panel Security Integration (Zero-Leakage 404)

If an administrator visits `http://localhost:8080/crud` and receives a **`404 Not Found`**, this is the **Zero-Leakage (404)** security mechanism:  
The `/crud` endpoint disguises itself as non-existent unless the request includes a valid administrator session Cookie (`ferro_crud_session` or `ferro_session`).

### Ensuring Seamless Access to `/crud`:
1. **On the Backend:** Upon administrator authentication, register the session:
   ```python
   if role == "admin":
       from pyferro.plugins.crud import create_crud_session
       create_crud_session({"username": user.login, "role": "admin"}, token=token)
   ```
2. **On the Frontend:** Calling `auth.login()` in `wsrpc.ts` sets the cookies automatically.
3. Accessing `window.open('/crud', '_blank')` immediately loads the admin interface.

---

## 6. Troubleshooting Guide

| Symptom | Cause | Resolution |
|---|---|---|
| **`Invalid username or password` despite correct credentials** | Hash format mismatch in DB (hex string or sha256 instead of `pbkdf2_sha256$<iter>$<salt>$<key>`) | Reset password via CLI: `python server.py --set-admin-password "password" --login "admin"` |
| **`Permission Denied` (-32000) on login method** | Method name does not start with `login.` and lacks `public=True` | Add `@rpc_method("auth.login", public=True)` or rename to `login.submit` |
| **User logs out on page reload (F5)** | Frontend does not persist `refresh_token` or Cookie | Use built-in `auth.login()`, which manages storage automatically |
| **Business RPC calls fail with permission error upon socket reconnect** | Calls fire before socket session re-authenticates | `wsrpc.ts` automatically queues calls via built-in Session Gatekeeper |
