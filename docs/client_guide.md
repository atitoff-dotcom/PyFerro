# Client SDK Guide: `client/wsrpc.ts`

> **Official PyFerro Client SDK (TypeScript & JavaScript)**  
> Zero-dependency reactive client featuring integrated authentication, full-duplex symmetric RPC, streaming multi-return, and tabular data compression (RFC 0002).

---

## 🧭 Table of Contents

1. [Overview & Quick Start](#1-overview--quick-start)
2. [Connection Lifecycle & Network Management](#2-connection-lifecycle--network-management)
3. [Reactive State Stores (SimpleStore)](#3-reactive-state-stores-simplestore)
4. [RPC Invocations & Error Handling](#4-rpc-invocations--error-handling)
5. [Integrated Authentication (`rpc.auth` / `AuthStore`)](#5-integrated-authentication-rpcauth--authstore)
6. [Tabular Data Decompression (RFC 0002)](#6-tabular-data-decompression-rfc-0002)
7. [Progress Streaming (Multi-Return)](#7-progress-streaming-multi-return)
8. [Full-Duplex Reverse RPC (Server &rarr; Client)](#8-full-duplex-reverse-rpc-server--client)
9. [Event Subscriptions & Broadcast (Pub/Sub)](#9-event-subscriptions--broadcast-pubsub)
10. [Strong User Typing (TypeScript Generics)](#10-strong-user-typing-typescript-generics)

---

## 1. Overview & Quick Start

`client/wsrpc.ts` is the single source of truth for frontend applications interacting with the PyFerro backend:
* **Single Persistent WebSocket:** Handles all RPC queries, live streams, server push alerts, and session authentication.
* **Zero Dependencies:** Zero npm package bloat. Uses the browser's native **Web Crypto API** for RSA password encryption.
* **Zero Boilerplate:** Built-in session gatekeeper, automatic cookie management, and transparent tabular data unpacking.

### Quick Start:
Copy `client/wsrpc.ts` into your application (e.g., `src/lib/wsrpc.ts`):

```typescript
import { rpc, auth } from './wsrpc';

// 1. Authenticate (if required)
await auth.login({ username: 'alex', password: 'my-password' });

// 2. Invoke RPC method
const tasks = await rpc.call('tasks.list');
console.log('Task list:', tasks);
```

---

## 2. Connection Lifecycle & Network Management

The client resolves WebSocket endpoints via `getWsUrl()`:
* **Vite dev servers** (`5173` / `4173`) are directed to `ws://127.0.0.1:8080/ws`.
* **Production environments** connect relative to `/ws` on `ws://` or `wss://`.

### Lifecycle Controls:
```typescript
import { BinaryWSRPC } from './wsrpc';

// Custom client instance (or use default singleton: import { rpc } from './wsrpc')
const client = new BinaryWSRPC('wss://api.example.com/ws');

// Configure auto-reconnect backoff (default: 3 seconds; 0 to disable)
client.reconnectWs = 3;

// Lifecycle hooks
client.onConnect = () => {
    console.log('✅ WebSocket connection established');
};

client.onStatusChange = (connected: boolean) => {
    console.log('Network state:', connected ? 'ONLINE' : 'OFFLINE');
};

// Explicit connect (rpc.call triggers connect automatically)
await client.connect();

// Manual disconnect
client.disconnect();
```

---

## 3. Reactive State Stores (SimpleStore)

The client ships with an ultra-lightweight `SimpleStore<T>` compatible with:
* **Svelte** store contract (`$store`).
* **React** `useSyncExternalStore`.
* **Vue** & **Vanilla JS** (`subscribe`).

### Exported Stores:
* `wsConnected`: `SimpleStore<boolean>` — Connection state boolean.
* `wsStatus`: `SimpleStore<'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'>` — Current network state.

#### Svelte Example:
```svelte
<script>
  import { wsConnected, wsStatus } from './wsrpc';
</script>

{#if !$wsConnected}
  <div class="banner">Connection lost. Reconnecting ({$wsStatus})...</div>
{/if}
```

---

## 4. RPC Invocations & Error Handling

### Basic Method Call: `rpc.call(method, params, options)`
```typescript
// Parameterless call
const ping = await rpc.call('system.ping');

// Named arguments
const task = await rpc.call('tasks.create', { 
    title: 'Prepare Release', 
    priority: 1 
});

// Custom call timeout in ms (default: 15000)
const result = await rpc.call('heavy.compute', { data: 123 }, 30000);
```

### JSON-RPC 2.0 Error Handling:
Errors reject the returned promise with an `Error` containing `code` and `data`:
```typescript
try {
    await rpc.call('admin.cleanup');
} catch (err: any) {
    console.error('RPC Error:', err.message); // Server message
    console.error('Error Code:', err.code);   // e.g. -32000 (Permission Denied)
}
```

---

## 5. Integrated Authentication (`rpc.auth` / `AuthStore`)

The `rpc.auth` subsystem (also exported as `auth`) encapsulates credentials, tokens, cookies, and session lifecycle.

### 5.1. Authentication Methods:
```typescript
import { auth } from './wsrpc';

// 1. Standard username/password login (login.submit)
const user = await auth.login({ username: 'alex', password: 'secret' });

// 2. Secure login with client-side RSA-OAEP encryption
// (Fetches server's ephemeral public key and encrypts password via Web Crypto API)
const secureUser = await auth.loginSecure({ username: 'alex', password: 'secret' });

// 3. OAuth, SSO, Telegram or Passkeys (custom RPC method)
// Call your custom backend handler and apply the session in one shot:
const oauthRes = await rpc.call('auth.google_oauth', { code: '...' });
const oauthUser = auth.setSession(oauthRes); // Atomically sets cookies, localStorage, and userStore
```

### 5.2. State Properties:
* `auth.user`: Current user object (`AuthUser | null`). Automatically normalizes conventional fields:
  - `id`, `uid`, `user_id`: Universal user ID aliases (`string | number`).
  - `avatar`, `photo_url`: User profile photo URL (`string | null`).
  - `email`: User email or `null` for phone/OAuth signups (`string | null`).
  - `username`, `name`, `role`, `roles`, `permissions`, `is_superadmin`.
* `auth.isValid`: `boolean` — Whether a session is active.
* `auth.token`: Active refresh token.
* `auth.jwtToken`: Short-lived JWT for REST & file upload endpoints.
* `auth.isLoading`: `boolean` — Session restoration in progress.

### 5.3. Reactive Subscription:
```typescript
const unsubscribe = auth.onChange((user) => {
    console.log('User changed:', user?.username);
});
```

### 5.4. Automatic Cookies & Storage:
Upon authentication, `AuthStore` sets:
* `localStorage.setItem('refresh_token', token)`
* `document.cookie` for `ferro_session` and `ferro_crud_session` (30 days, `SameSite=Lax`).
* `document.cookie` for `rpc_jwt` (24 hours).

### 5.5. Session Gatekeeper:
Calls made before authentication finishes (e.g. on F5 reload) are **automatically queued** until `auth.ensureInitialized()` completes, eliminating race conditions and unexpected permission errors.

---

## 6. Tabular Data Decompression (RFC 0002)

Methods decorated with `@tabular_response` return high-compression payloads (`{$tabular: true, fields: [...], rows: [...]}`).

`wsrpc.ts` decompresses these **transparently**:
```typescript
// Backend sends rows matrix; frontend receives standard objects array
const tasks = await rpc.call('tasks.list');
console.log(tasks); // [{ id: 1, title: 'Task 1' }, { id: 2, title: 'Task 2' }]
```

---

## 7. Progress Streaming (Multi-Return)

Long-running jobs stream progress chunks (`session.send_stream_chunk`):

```typescript
const report = await rpc.call(
    'reports.generate',
    { month: '2026-10' },
    {
        onChunk: (chunk) => {
            console.log(`Progress: ${chunk.progress}%, Step: ${chunk.step}`);
        },
        timeoutMs: 60000
    }
);
console.log('Report completed:', report.url);
```

---

## 8. Full-Duplex Reverse RPC (Server &rarr; Client)

WSRPC is symmetric: the server can query the client and await its response.

```typescript
// Register handler for server-initiated queries
rpc.register('client.get_env', async (params) => {
    return {
        userAgent: navigator.userAgent,
        screenWidth: window.screen.width,
        language: navigator.language
    };
});
```

---

## 9. Event Subscriptions & Broadcast (Pub/Sub)

Listen to realtime server broadcasts via `rpc.on`:

```typescript
const unsubscribe = rpc.on('chat.message', (message) => {
    console.log('Incoming message:', message);
});

// Unsubscribe when component unmounts
unsubscribe();
```

---

## 10. Strong User Typing (TypeScript Generics)

Parameterize the client with your application's user interface:

```typescript
import { BinaryWSRPC, type AuthUser } from './wsrpc';

interface AppUser extends AuthUser {
    department: string;
    points: number;
    role: 'admin' | 'moderator' | 'user';
}

export const rpc = new BinaryWSRPC<AppUser>();
export const auth = rpc.auth;

// Fully typed user properties
if (auth.user) {
    console.log(auth.user.department); // string
    console.log(auth.user.points);     // number
}
```
