/**
 * Клиентский SDK JSON-RPC 2.0 и движок Offline-First (IndexedDB) для PyFerro 2.0.
 *
 * Все прикладные данные, ответы методов (rpc_cache), бинарные медиафайлы (files_cache),
 * очередь оффлайн-мутаций (rpc_outbox) и системные метаданные (sys_meta)
 * хранятся в единой базе IndexedDB `pyferro2_storage`.
 */

const IDB_NAME = "pyferro2_storage";
const IDB_VERSION = 1;
const TOKEN_FALLBACK_KEY = "pyferro2_token";

let _memoryToken =
  typeof localStorage !== "undefined" ? localStorage.getItem(TOKEN_FALLBACK_KEY) || "" : "";

const _MEDIA_URL_RE = /(\/(?:files\/[A-Za-z0-9_-]+|images)\/[^\s"'<>)\]]+)/g;

/**
 * Асинхронный менеджер единой базы данных IndexedDB (`pyferro2_storage`).
 */
class PyFerroIndexedDB {
  constructor() {
    this.dbPromise = null;
  }

  open() {
    if (typeof indexedDB === "undefined") {
      return Promise.resolve(null);
    }
    if (this.dbPromise) return this.dbPromise;

    this.dbPromise = new Promise((resolve) => {
      try {
        const req = indexedDB.open(IDB_NAME, IDB_VERSION);
        req.onupgradeneeded = (ev) => {
          const db = ev.target.result;
          if (!db.objectStoreNames.contains("sys_meta")) {
            db.createObjectStore("sys_meta", { keyPath: "key" });
          }
          if (!db.objectStoreNames.contains("rpc_cache")) {
            const rpcStore = db.createObjectStore("rpc_cache", { keyPath: "cacheKey" });
            rpcStore.createIndex("by_method", "method", { unique: false });
            rpcStore.createIndex("by_scope", "scope", { unique: false });
            rpcStore.createIndex("by_updated_at", "updatedAt", { unique: false });
          }
          if (!db.objectStoreNames.contains("files_cache")) {
            const fileStore = db.createObjectStore("files_cache", { keyPath: "url" });
            fileStore.createIndex("by_last_accessed", "lastAccessed", { unique: false });
          }
          if (!db.objectStoreNames.contains("rpc_outbox")) {
            db.createObjectStore("rpc_outbox", { keyPath: "id", autoIncrement: true });
          }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
    return this.dbPromise;
  }

  async getMeta(key) {
    const db = await this.open();
    if (!db) return null;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("sys_meta", "readonly");
        const req = tx.objectStore("sys_meta").get(key);
        req.onsuccess = () => resolve(req.result ? req.result.value : null);
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  async setMeta(key, value) {
    const db = await this.open();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("sys_meta", "readwrite");
        tx.objectStore("sys_meta").put({ key, value, updatedAt: Date.now() });
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async getRpcCache(cacheKey) {
    const db = await this.open();
    if (!db) return null;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_cache", "readonly");
        const req = tx.objectStore("rpc_cache").get(cacheKey);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  async putRpcCache(entry, maxEntries = 2000) {
    const db = await this.open();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_cache", "readwrite");
        const store = tx.objectStore("rpc_cache");
        store.put(entry);

        const countReq = store.count();
        countReq.onsuccess = () => {
          const total = countReq.result;
          if (total > maxEntries) {
            const toDelete = total - maxEntries;
            let deleted = 0;
            const idx = store.index("by_updated_at");
            const cursorReq = idx.openCursor();
            cursorReq.onsuccess = (ev) => {
              const cursor = ev.target.result;
              if (cursor && deleted < toDelete) {
                cursor.delete();
                deleted++;
                cursor.continue();
              }
            };
          }
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async invalidateMethods(methods) {
    const db = await this.open();
    if (!db || !Array.isArray(methods) || methods.length === 0) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_cache", "readwrite");
        const store = tx.objectStore("rpc_cache");
        const idx = store.index("by_method");
        for (const m of methods) {
          const cursorReq = idx.openCursor(IDBKeyRange.only(m));
          cursorReq.onsuccess = (ev) => {
            const cursor = ev.target.result;
            if (cursor) {
              const val = cursor.value;
              // Помечаем запись как требующую ревалидации (expiresAt = 0), но сохраняем данные для оффлайна
              val.expiresAt = 0;
              cursor.update(val);
              cursor.continue();
            }
          };
        }
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async clearUserScopeCache() {
    const db = await this.open();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(["rpc_cache", "rpc_outbox"], "readwrite");
        const store = tx.objectStore("rpc_cache");
        const idx = store.index("by_scope");
        const cursorReq = idx.openCursor(IDBKeyRange.only("user"));
        cursorReq.onsuccess = (ev) => {
          const cursor = ev.target.result;
          if (cursor) {
            cursor.delete();
            cursor.continue();
          }
        };
        tx.objectStore("rpc_outbox").clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async clearAllRpcCache() {
    const db = await this.open();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_cache", "readwrite");
        tx.objectStore("rpc_cache").clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async hasFile(url) {
    const db = await this.open();
    if (!db) return false;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("files_cache", "readonly");
        const req = tx.objectStore("files_cache").getKey(url);
        req.onsuccess = () => resolve(req.result !== undefined);
        req.onerror = () => resolve(false);
      } catch {
        resolve(false);
      }
    });
  }

  async getFile(url) {
    const db = await this.open();
    if (!db) return null;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("files_cache", "readwrite");
        const store = tx.objectStore("files_cache");
        const req = store.get(url);
        req.onsuccess = () => {
          const rec = req.result;
          if (rec) {
            rec.lastAccessed = Date.now();
            store.put(rec);
          }
          resolve(rec || null);
        };
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  async putFile(url, blob, mimeType, maxMediaMb = 250) {
    const db = await this.open();
    if (!db || !blob) return;
    const sizeBytes = blob.size || 0;
    const maxBytes = maxMediaMb * 1024 * 1024;

    return new Promise((resolve) => {
      try {
        const tx = db.transaction("files_cache", "readwrite");
        const store = tx.objectStore("files_cache");
        store.put({
          url,
          blob,
          mimeType: mimeType || blob.type || "application/octet-stream",
          sizeBytes,
          lastAccessed: Date.now(),
        });

        const idx = store.index("by_last_accessed");
        const allReq = idx.getAll();
        allReq.onsuccess = () => {
          const items = allReq.result || [];
          let totalBytes = items.reduce((acc, it) => acc + (it.sizeBytes || 0), 0);
          for (const it of items) {
            if (totalBytes <= maxBytes) break;
            store.delete(it.url);
            totalBytes -= it.sizeBytes || 0;
          }
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async enqueueOutbox(entry) {
    const db = await this.open();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_outbox", "readwrite");
        tx.objectStore("rpc_outbox").add(entry);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  async listOutbox() {
    const db = await this.open();
    if (!db) return [];
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_outbox", "readonly");
        const req = tx.objectStore("rpc_outbox").getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => resolve([]);
      } catch {
        resolve([]);
      }
    });
  }

  async removeOutbox(id) {
    const db = await this.open();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("rpc_outbox", "readwrite");
        tx.objectStore("rpc_outbox").delete(id);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }
}

export const idbStorage = new PyFerroIndexedDB();

// Инициализируем токен из IndexedDB при старте
if (typeof window !== "undefined") {
  idbStorage.getMeta("auth_token").then((tok) => {
    if (tok && !_memoryToken) {
      _memoryToken = tok;
    } else if (_memoryToken && !tok) {
      idbStorage.setMeta("auth_token", _memoryToken);
    }
  });
}

export function getStoredToken() {
  if (_memoryToken) return _memoryToken;
  if (typeof localStorage !== "undefined") {
    return localStorage.getItem(TOKEN_FALLBACK_KEY) || "";
  }
  return "";
}

export function setStoredToken(token) {
  _memoryToken = token || "";
  if (typeof localStorage !== "undefined") {
    if (token) {
      localStorage.setItem(TOKEN_FALLBACK_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_FALLBACK_KEY);
    }
  }
  idbStorage.setMeta("auth_token", _memoryToken);
  if (!token) {
    idbStorage.clearUserScopeCache();
  }
}

/**
 * Прозрачно распаковывает пакеты Tabular Data Compression ($tabular: true)
 * обратно в объекты или массивы объектов на клиенте.
 */
export function unpackTabular(data) {
  if (!data || typeof data !== "object") return data;
  if (Array.isArray(data)) return data.map(unpackTabular);

  if (data.$tabular === true && Array.isArray(data.fields) && Array.isArray(data.rows)) {
    const fields = data.fields;
    const items = data.rows.map((row) => {
      const obj = {};
      for (let i = 0; i < fields.length; i++) {
        obj[fields[i]] = row[i];
      }
      return obj;
    });
    const extraKeys = Object.keys(data).filter(
      (k) => k !== "$tabular" && k !== "fields" && k !== "rows"
    );
    if (extraKeys.length === 0) return items;
    const res = {};
    for (const k of extraKeys) {
      res[k] = unpackTabular(data[k]);
    }
    res.items = items;
    return res;
  }

  const out = {};
  for (const [k, v] of Object.entries(data)) {
    out[k] = unpackTabular(v);
  }
  return out;
}

function canonicalParamsString(params) {
  if (!params || typeof params !== "object") return "{}";
  if (Array.isArray(params)) return JSON.stringify(params);
  const sortedKeys = Object.keys(params).sort();
  const obj = {};
  for (const k of sortedKeys) {
    obj[k] = params[k];
  }
  return JSON.stringify(obj);
}

function extractMediaUrls(data, outSet = new Set()) {
  if (!data) return outSet;
  if (typeof data === "string") {
    let m;
    _MEDIA_URL_RE.lastIndex = 0;
    while ((m = _MEDIA_URL_RE.exec(data)) !== null) {
      outSet.add(m[1]);
    }
    return outSet;
  }
  if (Array.isArray(data)) {
    for (const item of data) extractMediaUrls(item, outSet);
    return outSet;
  }
  if (typeof data === "object") {
    for (const val of Object.values(data)) {
      extractMediaUrls(val, outSet);
    }
  }
  return outSet;
}

function generateUuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

class RpcClient {
  constructor() {
    this.ws = null;
    this.seq = 1;
    this.pending = new Map();
    this.streams = new Map();
    this.inFlight = new Map();
    this.listeners = new Map();
    this.onPermissionDisconnect = null;
    this.manifest = {
      enabled: true,
      liefi_timeout_ms: 2500,
      max_media_mb: 250,
      max_rpc_entries: 2000,
      cache_epoch: 1,
      rules: {},
    };
    this._flushingOutbox = false;

    if (typeof window !== "undefined") {
      this._initCacheManifest();
      window.addEventListener("online", () => this.flushOutbox());
    }
  }

  async _initCacheManifest() {
    const saved = await idbStorage.getMeta("cache_manifest");
    if (saved && typeof saved === "object") {
      this.manifest = { ...this.manifest, ...saved };
    }
  }

  async applyCacheManifest(newManifest) {
    if (!newManifest || typeof newManifest !== "object") return;
    const prevEpoch = this.manifest.cache_epoch || 1;
    this.manifest = { ...this.manifest, ...newManifest };
    await idbStorage.setMeta("cache_manifest", this.manifest);

    if (newManifest.cache_epoch && newManifest.cache_epoch > prevEpoch) {
      await idbStorage.clearAllRpcCache();
    }

    if (this.manifest.enabled && this.manifest.rules) {
      for (const [methodName, rule] of Object.entries(this.manifest.rules)) {
        if (rule.p === 1 && rule.c === 1) {
          this.call(methodName, {}).catch(() => {});
        }
      }
    }
  }

  async prefetchMediaFromData(data) {
    if (typeof window === "undefined" || !this.manifest.enabled) return;
    const urls = extractMediaUrls(data);
    for (const url of urls) {
      try {
        const exists = await idbStorage.hasFile(url);
        if (exists) continue;
        const resp = await fetch(url);
        if (resp.ok) {
          const blob = await resp.blob();
          await idbStorage.putFile(
            url,
            blob,
            resp.headers.get("content-type") || blob.type,
            this.manifest.max_media_mb || 250
          );
        }
      } catch {
        // Игнорируем сетевые ошибки фоновой предзагрузки
      }
    }
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const token = getStoredToken();
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    this.ws = new WebSocket(`${proto}//${window.location.host}/ws${qs}`);

    this.ws.onopen = () => {
      this.flushOutbox();
    };

    this.ws.onmessage = (ev) => {
      if (ev.data === "pong") return;
      let packet;
      try {
        packet = JSON.parse(ev.data);
      } catch {
        return;
      }

      if (packet.method === "$cache.invalidate" && packet.params) {
        const methods = packet.params.methods || [];
        idbStorage.invalidateMethods(methods);
        this._emit("$cache.invalidate", packet.params);
        return;
      }

      if (packet.method === "$cache.config_updated" && packet.params) {
        this.applyCacheManifest(packet.params);
        this._emit("$cache.config_updated", packet.params);
        return;
      }

      if (packet.method === "$cache.purge" && packet.params) {
        this.manifest.cache_epoch = packet.params.cache_epoch || this.manifest.cache_epoch + 1;
        idbStorage.setMeta("cache_manifest", this.manifest);
        idbStorage.clearAllRpcCache();
        this._emit("$cache.purge", packet.params);
        return;
      }

      if (packet.method) {
        this._emit(packet.method, packet.params);
      }

      if (packet.id !== undefined && this.streams.has(packet.id)) {
        const handler = this.streams.get(packet.id);
        if (packet.error) {
          handler.onError?.(packet.error);
          this.streams.delete(packet.id);
        } else {
          handler.onItem?.(unpackTabular(packet.result));
        }
        return;
      }

      if (packet.id !== undefined && this.pending.has(packet.id)) {
        const { resolve, reject } = this.pending.get(packet.id);
        this.pending.delete(packet.id);
        if (packet.error) {
          reject(new Error(packet.error.message || "Ошибка RPC"));
        } else {
          resolve(packet);
        }
      }
    };

    this.ws.onclose = (ev) => {
      if (ev.code === 1008 || ev.code === 4001) {
        this.onPermissionDisconnect?.();
      }
    };
  }

  on(event, handler) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(handler);
    return () => {
      const set = this.listeners.get(event);
      if (set) set.delete(handler);
    };
  }

  _emit(event, data) {
    const set = this.listeners.get(event);
    if (set) {
      for (const fn of set) {
        try {
          fn(data);
        } catch {}
      }
    }
  }

  async _sendNetworkPacket(packet) {
    const token = getStoredToken();
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch("/rpc", {
      method: "POST",
      headers,
      body: JSON.stringify(packet),
    });

    const data = await res.json();
    if (data.error) {
      const err = new Error(data.error.message || "Ошибка RPC");
      err.code = data.error.code;
      throw err;
    }
    return data;
  }

  async flushOutbox() {
    if (this._flushingOutbox) return;
    if (typeof navigator !== "undefined" && navigator.onLine === false) return;
    this._flushingOutbox = true;
    try {
      const items = await idbStorage.listOutbox();
      for (const item of items) {
        try {
          await this._sendNetworkPacket({
            jsonrpc: "2.0",
            id: this.seq++,
            method: item.method,
            params: item.params,
            $idempotency_key: item.idempotencyKey,
          });
          await idbStorage.removeOutbox(item.id);
        } catch (err) {
          if (err && err.code) {
            await idbStorage.removeOutbox(item.id);
          } else {
            break;
          }
        }
      }
    } finally {
      this._flushingOutbox = false;
    }
  }

  stream(method, params, { onItem, onError, onDone } = {}) {
    this.connect();
    const id = this.seq++;
    this.streams.set(id, {
      onItem: (item) => {
        onItem?.(item);
        if (item && item.done) {
          this.streams.delete(id);
          onDone?.(item);
        }
      },
      onError: (err) => {
        this.streams.delete(id);
        onError?.(err);
      },
    });
    const send = () => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
      }
    };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      send();
    } else if (this.ws) {
      this.ws.addEventListener("open", send, { once: true });
    }
    return () => {
      this.streams.delete(id);
    };
  }

  async call(method, params = {}, options = {}) {
    const rule = this.manifest.enabled ? this.manifest.rules?.[method] : null;
    const isCacheable = Boolean(rule && rule.c === 1 && options.policy !== "network-only");
    const isOutboxAllowed = Boolean((rule && rule.o === 1) || options.queueIfOffline);
    const cacheKey = `${method}:${canonicalParamsString(params)}`;

    if (isCacheable && this.inFlight.has(cacheKey)) {
      return this.inFlight.get(cacheKey);
    }

    const execPromise = (async () => {
      let cached = null;
      if (isCacheable) {
        cached = await idbStorage.getRpcCache(cacheKey);
        if (cached && cached.epoch === this.manifest.cache_epoch) {
          if (rule.s === "ttl" && Date.now() < cached.expiresAt && options.policy !== "network-first") {
            return cached.data;
          }
          if (typeof navigator !== "undefined" && navigator.onLine === false) {
            return cached.data;
          }
        } else {
          cached = null;
        }
      }

      const reqPacket = {
        jsonrpc: "2.0",
        method,
        params,
        id: this.seq++,
      };
      if (cached && cached.etag) {
        reqPacket.$if_none_match = cached.etag;
      }
      if (isOutboxAllowed) {
        reqPacket.$idempotency_key = options.idempotencyKey || generateUuid();
      }

      const fetchAndProcess = async () => {
        const rawResp = await this._sendNetworkPacket(reqPacket);
        const cacheMeta = rawResp.$cache;

        if (rawResp.result && rawResp.result.$not_modified === true && cached) {
          const ttlMs = ((cacheMeta && cacheMeta.ttl) || rule?.t || 300) * 1000;
          cached.expiresAt = Date.now() + ttlMs;
          cached.updatedAt = Date.now();
          await idbStorage.putRpcCache(cached, this.manifest.max_rpc_entries || 2000);
          return cached.data;
        }

        const unpacked = unpackTabular(rawResp.result);

        if (method === "system.get_public_config" && unpacked && unpacked.cache_manifest) {
          this.applyCacheManifest(unpacked.cache_manifest);
        }

        if (isCacheable || cacheMeta) {
          const ttlMs = ((cacheMeta && cacheMeta.ttl) || rule?.t || 300) * 1000;
          const entry = {
            cacheKey,
            method,
            data: unpacked,
            etag: (cacheMeta && cacheMeta.etag) || "",
            scope: (cacheMeta && cacheMeta.scope) || "public",
            epoch: (cacheMeta && cacheMeta.epoch) || this.manifest.cache_epoch || 1,
            expiresAt: Date.now() + ttlMs,
            updatedAt: Date.now(),
          };
          await idbStorage.putRpcCache(entry, this.manifest.max_rpc_entries || 2000);

          if ((cacheMeta && cacheMeta.prefetch_media) || rule?.m === 1) {
            this.prefetchMediaFromData(unpacked);
          }
        }

        return unpacked;
      };

      try {
        if (cached && this.manifest.liefi_timeout_ms > 0) {
          return await Promise.race([
            fetchAndProcess(),
            new Promise((resolve) =>
              setTimeout(() => resolve(cached.data), this.manifest.liefi_timeout_ms)
            ),
          ]);
        }
        return await fetchAndProcess();
      } catch (err) {
        const isNetworkError = !err.code;
        if (isNetworkError && cached) {
          return cached.data;
        }
        if (isNetworkError && isOutboxAllowed) {
          await idbStorage.enqueueOutbox({
            idempotencyKey: reqPacket.$idempotency_key,
            method,
            params,
            createdAt: Date.now(),
          });
          return {
            status: "queued_offline",
            offline: true,
            idempotency_key: reqPacket.$idempotency_key,
          };
        }
        throw err;
      }
    })();

    if (isCacheable) {
      this.inFlight.set(cacheKey, execPromise);
      execPromise.finally(() => this.inFlight.delete(cacheKey));
    }

    return execPromise;
  }
}

const client = new RpcClient();
function rpcFn(method, params, options) {
  return client.call(method, params, options);
}
export const rpc = new Proxy(rpcFn, {
  get(target, prop) {
    const val = Reflect.get(client, prop);
    if (typeof val === "function") {
      return val.bind(client);
    }
    return val;
  },
  set(target, prop, value) {
    return Reflect.set(client, prop, value);
  },
});

/**
 * Реактивный контроллер пагинации таблиц для RPC-методов PyFerro 2.0.
 */
export function createPaginator(method, options = {}) {
  let searchTimer = null;
  const listeners = new Set();

  const state = {
    method,
    limit: options.limit || 20,
    page: 1,
    pages: 1,
    total: 0,
    items: [],
    loading: false,
    error: null,
    hasNext: false,
    hasPrev: false,
    nextCursor: null,
    prevCursor: null,
    searchQuery: options.search || "",
    filters: options.filters || {},
    sortBy: options.sortBy || null,
    sortOrder: options.sortOrder || "desc",
    extraParams: options.params || {},

    subscribe(fn) {
      listeners.add(fn);
      fn(state);
      return () => listeners.delete(fn);
    },

    notify() {
      for (const fn of listeners) fn(state);
    },

    get pageNumbers() {
      const current = state.page;
      const totalPages = Math.max(1, state.pages);
      if (totalPages <= 7) {
        return Array.from({ length: totalPages }, (_, i) => i + 1);
      }
      const pages = [];
      pages.push(1);
      if (current > 3) pages.push("...");

      const start = Math.max(2, current - 1);
      const end = Math.min(totalPages - 1, current + 1);
      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      if (current < totalPages - 2) pages.push("...");
      pages.push(totalPages);
      return pages;
    },

    async load() {
      state.loading = true;
      state.error = null;
      state.notify();

      const params = {
        ...state.extraParams,
        limit: state.limit,
        page: state.page,
        ...(state.searchQuery ? { search: state.searchQuery } : {}),
        ...(Object.keys(state.filters).length > 0 ? { filters: state.filters } : {}),
        ...(state.sortBy ? { sort_by: state.sortBy, order: state.sortOrder } : {}),
      };

      try {
        const res = await rpc.call(state.method, params);
        state.items = res.items || [];
        state.total = res.total ?? 0;
        state.pages = res.pages ?? (state.total ? Math.ceil(state.total / state.limit) : 1);
        state.page = res.page ?? state.page;
        state.hasNext = Boolean(res.has_next);
        state.hasPrev = Boolean(res.has_prev);
        state.nextCursor = res.next_cursor || null;
        state.prevCursor = res.prev_cursor || null;
      } catch (err) {
        state.error = err.message || "Ошибка загрузки";
      } finally {
        state.loading = false;
        state.notify();
      }
      return state;
    },

    async next() {
      if (!state.hasNext || state.loading) return;
      state.page++;
      return state.load();
    },

    async prev() {
      if (!state.hasPrev || state.loading) return;
      state.page = Math.max(1, state.page - 1);
      return state.load();
    },

    async goTo(pageNumber) {
      if (typeof pageNumber !== "number" || pageNumber === state.page || state.loading) return;
      if (pageNumber < 1 || pageNumber > state.pages) return;
      state.page = pageNumber;
      return state.load();
    },

    search(query, debounceMs = 250) {
      state.searchQuery = query;
      state.page = 1;
      if (searchTimer) clearTimeout(searchTimer);
      if (debounceMs <= 0) {
        return state.load();
      }
      return new Promise((resolve) => {
        searchTimer = setTimeout(() => {
          resolve(state.load());
        }, debounceMs);
      });
    },

    setFilter(key, val) {
      if (val === undefined || val === null || val === "") {
        delete state.filters[key];
      } else {
        state.filters[key] = val;
      }
      state.page = 1;
      return state.load();
    },

    setSorting(sortBy, sortOrder = "desc") {
      state.sortBy = sortBy;
      state.sortOrder = sortOrder;
      state.page = 1;
      return state.load();
    },

    setLimit(newLimit) {
      state.limit = Number(newLimit);
      state.page = 1;
      return state.load();
    },

    refresh() {
      return state.load();
    },
  };

  return state;
}
