const isBrowser = typeof window !== 'undefined';

/**
 * Легковесный реактивный стор с нулевыми зависимостями.
 * Полностью совместим со стандартом Svelte store contract ($store),
 * React (useSyncExternalStore), Vue и Vanilla JS (subscribe).
 */
type Listener<T> = (val: T) => void;
export class SimpleStore<T> {
    private value: T;
    private listeners = new Set<Listener<T>>();
    constructor(val: T) { this.value = val; }
    get(): T { return this.value; }
    set(val: T) { this.value = val; this.listeners.forEach(fn => fn(val)); }
    update(updater: (val: T) => T) { this.set(updater(this.value)); }
    subscribe(fn: Listener<T>): () => void {
        fn(this.value);
        this.listeners.add(fn);
        return () => { this.listeners.delete(fn); };
    }
}

// Реактивные сторы состояния соединения
export const wsConnected = new SimpleStore<boolean>(false);
export const wsStatus = new SimpleStore<'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'>('DISCONNECTED');

/**
 * Базовый интерфейс пользователя PyFerro Auth.
 */
export interface AuthUser {
    id?: number | string;
    uid?: number | string;
    user_id: number | string;
    username: string;
    role: string;
    roles?: string[];
    name?: string;
    email?: string | null;
    avatar?: string | null;
    photo_url?: string | null;
    permissions?: Record<string, any>;
    is_superadmin?: boolean;
    [key: string]: any;
}

/**
 * Учетные данные для входа.
 */
export interface LoginCredentials {
    username: string;
    password: string;
    remember?: boolean;
    user_agent?: string;
    [key: string]: any;
}

/**
 * Дополнительные опции входа.
 */
export interface LoginOptions {
    /** Метод входа (по умолчанию 'login.submit' с авто-фоллбэком на 'auth.login') */
    method?: string;
    /** Произвольные дополнительные параметры */
    extraParams?: Record<string, any>;
    user_agent?: string;
}

/**
 * Утилиты для безопасной работы с Cookie в браузере (Lax, max-age).
 */
export function setAuthCookie(name: string, value: string, maxAgeSec: number): void {
    if (typeof document === 'undefined') return;
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSec}; SameSite=Lax`;
}

export function getAuthCookie(name: string): string | null {
    if (typeof document === 'undefined' || !document.cookie) return null;
    const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
}

export function deleteAuthCookie(name: string): void {
    if (typeof document === 'undefined') return;
    document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

/**
 * Безопасное шифрование пароля через нативный Web Crypto API (RSA-OAEP, SHA-256).
 * Нулевые внешние зависимости: использует стандартный браузерный крипто-стек.
 */
export async function encryptPasswordRsa(publicKeyPem: string, text: string): Promise<string> {
    if (typeof window === 'undefined' || !window.crypto || !window.crypto.subtle) {
        throw new Error('[WSRPC Auth] Web Crypto API недоступен в текущем окружении');
    }
    const cleanB64 = publicKeyPem
        .replace(/-----BEGIN [A-Z0-9_\s]+-----/g, '')
        .replace(/-----END [A-Z0-9_\s]+-----/g, '')
        .replace(/\s+/g, '');
    
    const binaryDer = Uint8Array.from(atob(cleanB64), (c) => c.charCodeAt(0));
    const cryptoKey = await window.crypto.subtle.importKey(
        'spki',
        binaryDer.buffer,
        { name: 'RSA-OAEP', hash: 'SHA-256' },
        false,
        ['encrypt']
    );

    const encodedText = new TextEncoder().encode(text);
    const encryptedBuffer = await window.crypto.subtle.encrypt(
        { name: 'RSA-OAEP' },
        cryptoKey,
        encodedText
    );

    const bytes = new Uint8Array(encryptedBuffer);
    let binaryStr = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binaryStr += String.fromCharCode(bytes[i]);
    }
    return btoa(binaryStr);
}

/**
 * Реактивная подсистема аутентификации PyFerro (по аналогии с pb.authStore).
 * Совместима с Svelte ($auth), React, Vue и Vanilla JS.
 */
export class AuthStore<TUser extends AuthUser = AuthUser> {
    private rpcClient: BinaryWSRPC<TUser>;

    // Реактивные хранилища состояния
    public readonly userStore = new SimpleStore<TUser | null>(null);
    public readonly tokenStore = new SimpleStore<string | null>(null);
    public readonly jwtTokenStore = new SimpleStore<string | null>(null);
    public readonly isLoadingStore = new SimpleStore<boolean>(false);

    // Промис инициализации сессии (для Session Gatekeeper)
    private initPromise: Promise<boolean> | null = null;

    constructor(rpcClient: BinaryWSRPC<TUser>) {
        this.rpcClient = rpcClient;

        // Если в браузере уже есть токен в localStorage или cookies, инициализируем tokenStore
        if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
            const savedToken = localStorage.getItem('refresh_token') || getAuthCookie('ferro_session');
            if (savedToken) {
                this.tokenStore.set(savedToken);
            }
        }
    }

    /** Текущий авторизованный пользователь или null */
    get user(): TUser | null {
        return this.userStore.get();
    }

    /** Текущий refresh/session токен */
    get token(): string | null {
        return this.tokenStore.get();
    }

    /** Текущий JWT токен для REST/HTTP запросов */
    get jwtToken(): string | null {
        return this.jwtTokenStore.get();
    }

    /** Флаг валидности сессии (пользователь успешно авторизован) */
    get isValid(): boolean {
        return this.userStore.get() !== null;
    }

    /** Флаг процесса первоначальной инициализации сессии */
    get isLoading(): boolean {
        return this.isLoadingStore.get();
    }

    /**
     * Поддержка Svelte store contract ($auth)
     */
    subscribe(fn: (user: TUser | null) => void): () => void {
        return this.userStore.subscribe(fn);
    }

    /**
     * Удобный алиас для подписки на смену пользователя
     */
    onChange(fn: (user: TUser | null) => void): () => void {
        return this.subscribe(fn);
    }

    /**
     * Гарантирует, что проверка сессии завершена перед выполнением бизнес-RPC (Gatekeeper).
     */
    async ensureInitialized(): Promise<boolean> {
        if (!this.initPromise) {
            this.initPromise = this.restoreSession();
        }
        return this.initPromise;
    }

    /**
     * Вход по логину и паролю (стандартный login.submit с авто-фоллбэком на auth.login).
     */
    async login(credentials: LoginCredentials, options?: LoginOptions): Promise<TUser> {
        const userAgent = credentials.user_agent || options?.user_agent || (typeof navigator !== 'undefined' ? navigator.userAgent : 'wsrpc-client');
        const primaryMethod = options?.method || 'login.submit';

        try {
            const res: any = await this.rpcClient.call(primaryMethod, {
                username: credentials.username,
                password: credentials.password,
                user_agent: userAgent,
                ...(options?.extraParams || {})
            });
            return this.applyAuthSuccess(res);
        } catch (err: any) {
            // Если метод login.submit не найден (-32601), пробуем fallback на auth.login
            if (err?.code === -32601 && primaryMethod === 'login.submit') {
                try {
                    const fallbackRes: any = await this.rpcClient.call('auth.login', {
                        username: credentials.username,
                        password: credentials.password,
                        user_agent: userAgent,
                        ...(options?.extraParams || {})
                    });
                    return this.applyAuthSuccess(fallbackRes);
                } catch (fallbackErr: any) {
                    this.clear();
                    throw new Error(fallbackErr.message || 'Неверный логин или пароль');
                }
            }
            this.clear();
            throw new Error(err.message || 'Неверный логин или пароль');
        }
    }

    /**
     * Безопасный вход с RSA-шифрованием пароля (login.get_key + login.secure).
     */
    async loginSecure(credentials: LoginCredentials, options?: LoginOptions): Promise<TUser> {
        try {
            // 1. Получаем эфемерный открытый ключ RSA от сервера
            const keyRes: any = await this.rpcClient.call('login.get_key', {});
            if (!keyRes || !keyRes.public_key || !keyRes.key_id) {
                throw new Error('Сервер не вернул публичный ключ RSA для безопасного входа');
            }

            // 2. Шифруем пароль через нативный Web Crypto API (RSA-OAEP SHA-256)
            const encryptedPassword = await encryptPasswordRsa(keyRes.public_key, credentials.password);

            // 3. Вызываем защищенный RPC-метод
            const userAgent = credentials.user_agent || options?.user_agent || (typeof navigator !== 'undefined' ? navigator.userAgent : 'wsrpc-client');
            const res: any = await this.rpcClient.call('login.secure', {
                username: credentials.username,
                encrypted_password: encryptedPassword,
                key_id: keyRes.key_id,
                user_agent: userAgent,
                ...(options?.extraParams || {})
            });

            return this.applyAuthSuccess(res);
        } catch (err: any) {
            this.clear();
            throw new Error(err.message || 'Ошибка безопасного входа');
        }
    }

    /**
     * Восстановление сессии при старте приложения или перезагрузке страницы.
     */
    async restoreSession(): Promise<boolean> {
        this.isLoadingStore.set(true);
        try {
            // 1. Сначала проверяем login.whoami / auth.me (если сработал auto_auth_ws по Cookie)
            try {
                let whoami: any = null;
                try {
                    whoami = await this.rpcClient.call('login.whoami', {});
                } catch (e: any) {
                    if (e?.code === -32601) {
                        whoami = await this.rpcClient.call('auth.me', {});
                    }
                }

                if (whoami && (whoami.authenticated || whoami.user_id)) {
                    const userObj = this.normalizeUser(whoami);
                    this.userStore.set(userObj);
                    return true;
                }
            } catch {
                // Игнорируем: сокет в статусе гостя
            }

            // 2. Если whoami не авторизован, проверяем refresh_token в localStorage или Cookie
            let savedToken: string | null = null;
            if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
                savedToken = localStorage.getItem('refresh_token') || getAuthCookie('ferro_session');
            }

            if (savedToken) {
                try {
                    const userAgent = typeof navigator !== 'undefined' ? navigator.userAgent : 'wsrpc-client';
                    const refreshed: any = await this.rpcClient.call('login.refresh', {
                        token: savedToken,
                        user_agent: userAgent
                    });

                    if (refreshed && (refreshed.username || refreshed.user_id)) {
                        this.applyAuthSuccess(refreshed);
                        return true;
                    }
                } catch (err) {
                    console.warn('[WSRPC Auth] Токен сессии устарел или недействителен, очищаем:', err);
                    this.clear();
                }
            }

            this.clear();
            return false;
        } finally {
            this.isLoadingStore.set(false);
        }
    }

    /**
     * Синхронизация сессии при физическом переподключении сокета.
     */
    async syncOnReconnect(): Promise<void> {
        if (this.isValid) {
            try {
                let whoami: any = null;
                try {
                    whoami = await this.rpcClient.call('login.whoami', {});
                } catch (e: any) {
                    if (e?.code === -32601) {
                        whoami = await this.rpcClient.call('auth.me', {});
                    }
                }

                if (!whoami || !whoami.authenticated) {
                    // Cookie не подхватился автоматически — восстанавливаем по токену
                    await this.restoreSession();
                }
            } catch (err) {
                console.error('[WSRPC Auth] Ошибка синхронизации сессии при реконнекте:', err);
            }
        }
    }

    /**
     * Выход из учетной записи с отзывом сессии на сервере и очисткой на клиенте.
     */
    async logout(): Promise<void> {
        try {
            const token = this.token;
            try {
                await this.rpcClient.call('auth.logout', { token });
            } catch (e: any) {
                if (e?.code === -32601) {
                    await this.rpcClient.call('login.logout', { token });
                }
            }
        } catch {
            // Игнорируем сетевые сбои при логауте
        } finally {
            this.clear();
        }
    }

    /**
     * Полная локальная очистка учетных данных и Cookies.
     */
    clear(): void {
        this.userStore.set(null);
        this.tokenStore.set(null);
        this.jwtTokenStore.set(null);
        this.initPromise = null;

        if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
            localStorage.removeItem('refresh_token');
        }
        deleteAuthCookie('ferro_session');
        deleteAuthCookie('ferro_crud_session');
        deleteAuthCookie('rpc_jwt');
    }

    /**
     * Унифицированная нормализация объекта пользователя под стандартные UI-соглашения.
     * Гарантирует наличие алиасов id, uid, user_id, avatar, photo_url и nullable email.
     */
    public normalizeUser(res: any): TUser {
        const id = res.user_id ?? res.id ?? res.uid ?? res.username;
        return {
            id,
            uid: res.user_id ?? res.uid ?? id,
            user_id: res.user_id ?? res.uid ?? id,
            avatar: res.photo_url || res.avatar || null,
            photo_url: res.photo_url || res.avatar || null,
            username: res.username || res.login || 'user',
            role: res.role || (res.roles && res.roles[0]) || 'user',
            roles: res.roles || (res.role ? [res.role] : ['user']),
            name: res.name || res.username || res.login,
            email: res.email ?? null,
            permissions: res.permissions || {},
            is_superadmin: Boolean(res.is_superadmin),
            authenticated: res.authenticated !== undefined ? Boolean(res.authenticated) : Boolean(id),
            ...res
        } as TUser;
    }

    /**
     * Применение результата успешной авторизации (стандартный вход, OAuth, SSO, Telegram, Passkeys).
     * Сохраняет токены, атомарно обновляет Cookies и реактивные сторы.
     */
    public setSession(res: any): TUser {
        return this.applyAuthSuccess(res);
    }

    /**
     * Обработчик успешного ответа сервера с данными авторизации.
     * Сохраняет токены, атомарно обновляет Cookies и реактивные сторы.
     */
    public applyAuthSuccess(res: any): TUser {
        const userObj = this.normalizeUser(res);

        this.userStore.set(userObj);

        const token = res.token;
        const jwt = res.jwt_token || res.jwt;
        if (token) {
            this.tokenStore.set(token);
            setAuthCookie('ferro_session', token, 2592000);      // 30 дней для сокета и HTTP
            setAuthCookie('ferro_crud_session', jwt || token, 2592000); // 30 дней для панели /crud (JWT гарантирует Zero-Leakage 404 валидацию)
            if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
                localStorage.setItem('refresh_token', token);
            }
        }

        if (jwt) {
            this.jwtTokenStore.set(jwt);
            setAuthCookie('rpc_jwt', jwt, 86400); // 24 часа для REST / uploads
            if (!token) {
                setAuthCookie('ferro_crud_session', jwt, 86400);
            }
        }

        return userObj;
    }
}

// Описание структуры для отслеживания ожидающих ответа RPC-запросов (Promises)
interface PendingRequest {
    resolve: (value: any) => void;
    reject: (reason: any) => void;
    timeoutId: number; // ID таймера ожидания таймаута
}

/**
 * Определение адреса WebSocket для подключения (системный стандарт /ws)
 */
export function getWsUrl(): string {
    if (typeof window !== 'undefined') {
        if ((window as any).__WSRPC_URL__) {
            return (window as any).__WSRPC_URL__;
        }
        const isHttps = window.location.protocol === 'https:';
        const wsProto = isHttps ? 'wss:' : 'ws:';
        
        // Локальная разработка через Vite dev-сервер (5173/4173): бэкенд Granian на порту 8080
        if (['5173', '4173'].includes(window.location.port)) {
            const host = window.location.hostname || '127.0.0.1';
            const url = `ws://${host}:8080/ws`;
            console.info(`[WSRPC getWsUrl] Vite dev server detected -> ${url}`);
            return url;
        }
        
        // Системный стандарт /ws: единообразно для HTTP, HTTPS и Nginx
        const url = `${wsProto}//${window.location.host}/ws`;
        console.info(`[WSRPC getWsUrl] Connection -> ${url}`);
        return url;
    }
    return 'ws://127.0.0.1:8080/ws';
}

/**
 * Реактивный JSON-RPC 2.0 клиент на Svelte 5 (BinaryWSRPC).
 * Обеспечивает полную обратную совместимость с интерфейсом старого wsrpc.ts.
 */
/**
 * WSRPC Tabular Payload Decompression (RFC 0002).
 * Автоматически распаковывает компактный табличный формат {$tabular: true, fields: [...], rows: [...]}
 * в плоские JavaScript-объекты. Рекурсивно обрабатывает списки и словари.
 */
export function unpackTabular(data: any): any {
    if (!data || typeof data !== "object") return data;

    if (data.$tabular === true && Array.isArray(data.fields) && Array.isArray(data.rows)) {
        const fields = data.fields;
        const items = data.rows.map((row: any[]) => {
            const obj: Record<string, any> = {};
            for (let i = 0; i < fields.length; i++) {
                obj[fields[i]] = row[i];
            }
            return obj;
        });

        const extraKeys = Object.keys(data).filter(k => k !== '$tabular' && k !== 'fields' && k !== 'rows');
        if (extraKeys.length === 0) {
            return items;
        }

        return { ...data, items };
    }

    if (Array.isArray(data)) {
        return data.map(item => unpackTabular(item));
    }

    const res: Record<string, any> = {};
    for (const key of Object.keys(data)) {
        res[key] = unpackTabular(data[key]);
    }
    return res;
}

/**
 * WSRPC Tabular Payload Compression (RFC 0002).
 * Упаковывает массив объектов в компактный табличный формат {$tabular: true, fields: [...], rows: [...]}.
 */
export function packTabular(items: any[], fields?: string[]): any {
    if (!items || !items.length) {
        return { $tabular: true, fields: fields || [], rows: [] };
    }
    const resolvedFields = fields || Object.keys(items[0]);
    const rows = items.map((item) => resolvedFields.map((f) => item[f]));
    return {
        $tabular: true,
        fields: resolvedFields,
        rows
    };
}

export class BinaryWSRPC<TUser extends AuthUser = AuthUser> {
    // Статус подключения
    public status: 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' = 'DISCONNECTED';
    // Настройка времени переподключения (в секундах). 0 - отключить автореконнект.
    public reconnectWs = 3;

    // Встроенная подсистема аутентификации (Zero-Boilerplate AuthStore)
    public readonly auth: AuthStore<TUser>;

    private ws: WebSocket | null = null;
    private idCounter = 0; // Инкрементальный счетчик ID для JSON-RPC запросов
    
    // Хранилище Promises для ожидающих ответа запросов (ID -> PendingRequest)
    private pendingRequests = new Map<number | string, PendingRequest>();
    
    // Реестр зарегистрированных на клиенте методов, которые может вызывать сервер (симметричный RPC)
    private serverMethods = new Map<string, (params: any) => Promise<any>>();
    
    // Реестр активных подписок на стримы (ID -> колбэк для чанков данных)
    private streamListeners = new Map<number | string, (data: any) => void>();
 
    private url = '';
    private reconnectTimerId: number | null = null;
    private isIntentionallyClosed = false; // Флаг ручного закрытия (чтобы не запускать реконнект)
 
    // Коллбеки для совместимости со старой кодовой базой
    private connectingPromise: Promise<void> | null = null;
    public onConnect: (() => void) | null = null; // Вызывается при каждом успешном коннекте
    public onStatusChange: ((connected: boolean) => void) | null = null; // Вызывается при изменении состояния сети (true/false)

    // Системный шлюз авторизации сессии (Gatekeeper): гарантирует авторизацию сессии на сокете до отправки бизнес-запросов
    public authInterceptor: (() => Promise<any>) | null = null;
 
    constructor(url?: string) {
        this.url = url || getWsUrl();
        this.auth = new AuthStore<TUser>(this);
        if (isBrowser) {
            console.log('[WSRPC] Клиент WSRPC инициализирован для URL:', this.url);
        }
    }
 
    /**
     * Установка соединения с WebSocket-сервером.
     * Возвращает Promise, который разрешается при успешном подключении (onopen).
     */
    connect(url?: string): Promise<void> {
        if (!isBrowser) return Promise.resolve();
        if (this.status === 'CONNECTED' && this.ws && this.ws.readyState === WebSocket.OPEN) {
            return Promise.resolve();
        }
        if (this.connectingPromise) {
            return this.connectingPromise;
        }
        if (url) {
            this.url = url;
        }
        
        this.isIntentionallyClosed = false;
        this.status = 'CONNECTING';
        wsStatus.set('CONNECTING');
        wsConnected.set(false);
 
        console.info(`[WSRPC] Подключение к ${this.url}...`);
 
        this.connectingPromise = new Promise((resolve, reject) => {
            // Создаем таймер таймаута соединения (5 секунд)
            const connectionTimeout = window.setTimeout(() => {
                if (this.status === 'CONNECTING') {
                    console.warn(`[WSRPC] ⏰ Превышен таймаут подключения к ${this.url}`);
                    this.status = 'DISCONNECTED';
                    this.connectingPromise = null;
                    if (this.onStatusChange) this.onStatusChange(false);
                    if (this.ws) {
                        this.ws.onopen = null;
                        this.ws.onmessage = null;
                        this.ws.onclose = null;
                        this.ws.onerror = null;
                        this.ws.close();
                        this.ws = null;
                    }
                    reject(new Error('WebSocket connection timeout'));
                }
            }, 5000);

            try {
                this.ws = new WebSocket(this.url);
            } catch (err) {
                clearTimeout(connectionTimeout);
                this.status = 'DISCONNECTED';
                this.connectingPromise = null;
                if (this.onStatusChange) this.onStatusChange(false);
                reject(err);
                return;
            }
 
            this.ws.onopen = () => {
                clearTimeout(connectionTimeout);
                this.connectingPromise = null;
                console.info('[WSRPC] ✅ Соединение с сервером установлено.');
                this.status = 'CONNECTED';
                wsStatus.set('CONNECTED');
                wsConnected.set(true);
 
                // Оповещаем UI о подключении
                if (this.onStatusChange) this.onStatusChange(true);
 
                // Очищаем таймер переподключения
                if (this.reconnectTimerId) {
                    clearTimeout(this.reconnectTimerId);
                    this.reconnectTimerId = null;
                }
 
                // Вызываем триггер на подключение
                if (this.onConnect) this.onConnect();

                // Фоновая синхронизация сессии пользователя при подключении/переподключении
                if (this.auth) {
                    if (this.auth.isValid) {
                        this.auth.syncOnReconnect().catch((err) => {
                            console.warn('[WSRPC] Ошибка авто-синхронизации сессии при реконнекте:', err);
                        });
                    } else if (this.auth.token || (typeof document !== 'undefined' && (getAuthCookie('ferro_session') || getAuthCookie('ferro_crud_session')))) {
                        this.auth.restoreSession().catch((err) => {
                            console.warn('[WSRPC] Ошибка авто-восстановления сессии при подключении:', err);
                        });
                    }
                }
                
                resolve();
            };
 
            this.ws.onmessage = async (event: MessageEvent) => {
                console.debug('[WSRPC] ⬇️ Входящий пакет:', event.data);
                try {
                    const data = JSON.parse(event.data);
                    await this.handleIncomingMessage(data);
                } catch (err) {
                    console.error('[WSRPC] ❌ Ошибка парсинга входящего JSON:', err);
                }
            };
 
            this.ws.onclose = (event) => {
                clearTimeout(connectionTimeout);
                this.connectingPromise = null;
                this.status = 'DISCONNECTED';
                wsStatus.set('DISCONNECTED');
                wsConnected.set(false);
                
                if (this.onStatusChange) this.onStatusChange(false);
                
                // Отклоняем промис подключения, если оно завершилось до открытия (onopen)
                reject(new Error(`WebSocket connection closed (code: ${event.code})`));

                // Отклоняем все зависшие RPC-запросы
                this.cleanup(new Error('WebSocket disconnected'));
 
                // Запускаем авто-реконнект, если сокет не закрыт вручную и он включен
                if (!this.isIntentionallyClosed && this.reconnectWs > 0) {
                    console.warn(`[WSRPC] 🔌 Соединение потеряно (код: ${event.code}). Реконнект через ${this.reconnectWs} сек...`);
                    if (!this.reconnectTimerId) {
                        this.reconnectTimerId = window.setTimeout(() => {
                            this.reconnectTimerId = null;
                            this.connect();
                        }, this.reconnectWs * 1000);
                    }
                }
            };
 
            this.ws.onerror = (error) => {
                clearTimeout(connectionTimeout);
                this.connectingPromise = null;
                console.error('[WSRPC] 🚨 Ошибка сокета:', error);
                reject(error);
            };
        });
        return this.connectingPromise;
    }

    /** 
     * Принудительное закрытие соединения 
     */
    disconnect() {
        this.isIntentionallyClosed = true;
        if (this.ws) {
            this.ws.close();
        }
    }

    /**
     * Регистрация клиентского метода для вызова сервером (совместимость со старым wsrpc.ts)
     * Поддерживает передачу позиционных (массив) и именованных (объект) аргументов.
     */
    register(rpcName: string, handlerFunc: Function) {
        this.serverMethods.set(rpcName, async (params) => {
            if (Array.isArray(params)) {
                return handlerFunc(...params); // Раскрываем массив аргументов
            }
            return handlerFunc(params); // Передаем объект
        });
    }

    /**
     * Алиас для register (декларативное имя)
     */
    registerMethod(rpcName: string, handlerFunc: Function) {
        this.register(rpcName, handlerFunc);
    }

    /**
     * Подписка на событие / нотификацию от сервера с возвратом функции отписки
     */
    on(event: string, handler: (data: any) => void): () => void {
        console.info(`[WSRPC] 📡 rpc.on("${event}") зарегистрирован`);
        this.register(event, (params: any) => {
            console.info(`[WSRPC] ⚡ Событие "${event}" получено:`, params);
            return handler(params);
        });
        return () => {
            console.info(`[WSRPC] 🔕 rpc.on("${event}") отписка`);
            this.serverMethods.delete(event);
        };
    }

    /**
     * Отправка запроса к серверу. Возвращает Promise с результатом.
     */
    async request(method: string, params: any = {}, timeoutMs = 15000): Promise<any> {
        if (this.status !== 'CONNECTED' || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            try {
                console.info(`[WSRPC] request("${method}") ожидает подключения...`);
                await this.connect();
            } catch (err) {
                console.error(`[WSRPC] request("${method}") ошибка авто-подключения:`, err);
                return Promise.reject(err);
            }
        }


        // Системный шлюз (Gatekeeper): гарантирует авторизацию сессии на сокете до выполнения бизнес-запросов
        const isBypassMethod = method.startsWith("login.") || method.startsWith("system.") || method.startsWith("auth.");
        if (!isBypassMethod) {
            if (this.authInterceptor) {
                try {
                    await this.authInterceptor();
                } catch (authErr) {
                    console.warn("[WSRPC Gatekeeper] Ошибка ожидания пользовательского authInterceptor:", authErr);
                }
            } else if (this.auth) {
                try {
                    await this.auth.ensureInitialized();
                } catch (authErr) {
                    console.warn("[WSRPC Gatekeeper] Ошибка ожидания инициализации сессии:", authErr);
                }
            }
        }

        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                return reject(new Error('WSRPC: Not connected to server'));
            }

            const rpcId = this.idCounter++;
            const payload = { jsonrpc: '2.0', method, params, id: rpcId };
            console.debug(`[WSRPC] ⬆️ Запрос [ID: ${rpcId}] -> "${method}":`, params);

            // Таймер таймаута для предотвращения утечки промисов
            const timeoutId = window.setTimeout(() => {
                console.warn(`[WSRPC] ⏰ Таймаут запроса [ID: ${rpcId}] -> "${method}"`);
                const pending = this.pendingRequests.get(rpcId);
                if (pending) {
                    pending.reject(new Error(`Timeout for ${method}`));
                    this.pendingRequests.delete(rpcId);
                }
            }, timeoutMs);

            this.pendingRequests.set(rpcId, { resolve, reject, timeoutId });
            this.ws.send(JSON.stringify(payload));
        });
    }

    /**
     * Совместимость со старым rpc.call
     */
    call<T = any>(
        rpcName: string,
        args: any = {},
        timeoutOrOptions: number | { timeoutMs?: number; onChunk?: (chunk: any) => void } = 15000
    ): Promise<T> {
        if (typeof timeoutOrOptions === 'object' && timeoutOrOptions !== null) {
            if (timeoutOrOptions.onChunk) {
                return this.callStream(rpcName, args, timeoutOrOptions.onChunk, timeoutOrOptions.timeoutMs || 60000);
            }
            return this.request(rpcName, args, timeoutOrOptions.timeoutMs || 15000);
        }
        return this.request(rpcName, args, typeof timeoutOrOptions === 'number' ? timeoutOrOptions : 15000);
    }

    /**
     * Вызов метода со стримингом прогресса (мультиретурн).
     * Вызывает onChunkCallback для каждого промежуточного чанка (stream: true)
     * и возвращает Promise, который резолвится финальным результатом операции.
     */
    async callStream<T = any>(
        rpcName: string,
        args: any = {},
        onChunkCallback?: (chunk: any) => void,
        timeoutMs = 60000
    ): Promise<T> {
        if (this.status !== 'CONNECTED' || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            try {
                await this.connect();
            } catch (err) {
                return Promise.reject(err);
            }
        }


        // Системный шлюз (Gatekeeper) для потоковых запросов
        const isBypassMethod = rpcName.startsWith("login.") || rpcName.startsWith("system.") || rpcName.startsWith("auth.");
        if (!isBypassMethod && this.authInterceptor) {
            try {
                await this.authInterceptor();
            } catch (authErr) {
                console.warn("[WSRPC Gatekeeper] Ошибка ожидания авторизации сессии (stream):", authErr);
            }
        }

        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                return reject(new Error('WSRPC: Not connected to server'));
            }

            const rpcId = this.idCounter++;
            const payload = { jsonrpc: '2.0', method: rpcName, params: args, id: rpcId };

            if (onChunkCallback) {
                this.streamListeners.set(rpcId, onChunkCallback);
            }

            const timeoutId = window.setTimeout(() => {
                console.warn(`[WSRPC] ⏰ Таймаут стрим-запроса [ID: ${rpcId}] -> "${rpcName}"`);
                const pending = this.pendingRequests.get(rpcId);
                if (pending) {
                    pending.reject(new Error(`Timeout for ${rpcName}`));
                    this.pendingRequests.delete(rpcId);
                    this.streamListeners.delete(rpcId);
                }
            }, timeoutMs);

            this.pendingRequests.set(rpcId, { resolve, reject, timeoutId });
            this.ws.send(JSON.stringify(payload));
        });
    }

    /**
     * Подписка на стрим (совместимость со старым rpc.subscribeStream в wsrpc.ts).
     * Сервер будет присылать пакеты с результатом, помеченным как {"stream": true}.
     */
    subscribeStream(rpcName: string, args: any = {}, onChunkCallback: (data: any) => void) {
        if (!this.ws || this.status !== 'CONNECTED') {
            throw new Error('WSRPC: Not connected to server');
        }

        const rpcId = this.idCounter++;
        const payload = { jsonrpc: '2.0', method: rpcName, params: args, id: rpcId };

        this.streamListeners.set(rpcId, onChunkCallback);
        this.ws.send(JSON.stringify(payload));

        // Возвращаем функцию отписки
        return () => {
            this.streamListeners.delete(rpcId);
        };
    }

    /**
     * Обработка всех входящих сообщений
     */
    private async handleIncomingMessage(data: any) {
        const rpcId = data.id;

        // 1. Проверяем, не является ли ответ чанком стрима (stream: true)
        if (rpcId !== undefined && data.result && data.result.stream) {
            const listener = this.streamListeners.get(rpcId);
            if (listener) {
                listener(unpackTabular(data.result.data));
                return;
            }
        }

        // 2. Стандартный ответ сервера на наш запрос (содержит result или error)
        if (rpcId !== undefined && ('result' in data || 'error' in data)) {
            const pending = this.pendingRequests.get(rpcId);
            if (!pending) return;
            clearTimeout(pending.timeoutId);
            this.pendingRequests.delete(rpcId);
            this.streamListeners.delete(rpcId);

            if ('error' in data) {
                const errMsg = typeof data.error === 'object' && data.error !== null 
                    ? (data.error.message || JSON.stringify(data.error)) 
                    : String(data.error);
                console.warn(`[WSRPC] ❌ Ошибка от сервера [ID: ${rpcId}]:`, errMsg);
                const err = new Error(errMsg);
                (err as any).code = data.error?.code;
                (err as any).data = data.error?.data;
                pending.reject(err);
            } else {
                console.debug(`[WSRPC] ✅ Ответ сервера [ID: ${rpcId}]:`, data.result);
                pending.resolve(unpackTabular(data.result));
            }
            return;
        }

        // 3. Запрос от сервера к нам (симметричный RPC)
        if ('method' in data) {
            const method = data.method;
            console.info(`[WSRPC] 📥 Входящий вызов/нотификация от сервера: "${method}"`, data.params);
            const handler = this.serverMethods.get(method);
            if (!handler) {
                if (rpcId !== null && rpcId !== undefined) {
                    this.sendRaw({ 
                        jsonrpc: '2.0', 
                        error: { code: -32601, message: `Method '${method}' not found` }, 
                        id: rpcId 
                    });
                }
                return;
            }
            try {
                const result = await handler(unpackTabular(data.params || {}));
                if (rpcId !== null && rpcId !== undefined) {
                    this.sendRaw({ jsonrpc: '2.0', result, id: rpcId });
                }
            } catch (err: any) {
                if (rpcId !== null && rpcId !== undefined) {
                    this.sendRaw({ 
                        jsonrpc: '2.0', 
                        error: { code: -32603, message: err.message || String(err) }, 
                        id: rpcId 
                    });
                }
            }
        }
    }

    /**
     * Отправка сырого сообщения в вебсокет
     */
    private sendRaw(payload: any) {
        if (this.ws && this.status === 'CONNECTED') {
            this.ws.send(JSON.stringify(payload));
        }
    }

    /**
     * Очистка реестра ожидающих промисов при разрыве соединения
     */
    private cleanup(error: Error) {
        for (const pending of this.pendingRequests.values()) {
            clearTimeout(pending.timeoutId);
            pending.reject(error);
        }
        this.pendingRequests.clear();
        this.streamListeners.clear();
    }
}

// Глобальный синглтон-клиент WSRPC и реактивная подсистема аутентификации
export const rpc = new BinaryWSRPC();
export const auth = rpc.auth;
export default rpc;
