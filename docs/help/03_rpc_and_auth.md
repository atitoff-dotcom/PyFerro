# RPC-маршрутизация и авторизация

Каждый метод API регистрируется через декоратор роутера с указанием необходимых системных ролей или публичного доступа.

---

## 1. Регистрация RPC-методов на бэкенде

```python
from pyferro2.core.constants import admRole
from pyferro2.core.session_data import SessionData

# Публичный метод (доступен гостям)
@router.rpc_method(public=True)
async def get_public_catalog() -> dict:
    return {"status": "ok", "items": []}

# Доступно авторизованным пользователям (роль user или admin)
@router.rpc_method()
async def get_profile(session_data: SessionData) -> dict:
    return {"user_id": session_data.user_id, "username": session_data.username}

# Доступно только роли adm_help и главному admin
@router.rpc_method(role=[admRole.adm_help])
async def get_help_articles(session_data: SessionData) -> dict:
    return {"items": []}

# Доступно строго главному администратору (роль admin)
@router.rpc_method(role=[admRole.admin])
async def get_system_metrics(session_data: SessionData) -> dict:
    return {"cpu": 12.5, "memory_mb": 256}
```

---

## 2. Системные роли безопасности

* **`guest`** — неавторизованный посетитель.
* **`user`** — базовый зарегистрированный пользователь платформы.
* **`admin`** — главный суперпользователь, имеет доступ ко всем методам и разделам.
* **`adm_*`** — гранулярный доступ к разделам панели управления (`/pyferro_admin`):
  * `adm_crud` — просмотр и редактирование таблиц базы данных.
  * `adm_users` — управление учетными записями пользователей.
  * `adm_roles` — управление матрицей прав и ролей (RBAC).
  * `adm_settings` — глобальные конфигурации системы.
  * `adm_seo` — управление SEO-правилами, метатегами и sitemap.
  * `adm_help` — доступ к данному справочнику разработчика (`/pyferro_admin/help`).

---

## 3. 📱 Памятка разработчика клиентских приложений (SPA / Web / Mobile)

Чтобы между панелью управления (`/pyferro_admin`), клиентским сайтом и внешними сервисами не возникало путаницы с авторизацией, следуйте стандартному контракту PyFerro.

### 🔑 Хранение токена и работа с Cookie
1. **Основное имя ключа:** `pyferro2_token`.
2. **Сессионная кука:** `ferro_session` (или `pyferro2_token`).
3. **Синхронизация при входе:**
   При получении токета от `auth.login` клиент обязан записать его в `localStorage` и продублировать в `Cookie`:
   ```javascript
   // 1. В локальное хранилище
   localStorage.setItem("pyferro2_token", token);

   // 2. В сессионную куку на весь домен (для бесшовного перехода между разделами)
   document.cookie = `ferro_session=${encodeURIComponent(token)}; path=/; max-age=2592000; SameSite=Lax`;
   document.cookie = `pyferro2_token=${encodeURIComponent(token)}; path=/; max-age=2592000; SameSite=Lax`;
   ```
4. **Сброс при выходе (`auth.logout`):**
   ```javascript
   localStorage.removeItem("pyferro2_token");
   document.cookie = "ferro_session=; path=/; max-age=0; SameSite=Lax";
   document.cookie = "pyferro2_token=; path=/; max-age=0; SameSite=Lax";
   ```

### 🌐 Подключение по WebSocket (`/ws`)
1. Клиент читает токен из `localStorage` либо из `document.cookie`.
2. При открытии сокета токен передается query-параметром:
   ```javascript
   const token = getStoredToken();
   const qs = token ? `?token=${encodeURIComponent(token)}` : "";
   const ws = new WebSocket(`wss://${location.host}/ws${qs}`);
   ```
   *Даже если токен не передан в query, браузер автоматически отправит куку `ferro_session` в заголовках HTTP Upgrade, и бэкенд PyFerro восстановит сессию.*

3. Сразу после открытия соединения клиент вызывает `auth.me` для получения актуального паспорта пользователя (`user_id`, `username`, `roles`, `permissions`, `is_admin`).

### ⚠️ Частые архитектурные ошибки и их решение

1. **Разделение доменов (`www` vs `non-www`):**
   * Браузер считает `domain.ru` и `www.domain.ru` разными источниками (**Origins**). У них полностью изолированный `localStorage`.
   * **Решение:** всегда настраивать жесткий HTTP 301-редирект с одного на другой на уровне Nginx (например, с `www.domain.ru` на `domain.ru`).
2. **Слепой отказ от сессии при пустом LocalStorage:**
   * Нельзя сразу объявлять пользователя `guest`, если в `localStorage` нет токена — токен может находиться в Cookie (например, после входа в `/pyferro_admin`). Сначала проверьте Cookie `ferro_session`/`pyferro2_token`, либо вызовите `auth.me` через сокет.
3. **Хэширование паролей:**
   * PyFerro 2 использует стандартный криптостойкий алгоритм **scrypt** (OpenSSL). Все пароли в таблице `pf_auth_user` должны иметь формат `scrypt$<salt_hex>$<digest_hex>`.
