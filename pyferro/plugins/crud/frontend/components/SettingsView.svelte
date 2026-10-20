<script lang="ts">
  import { onMount } from "svelte";

  interface Props {
    lang?: "ru" | "en";
    rpcClient: any;
    onnotify?: (msg: string, type: "success" | "error" | "info") => void;
  }

  let { lang = "ru", rpcClient, onnotify }: Props = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let errorMsg = $state("");

  // Оперативные настройки
  let logLevel = $state("INFO");
  let dbEcho = $state(false);
  let allowGuests = $state(true);
  let guestIdleTimeout = $state(300);
  let userIdleTimeout = $state(3600);

  // Read-only системная инфа
  let systemInfo = $state<any>({});
  let pluginMatrix = $state<any>({});

  const t = $derived({
    title: lang === "ru" ? "Настройки платформы" : "Platform Settings",
    hotSection: lang === "ru" ? "Оперативные параметры (Online Hot-Config)" : "Runtime Parameters (Online Hot-Config)",
    hotDesc: lang === "ru" ? "Параметры применяются мгновенно без перезапуска сервера и без разрыва соединений" : "Changes apply immediately without server restart or connection drops",
    readOnlySection: lang === "ru" ? "Системная информация (Read-Only)" : "System Information (Read-Only)",
    readOnlyDesc: lang === "ru" ? "Конфигурация ядра и статус сервисов, загруженные из окружения" : "Core configuration and service status loaded from environment",
    logLevel: lang === "ru" ? "Уровень логирования:" : "Log Level:",
    dbEcho: lang === "ru" ? "Эхо SQL-запросов (db_echo):" : "SQL Query Echo (db_echo):",
    dbEchoDesc: lang === "ru" ? "Вывод каждого выполняемого SQL-запроса в терминал/лог" : "Output each executed SQL statement to terminal/log",
    allowGuests: lang === "ru" ? "Разрешить гостевой доступ (allow_guests):" : "Allow Guest Access (allow_guests):",
    allowGuestsDesc: lang === "ru" ? "Разрешает неавторизованным клиентам опрашивать разрешенные RPC и витрины" : "Allows anonymous visitors to access whitelisted public RPCs and CRUD",
    guestIdle: lang === "ru" ? "Таймаут неактивности гостей (сек):" : "Guest Idle Timeout (sec):",
    userIdle: lang === "ru" ? "Таймаут неактивности пользователей (сек):" : "User Idle Timeout (sec):",
    saveBtn: lang === "ru" ? "Применить онлайн" : "Apply Online",
    savingBtn: lang === "ru" ? "Применение..." : "Applying...",
    savedSuccess: lang === "ru" ? "Параметры успешно применены в рантайме!" : "Runtime parameters successfully applied!",
    refreshBtn: lang === "ru" ? "Обновить" : "Refresh",
    engineVersion: lang === "ru" ? "Версия PyFerro Engine:" : "PyFerro Engine Version:",
    dbDriver: lang === "ru" ? "Драйвер базы данных:" : "Database Driver:",
    sessionLifetime: lang === "ru" ? "Срок действия токена (дней):" : "Token Lifetime (days):",
    maxSessions: lang === "ru" ? "Макс. активных сессий на пользователя:" : "Max Active Sessions per User:",
    securityModel: lang === "ru" ? "Модель безопасности:" : "Security Model:",
    activePlugins: lang === "ru" ? "Подключенные компоненты платформы" : "Active Platform Components",
  });

  async function loadData() {
    isLoading = true;
    errorMsg = "";
    try {
      const [conf, matrix] = await Promise.all([
        rpcClient.call("system.config"),
        rpcClient.call("system.plugin_matrix")
      ]);
      systemInfo = conf || {};
      pluginMatrix = matrix || {};

      if (matrix?.runtime) {
        logLevel = matrix.runtime.log_level || "INFO";
        dbEcho = !!matrix.runtime.db_echo;
        allowGuests = matrix.runtime.allow_guests !== undefined ? !!matrix.runtime.allow_guests : true;
        guestIdleTimeout = matrix.runtime.guest_idle_timeout || 300;
        userIdleTimeout = matrix.runtime.user_idle_timeout || 3600;
      }
    } catch (e: any) {
      errorMsg = e.message || String(e);
    } finally {
      isLoading = false;
    }
  }

  async function saveHotConfig() {
    isSaving = true;
    try {
      await rpcClient.call("system.update_hot_config", {
        log_level: logLevel,
        db_echo: dbEcho,
        allow_guests: allowGuests,
        guest_idle_timeout: Number(guestIdleTimeout),
        user_idle_timeout: Number(userIdleTimeout)
      });
      if (onnotify) onnotify(t.savedSuccess, "success");
      await loadData();
    } catch (e: any) {
      const err = e.message || String(e);
      if (onnotify) onnotify(err, "error");
    } finally {
      isSaving = false;
    }
  }

  onMount(() => {
    loadData();
  });
</script>

<div class="flex-1 flex flex-col p-6 gap-6 overflow-y-auto">
  <!-- Верхняя шапка -->
  <div class="flex items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-xs">
    <div class="flex flex-col">
      <h2 class="text-sm font-bold text-foreground">{t.title}</h2>
      <span class="text-2xs text-muted-foreground">{t.hotDesc}</span>
    </div>
    <button
      type="button"
      onclick={loadData}
      class="px-3.5 py-1.5 rounded-lg border border-border bg-muted/60 text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
    >
      ↻ {t.refreshBtn}
    </button>
  </div>

  {#if isLoading}
    <div class="flex flex-col items-center justify-center p-12 text-sm text-muted-foreground gap-2">
      <div class="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
      <span>Загрузка...</span>
    </div>
  {:else if errorMsg}
    <div class="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-xs">
      {errorMsg}
    </div>
  {:else}
    <!-- Секция: Онлайн-настройки -->
    <div class="flex flex-col gap-4 p-5 rounded-xl bg-card border border-border shadow-xs">
      <div class="flex items-center gap-2 border-b border-border/60 pb-3">
        <span class="text-xs font-bold uppercase tracking-wider text-primary">{t.hotSection}</span>
        <span class="px-2 py-0.5 rounded-full text-3xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">Live</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Log Level -->
        <div class="flex flex-col gap-1.5">
          <label for="log-level-select" class="text-xs font-semibold text-foreground">{t.logLevel}</label>
          <select
            id="log-level-select"
            bind:value={logLevel}
            class="rounded-lg border border-input bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer shadow-2xs"
          >
            <option value="DEBUG">DEBUG (Подробный вывод)</option>
            <option value="INFO">INFO (Штатный)</option>
            <option value="WARNING">WARNING (Только предупреждения)</option>
            <option value="ERROR">ERROR (Только ошибки)</option>
          </select>
        </div>

        <!-- Allow Guests -->
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-semibold text-foreground">{t.allowGuests}</span>
          <label class="flex items-center gap-2.5 mt-1 cursor-pointer">
            <input
              type="checkbox"
              bind:checked={allowGuests}
              class="h-4 w-4 rounded border-input text-primary focus:ring-primary cursor-pointer"
            />
            <span class="text-xs text-muted-foreground">{t.allowGuestsDesc}</span>
          </label>
        </div>

        <!-- SQL Echo -->
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-semibold text-foreground">{t.dbEcho}</span>
          <label class="flex items-center gap-2.5 mt-1 cursor-pointer">
            <input
              type="checkbox"
              bind:checked={dbEcho}
              class="h-4 w-4 rounded border-input text-primary focus:ring-primary cursor-pointer"
            />
            <span class="text-xs text-muted-foreground">{t.dbEchoDesc}</span>
          </label>
        </div>

        <!-- Guest Idle Timeout -->
        <div class="flex flex-col gap-1.5">
          <label for="guest-timeout-input" class="text-xs font-semibold text-foreground">{t.guestIdle}</label>
          <input
            id="guest-timeout-input"
            type="number"
            bind:value={guestIdleTimeout}
            min="10"
            class="rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary shadow-2xs"
          />
        </div>

        <!-- User Idle Timeout -->
        <div class="flex flex-col gap-1.5">
          <label for="user-timeout-input" class="text-xs font-semibold text-foreground">{t.userIdle}</label>
          <input
            id="user-timeout-input"
            type="number"
            bind:value={userIdleTimeout}
            min="60"
            class="rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary shadow-2xs"
          />
        </div>
      </div>

      <div class="mt-2 pt-3 border-t border-border/60 flex justify-end">
        <button
          type="button"
          onclick={saveHotConfig}
          disabled={isSaving}
          class="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all cursor-pointer shadow-xs disabled:opacity-50"
        >
          {#if isSaving}
            <div class="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
            <span>{t.savingBtn}</span>
          {:else}
            <span>✓ {t.saveBtn}</span>
          {/if}
        </button>
      </div>
    </div>

    <!-- Секция: Системная информация Read-Only -->
    <div class="flex flex-col gap-4 p-5 rounded-xl bg-card border border-border shadow-xs">
      <div class="flex items-center gap-2 border-b border-border/60 pb-3">
        <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t.readOnlySection}</span>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
        <div class="p-3 rounded-lg bg-muted/40 border border-border/50 flex flex-col gap-1">
          <span class="text-3xs font-semibold text-muted-foreground uppercase">{t.engineVersion}</span>
          <span class="text-xs font-mono font-bold text-foreground">v0.5.15 (High-Perf ASGI)</span>
        </div>

        <div class="p-3 rounded-lg bg-muted/40 border border-border/50 flex flex-col gap-1">
          <span class="text-3xs font-semibold text-muted-foreground uppercase">{t.dbDriver}</span>
          <span class="text-xs font-mono font-bold text-foreground">
            {pluginMatrix?.database?.dialect || "SQLite (aiosqlite / WAL)"}
          </span>
        </div>

        <div class="p-3 rounded-lg bg-muted/40 border border-border/50 flex flex-col gap-1">
          <span class="text-3xs font-semibold text-muted-foreground uppercase">{t.sessionLifetime}</span>
          <span class="text-xs font-mono font-bold text-foreground">
            {pluginMatrix?.auth?.session_lifetime_days || 30} дн.
          </span>
        </div>

        <div class="p-3 rounded-lg bg-muted/40 border border-border/50 flex flex-col gap-1">
          <span class="text-3xs font-semibold text-muted-foreground uppercase">{t.maxSessions}</span>
          <span class="text-xs font-mono font-bold text-foreground">
            {pluginMatrix?.auth?.max_active_sessions || 5}
          </span>
        </div>

        <div class="p-3 rounded-lg bg-muted/40 border border-border/50 flex flex-col gap-1">
          <span class="text-3xs font-semibold text-muted-foreground uppercase">{t.securityModel}</span>
          <span class="text-xs font-mono font-bold text-foreground">
            Granular CQRS + RLS + RFC 0002 Tabular
          </span>
        </div>
      </div>
    </div>
  {/if}
</div>