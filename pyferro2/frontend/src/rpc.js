/**
 * Легковесный клиент JSON-RPC 2.0 для PyFerro 2.0 (/pyferro_admin).
 * Поддерживает:
 * - WebSocket /ws (с поддержкой мультиретурна yield и авто-переподключением при смене прав)
 * - HTTP POST /rpc (резервный синхронный вызов)
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

export const rpc = new RpcClient();
