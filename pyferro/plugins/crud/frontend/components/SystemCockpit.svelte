<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { rpc } from "../wsrpc_client";

  interface Props {
    lang: "ru" | "en";
  }

  let { lang }: Props = $props();

  type SystemTab = "sessions" | "cache" | "broadcast" | "logs" | "config";
  let activeTab = $state<SystemTab>("sessions");

  // --- Состояния вкладок ---
  // 1. Сессии
  let sessions = $state<any[]>([]);
  let loadingSessions = $state(false);
  let sessionActionMsg = $state<string | null>(null);
  let sessionActionError = $state(false);

  // 2. Smart Cache
  let cacheStats = $state<any[]>([]);
  let loadingCache = $state(false);
  let customTagInput = $state("");
  let cacheActionMsg = $state<string | null>(null);
  let cacheActionError = $state(false);

  // 3. Broadcast
  const BROADCAST_LEVELS = ["info", "success", "warning", "error"] as const;
  let broadcastMsg = $state("");
  let broadcastTitle = $state("");
  let broadcastLevel = $state<"info" | "warning" | "error" | "success">("info");
  let sendingBroadcast = $state(false);
  let broadcastResult = $state<string | null>(null);

  // 4. Логи
  let logs = $state<any[]>([]);
  let loadingLogs = $state(false);
  let logFilterLevel = $state<string>("ALL");
  let logSearch = $state("");
  let autoRefreshLogs = $state(true);
  let logTimer: any = null;

  // 5. Конфигурация и плагины
  let pluginMatrixData = $state<any>(null);
  let loadingConfig = $state(false);
  let savingHotConfig = $state(false);
  let hotConfigMsg = $state<string | null>(null);
  let configErrorMsg = $state<string | null>(null);

  let editLogLevel = $state("INFO");
  let editDbEcho = $state(false);
  let editAllowGuests = $state(true);
  let editGuestTimeout = $state(900);
  let editUserTimeout = $state(1800);

  const t = $derived({
    ru: {
      tabs: {
        sessions: "Активные сессии",
        cache: "Smart Cache (RFC 0001)",
        broadcast: "Системные оповещения",
        logs: "Системные логи",
        config: "Параметры и плагины",
      },
      refresh: "Обновить",
      autoRefresh: "Авто-обновление (2с)",
      sessions: {
        title: "Мониторинг WebSocket-сессий",
        subtitle: "Список открытых дуплексных подключений к серверу Granian RSGI.",
        id: "ID сессии",
        ip: "IP адрес",
        user: "Пользователь",
        role: "Роль",
        idle: "Бездействие",
        status: "Статус",
        action: "Действие",
        currentSession: "Текущая сессия",
        connected: "Подключен",
        kick: "Отключить",
        kickConfirm: "Принудительно разорвать соединение с сессией",
        noSessions: "Нет активных сессий",
        secAgo: "сек. назад",
      },
      cache: {
        title: "Smart Cache (RFC 0001)",
        subtitle: "Инспекция монотонных версий тегов и мгновенная реактивная инвалидация.",
        tag: "Тег кэша",
        version: "Монотонная версия",
        invalidate: "Сбросить тег",
        customTagPlaceholder: "Введите имя тега (например, tasks или forum.topic.42)...",
        invalidateBtn: "Инвалидировать тег",
        noTags: "Реестр тегов пуст",
      },
      broadcast: {
        title: "Системная O(1) Zero-Copy Рассылка",
        subtitle: "Мгновенное всплывающее оповещение всем подключенным сокетам без блокировки.",
        titleLabel: "Заголовок уведомления:",
        titlePlaceholder: "Например: Плановые технические работы",
        msgLabel: "Текст сообщения:",
        msgPlaceholder: "Введите важное системное сообщение для пользователей...",
        levelLabel: "Уровень важности:",
        sendBtn: "Отправить оповещение",
        sending: "Отправка...",
      },
      logs: {
        title: "Оперативный журнал сервера",
        subtitle: "Кольцевой буфер событий ядра и RPC-запросов из памяти приложения.",
        filterAll: "Все уровни",
        searchPlaceholder: "Поиск по логам...",
        noLogs: "Записей в журнале нет",
      },
      config: {
        title: "Параметры ядра и плагинов",
        subtitle: "Инспекция подключенных модулей, оперативный пульт и горячая конфигурация.",
        hotSettings: "Оперативный пульт (Live Hot-Apply)",
        hotSettingsDesc: "Применяется мгновенно в оперативной памяти без перезапуска сервиса и обрыва сокетов.",
        pluginMatrix: "Матрица плагинов ядра",
        pluginMatrixDesc: "Рабочее состояние и параметры официальных модулей платформы PyFerro.",
        infra: "Инфраструктура (Code-First)",
        infraDesc: "Структурные параметры сетевого сокета и процесса задаются в коде server.py.",
        logLevel: "Уровень логирования:",
        sqlEcho: "Трассировка SQL (Echo в консоль):",
        allowGuests: "Разрешить гостевой доступ:",
        guestTimeout: "Таймаут гостей (сек):",
        userTimeout: "Таймаут пользователей (сек):",
        applyHotBtn: "Применить в рантайме",
        applying: "Применение...",
        hotSuccess: "Оперативные настройки успешно применены в рантайме!",
        active: "Активен",
        inactive: "Не подключен",
        modelsCount: "Моделей в CRUD:",
        tagsCount: "Тегов в кэше:",
        botRoutes: "SEO SSR-маршрутов:",
        connectedSockets: "Активных сокетов:",
        storageDir: "Каталог файлов:",
        dialect: "СУБД:",
        inspectBtn: "Перейти к управлению",
      }
    },
    en: {
      tabs: {
        sessions: "Active Sessions",
        cache: "Smart Cache (RFC 0001)",
        broadcast: "Broadcast Alerts",
        logs: "Live Logs",
        config: "Engine & Plugins",
      },
      refresh: "Refresh",
      autoRefresh: "Auto-refresh (2s)",
      sessions: {
        title: "WebSocket Sessions Monitor",
        subtitle: "Active duplex client connections on Granian RSGI server.",
        id: "Session ID",
        ip: "IP Address",
        user: "User",
        role: "Role",
        idle: "Idle Time",
        status: "Status",
        action: "Action",
        currentSession: "Current session",
        connected: "Connected",
        kick: "Disconnect",
        kickConfirm: "Force disconnect session",
        noSessions: "No active sessions",
        secAgo: "sec ago",
      },
      cache: {
        title: "Smart Cache (RFC 0001)",
        subtitle: "Tag version registry inspection and instant reactive invalidation.",
        tag: "Cache Tag",
        version: "Monotonic Version",
        invalidate: "Invalidate",
        customTagPlaceholder: "Enter cache tag name...",
        invalidateBtn: "Invalidate Tag",
        noTags: "Tag registry is empty",
      },
      broadcast: {
        title: "System O(1) Zero-Copy Broadcast",
        subtitle: "Instant non-blocking notification to all connected WebSockets.",
        titleLabel: "Alert Title:",
        titlePlaceholder: "e.g. Scheduled Maintenance",
        msgLabel: "Message Body:",
        msgPlaceholder: "Enter urgent system broadcast message...",
        levelLabel: "Severity Level:",
        sendBtn: "Send Broadcast",
        sending: "Sending...",
      },
      logs: {
        title: "Live Server Log Streamer",
        subtitle: "Ring buffer of core events and RPC calls in server memory.",
        filterAll: "All levels",
        searchPlaceholder: "Search logs...",
        noLogs: "No log records found",
      },
      config: {
        title: "Framework & Plugin Settings",
        subtitle: "Plugin inspection matrix, runtime operational controls and hot configuration.",
        hotSettings: "Live Operational Controls (Hot-Apply)",
        hotSettingsDesc: "Applied instantly in server memory without restarting or disconnecting WebSockets.",
        pluginMatrix: "Core Plugin Matrix",
        pluginMatrixDesc: "Operational state and parameters of official PyFerro platform modules.",
        infra: "Infrastructure (Code-First)",
        infraDesc: "Structural process and network socket settings are defined in server.py.",
        logLevel: "Log Level:",
        sqlEcho: "SQL Trace (Echo to console):",
        allowGuests: "Allow Guest Access:",
        guestTimeout: "Guest Idle Timeout (sec):",
        userTimeout: "User Idle Timeout (sec):",
        applyHotBtn: "Apply in Runtime",
        applying: "Applying...",
        hotSuccess: "Operational settings successfully applied in runtime!",
        active: "Active",
        inactive: "Not connected",
        modelsCount: "CRUD Models:",
        tagsCount: "Cache Tags:",
        botRoutes: "SEO SSR Routes:",
        connectedSockets: "Active Sockets:",
        storageDir: "Files Directory:",
        dialect: "DBMS:",
        inspectBtn: "Manage",
      }
    }
  }[lang]);

  // Загрузка активных сессий
  async function loadSessions() {
    loadingSessions = true;
    sessionActionMsg = null;
    sessionActionError = false;
    try {
      const res = await rpc.call("admin.sessions_list", {});
      sessions = Array.isArray(res) ? res : [];
    } catch (e: any) {
      console.error("[System Cockpit] Ошибка загрузки сессий:", e);
      sessionActionError = true;
      const raw = typeof e === "string" ? e : (e?.message || "Ошибка загрузки сессий");
      if (raw.includes("Unauthorized") || raw.includes("Доступ запрещен")) {
        sessionActionMsg = `🔒 Ошибка доступа: сессия не авторизована или истекла (${raw}). Выполните вход под администратором.`;
      } else {
        sessionActionMsg = raw;
      }
    } finally {
      loadingSessions = false;
    }
  }

  // Принудительное отключение сессии (Kick)
  async function killSession(sessionId: number, username: string) {
    if (!confirm(`${t.sessions.kickConfirm} #${sessionId} (${username})?`)) return;
    try {
      await rpc.call("admin.session_kill", { session_id: sessionId });
      sessionActionError = false;
      sessionActionMsg = `Сессия #${sessionId} успешно отключена`;
      await loadSessions();
    } catch (e: any) {
      alert(`Ошибка отключения: ${e?.message || e}`);
    }
  }

  // Загрузка статистики Smart Cache
  async function loadCacheStats() {
    loadingCache = true;
    cacheActionMsg = null;
    cacheActionError = false;
    try {
      const res = await rpc.call("system.cache_stats", {});
      cacheStats = Array.isArray(res) ? res : [];
    } catch (e: any) {
      console.error("[System Cockpit] Ошибка кэша:", e);
      cacheActionError = true;
      const raw = typeof e === "string" ? e : (e?.message || "Ошибка загрузки кэша");
      if (raw.includes("Unauthorized") || raw.includes("Доступ запрещен")) {
        cacheActionMsg = `🔒 Ошибка доступа: сессия не авторизована или истекла (${raw}). Выполните вход под администратором.`;
      } else {
        cacheActionMsg = raw;
      }
    } finally {
      loadingCache = false;
    }
  }

  // Инвалидация тега
  async function invalidateTags(tagNames: string[]) {
    try {
      const res = await rpc.call("system.cache_invalidate", { tags: tagNames });
      cacheActionError = false;
      cacheActionMsg = `Теги успешно инвалидированы: ${tagNames.join(", ")}`;
      customTagInput = "";
      await loadCacheStats();
    } catch (e: any) {
      alert(`Ошибка инвалидации: ${e?.message || e}`);
    }
  }

  // Отправка системного Broadcast
  async function sendBroadcast() {
    if (!broadcastMsg.trim()) return;
    sendingBroadcast = true;
    broadcastResult = null;
    try {
      const res: any = await rpc.call("system.broadcast", {
        message: broadcastMsg.trim(),
        title: broadcastTitle.trim() || undefined,
        level: broadcastLevel,
      });
      broadcastResult = `Оповещение успешно доставлено ${res?.delivered_count ?? 0} клиентам!`;
      broadcastMsg = "";
      broadcastTitle = "";
    } catch (e: any) {
      broadcastResult = `Ошибка отправки: ${e?.message || e}`;
    } finally {
      sendingBroadcast = false;
    }
  }

  // Загрузка системных логов
  async function loadLogs() {
    loadingLogs = true;
    try {
      const res = await rpc.call("system.recent_logs", { limit: 120 });
      logs = Array.isArray(res) ? res : [];
    } catch (e: any) {
      console.error("[System Cockpit] Ошибка загрузки логов:", e);
    } finally {
      loadingLogs = false;
    }
  }

  // Загрузка матрицы плагинов и параметров ядра
  async function loadConfig() {
    loadingConfig = true;
    hotConfigMsg = null;
    configErrorMsg = null;
    try {
      const res: any = await rpc.call("system.plugin_matrix", {});
      pluginMatrixData = res || null;
      if (res?.runtime) {
        editLogLevel = res.runtime.log_level || "INFO";
        editDbEcho = Boolean(res.runtime.db_echo);
        editAllowGuests = Boolean(res.runtime.allow_guests);
        editGuestTimeout = Number(res.runtime.guest_idle_timeout) || 900;
        editUserTimeout = Number(res.runtime.user_idle_timeout) || 1800;
      }
    } catch (e: any) {
      console.error("[System Cockpit] Ошибка матрицы плагинов:", e);
      const raw = typeof e === "string" ? e : (e?.message || "Ошибка загрузки матрицы плагинов и параметров ядра");
      if (raw.includes("Unauthorized") || raw.includes("Доступ запрещен")) {
        configErrorMsg = `🔒 Ошибка доступа: сессия не авторизована или истекла (${raw}). Выполните вход под администратором.`;
      } else {
        configErrorMsg = raw;
      }
    } finally {
      loadingConfig = false;
    }
  }

  // Горячее применение настроек в рантайме
  async function saveHotConfig() {
    savingHotConfig = true;
    hotConfigMsg = null;
    try {
      const res: any = await rpc.call("system.update_hot_config", {
        log_level: editLogLevel,
        db_echo: editDbEcho,
        allow_guests: editAllowGuests,
        guest_idle_timeout: editGuestTimeout,
        user_idle_timeout: editUserTimeout,
      });
      hotConfigMsg = t.config.hotSuccess;
      await loadConfig();
    } catch (e: any) {
      alert(`Ошибка применения настроек: ${e?.message || e}`);
    } finally {
      savingHotConfig = false;
    }
  }

  // Реакция на переключение вкладок
  $effect(() => {
    if (activeTab === "sessions") loadSessions();
    else if (activeTab === "cache") loadCacheStats();
    else if (activeTab === "logs") loadLogs();
    else if (activeTab === "config") loadConfig();
  });

  // Авто-обновление логов
  $effect(() => {
    if (activeTab === "logs" && autoRefreshLogs) {
      logTimer = setInterval(() => {
        loadLogs();
      }, 2000);
    } else {
      if (logTimer) clearInterval(logTimer);
    }
    return () => {
      if (logTimer) clearInterval(logTimer);
    };
  });

  const filteredLogs = $derived(
    logs.filter((item) => {
      if (logFilterLevel !== "ALL" && item.level !== logFilterLevel) return false;
      if (logSearch.trim()) {
        const q = logSearch.toLowerCase();
        const m = (item.message || "").toLowerCase();
        const c = (item.ctx || "").toLowerCase();
        const l = (item.logger || "").toLowerCase();
        return m.includes(q) || c.includes(q) || l.includes(q);
      }
      return true;
    })
  );

  onMount(() => {
    loadSessions();
  });

  onDestroy(() => {
    if (logTimer) clearInterval(logTimer);
  });
</script>

<div class="flex-1 flex flex-col p-6 overflow-y-auto gap-6 bg-background">
  <!-- Верхний блок переключения системных инструментов -->
  <div class="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-border">
    <div class="flex items-center gap-2">
      <span class="text-xl">⚙️</span>
      <div>
        <h2 class="text-lg font-bold tracking-tight text-foreground">Mission Control Cockpit</h2>
        <p class="text-xs text-muted-foreground">Управление сетевым ядром, сессиями, кэшем и системными событиями</p>
      </div>
    </div>

    <!-- Вкладки подраздела System -->
    <div class="flex items-center gap-1.5 p-1 rounded-xl bg-card border border-border shadow-2xs">
      <button
        type="button"
        onclick={() => (activeTab = "sessions")}
        class="px-3.5 py-1.5 rounded-lg text-xs transition-all cursor-pointer {activeTab === 'sessions' ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
      >
        👥 {t.tabs.sessions}
      </button>
      <button
        type="button"
        onclick={() => (activeTab = "cache")}
        class="px-3.5 py-1.5 rounded-lg text-xs transition-all cursor-pointer {activeTab === 'cache' ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
      >
        ⚡ {t.tabs.cache}
      </button>
      <button
        type="button"
        onclick={() => (activeTab = "broadcast")}
        class="px-3.5 py-1.5 rounded-lg text-xs transition-all cursor-pointer {activeTab === 'broadcast' ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
      >
        📢 {t.tabs.broadcast}
      </button>
      <button
        type="button"
        onclick={() => (activeTab = "logs")}
        class="px-3.5 py-1.5 rounded-lg text-xs transition-all cursor-pointer {activeTab === 'logs' ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
      >
        📜 {t.tabs.logs}
      </button>
      <button
        type="button"
        onclick={() => (activeTab = "config")}
        class="px-3.5 py-1.5 rounded-lg text-xs transition-all cursor-pointer {activeTab === 'config' ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
      >
        🛠️ {t.tabs.config}
      </button>
    </div>
  </div>

  <!-- ВКЛАДКА 1: АКТИВНЫЕ СЕССИИ -->
  {#if activeTab === "sessions"}
    <div class="flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-bold text-foreground">{t.sessions.title}</h3>
          <p class="text-xs text-muted-foreground">{t.sessions.subtitle}</p>
        </div>
        <button
          type="button"
          onclick={loadSessions}
          disabled={loadingSessions}
          class="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-semibold hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
        >
          🔄 {t.refresh}
        </button>
      </div>

      {#if sessionActionMsg}
        <div class="p-3 rounded-lg border text-xs font-medium {sessionActionError ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-border bg-card text-foreground'}">
          {sessionActionError ? "❌" : "ℹ️"} {sessionActionMsg}
        </div>
      {/if}

      <div class="border border-border rounded-xl bg-card overflow-hidden shadow-2xs">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-border bg-muted/40 text-muted-foreground font-semibold">
              <th class="py-2.5 px-4">{t.sessions.id}</th>
              <th class="py-2.5 px-4">{t.sessions.ip}</th>
              <th class="py-2.5 px-4">{t.sessions.user}</th>
              <th class="py-2.5 px-4">{t.sessions.role}</th>
              <th class="py-2.5 px-4">{t.sessions.idle}</th>
              <th class="py-2.5 px-4">{t.sessions.status}</th>
              <th class="py-2.5 px-4 text-right">{t.sessions.action}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#if loadingSessions}
              <tr>
                <td colspan="7" class="py-8 text-center text-muted-foreground">Загрузка сессий...</td>
              </tr>
            {:else if sessions.length === 0}
              <tr>
                <td colspan="7" class="py-8 text-center text-muted-foreground">{t.sessions.noSessions}</td>
              </tr>
            {:else}
              {#each sessions as s (s.session_id)}
                <tr class="hover:bg-muted/20 transition-colors">
                  <td class="py-2.5 px-4 font-mono font-medium text-foreground">
                    #{s.session_id}
                  </td>
                  <td class="py-2.5 px-4 font-mono text-muted-foreground">
                    {s.ip}
                  </td>
                  <td class="py-2.5 px-4 font-semibold text-foreground">
                    {s.username}
                  </td>
                  <td class="py-2.5 px-4">
                    <span class="px-2 py-0.5 rounded-full text-2xs font-semibold border {s.role === 'admin' ? 'bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400' : 'bg-muted border-border text-muted-foreground'}">
                      {s.role}
                    </span>
                  </td>
                  <td class="py-2.5 px-4 font-mono text-muted-foreground">
                    {s.idle_seconds} {t.sessions.secAgo}
                  </td>
                  <td class="py-2.5 px-4">
                    {#if s.is_current}
                      <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-bold bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400">
                        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        {t.sessions.currentSession}
                      </span>
                    {:else}
                      <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-semibold bg-primary/10 border border-primary/30 text-primary">
                        <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                        {t.sessions.connected}
                      </span>
                    {/if}
                  </td>
                  <td class="py-2.5 px-4 text-right">
                    {#if !s.is_current}
                      <button
                        type="button"
                        onclick={() => killSession(s.session_id, s.username)}
                        class="px-2.5 py-1 rounded-md text-2xs font-semibold bg-destructive/10 border border-destructive/20 text-destructive hover:bg-destructive hover:text-destructive-foreground transition-all cursor-pointer"
                      >
                        🔌 {t.sessions.kick}
                      </button>
                    {:else}
                      <span class="text-2xs text-muted-foreground italic">—</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </div>

  <!-- ВКЛАДКА 2: SMART CACHE -->
  {:else if activeTab === "cache"}
    <div class="flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-bold text-foreground">{t.cache.title}</h3>
          <p class="text-xs text-muted-foreground">{t.cache.subtitle}</p>
        </div>
        <button
          type="button"
          onclick={loadCacheStats}
          disabled={loadingCache}
          class="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-semibold hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
        >
          🔄 {t.refresh}
        </button>
      </div>

      <!-- Ручной сброс тегов -->
      <div class="flex items-center gap-2 p-3 rounded-xl border border-border bg-card shadow-2xs">
        <input
          type="text"
          bind:value={customTagInput}
          placeholder={t.cache.customTagPlaceholder}
          class="flex-1 px-3 py-1.5 rounded-lg border border-border bg-background text-foreground text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          type="button"
          onclick={() => {
            if (customTagInput.trim()) {
              const tags = customTagInput.split(",").map((x) => x.trim()).filter(Boolean);
              invalidateTags(tags);
            }
          }}
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 transition-opacity cursor-pointer"
        >
          ⚡ {t.cache.invalidateBtn}
        </button>
      </div>

      {#if cacheActionMsg}
        <div class="p-3 rounded-lg border text-xs font-medium {cacheActionError ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-border bg-card text-foreground'}">
          {cacheActionError ? "❌" : "✅"} {cacheActionMsg}
        </div>
      {/if}

      <div class="border border-border rounded-xl bg-card overflow-hidden shadow-2xs">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-border bg-muted/40 text-muted-foreground font-semibold">
              <th class="py-2.5 px-4">{t.cache.tag}</th>
              <th class="py-2.5 px-4">{t.cache.version}</th>
              <th class="py-2.5 px-4 text-right">Действие</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#if loadingCache}
              <tr>
                <td colspan="3" class="py-8 text-center text-muted-foreground">Загрузка тегов кэша...</td>
              </tr>
            {:else if cacheStats.length === 0}
              <tr>
                <td colspan="3" class="py-8 text-center text-muted-foreground">{t.cache.noTags}</td>
              </tr>
            {:else}
              {#each cacheStats as c (c.tag)}
                <tr class="hover:bg-muted/20 transition-colors">
                  <td class="py-2.5 px-4 font-mono font-medium text-foreground">
                    🏷️ {c.tag}
                  </td>
                  <td class="py-2.5 px-4 font-mono font-bold text-primary">
                    v{c.version}
                  </td>
                  <td class="py-2.5 px-4 text-right">
                    <button
                      type="button"
                      onclick={() => invalidateTags([c.tag])}
                      class="px-2.5 py-1 rounded-md text-2xs font-semibold border border-primary/30 text-primary hover:bg-primary hover:text-primary-foreground transition-all cursor-pointer"
                    >
                      ⚡ {t.cache.invalidate}
                    </button>
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </div>

  <!-- ВКЛАДКА 3: BROADCAST -->
  {:else if activeTab === "broadcast"}
    <div class="flex flex-col gap-4 max-w-2xl">
      <div>
        <h3 class="text-sm font-bold text-foreground">{t.broadcast.title}</h3>
        <p class="text-xs text-muted-foreground">{t.broadcast.subtitle}</p>
      </div>

      <div class="flex flex-col gap-4 p-5 rounded-xl border border-border bg-card shadow-2xs">
        <div class="flex flex-col gap-1.5">
          <label for="broadcast-title-input" class="text-xs font-semibold text-foreground">{t.broadcast.titleLabel}</label>
          <input
            id="broadcast-title-input"
            type="text"
            bind:value={broadcastTitle}
            placeholder={t.broadcast.titlePlaceholder}
            class="px-3 py-2 rounded-lg border border-border bg-background text-foreground text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-semibold text-foreground">{t.broadcast.levelLabel}</span>
          <div class="flex items-center gap-2">
            {#each BROADCAST_LEVELS as lvl}
              <button
                type="button"
                onclick={() => (broadcastLevel = lvl)}
                class="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer {broadcastLevel === lvl ? 'bg-primary text-primary-foreground border-primary' : 'bg-background text-foreground border-border hover:bg-muted'}"
              >
                {lvl.toUpperCase()}
              </button>
            {/each}
          </div>
        </div>

        <div class="flex flex-col gap-1.5">
          <label for="broadcast-msg-input" class="text-xs font-semibold text-foreground">{t.broadcast.msgLabel}</label>
          <textarea
            id="broadcast-msg-input"
            bind:value={broadcastMsg}
            rows="3"
            placeholder={t.broadcast.msgPlaceholder}
            class="px-3 py-2 rounded-lg border border-border bg-background text-foreground text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-none"
          ></textarea>
        </div>


        {#if broadcastResult}
          <div class="p-3 rounded-lg border border-border bg-muted/40 text-xs text-foreground font-medium">
            📢 {broadcastResult}
          </div>
        {/if}

        <div class="flex items-center justify-end">
          <button
            type="button"
            onclick={sendBroadcast}
            disabled={sendingBroadcast || !broadcastMsg.trim()}
            class="px-4 py-2 rounded-lg text-xs font-bold bg-primary text-primary-foreground hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 shadow-xs"
          >
            {sendingBroadcast ? t.broadcast.sending : t.broadcast.sendBtn}
          </button>
        </div>
      </div>
    </div>

  <!-- ВКЛАДКА 4: СИСТЕМНЫЕ ЛОГИ -->
  {:else if activeTab === "logs"}
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-sm font-bold text-foreground">{t.logs.title}</h3>
          <p class="text-xs text-muted-foreground">{t.logs.subtitle}</p>
        </div>

        <div class="flex items-center gap-2">
          <!-- Фильтр уровня -->
          <select
            bind:value={logFilterLevel}
            class="px-2.5 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-semibold focus:outline-none cursor-pointer"
          >
            <option value="ALL">{t.logs.filterAll}</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </select>

          <!-- Поиск -->
          <input
            type="text"
            bind:value={logSearch}
            placeholder={t.logs.searchPlaceholder}
            class="px-3 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs placeholder:text-muted-foreground focus:outline-none"
          />

          <!-- Тумблер авто-обновления -->
          <button
            type="button"
            onclick={() => (autoRefreshLogs = !autoRefreshLogs)}
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-semibold transition-all cursor-pointer {autoRefreshLogs ? 'bg-primary/10 border-primary/30 text-primary' : 'bg-card text-muted-foreground'}"
          >
            <span class="w-2 h-2 rounded-full {autoRefreshLogs ? 'bg-primary animate-pulse' : 'bg-muted-foreground'}"></span>
            {t.autoRefresh}
          </button>

          <button
            type="button"
            onclick={loadLogs}
            class="px-3 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-semibold hover:bg-muted transition-colors cursor-pointer"
          >
            🔄
          </button>
        </div>
      </div>

      <!-- Терминал логов -->
      <div class="rounded-xl border border-border bg-[#1f1611] text-[#ece4d9] font-mono text-xs p-4 overflow-x-auto max-h-[600px] overflow-y-auto shadow-inner flex flex-col gap-1.5">
        {#if filteredLogs.length === 0}
          <div class="py-12 text-center text-[#8e7e72] italic font-sans">{t.logs.noLogs}</div>
        {:else}
          {#each filteredLogs as l}
            <div class="leading-relaxed hover:bg-white/5 px-2 py-0.5 rounded transition-colors flex items-start gap-2">
              <span class="text-[#8e7e72] shrink-0 select-none">[{l.time_str || ""}]</span>
              <span class="font-bold shrink-0 {l.level === 'ERROR' ? 'text-red-400' : l.level === 'WARNING' ? 'text-amber-400' : l.level === 'INFO' ? 'text-emerald-400' : 'text-cyan-400'}">
                [{l.level}]
              </span>
              <span class="text-[#ab9c90] shrink-0 font-semibold">{l.ctx}</span>
              <span class="text-[#dfd7cc] break-all">{l.message}</span>
            </div>
          {/each}
        {/if}
      </div>
    </div>

  <!-- ВКЛАДКА 5: ПАРАМЕТРЫ И ПЛАГИНЫ -->
  {:else if activeTab === "config"}
    <div class="flex flex-col gap-6 max-w-4xl">
      <!-- Заголовок и кнопка обновления -->
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-bold text-foreground">{t.config.title}</h3>
          <p class="text-xs text-muted-foreground">{t.config.subtitle}</p>
        </div>
        <button
          type="button"
          onclick={loadConfig}
          disabled={loadingConfig}
          class="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-semibold hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
        >
          🔄 {t.refresh}
        </button>
      </div>

      {#if hotConfigMsg}
        <div class="flex items-center justify-between px-4 py-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs font-semibold">
          <span>✅ {hotConfigMsg}</span>
          <button type="button" onclick={() => (hotConfigMsg = null)} class="hover:underline cursor-pointer">✕</button>
        </div>
      {/if}

      {#if configErrorMsg}
        <div class="flex items-center justify-between p-4 rounded-xl border border-destructive/30 bg-destructive/10 text-destructive text-xs font-semibold">
          <span>❌ {configErrorMsg}</span>
          <button type="button" onclick={loadConfig} class="px-3 py-1 rounded-lg bg-destructive text-destructive-foreground hover:opacity-90 cursor-pointer">
            Повторить
          </button>
        </div>
      {/if}

      {#if loadingConfig && !pluginMatrixData}
        <div class="py-12 text-center text-muted-foreground">Загрузка матрицы плагинов и параметров...</div>
      {:else if pluginMatrixData}
        <!-- БЛОК 1: ОПЕРАТИВНЫЙ ПУЛЬТ (LIVE HOT-APPLY) -->
        <div class="flex flex-col gap-4 p-5 rounded-xl border border-border bg-card shadow-2xs">
          <div class="flex items-center justify-between border-b border-border pb-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-base">⚡</span>
                <h4 class="text-sm font-bold text-foreground">{t.config.hotSettings}</h4>
                <span class="px-2 py-0.5 rounded-full text-2xs font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                  🟢 Hot-Apply (Мгновенно)
                </span>
              </div>
              <p class="text-xs text-muted-foreground mt-0.5">{t.config.hotSettingsDesc}</p>
            </div>
          </div>

          <form onsubmit={(e) => { e.preventDefault(); saveHotConfig(); }} class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <!-- Уровень логов -->
            <div class="flex flex-col gap-1.5">
              <label for="log-level" class="font-semibold text-foreground">{t.config.logLevel}</label>
              <select
                id="log-level"
                bind:value={editLogLevel}
                class="px-3 py-2 rounded-lg border border-border bg-background text-foreground font-semibold text-xs focus:ring-1 focus:ring-primary focus:outline-hidden"
              >
                <option value="DEBUG">DEBUG (Максимальная детализация)</option>
                <option value="INFO">INFO (Штатный режим)</option>
                <option value="WARNING">WARNING (Только предупреждения)</option>
                <option value="ERROR">ERROR (Только ошибки)</option>
              </select>
            </div>

            <!-- Тумблер SQL Echo -->
            <div class="flex flex-col gap-1.5">
              <label for="sql-echo" class="font-semibold text-foreground">{t.config.sqlEcho}</label>
              <label class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background cursor-pointer">
                <input
                  id="sql-echo"
                  type="checkbox"
                  bind:checked={editDbEcho}
                  class="rounded text-primary focus:ring-primary"
                />
                <span class="text-xs font-medium text-foreground">
                  {editDbEcho ? "Включено (печать в консоль)" : "Выключено"}
                </span>
              </label>
            </div>

            <!-- Гостевой доступ -->
            <div class="flex flex-col gap-1.5">
              <label for="allow-guests" class="font-semibold text-foreground">{t.config.allowGuests}</label>
              <label class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background cursor-pointer">
                <input
                  id="allow-guests"
                  type="checkbox"
                  bind:checked={editAllowGuests}
                  class="rounded text-primary focus:ring-primary"
                />
                <span class="text-xs font-medium text-foreground">
                  {editAllowGuests ? "Разрешен" : "Запрещен"}
                </span>
              </label>
            </div>

            <!-- Таймауты -->
            <div class="grid grid-cols-2 gap-2">
              <div class="flex flex-col gap-1.5">
                <label for="guest-timeout" class="font-semibold text-foreground">{t.config.guestTimeout}</label>
                <input
                  id="guest-timeout"
                  type="number"
                  min="10"
                  bind:value={editGuestTimeout}
                  class="px-3 py-2 rounded-lg border border-border bg-background text-foreground font-mono text-xs focus:ring-1 focus:ring-primary focus:outline-hidden"
                />
              </div>
              <div class="flex flex-col gap-1.5">
                <label for="user-timeout" class="font-semibold text-foreground">{t.config.userTimeout}</label>
                <input
                  id="user-timeout"
                  type="number"
                  min="10"
                  bind:value={editUserTimeout}
                  class="px-3 py-2 rounded-lg border border-border bg-background text-foreground font-mono text-xs focus:ring-1 focus:ring-primary focus:outline-hidden"
                />
              </div>
            </div>

            <!-- Кнопка применения -->
            <div class="md:col-span-2 flex justify-end pt-2">
              <button
                type="submit"
                disabled={savingHotConfig}
                class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground font-bold text-xs hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 shadow-xs"
              >
                <span>⚡</span>
                <span>{savingHotConfig ? t.config.applying : t.config.applyHotBtn}</span>
              </button>
            </div>
          </form>
        </div>

        <!-- БЛОК 2: МАТРИЦА ПЛАГИНОВ ЯДРА (PLUGIN MATRIX) -->
        <div class="flex flex-col gap-4">
          <div class="flex items-center justify-between border-b border-border pb-2">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-base">🧩</span>
                <h4 class="text-sm font-bold text-foreground">{t.config.pluginMatrix}</h4>
              </div>
              <p class="text-xs text-muted-foreground mt-0.5">{t.config.pluginMatrixDesc}</p>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <!-- 1. Database -->
            {#if pluginMatrixData.plugins?.db}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>🗄️</span> <span>{pluginMatrixData.plugins.db.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>{t.config.dialect}</span>
                    <span class="font-mono font-bold uppercase text-foreground">{pluginMatrixData.plugins.db.dialect}</span>
                  </div>
                  <div class="flex flex-col gap-0.5 pt-1">
                    <span>URL:</span>
                    <span class="font-mono text-3xs text-foreground break-all">{pluginMatrixData.plugins.db.url_masked}</span>
                  </div>
                </div>
              </div>
            {/if}

            <!-- 2. Smart Cache -->
            {#if pluginMatrixData.plugins?.smart_cache}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>⚡</span> <span>{pluginMatrixData.plugins.smart_cache.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>{t.config.tagsCount}</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.smart_cache.tag_count}</span>
                  </div>
                  <button
                    type="button"
                    onclick={() => (activeTab = "cache")}
                    class="mt-2 text-2xs text-primary font-bold hover:underline text-left cursor-pointer"
                  >
                    🔍 {t.config.inspectBtn} &rarr;
                  </button>
                </div>
              </div>
            {/if}

            <!-- 3. CRUD -->
            {#if pluginMatrixData.plugins?.crud}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>📊</span> <span>{pluginMatrixData.plugins.crud.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>{t.config.modelsCount}</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.crud.models_count}</span>
                  </div>
                </div>
              </div>
            {/if}

            <!-- 4. Files -->
            {#if pluginMatrixData.plugins?.files}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>📁</span> <span>{pluginMatrixData.plugins.files.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>{t.config.storageDir}</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.files.storage_dir}</span>
                  </div>
                  <div class="flex justify-between">
                    <span>Макс. размер:</span>
                    <span class="font-mono text-foreground">{pluginMatrixData.plugins.files.max_upload_size}</span>
                  </div>
                </div>
              </div>
            {/if}

            <!-- 5. SEO -->
            {#if pluginMatrixData.plugins?.seo}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>🌐</span> <span>{pluginMatrixData.plugins.seo.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>{t.config.botRoutes}</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.seo.bot_routes_count}</span>
                  </div>
                </div>
              </div>
            {/if}

            <!-- 6. Broadcast -->
            {#if pluginMatrixData.plugins?.broadcast}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>📣</span> <span>{pluginMatrixData.plugins.broadcast.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>Шина доставки:</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.broadcast.backplane_type}</span>
                  </div>
                  <div class="flex justify-between">
                    <span>{t.config.connectedSockets}</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.broadcast.connected_sessions}</span>
                  </div>
                </div>
              </div>
            {/if}

            <!-- 7. Auth -->
            {#if pluginMatrixData.plugins?.auth}
              <div class="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card shadow-2xs">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-xs text-foreground flex items-center gap-1.5">
                    <span>🛡️</span> <span>{pluginMatrixData.plugins.auth.name}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {t.config.active}
                  </span>
                </div>
                <div class="flex flex-col gap-1 text-2xs text-muted-foreground">
                  <div class="flex justify-between">
                    <span>Префикс гостей:</span>
                    <span class="font-mono font-bold text-foreground">{pluginMatrixData.plugins.auth.login_rpc}*</span>
                  </div>
                  <div class="flex justify-between">
                    <span>Срок JWT:</span>
                    <span class="font-mono text-foreground">{pluginMatrixData.plugins.auth.token_expire_hours} ч.</span>
                  </div>
                </div>
              </div>
            {/if}
          </div>
        </div>

        <!-- БЛОК 3: ИНФРАСТРУКТУРА (READ-ONLY) -->
        <div class="flex flex-col gap-3 p-4 rounded-xl border border-border bg-card/60 shadow-2xs">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-sm">⚙️</span>
              <h4 class="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t.config.infra}</h4>
            </div>
            <span class="text-2xs text-muted-foreground">{t.config.infraDesc}</span>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div class="flex flex-col gap-0.5 p-2 rounded-lg bg-background border border-border">
              <span class="text-2xs text-muted-foreground">Python</span>
              <span class="font-mono font-bold text-foreground">{pluginMatrixData.runtime?.python_version}</span>
            </div>
            <div class="flex flex-col gap-0.5 p-2 rounded-lg bg-background border border-border">
              <span class="text-2xs text-muted-foreground">Платформа ОС</span>
              <span class="font-mono font-bold text-foreground">{pluginMatrixData.runtime?.platform}</span>
            </div>
            <div class="flex flex-col gap-0.5 p-2 rounded-lg bg-background border border-border">
              <span class="text-2xs text-muted-foreground">Сервер сети</span>
              <span class="font-mono font-bold text-foreground">Granian (Rust RSGI)</span>
            </div>
            <div class="flex flex-col gap-0.5 p-2 rounded-lg bg-background border border-border">
              <span class="text-2xs text-muted-foreground">Протокол</span>
              <span class="font-mono font-bold text-foreground">WSRPC 2.0 (Duplex)</span>
            </div>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>
