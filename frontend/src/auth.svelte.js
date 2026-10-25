/**
 * Состояние сессии панели управления (/pyferro_admin).
 * Хранит строго паспортные поля из `SessionData`:
 * `{ userId, username, roles, isAdmin }`
 *
 * Допуск в `/pyferro_admin` разрешен ТОЛЬКО если у пользователя есть роль
 * `admin` или хотя бы одна роль `adm_*`.
 */

import { rpc, setStoredToken } from "./rpc.js";

export const authState = $state({
  userId: null,
  username: "guest",
  roles: [],
  isAdmin: false,
  loading: true,
});

export function canAccessAdminPanel() {
  if (authState.isAdmin) return true;
  return authState.roles.some((r) => r === "admin" || r.startsWith("adm_"));
}

export function hasAdminSection(section) {
  if (authState.isAdmin || authState.roles.includes("admin")) return true;
  return authState.roles.includes(`adm_${section}`);
}

export async function refreshSession() {
  authState.loading = true;
  try {
    const me = await rpc.call("auth.me");
    authState.userId = me.user_id;
    authState.username = me.username || "guest";
    authState.roles = me.roles || [];
    authState.isAdmin = Boolean(me.is_admin);
    rpc.connect();
  } catch {
    authState.userId = null;
    authState.username = "guest";
    authState.roles = [];
    authState.isAdmin = false;
  } finally {
    authState.loading = false;
  }
}

export async function loginAdmin(username, password) {
  const res = await rpc.call("auth.login", { username, password });
  setStoredToken(res.token);
  const u = res.user;
  authState.userId = u.user_id;
  authState.username = u.username;
  authState.roles = u.roles || [];
  authState.isAdmin = Boolean(u.is_admin);
  rpc.connect();
  return u;
}

export async function logoutAdmin() {
  try {
    await rpc.call("auth.logout");
  } catch {
    // Игнорируем сетевые ошибки при выходе
  }
  setStoredToken("");
  authState.userId = null;
  authState.username = "guest";
  authState.roles = [];
  authState.isAdmin = false;
}

rpc.onPermissionDisconnect = () => {
  refreshSession();
};
