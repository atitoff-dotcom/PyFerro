# Руководство по архитектуре и реализации аутентификации (Бэкенд и Фронтенд)

> **Стандарт для разработчиков и ИИ-ассистентов (Cursor, Antigravity, Claude, ChatGPT, Windsurf, Copilot)**  
> Этот документ содержит исчерпывающее руководство по реализации входа, хранения паролей, управления сессиями, работы WebSocket-шлюза (`Gatekeeper`) и интеграции фронтенда в приложениях на фреймворке `PyFerro`.

---

## 🧭 Содержание

1. [Фундаментальная модель авторизации: WSRPC vs REST](#1-фундаментальная-модель-авторизации-wsrpc-vs-rest)
2. [Хранение и хэширование паролей: почему «пароль не совпадает»](#2-хранение-и-хэширование-паролей-почему-пароль-не-совпадает)
   - [Канонический алгоритм PBKDF2-SHA256](#21-канонический-алгоритм-pbkdf2-sha256)
   - [Анти-паттерны и рудименты старых проектов](#22-анти-паттерны-и-рудименты-старых-проектов)
   - [Утилита смены/сброса пароля (CLI и Python-скрипт)](#23-утилита-сменысброса-пароля-cli-и-python-скрипт)
3. [Бэкенд: Контракты RPC-методов и сессии](#3-бэкенд-контракты-rpc-методов-и-сессии)
   - [Правило префикса `login.` и флага `public=True` (Default Deny)](#31-правило-префикса-login-и-флага-publictrue-default-deny)
   - [Вариант А: Использование встроенного плагина `plugins.auth`](#32-вариант-а-использование-встроенного-плагина-pluginsauth)
   - [Вариант Б: Легковесный кастомный хендлер входа](#33-вариант-б-легковесный-кастомный-хендлер-входа)
   - [Автоматическая авторизация WebSocket по Cookie (`auto_auth_ws`)](#34-автоматическая-авторизация-websocket-по-cookie-auto_auth_ws)
4. [Фронтенд: Реализация клиента и жизненный цикл](#4-фронтенд-реализация-клиента-и-жизненный-цикл)
   - [Архитектура канонического клиента `wsrpc.ts`](#41-архитектура-канонического-клиента-wsrpcts)
   - [Шлюз авторизации (`authInterceptor` / Gatekeeper)](#42-шлюз-авторизации-authinterceptor--gatekeeper)
   - [Эталонный сервис авторизации (TypeScript)](#43-эталонный-сервис-авторизации-typescript)
   - [Интеграция с UI (Svelte 5 / React / Vue)](#44-интеграция-с-ui-svelte-5--react--vue)
5. [Интеграция с Панелью Управления CRUD (Zero-Leakage 404)](#5-интеграция-с-панелью-управления-crud-zero-leakage-404)
6. [Таблица типичных ошибок и решений (Troubleshooting)](#6-таблица-типичных-ошибок-и-решений-troubleshooting)

---

## 1. Фундаментальная модель авторизации: WSRPC vs REST

В традиционном REST API каждый HTTP-запрос независим и передает заголовок `Authorization: Bearer <JWT>`. Бэкенд на каждый запрос распаковывает и валидирует криптографическую подпись.

В **`PyFerro`** концепция принципиально иная:
1. **Постоянное соединение (Stateful Socket):** Клиент открывает постоянное дуплексное WebSocket-соединение.
2. **Аутентификация соединения один раз (O(1)):** После успешного входа объект сессии сокета помечается авторизованным (`session.data = AuthSession(...)`).
3. **Мгновенная проверка прав:** Все последующие RPC-вызовы в рамках этого соединения проверяются в оперативной памяти за **доли микросекунды**, без повторных обращений к БД и без проверки крипто-подписей JWT на каждый клик.
4. **Двойной контур:**
   - **WebSocket-контур:** Управляет RPC-методами, реактивными событиями и стримингом данных.
   - **HTTP-контур:** Управляет раздачей статики, загрузкой файлов (2PC `/upload`) и доступом к панели `/crud`. Для HTTP-контура используются Http-Only Cookie (`ferro_session`, `ferro_crud_session`).
5. **Бесшовный авто-логин (`auto_auth_ws=True`):** При обрыве сети и переподключении сокета сервер автоматически считывает Cookie браузера во время WebSocket Handshake и восстанавливает сессию сокета в памяти **до** выполнения бизнес-запросов.

---

## 2. Хранение и хэширование паролей: почему «пароль не совпадает»

Самая частая проблема при миграции старых проектов или создании новых — **несовпадение формата хэша пароля**.

### 2.1. Канонический алгоритм PBKDF2-SHA256

Канонический стандарт `PyFerro` использует **PBKDF2 с HMAC-SHA256** и обязательным хранением соли и ключа в кодировке **Base64**.

Строка `password_hash` в БД обязана иметь следующий формат:
```text
pbkdf2_sha256$<iterations>$<salt_b64>$<key_b64>
```

Где:
- `pbkdf2_sha256` — идентификатор алгоритма (префикс).
- `iterations` — число итераций (по умолчанию `10000` или `100000`).
- `salt_b64` — 16 случайных байт криптографической соли (`os.urandom(16)`), закодированных в **Base64** (`base64.b64encode(salt).decode("utf-8")`).
- `key_b64` — 32 байта результата `hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)`, закодированных в **Base64** (`base64.b64encode(key).decode("utf-8")`).

#### Реализация в Python (Канон):

```python
import base64
import hashlib
import hmac
import os

def hash_password(password: str, salt: bytes = None, iterations: int = 10000) -> str:
    """Генерация канонического хэша пароля для PyFerro."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("utf-8")
    key_b64 = base64.b64encode(key).decode("utf-8")
    return f"pbkdf2_sha256${iterations}${salt_b64}${key_b64}"

def verify_password(stored_hash: str, raw_password: str) -> bool:
    """Проверка пароля с поддержкой PBKDF2-SHA256 и legacy SHA-256."""
    if not stored_hash or not raw_password:
        return False
        
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            parts = stored_hash.split("$")
            if len(parts) != 4:
                return False
            _, iterations_str, salt_b64, key_b64 = parts
            iterations = int(iterations_str)
            salt = base64.b64decode(salt_b64)
            expected_key = base64.b64decode(key_b64)
            
            actual_key = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(expected_key, actual_key)
        except Exception:
            return False
            
    # Legacy fallback: плоский SHA-256 (64 hex-символа)
    try:
        legacy_hash = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_hash, stored_hash)
    except Exception:
        return False
```

---

### 2.2. Анти-паттерны и рудименты старых проектов

Если при верном пароле сервер возвращает `Неверный логин или пароль` / `401`, проверьте следующие 6 причин:

| № | Ошибка / Рудимент | Что реально в БД | Почему не совпадает | Как исправить |
|---|---|---|---|---|
| **1** | **Hex вместо Base64** | `pbkdf2_sha256$10000$a1b2c3...` (hex-строка) | `base64.b64decode()` ломается или дает неверные байты | Перегенерировать хэш через канонический `hash_password()` с Base64. |
| **2** | **Двоеточие `:` вместо `$`** | `salt:hash` или `pbkdf2:10000:...` | `stored_hash.split("$")` не находит 4 фрагмента | Привести разделители к знаку доллара `$`. |
| **3** | **Сырой пароль в БД** | `admin123` (plain text) | `verify_password` хэширует введенный пароль и сравнивает со строкой | Никогда не хранить сырой текст! Захэшировать через `hash_password()`. |
| **4** | **Сторонние форматы (Django / Passlib / bcrypt)** | `pbkdf2_sha256$260000$...` или `$2b$12$...` | Другие схемы упаковки соли/хеша | Конвертировать старые хэши скриптом миграции или сбросить пароль. |
| **5** | **Поле в таблице называется `username`, а не `login`** | Запрос ищет `User.login == username`, а колонка пуста | SQL-запрос не находит запись пользователя (`None`) | Проверить схему: в `plugins.auth` поле пользователя называется `login`, а не `username`. |
| **6** | **Пробелы / Перевод строки в CLI** | В пароль попал `\r\n` из файла или консоли | Хэш строится от `admin123\n` | Всегда делать `.strip()` на аргументах пароля в скриптах. |

---

### 2.3. Утилита смены/сброса пароля (CLI и Python-скрипт)

#### Способ 1: Встроенный CLI приложения (Рекомендуемый)

Фреймворк поддерживает нативную утилиту командной строки для обновления пароля администратора (строго DML без изменения схемы):

```bash
# Интерактивный безопасный ввод с подтверждением:
python server.py --set-admin-password

# Или прямая установка для конкретного логина:
python server.py --set-admin-password "StrongPass123!" --login admin
```

#### Способ 2: Универсальный скрипт сброса пароля (`reset_password.py`)

Если вы работаете со старой базой данных (SQLite или PostgreSQL), используйте готовый скрипт:

```python
#!/usr/bin/env python3
"""
Скрипт безопасного обновления пароля пользователя.
Запуск: python reset_password.py admin MyNewPassword app.db
"""
import sys
import sqlite3
import base64
import hashlib
import os

def generate_hash(password: str) -> str:
    salt = os.urandom(16)
    iterations = 10000
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("utf-8")
    key_b64 = base64.b64encode(key).decode("utf-8")
    return f"pbkdf2_sha256${iterations}${salt_b64}${key_b64}"

def main():
    if len(sys.argv) < 3:
        print("Использование: python reset_password.py <login> <new_password> [db_path]")
        sys.exit(1)

    login = sys.argv[1].strip()
    new_password = sys.argv[2].strip()
    db_path = sys.argv[3] if len(sys.argv) > 3 else "app.db"

    pw_hash = generate_hash(new_password)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Проверяем наличие пользователя
    cur.execute("SELECT id, login FROM auth_user WHERE login = ? OR email = ?", (login, login))
    row = cur.fetchone()
    if not row:
        print(f"❌ Пользователь с логином/email '{login}' не найден в {db_path}!")
        conn.close()
        sys.exit(1)

    user_id = row[0]
    cur.execute("UPDATE auth_user SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    conn.commit()
    conn.close()
    print(f"✅ Пароль для пользователя '{login}' (ID: {user_id}) успешно обновлен в {db_path}!")

if __name__ == "__main__":
    main()
```

---

## 3. Бэкенд: Контракты RPC-методов и сессии

### 3.1. Правило префикса `login.` и флага `public=True` (Default Deny)

> ⚠️ **КРИТИЧЕСКИЙ ЗАКОН БЕЗОПАСНОСТИ `PyFerro`:**  
> По умолчанию в приложении включен **Default Deny**: все методы закрыты для неавторизованных гостей.

По умолчанию параметр приложения настроен как `login_rpc="login."`:
- Любой RPC-метод, имя которого начинается с `login.` (например, `login.submit`, `login.get_key`, `login.refresh`, `login.whoami`), **автоматически открыт неавторизованным гостям**.
- Если вы назвали свой метод **`auth.login`**, **`user.auth`** или **`api.login`**, гость получит ошибку `Permission Denied` (-32000), **ЕСЛИ НЕ УКАЗАН ЯВНЫЙ ФЛАГ `public=True`**:

```python
# ❌ ОШИБКА: Гость не сможет вызвать этот метод! Будет RPCError(-32000, "Permission Denied")
@app.rpc("auth.login")
async def login_bad(session, params: dict):
    ...

# ✅ ПРАВИЛЬНО (Вариант 1): Имя начинается с login.
@app.rpc("login.submit")
async def login_standard(session, username: str, password: str):
    ...

# ✅ ПРАВИЛЬНО (Вариант 2): Метод с любым префиксом, но с явным public=True
@app.rpc("auth.login", public=True)
async def login_custom(session, params: dict):
    ...
```

---

### 3.2. Вариант А: Использование встроенного плагина `plugins.auth`

Если проект использует коробочный плагин `pyferro.plugins.auth`:

#### Коробочные RPC-методы плагина:
1. **`login.get_key`** — генерирует эфемерную пару ключей RSA для E2E-шифрования пароля перед отправкой из браузера.
2. **`login.submit`** — стандартный вход по открытому логину и паролю.
   - Параметры: `{"username": "...", "password": "...", "user_agent": "..."}`
3. **`login.secure`** — безопасный вход: пароль зашифрован открытым ключом RSA на клиенте и расшифровывается на сервере приватным ключом.
   - Параметры: `{"username": "...", "encrypted_password": "...", "key_id": "...", "user_agent": "..."}`
4. **`login.refresh`** — продление сессии и скользящий RefreshToken (Sliding Expiration).
   - Параметры: `{"token": "...", "user_agent": "..."}`
5. **`login.whoami`** — проверка статуса авторизации сокета (возвращает роли, права и профиль).
6. **`auth.logout`** — удаление сессии из БД и сокета.

#### Формат успешного ответа:
```json
{
  "token": "refresh_token_hex_string_32",
  "jwt_token": "eyJhbGciOi...",
  "user_id": 1,
  "username": "admin",
  "name": "Administrator",
  "email": "admin@example.com",
  "role": "admin",
  "roles": ["admin"],
  "permissions": { ... },
  "is_superadmin": true
}
```

---

### 3.3. Вариант Б: Легковесный кастомный хендлер входа

Если вы создаете легковесный сервис без тяжелых моделей ролей (паттерн Showcase):

```python
import secrets
from pyferro import FerroApp, rpc_method, RPCError
from pyferro.core.session import current_transport_ctx
from pyferro.plugins.auth.core import AuthSession, current_user_ctx

# 1. Структура данных сессии в памяти
class UserSessionData:
    def __init__(self, user_id: int, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.is_superadmin = (role == "admin")
        self.allowed_rpc_methods = {"*"} if self.is_superadmin else {"tasks.*", "login.*"}

@rpc_method("auth.login", public=True)
async def custom_login(session, params: dict):
    username = params.get("username", "").strip()
    password = params.get("password", "").strip()

    # Проверка пароля (вызов канонической функции verify_password)
    user = await find_user_in_db(username)
    if not user or not verify_password(user.password_hash, password):
        raise RPCError(-32602, "Неверный логин или пароль")

    token = secrets.token_hex(24)
    role = "admin" if user.is_admin else "user"

    # Формируем объект контекста сессии
    user_data = UserSessionData(user.id, user.login, role)

    # Привязываем сессию к транспорту WebSocket
    transport = current_transport_ctx.get() or session
    
    # ⚠️ ВАЖНО: установка session.data превращает гостевой сокет в авторизованный
    session_auth = AuthSession(
        uid=user.id,
        user=user,
        user_name=user.login,
        user_role=role,
        user_roles=[role],
        session_db_id=0,
        user_ctx=user_data,
        allowed_rpc_methods=user_data.allowed_rpc_methods,
        send_request_cb=getattr(transport, "send_request", None),
        send_stream_cb=getattr(transport, "send_stream_chunk", None),
        close_cb=getattr(transport, "close", None)
    )
    transport.data = session_auth
    if hasattr(session, "data"):
        session.data = session_auth

    # Если пользователь администратор — регистрируем сессию в CRUD панели
    if role == "admin":
        from pyferro.plugins.crud import create_crud_session
        create_crud_session({"username": user.login, "role": "admin"}, token=token)

    return {
        "success": True,
        "token": token,
        "username": user.login,
        "role": role,
        "user_id": user.id
    }
```

---

### 3.4. Автоматическая авторизация WebSocket по Cookie (`auto_auth_ws`)

В `FerroApp` по умолчанию включен флаг `auto_auth_ws=True`.

**Как это работает:**
1. При установке WebSocket-соединения браузер передает свои Cookie:
   - `ferro_crud_session`
   - `ferro_session`
   - `rpc_jwt`
   - `token`
2. Метод `_auto_authenticate_ws(session)` извлекает токен:
   - Сначала проверяет хранилище CRUD-сессий (`get_crud_session(token)`).
   - Затем декодирует JWT через `decode_access_token(token)`.
3. Если валидация успешна, объект `AuthSession` создается и присваивается `session.data` **до того, как клиент пришлет первый RPC-запрос**.
4. В логах сервера появляется подтверждение:
   ```text
   [AutoAuth] WebSocket #1 автоматически авторизован по Cookie как admin (admin)
   ```

---

## 4. Фронтенд: Реализация клиента и жизненный цикл

### 4.1. Архитектура канонического клиента `wsrpc.ts`

В клиентской библиотеке `client/wsrpc.ts` реализован высокопроизводительный класс `BinaryWSRPC`:
- Автоматическое определение URL сокета (`getWsUrl()`).
- Автоматический реконнект при обрывах сети.
- Распаковка табличного сжатия (RFC 0002 Tabular Data).
- Поддержка стриминга (`callStream`) и симметричных вызовов (`register`).
- **Системный шлюз авторизации (`authInterceptor` / Gatekeeper).**

---

### 4.2. Шлюз авторизации (`authInterceptor` / Gatekeeper)

При открытии SPA-приложения компоненты сразу начинают отправлять фоновые RPC-запросы (`tasks.list`, `orders.get_all` и т.д.).  
Если сокет еще не успел завершить авторизацию, все эти запросы упадут с ошибкой `Permission Denied`.

Для предотвращения этой проблемы в `wsrpc.ts` встроен механизм **Gatekeeper**:

```typescript
// Внутри wsrpc.ts:
const isBypassMethod = method.startsWith("login.") || method.startsWith("system.") || method.startsWith("auth.");
if (!isBypassMethod && this.authInterceptor) {
    try {
        await this.authInterceptor(); // Ожидает завершения проверки авторизации!
    } catch (authErr) {
        console.warn("[WSRPC Gatekeeper] Ошибка ожидания авторизации:", authErr);
    }
}
```

Все методы `login.*`, `auth.*`, `system.*` проходят **без задержек** (bypass), а бизнес-методы ждут, пока приложение восстановит сессию!

---

### 4.3. Эталонный сервис авторизации (TypeScript)

Создайте в вашем фронтенд-проекте эталонный сервис `services/auth.ts`:

```typescript
import { BinaryWSRPC } from "../client/wsrpc";

export interface UserProfile {
    user_id: number;
    username: string;
    role: string;
    roles?: string[];
    name?: string;
    email?: string;
}

export class AuthService {
    private rpc: BinaryWSRPC;
    public currentUser: UserProfile | null = null;
    public isAuthenticated = false;

    // Промис инициализации для Gatekeeper
    private initPromise: Promise<boolean> | null = null;

    constructor(rpcClient: BinaryWSRPC) {
        this.rpc = rpcClient;
        
        // 1. Привязываем Gatekeeper к WSRPC клиенту
        this.rpc.authInterceptor = () => this.ensureInitialized();
        
        // 2. При каждом успешном физическом подключении сокета проверяем сессию
        this.rpc.onConnect = () => {
            this.syncSessionOnConnect();
        };
    }

    /**
     * Гарантирует, что проверка сессии завершена перед выполнением бизнес-RPC
     */
    public async ensureInitialized(): Promise<boolean> {
        if (!this.initPromise) {
            this.initPromise = this.restoreSession();
        }
        return this.initPromise;
    }

    /**
     * Вход по логину и паролю
     */
    public async login(username: string, password: string): Promise<UserProfile> {
        try {
            // Вызываем стандартный метод login.submit (или auth.login)
            const res: any = await this.rpc.call("login.submit", {
                username,
                password,
                user_agent: navigator.userAgent
            });

            this.currentUser = {
                user_id: res.user_id,
                username: res.username,
                role: res.role,
                roles: res.roles || [res.role],
                name: res.name || res.username,
                email: res.email
            };
            this.isAuthenticated = true;

            // ⚠️ ВАЖНО: Устанавливаем Cookie для HTTP-контура, авто-реконнекта и панели /crud
            if (res.token) {
                // Cookie для CRUD-панели и авто-авторизации сокета
                document.cookie = `ferro_session=${res.token}; path=/; max-age=2592000; SameSite=Lax`;
                document.cookie = `ferro_crud_session=${res.token}; path=/; max-age=2592000; SameSite=Lax`;
                localStorage.setItem("refresh_token", res.token);
            }
            if (res.jwt_token) {
                document.cookie = `rpc_jwt=${res.jwt_token}; path=/; max-age=86400; SameSite=Lax`;
            }

            return this.currentUser;
        } catch (err: any) {
            this.isAuthenticated = false;
            this.currentUser = null;
            throw new Error(err.message || "Неверный логин или пароль");
        }
    }

    /**
     * Восстановление сессии при загрузке страницы
     */
    public async restoreSession(): Promise<boolean> {
        const token = localStorage.getItem("refresh_token");
        
        // 1. Попробуем проверить текущего пользователя через whoami (если сработал auto_auth_ws по Cookie)
        try {
            const whoami: any = await this.rpc.call("login.whoami", {});
            if (whoami && whoami.authenticated) {
                this.currentUser = {
                    user_id: whoami.user_id,
                    username: whoami.username,
                    role: whoami.role,
                    roles: whoami.roles,
                    name: whoami.name
                };
                this.isAuthenticated = true;
                return true;
            }
        } catch (e) {
            // Игнорируем: сокет пока гостевой
        }

        // 2. Если whoami гость, но есть сохраненный refresh_token — продлеваем
        if (token) {
            try {
                const refreshed: any = await this.rpc.call("login.refresh", {
                    token,
                    user_agent: navigator.userAgent
                });
                if (refreshed && refreshed.username) {
                    this.currentUser = {
                        user_id: refreshed.user_id,
                        username: refreshed.username,
                        role: refreshed.role,
                        roles: refreshed.roles,
                        name: refreshed.name
                    };
                    this.isAuthenticated = true;
                    if (refreshed.token) {
                        localStorage.setItem("refresh_token", refreshed.token);
                    }
                    return true;
                }
            } catch (err) {
                console.warn("[Auth] Refresh token недействителен, очищаем:", err);
                this.logoutLocal();
            }
        }

        this.isAuthenticated = false;
        this.currentUser = null;
        return false;
    }

    /**
     * Синхронизация сессии при физическом переподключении сокета (onConnect)
     */
    private async syncSessionOnConnect() {
        if (this.isAuthenticated) {
            // Если мы уже были авторизованы, проверяем, подхватил ли сокет Cookie
            try {
                const whoami: any = await this.rpc.call("login.whoami", {});
                if (!whoami.authenticated) {
                    // Cookie не подхватился автоматически — восстанавливаем по токену
                    await this.restoreSession();
                }
            } catch (err) {
                console.error("[Auth] Ошибка синхронизации сессии при реконнекте:", err);
            }
        }
    }

    /**
     * Выход из учетной записи
     */
    public async logout(): Promise<void> {
        try {
            await this.rpc.call("auth.logout", {});
        } catch (e) {
            // Игнорируем сетевые ошибки при выходе
        } finally {
            this.logoutLocal();
        }
    }

    private logoutLocal() {
        this.currentUser = null;
        this.isAuthenticated = false;
        this.initPromise = null;
        localStorage.removeItem("refresh_token");
        // Удаляем Cookie
        document.cookie = "ferro_session=; path=/; max-age=0";
        document.cookie = "ferro_crud_session=; path=/; max-age=0";
        document.cookie = "rpc_jwt=; path=/; max-age=0";
    }
}
```

---

### 4.4. Интеграция с UI (Svelte 5 / React / Vue)

#### Пример на Svelte 5 (с рунами `$state`):

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { BinaryWSRPC } from './client/wsrpc';
  import { AuthService } from './services/auth';

  const rpc = new BinaryWSRPC();
  const auth = new AuthService(rpc);

  let username = $state('');
  let password = $state('');
  let errorMessage = $state('');
  let isLoading = $state(false);

  let user = $state(auth.currentUser);

  onMount(async () => {
    await rpc.connect();
    await auth.ensureInitialized();
    user = auth.currentUser;
  });

  async function handleLogin() {
    errorMessage = '';
    isLoading = true;
    try {
      user = await auth.login(username, password);
    } catch (err: any) {
      errorMessage = err.message || 'Ошибка авторизации';
    } finally {
      isLoading = false;
    }
  }

  async function handleLogout() {
    await auth.logout();
    user = null;
  }
</script>

{#if user}
  <div class="user-panel">
    <span>Привет, <strong>{user.username}</strong> ({user.role})</span>
    {#if user.role === 'admin'}
      <a href="/crud" target="_blank" class="btn">Админ-панель CRUD</a>
    {/if}
    <button onclick={handleLogout}>Выйти</button>
  </div>
{:else}
  <form onsubmit|preventDefault={handleLogin}>
    <input bind:value={username} placeholder="Логин" required />
    <input type="password" bind:value={password} placeholder="Пароль" required />
    {#if errorMessage}
      <p class="error">{errorMessage}</p>
    {/if}
    <button type="submit" disabled={isLoading}>
      {isLoading ? 'Вход...' : 'Войти'}
    </button>
  </form>
{/if}
```

---

### 4.5. Архитектура SPA: Предотвращение Race Condition при реконнекте (Layout & Child Pages)

В реальных SPA-приложениях (SvelteKit, Nuxt, React Router) архитектура строится на древовидной иерархии: корневой лейаут (`+layout.svelte` / `App.tsx`) и десятки независимых дочерних страниц (`/orders`, `/banks`, `/dashboard`).

#### Анатомия проблемы (почему возникает всплеск `Permission Denied`):
1. Происходит кратковременный обрыв связи (сон ноутбука, перезапуск сервера, сбой Wi-Fi).
2. Сокет переподключается и переходит в статус `OPEN` (`status === 'CONNECTED'`).
3. Корневой лейаут начинает асинхронно восстанавливать сессию (например, вызывает `rpc.call("login.refresh")`).
4. **Но дочерние страницы уже активны!** Они видят, что статус сокета `CONNECTED`, и в ту же миллисекунду отправляют рабочие запросы (`orders.list`, `stats.get`).
5. Бизнес-запросы приходят на сервер **раньше**, чем сервер успел обработать `login.refresh`.
6. Сервер (в режиме Default Deny) абсолютно справедливо возвращает ошибку: `RPCError(-32000, "Permission Denied: User is not authenticated")`.

---

#### Канонические решения проблемы

##### Способ 1: Идиоматичный UI-барьер в Лейауте (Рекомендуемый для SPA)
Самое простое, визуально чистое и надёжное решение в компонентных фреймворках — **не рендерить и не монтировать дочерние бизнес-компоненты, пока сессия лейаута не готова**:

```svelte
<!-- +layout.svelte (Svelte 5) -->
<script lang="ts">
  let isSessionReady = $state(false);

  // При старте или реконнекте:
  async function initSession() {
    try {
      await authService.ensureInitialized();
    } finally {
      isSessionReady = true;
    }
  }
</script>

{#if isSessionReady}
  {@render children()}
{:else}
  <div class="session-loader">
    <span>Восстановление защищенной сессии...</span>
  </div>
{/if}
```
*Эффект:* Дочерние страницы даже не будут созданы в DOM и физически не отправят ни одного запроса, пока лейаут не подтвердит сессию. Ноль гонок, ноль лишнего кода.

---

##### Способ 2: Сетевой шлюз `authInterceptor` (На транспортном уровне)
Если дочерние страницы должны оставаться смонтированными во время реконнекта, настройте системный шлюз клиента `BinaryWSRPC`. 

При инициализации сокета свяжите `authInterceptor` с функцией восстановления сессии:

```typescript
// services/rpc.ts или в точке инициализации приложения:
const rpc = new BinaryWSRPC();

rpc.authInterceptor = async () => {
    // Если токена нет в хранилище, сразу выходим (пользователь — гость)
    const token = localStorage.getItem("refresh_token");
    if (!token) return;

    // Вызов login.refresh пройдет через шлюз БЕЗ задержек (попадает под bypass login.*),
    // в то время как любые параллельные вызовы orders.list будут придержаны шлюзом.
    await rpc.call("login.refresh", { token, user_agent: navigator.userAgent });
};
```

---

#### 4.6. Разработка на Vite: Настройка Dev-Server Proxy

В режиме разработки фронтенд часто запущен на отдельном порту (например, Vite на `http://localhost:5173`), а бэкенд Granian на `http://localhost:8080`.  
В этом случае куки браузера с порта `5173` не передаются на порт `8080`, из-за чего нативный механизм `auto_auth_ws=True` не может авторизовать сокет во время Handshake.

**Правильное решение:** настроить проксирование в `vite.config.ts`:

```typescript
import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      // Проксируем WebSocket соединения к Granian RSGI
      '/ws': {
        target: 'ws://127.0.0.1:8080',
        ws: true
      },
      // Проксируем HTTP API (загрузка файлов, статика, auth)
      '/api': 'http://127.0.0.1:8080',
      '/upload': 'http://127.0.0.1:8080'
    }
  }
});
```
После настройки прокси клиент подключается к сокету по относительному адресу (`/ws` на том же хосте и порту). Кука `ferro_session` летит в WebSocket Handshake автоматически, и сокет открывается **уже авторизованным**, без необходимости делать ручной `login.refresh`!

---

#### 4.7. Анти-паттерны интеграции клиента (Чего делать НЕЛЬЗЯ)

1. ❌ **Не тащите прикладную логику в транспортный клиент:**  
   Категорически запрещено модифицировать `wsrpc.ts`, вшивая туда чтение специфичных конфигов вроде `/settings.json`, специфичные пути логирования (`/client_log`) или вызовы `login.whoami` на `onopen`. Транспортный уровень обязан оставаться легковесным и нейтральным.
2. ❌ **Не вызывайте бизнес-методы в дочерних компонентах вслепую:**  
   Компоненты не должны надеяться на удачу. Либо защищайте рендеринг через `{#if isSessionReady}`, либо регистрируйте `rpc.authInterceptor`.
3. ❌ **Не запускайте параллельный шторм `refresh`:**  
   Не вызывайте `login.refresh` независимо из каждого компонента или виджета. Восстановление сессии должно выполняться централизованно через единый сервис авторизации.

---

## 5. Интеграция с Панелью Управления CRUD (Zero-Leakage 404)

Если администратор пытается открыть `http://localhost:8080/crud` и видит **`404 Not Found`**, это **не баг роутинга и не сломанная статика**.

Это механизм **Zero-Leakage (404)**:  
Эндпоинт `/crud` намеренно маскируется под несуществующую страницу, если запрос не содержит Cookie администратора:
- `ferro_crud_session`
- или `ferro_session`

### Как гарантировать работу перехода в `/crud`:
1. **На бэкенде** при авторизации пользователя с ролью `admin` зарегистрируйте его сессию:
   ```python
   if role == "admin":
       from pyferro.plugins.crud import create_crud_session
       create_crud_session({"username": user.login, "role": "admin"}, token=token)
   ```
2. **На фронтенде** обязательно запишите токен в Cookie:
   ```javascript
   document.cookie = `ferro_crud_session=${res.token}; path=/; max-age=86400; SameSite=Lax`;
   ```
3. После этого открытие `window.open('/crud', '_blank')` сразу покажет полнофункциональную панель управления.

---

## 6. Таблица типичных ошибок и решений (Troubleshooting)

| Симптом | Причина | Решение |
|---|---|---|
| **`Неверный логин или пароль` при верных данных** | Не совпадает алгоритм/формат хэша в БД (вместо `pbkdf2_sha256$<iter>$<salt_b64>$<key_b64>` лежит hex или sha256) | Сбросить пароль через CLI: `python server.py --set-admin-password "пароль" --login "логин"` |
| **`Permission Denied` (-32000) при вызове метода логина** | Метод назван не с префикса `login.` (например `auth.login`) и не имеет флага `public=True` | Добавить `@rpc_method("auth.login", public=True)` или переименовать в `login.submit` |
| **При обновлении страницы пользователь разлогинивается** | Фронтенд не сохраняет `refresh_token` в `localStorage` или не устанавливает `ferro_session` Cookie | Устанавливать Cookie и вызывать `auth.ensureInitialized()` / `restoreSession()` при старте |
| **При переподключении сокета бизнес-запросы падают с ошибкой прав** | Запросы улетают до восстановления сессии сокета | Настроить `rpc.authInterceptor = () => auth.ensureInitialized()` на клиенте |
| **Переход на `/crud` возвращает `404 Not Found`** | Отсутствует Cookie `ferro_crud_session` или `ferro_session` с валидным токеном администратора | Вызывать `crud.create_crud_session(...)` на бэке и ставить Cookie на фронте |
| **`Пользователь не авторизован` внутри SQLAlchemy ORM** | Сработал RLS-фильтр `RowSecureModel`, но в текущей корутине не установлен `current_user_ctx` | Проверить, что сессия сокета авторизована (`session.data = AuthSession(...)`) или использовать `system_bypass_ctx` для системных задач |
