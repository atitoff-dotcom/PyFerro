# 🌐 Интеграция Nginx / Angie / Caddy с PyFerro и Granian

Документ описывает архитектуру взаимодействия обратного прокси (**Nginx / Angie / Caddy**), высокопроизводительного Rust HTTP-сервера (**Granian**, протокол **RSGI**) и фреймворка **PyFerro**, а также готовые боевые конфигурации.

---

## 🏛️ Архитектурный паттерн: «Золотая середина»

В высоконагруженных и безопасных веб-системах применяется строгое разделение обязанностей:

* **Nginx / Ingress («Мускулы»):**
  * Терминация TLS/SSL и поддержка HTTP/2, HTTP/3.
  * Прямая раздача файлов с диска через системный вызов ядра Linux **`sendfile`** и пулы потоков **`aio threads`** (Zero-Copy) без задействования Python и вымывания Page Cache ОС.
  * Защита от медленных клиентов (Slowloris), жёсткие таймауты чтения чанков и изолированная песочница (`Content-Security-Policy: sandbox`) для раздаваемых файлов.
  * Долгоживущие WebSocket-соединения с мгновенной доставкой пакетов.
* **PyFerro + Granian («Мозг»):**
  * Полная валидация авторизации и прав (JWT, RBAC, сессии).
  * Двухфазная загрузка файлов (2PC) и бизнес-логика.
  * Отсутствие двойной буферизации и накладных расходов: память фиксирована $O(1)$.

---

## 1. Загрузка файлов (Upload): Потоковый Fail-Fast (RSGI)

### Защита от Disk Exhaustion DoS и Slowloris
Если позволить прокси-серверу сохранять тело входящего запроса на диск до проверки подлинности, любой злоумышленник может исчерпать свободное место на диске мусорными запросами.

В PyFerro и Granian (протокол **RSGI**) используется подход **потокового отсечения на этапе заголовков**:
1. В Nginx отключается буферизация тела: `proxy_request_buffering off;`, а также задаются жёсткие таймауты чтения чанков (`client_body_timeout 15s;`), чтобы при отключенной буферизации медленный клиент не удерживал воркер.
2. Как только клиент передаёт HTTP-заголовки (`Authorization: Bearer <token>`, `Content-Length`), Nginx немедленно проксирует их в Granian.
3. **PyFerro проверяет JWT, права транзакции и `Content-Length` в `scope.headers` ДО чтения потока тела:**
   * **Если JWT невалиден, нет доступа к транзакции или `Content-Length > max_file_size`:** PyFerro мгновенно отдаёт HTTP `401 Unauthorized` / `403 Forbidden` / `413 Payload Too Large` (`proto.response_bytes(...)`) и завершает обработку, даже не начиная итерацию по потоку `proto` (`async for chunk in proto`). Granian и Nginx закрывают соединение. На диск не записывается ни одного байта.
   * **Если проверки пройдены:** PyFerro асинхронно итерирует входящие чанки из `proto` (с защитой от Slowloris по таймауту `chunk_timeout = 15.0 с` -> `408 Request Timeout`) и пишет их во временное хранилище транзакции с расчётом SHA-256 на лету. При превышении `max_file_size` или обрыве связи частично записанный файл мгновенно удаляется. Расход RAM остаётся $O(1)$ независимо от размера файла.

> **Важно (синхронизация лимитов):** Лимит `client_max_body_size` в Nginx должен соответствовать параметру `max_file_size` в `FileStorage` (по умолчанию `DEFAULT_MAX_FILE_SIZE = 250 МБ`). Если в Nginx разрешено `2G`, укажите соответствующий `max_file_size` при инициализации `FileStorage`.

### Двухфазная загрузка (2PC) в PyFerro:
1. **Фаза 1 (Init):** Клиент вызывает RPC `files.init_upload` -> получает временный `folder_hash` и `upload_url`.
2. **Заливка:** Потоковая отправка `POST /upload?folder=<folder_hash>&filename=<name>`.
3. **Фаза 2 (Commit):** Клиент вызывает RPC `files.commit(folder_hash=..., is_public=True)` -> атомарный перенос в постоянное хранилище (`os.replace`) и создание записи в `pf_file_metadata`.

---

## 2. Скачивание файлов (Download): `X-Accel-Redirect` и защита от XSS

Для раздачи защищенных файлов клиентам не требуется прогонять гигабайты через Python:

1. Клиент запрашивает файл: `GET /files/<folder>/<name>` (с JWT в заголовке `Authorization`, cookie или в одноразовом файловом токене `?token=`).
2. PyFerro проверяет токен, статус пользователя и права доступа к файлу.
3. PyFerro возвращает пустой HTTP-ответ (`proto.response_empty(200, ...)`) с заголовком:
   ```http
   X-Accel-Redirect: /internal_files/<folder>/<name>
   ```
4. Nginx перехватывает этот заголовок и передаёт файл с диска клиенту напрямую через ядро ОС (**`sendfile on; aio threads;`**).
5. **Безопасность при раздаче пользовательских файлов:**
   * Директория `/internal_files/` помечена в Nginx как `internal;` — прямой доступ снаружи к ней заблокирован.
   * Для защиты от **Stored XSS** (если пользователь загрузил `.svg` или `.html` с вредоносным JS и открыл прямую ссылку) Nginx принудительно добавляет `Content-Security-Policy: default-src 'none'; sandbox` и `X-Content-Type-Options: nosniff`.
   * Для предотвращения утечки файлового `?token=` через заголовок `Referer` и в дисковые логи в локации раздачи отключается `access_log` и выставляется `Referrer-Policy: no-referrer`.

---

## 3. WebSocket и мультиретурн (`yield`)

PyFerro поддерживает полнодуплексный JSON-RPC 2.0 и стриминг асинхронных генераторов (`yield`).
Для стабильной работы соединений:
* В Nginx отключается буферизация ответов (`proxy_buffering off;`), чтобы каждый `yield` или `session.notify` доставлялся на фронтенд без задержек.
* Выставляется увеличенный таймаут (`proxy_read_timeout 86400s;`), чтобы Nginx не сбрасывал простаивающие подписки каждые 60 секунд.
* В блоке `map $http_upgrade $connection_upgrade` для пустого `$http_upgrade` используется `""` (а не `close`), чтобы не разрывать пул `keepalive` соединений к `granian_backend` на обычных HTTP-запросах.

---

## 4. Полная боевая конфигурация Nginx / Angie

```nginx
# В секции http { ... } определяем корректный заголовок Connection:
# - "upgrade" для WebSocket
# - "" (пусто) для сохранения HTTP/1.1 Keep-Alive к upstream granian_backend
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      "";
}

upstream granian_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}

server {
    listen 80;
    server_name example.com;

    # 1. WebSocket JSON-RPC 2.0 и мультиретурн (yield) для Granian
    location /ws {
        proxy_pass http://granian_backend/ws;
        proxy_http_version 1.1;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Отключаем буферизацию для мгновенной доставки пакетов yield и session.notify
        proxy_buffering off;
        # Держим соединение для долгих подписок (heartbeat ping/pong поддерживает активность)
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # 2. Потоковая закачка файлов напрямую в Granian без буферизации на диске Nginx (Fail-Fast)
    location /upload {
        # Должно быть синхронизировано с FileStorage(max_file_size=...)
        client_max_body_size 2G;
        # Защита от Slowloris при отключенной буферизации запроса
        client_body_timeout 15s;

        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_send_timeout 30s;
        proxy_read_timeout 60s;
        proxy_pass http://granian_backend/upload;
    }

    # 3. Внутренняя раздача файлов с диска мимо Python (по заголовку X-Accel-Redirect от PyFerro)
    location /internal_files/ {
        internal;
        alias /var/lib/pyferro/storage/;

        # Zero-Copy и защита Page Cache ОС от вымывания большими файлами
        sendfile on;
        tcp_nopush on;
        aio threads;
        directio 8m;

        # Не логируем возможные query-токены (?token=...) и защищаем от утечки в Referer
        access_log off;
        add_header Referrer-Policy "no-referrer" always;

        # Защита от Stored XSS при открытии загруженных пользователями SVG/HTML в браузере
        add_header X-Content-Type-Options "nosniff" always;
        add_header Content-Security-Policy "default-src 'none'; sandbox" always;
    }

    # 4. Остальные HTTP-маршруты (/rpc, /files/..., /pyferro_admin)
    location / {
        proxy_pass http://granian_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Конфигурация Caddy v2 (`Caddyfile`)

Caddy поддерживает потоковую передачу и раздачу через `X-Accel-Redirect` с помощью директивы `handle_response` (при этом важно явно удалять внутренний заголовок `X-Accel-Redirect` и настраивать заголовки безопасности):

```caddyfile
example.com {
    # Лимит размера загружаемого тела (синхронизировать с FileStorage.max_file_size)
    request_body {
        max_size 2GB
    }

    reverse_proxy 127.0.0.1:8000 {
        # Отключаем буферизацию для мгновенного стриминга (yield / WebSocket / Fail-Fast)
        flush_interval -1

        @accel header X-Accel-Redirect *
        handle_response @accel {
            # Скрываем внутренний заголовок редиректа от клиента и включаем песочницу безопасности
            header -X-Accel-Redirect
            header X-Content-Type-Options "nosniff"
            header Content-Security-Policy "default-src 'none'; sandbox"
            header Referrer-Policy "no-referrer"

            root * /var/lib/pyferro/storage
            rewrite * {rp.header.X-Accel-Redirect}
            uri strip_prefix /internal_files
            file_server
        }
    }
}
```
