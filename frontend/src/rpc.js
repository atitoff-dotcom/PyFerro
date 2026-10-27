/**
 * Легковесный клиент JSON-RPC 2.0 для PyFerro 2.0 (/pyferro_admin).
 * Поддерживает:
 * - WebSocket /ws (с поддержкой мультиретурна yield и авто-переподключением при смене прав)
 * - HTTP POST /rpc (резервный синхронный вызов)
 * - Сжатие Tabular Data ($tabular)
 * - Реактивный контроллер пагинации createPaginator
 */

const TOKEN_STORAGE_KEY = "pyferro2_token";

export function getStoredToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

export function setStoredToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
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

class RpcClient {
  constructor() {
    this.ws = null;
    this.seq = 1;
    this.pending = new Map();
    this.streams = new Map();
    this.onPermissionDisconnect = null;
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const token = getStoredToken();
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    this.ws = new WebSocket(`${proto}//${window.location.host}/ws${qs}`);

    this.ws.onmessage = (ev) => {
      if (ev.data === "pong") return;
      let packet;
      try {
        packet = JSON.parse(ev.data);
      } catch {
        return;
      }

      if (packet.id !== undefined && this.streams.has(packet.id)) {
        const handler = this.streams.get(packet.id);
        if (packet.error) {
          handler.onError?.(packet.error);
          this.streams.delete(packet.id);
        } else {
          handler.onItem?.(packet.result);
        }
        return;
      }

      if (packet.id !== undefined && this.pending.has(packet.id)) {
        const { resolve, reject } = this.pending.get(packet.id);
        this.pending.delete(packet.id);
        if (packet.error) {
          reject(new Error(packet.error.message || "Ошибка RPC"));
        } else {
          resolve(packet.result);
        }
      }
    };

    this.ws.onclose = (ev) => {
      // При коде 1008 / 4001 сервер разорвал сессию из-за смены прав/ролей
      if (ev.code === 1008 || ev.code === 4001) {
        this.onPermissionDisconnect?.();
      }
    };
  }

  async call(method, params = {}) {
    const token = getStoredToken();
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const id = this.seq++;
    const res = await fetch("/rpc", {
      method: "POST",
      headers,
      body: JSON.stringify({ jsonrpc: "2.0", method, params, id }),
    });

    const data = await res.json();
    if (data.error) {
      const err = new Error(data.error.message || "Ошибка RPC");
      err.code = data.error.code;
      throw err;
    }
    return unpackTabular(data.result);
  }
}

const client = new RpcClient();
function rpcFn(method, params) {
  return client.call(method, params);
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
 *
 * @param {string} method - имя RPC-метода (например, "Book.read")
 * @param {object} [options] - параметры инициализации (limit, search, filters, sortBy, sortOrder)
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

    /** Подписка на обновление состояния (для React, Vue, Svelte store или Vanilla JS) */
    subscribe(fn) {
      listeners.add(fn);
      fn(state);
      return () => listeners.delete(fn);
    },

    notify() {
      for (const fn of listeners) fn(state);
    },

    /** Список номеров страниц и многоточий для вывода в UI: [1, '...', 4, 5, 6, '...', 25] */
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

    /** Загрузка данных текущей страницы */
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

    /** Переход на следующую страницу */
    async next() {
      if (!state.hasNext || state.loading) return;
      state.page++;
      return state.load();
    },

    /** Переход на предыдущую страницу */
    async prev() {
      if (!state.hasPrev || state.loading) return;
      state.page = Math.max(1, state.page - 1);
      return state.load();
    },

    /** Переход на конкретный номер страницы */
    async goTo(pageNumber) {
      if (typeof pageNumber !== "number" || pageNumber === state.page || state.loading) return;
      if (pageNumber < 1 || pageNumber > state.pages) return;
      state.page = pageNumber;
      return state.load();
    },

    /** Живой поиск с автоматическим debounce и сбросом на страницу 1 */
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

    /** Установка точного фильтра по полю */
    setFilter(key, val) {
      if (val === undefined || val === null || val === "") {
        delete state.filters[key];
      } else {
        state.filters[key] = val;
      }
      state.page = 1;
      return state.load();
    },

    /** Установка сортировки */
    setSorting(sortBy, sortOrder = "desc") {
      state.sortBy = sortBy;
      state.sortOrder = sortOrder;
      state.page = 1;
      return state.load();
    },

    /** Изменение лимита строк на страницу */
    setLimit(newLimit) {
      state.limit = Number(newLimit);
      state.page = 1;
      return state.load();
    },

    /** Перезагрузка текущей страницы */
    refresh() {
      return state.load();
    },
  };

  return state;
}
