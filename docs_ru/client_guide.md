# Руководство по клиентскому SDK: `client/wsrpc.ts`

> **Официальный клиент платформы `PyFerro` (TypeScript & JavaScript)**  
> Легковесный клиент с нулевыми внешними зависимостями, реактивным управлением состоянием, встроенной аутентификацией, поддержкой симметричного RPC, потокового стриминга и табличного сжатия (RFC 0002).

---

## 🧭 Содержание

1. [Концепция и Быстрый старт](#1-концепция-и-быстрый-старт)
2. [Жизненный цикл подключения и сеть](#2-жизненный-цикл-подключения-и-сеть)
3. [Реактивные хранилища состояния (SimpleStore)](#3-реактивные-хранилища-состояния-simplestore)
4. [Вызовы RPC и обработка результатов](#4-вызовы-rpc-и-обработка-результатов)
5. [Встроенная аутентификация (`rpc.auth` / `AuthStore`)](#5-встроенная-аутентификация-rpcauth--authstore)
6. [Табличное сжатие данных (RFC 0002)](#6-табличное-сжатие-данных-rfc-0002)
7. [Потоковый стриминг прогресса (Multi-Return)](#7-потоковый-стриминг-прогресса-multi-return)
8. [Полнодуплексный Reverse RPC (Сервер &rarr; Клиент)](#8-полнодуплексный-reverse-rpc-сервер--клиент)
9. [Подписка на события и Broadcast (Pub/Sub)](#9-подписка-на-события-и-broadcast-pubsub)
10. [Строгая типизация пользователя (TypeScript Generics)](#10-строгая-типизация-пользователя-typescript-generics)

---

## 1. Концепция и Быстрый старт

`client/wsrpc.ts` — это единый источник правды для взаимодействия фронтенда с бэкендом PyFerro:
* **Единый постоянный WebSocket** для всех RPC-запросов, фоновых рассылок, стриминга и аутентификации.
* **Нулевые зависимости (Zero Dependencies):** не требует внешних библиотек (JSEncrypt, Axios и т.д.). Шифрование выполняется через нативный браузерный **Web Crypto API**.
* **Zero-Boilerplate:** аутентификация, cookies, session gatekeeper и распаковка табличных данных встроены прямо в клиент.

### Установка и импорт в проекте:
Скопируйте `client/wsrpc.ts` в ваш проект (например, в `src/lib/wsrpc.ts`):

```typescript
import { rpc, auth } from './wsrpc';

// 1. Вход в систему (если требуется)
await auth.login({ username: 'alex', password: 'my-password' });

// 2. Вызов RPC-метода
const tasks = await rpc.call('tasks.list');
console.log('Список задач:', tasks);
```

---

## 2. Жизненный цикл подключения и сеть

По умолчанию клиент автоматически определяет адрес сервера через функцию `getWsUrl()`:
* При разработке через Vite dev-сервер (`5173` / `4173`) направляет соединение на `ws://127.0.0.1:8080/ws`.
* В production формирует относительный путь `/ws` с учетом протокола (`ws://` или `wss://`).

### Управление подключением:
```typescript
import { BinaryWSRPC } from './wsrpc';

// Создание клиента с явным URL (или используйте глобальный синглтон rpc)
const client = new BinaryWSRPC('wss://api.example.com/ws');

// Настройка времени авто-переподключения в секундах (по умолчанию 3 сек; 0 — отключить)
client.reconnectWs = 3;

// Хуки жизненного цикла сети
client.onConnect = () => {
    console.log('✅ WebSocket соединение успешно установлено');
};

client.onStatusChange = (connected: boolean) => {
    console.log('Статус сети изменился:', connected ? 'ONLINE' : 'OFFLINE');
};

// Ручной коннект (при первом вызове rpc.call подключение произойдет автоматически)
await client.connect();

// Принудительное закрытие (авто-реконнект отключается)
client.disconnect();
```

---

## 3. Реактивные хранилища состояния (SimpleStore)

В клиенте реализован легковесный реактивный класс `SimpleStore<T>`, на 100% совместимый с:
* Контрактом сторов **Svelte** (`$store`).
* Хуком `useSyncExternalStore` в **React**.
* Реактивными эффектами в **Vue** и **Vanilla JS** (`subscribe`).

### Экспортируемые сетевые сторы:
* `wsConnected`: `SimpleStore<boolean>` — флаг активного соединения.
* `wsStatus`: `SimpleStore<'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'>` — текущий сетевой статус.

#### Пример индикатора сети на Svelte:
```svelte
<script>
  import { wsConnected, wsStatus } from './wsrpc';
</script>

{#if !$wsConnected}
  <div class="banner">Связь потеряна. Статус: {$wsStatus}...</div>
{/if}
```

#### Пример на Vanilla JS / React:
```typescript
import { wsConnected } from './wsrpc';

const unsubscribe = wsConnected.subscribe((connected) => {
    document.getElementById('status').textContent = connected ? 'Онлайн' : 'Офлайн';
});
```

---

## 4. Вызовы RPC и обработка результатов

### Базовый вызов: `rpc.call(method, params, options)`
```typescript
// Вызов без параметров
const ping = await rpc.call('system.ping');

// Вызов с параметрами
const task = await rpc.call('tasks.create', { 
    title: 'Подготовить релиз', 
    priority: 1 
});

// Настройка персонального таймаута (в миллисекундах)
const result = await rpc.call('heavy.compute', { data: 123 }, 30000);
```

### Обработка ошибок (JSON-RPC 2.0):
При ошибке сервера промис отклоняется с объектом `Error`, содержащим поля `code` и `data`:
```typescript
try {
    await rpc.call('admin.delete_all');
} catch (err: any) {
    console.error('Ошибка RPC:', err.message); // Текст ошибки от сервера
    console.error('Код ошибки:', err.code);     // Например, -32000 (Permission Denied) или -32601
}
```

---

## 5. Встроенная аутентификация (`rpc.auth` / `AuthStore`)

Подсистема `rpc.auth` (также доступна как отдельный экспорт `auth`) полностью берет на себя управление сессиями, токенами и куками.

### 5.1. Методы входа:
```typescript
import { auth } from './wsrpc';

// 1. Стандартный вход по логину и паролю (login.submit)
const user = await auth.login({ username: 'alex', password: 'secret' });

// 2. Безопасный вход с автоматическим RSA-OAEP шифрованием пароля
// (Запрашивает эфемерный публичный ключ RSA у сервера и шифрует пароль через Web Crypto API)
const secureUser = await auth.loginSecure({ username: 'alex', password: 'secret' });

// 3. Вход через OAuth, Telegram, SMS или Passkeys (произвольный RPC-метод)
// Вызовите свой бэкенд-метод и примените полученную сессию в один вызов:
const oauthRes = await rpc.call('auth.vk_oauth', { code: '...' });
const oauthUser = auth.setSession(oauthRes); // атомарно выставляет cookies, localStorage и userStore
```

### 5.2. Реактивное состояние и свойства `auth`:
* `auth.user`: текущий объект пользователя (`AuthUser | null`). Автоматически нормализует стандартные поля:
  - `id`, `uid`, `user_id`: универсальные алиасы идентификатора пользователя (`string | number`).
  - `avatar`, `photo_url`: ссылка на аватар профиля (`string | null`).
  - `email`: электронная почта или `null` при регистрации по телефону/OAuth (`string | null`).
  - `username`, `name`, `role`, `roles`, `permissions`, `is_superadmin`.
* `auth.isValid`: `boolean` — авторизован ли пользователь в данный момент.
* `auth.token`: текущий токен сессии / refresh_token.
* `auth.jwtToken`: короткоживущий JWT для REST API и загрузки файлов.
* `auth.isLoading`: `boolean` — идет ли процесс первоначальной проверки сессии.

### 5.3. Реактивная подписка на смену пользователя:
`auth` реализует интерфейс `SimpleStore`, поэтому в Svelte можно писать `$auth`:
```svelte
<script>
  import { auth } from './wsrpc';
</script>

{#if auth.isValid}
  <p>Привет, {auth.user?.name}!</p>
  <button on:click={() => auth.logout()}>Выйти</button>
{:else}
  <p>Вы вошли как гость</p>
{/if}
```
В React/Vue/JS:
```typescript
const unsubscribe = auth.onChange((user) => {
    console.log('Пользователь обновился:', user);
});
```

### 5.4. Авто-сохранение сессии и Cookie:
При успешном входе `AuthStore` автоматически устанавливает:
* `localStorage.setItem('refresh_token', token)`
* `document.cookie` для `ferro_session` и `ferro_crud_session` (срок 30 дней, `SameSite=Lax`) — открывает доступ к сокетам и панели `/crud`.
* `document.cookie` для `rpc_jwt` (срок 24 часа).

### 5.5. Session Gatekeeper (Шлюз от гонок запросов):
При старте страницы или F5 защищенные RPC-запросы (`tasks.list`, `profile.get`) **автоматически удерживаются в очереди**, пока `auth.ensureInitialized()` не восстановит сессию по Cookie/токену. Бизнес-запросы никогда не падают с ложной ошибкой `Permission Denied`!

---

## 6. Табличное сжатие данных (RFC 0002)

Серверные методы, декорированные `@tabular_response`, возвращают компактные пакеты вида `{$tabular: true, fields: [...], rows: [...]}`.

Клиент `wsrpc.ts` распаковывает их **прозрачно на лету**:
```typescript
// Бэкенд возвращает сжатую матрицу rows, а клиент получает привычный массив объектов!
const tasks = await rpc.call('tasks.list');
console.log(tasks); // [{ id: 1, title: 'Задача 1' }, { id: 2, title: 'Задача 2' }]
```

Если требуется распаковать или упаковать данные вручную:
```typescript
import { unpackTabular, packTabular } from './wsrpc';

const plainObjects = unpackTabular(compressedPayload);
const compressed = packTabular(plainObjects, ['id', 'title']);
```

---

## 7. Потоковый стриминг прогресса (Multi-Return)

Для длительных задач сервер может слать промежуточные чанки (`session.send_stream_chunk`).  
Клиент принимает их через колбэк `onChunk`:

```typescript
const finalReport = await rpc.call(
    'reports.generate',
    { month: '2026-10' },
    {
        onChunk: (chunk) => {
            console.log(`Прогресс: ${chunk.progress}%, шаг: ${chunk.step}`);
            updateProgressBar(chunk.progress);
        },
        timeoutMs: 60000 // 1 минута на тяжелую задачу
    }
);
console.log('Финальный отчет готов:', finalReport.url);
```

---

## 8. Полнодуплексный Reverse RPC (Сервер &rarr; Клиент)

WSRPC полностью симметричен: сервер может сам инициировать запрос в браузер через `session.send_request("client.method")` и ожидать ответ.

Регистрация клиентского метода:
```typescript
// Сервер вызывает rpc_method client.get_env
rpc.register('client.get_env', async (params) => {
    return {
        userAgent: navigator.userAgent,
        screenWidth: window.screen.width,
        language: navigator.language
    };
});
```

---

## 9. Подписка на события и Broadcast (Pub/Sub)

Для прослушивания серверных нотификаций реального времени используйте `rpc.on`:

```typescript
// Подписка на серверные события
const unsubscribe = rpc.on('chat.message', (message) => {
    console.log('Новое сообщение в чате:', message);
});

// Отписка от событий при размонтировании компонента
onDestroy(() => {
    unsubscribe();
});
```

---

## 10. Строгая типизация пользователя (TypeScript Generics)

Если ваша схема пользователя содержит специфичные для проекта поля (роли, баланс, отдел):

```typescript
import { BinaryWSRPC, type AuthUser } from './wsrpc';

// 1. Описываем модель
interface MyUser extends AuthUser {
    department: string;
    points: number;
    role: 'admin' | 'moderator' | 'user';
}

// 2. Инициализируем типизированный клиент
export const rpc = new BinaryWSRPC<MyUser>();
export const auth = rpc.auth;

// Теперь TypeScript знает все кастомные поля!
if (auth.user) {
    console.log(auth.user.department); // string
    console.log(auth.user.points);     // number
}
```
