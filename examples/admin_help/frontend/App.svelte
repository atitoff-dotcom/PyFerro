<script lang="ts">
  import { onMount } from "svelte";
  import { rpc, wsStatus, auth } from "@wsrpc/wsrpc";
  import CodeBox from "./components/CodeBox.svelte";

  // Активная вкладка: "rpc", "migrations" или "seo"
  let activeTab = $state<"rpc" | "migrations" | "seo">("rpc");

  // Статус WebSocket
  let connectionState = $state<"CONNECTED" | "CONNECTING" | "DISCONNECTED">("CONNECTING");
  let pingRttMs = $state<number | null>(null);

  // Сворачиваемые секции (по умолчанию первая открыта)
  let openSections = $state<Record<string, boolean>>({
    "rpc_basic": true,
    "rpc_stream": false,
    "rpc_errors": false,
    "rpc_tabular": false,
    "rpc_reverse": false,
    "mig_architecture": true,
    "mig_snapshot": false,
    "mig_cli": false,
    "seo_intro": true,
    "seo_tables": true,
    "seo_url": true,
    "seo_crawler": true,
    "seo_gui": true,
  });

  function toggleSection(id: string) {
    openSections[id] = !openSections[id];
  }

  // --- ТЕСТ 1: Базовый RPC Echo ---
  let echoMessage = $state("Привет, PyFerro WSRPC!");
  let echoLoading = $state(false);
  let echoResult = $state<any>(null);
  let echoRtt = $state<number | null>(null);
  let echoWireFrame = $state<{ req: string; res: string } | null>(null);

  // --- ТЕСТ 2: Потоковый мультивывод (Стриминг чанков) ---
  let streamSteps = $state(5);
  let streamRunning = $state(false);
  let streamProgress = $state(0);
  let streamEvents = $state<Array<{ step: number; text: string; elapsed: number }>>([]);
  let streamFinalResult = $state<any>(null);

  // --- ТЕСТ 3: Ошибки RPCError ---
  let errorLoading = $state(false);
  let errorResult = $state<any>(null);
  let errorWireFrame = $state<{ req: string; res: string } | null>(null);

  // --- ТЕСТ 4: Табулярное сжатие данных (RFC 0002) ---
  let tabularCount = $state(20);
  let tabularLoading = $state(false);
  let tabularResult = $state<any>(null);
  let tabularRtt = $state<number | null>(null);
  let tabularViewTab = $state<"preview" | "wire_tabular" | "wire_raw">("preview");

  // --- ТЕСТ 5: Симметричный Reverse RPC ---
  let reverseLoading = $state(false);
  let reverseResult = $state<any>(null);
  let reverseHistory = $state<Array<{ time: string; method: string; prompt: string; clientSent: any }>>([]);

  // --- ТЕСТ 6: Статус миграций ---
  let migrationLoading = $state(false);
  let migrationStatus = $state<any>(null);

  // --- ТЕСТ 7: Dry Run / Теневая проверка ---
  let dryRunLoading = $state(false);
  let dryRunResult = $state<any>(null);

  // --- АВТОРИЗАЦИЯ И SSO ДЛЯ SHOWCASE ---
  interface AuthUser {
    authenticated: boolean;
    username?: string;
    role?: string;
    roles?: string[];
    is_superadmin?: boolean;
  }
  let authUser = $state<AuthUser | null>(null);
  let isLoginModalOpen = $state(false);
  let loginUsername = $state("admin");
  let loginPassword = $state("");
  let loginLoading = $state(false);
  let loginError = $state("");

  async function checkAuth() {
    try {
      const ok = await auth.restoreSession();
      if (ok && auth.user) {
        authUser = {
          authenticated: true,
          username: auth.user.username,
          role: auth.user.role,
          roles: auth.user.roles,
          is_superadmin: auth.user.is_superadmin,
        };
      } else {
        const res = await rpc.call("login.whoami", {});
        if (res && res.authenticated) {
          authUser = res;
          auth.setSession(res);
        } else {
          authUser = null;
        }
      }
    } catch {
      authUser = null;
    }
  }

  async function doLogin() {
    if (!loginUsername.trim() || !loginPassword) {
      loginError = "Введите логин и пароль";
      return;
    }
    loginLoading = true;
    loginError = "";
    try {
      const user = await auth.login({
        username: loginUsername.trim(),
        password: loginPassword,
      });
      if (user) {
        authUser = {
          authenticated: true,
          username: user.username,
          role: user.role,
          roles: user.roles,
          is_superadmin: user.is_superadmin,
        };
        isLoginModalOpen = false;
        loginPassword = "";
      }
    } catch (e: any) {
      loginError = e.message || "Неверный логин или пароль";
    } finally {
      loginLoading = false;
    }
  }

  async function doLogout() {
    try {
      await auth.logout();
    } catch {}
    authUser = null;
    await checkAuth();
  }

  onMount(() => {
    // Явно запускаем WebSocket подключение
    rpc.connect();

    const unsub = wsStatus.subscribe((val) => {
      connectionState = val;
      if (val === "CONNECTED") {
        measurePing();
        checkAuth();
      }
    });

    const unsubAuth = auth.subscribe((user) => {
      if (user && (user.authenticated || user.user_id)) {
        authUser = {
          authenticated: true,
          username: user.username,
          role: user.role,
          roles: user.roles,
          is_superadmin: user.is_superadmin,
        };
      } else if (!user) {
        authUser = null;
      }
    });

    const cleanupNotification = rpc.on("help.stream_chunk", (data: any) => {
      if (data) {
        streamProgress = data.progress || 0;
        streamEvents = [
          ...streamEvents,
          {
            step: data.step,
            text: data.status_text || `Чанк #${data.step}`,
            elapsed: data.elapsed_ms || 0,
          },
        ];
      }
    });

    // Регистрация метода обратного вызова (Reverse RPC) в браузере:
    const unregisterReverse = rpc.register("client.get_environment", async (payload: any) => {
      const clientInfo = {
        screen_resolution: `${window.innerWidth}x${window.innerHeight}`,
        color_depth: `${window.screen.colorDepth}-bit`,
        user_agent: navigator.userAgent.slice(0, 48) + "...",
        language: navigator.language || "ru-RU",
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        client_clock: new Date().toLocaleTimeString(),
      };
      reverseHistory = [
        {
          time: new Date().toLocaleTimeString(),
          method: "client.get_environment",
          prompt: payload?.prompt || "Запрос от сервера",
          clientSent: clientInfo,
        },
        ...reverseHistory.slice(0, 4),
      ];
      return clientInfo;
    });

    return () => {
      unsub();
      unsubAuth();
      if (typeof cleanupNotification === "function") cleanupNotification();
      if (typeof unregisterReverse === "function") unregisterReverse();
    };
  });

  async function measurePing() {
    const t0 = performance.now();
    try {
      await rpc.call("help.rpc.ping");
      pingRttMs = Math.round((performance.now() - t0) * 10) / 10;
    } catch {
      pingRttMs = null;
    }
  }

  async function runEchoTest() {
    echoLoading = true;
    echoResult = null;
    echoWireFrame = null;
    const t0 = performance.now();

    const requestPayload = {
      jsonrpc: "2.0",
      id: Math.floor(Math.random() * 10000),
      method: "help.rpc.echo",
      params: { message: echoMessage, simulate_error: false },
    };

    try {
      const res = await rpc.call("help.rpc.echo", requestPayload.params);
      echoRtt = Math.round((performance.now() - t0) * 10) / 10;
      echoResult = { success: true, data: res };
      echoWireFrame = {
        req: JSON.stringify(requestPayload, null, 2),
        res: JSON.stringify({ jsonrpc: "2.0", id: requestPayload.id, result: res }, null, 2),
      };
    } catch (err: any) {
      echoRtt = Math.round((performance.now() - t0) * 10) / 10;
      echoResult = { success: false, error: err };
    } finally {
      echoLoading = false;
    }
  }

  async function runStreamTest() {
    streamRunning = true;
    streamProgress = 0;
    streamEvents = [];
    streamFinalResult = null;

    try {
      const res = await rpc.call("help.rpc.multi_output", {
        steps: streamSteps,
        delay: 0.15,
      });
      streamProgress = 100;
      streamFinalResult = res;
    } catch (err) {
      streamFinalResult = { error: String(err) };
    } finally {
      streamRunning = false;
    }
  }

  async function runErrorTest() {
    errorLoading = true;
    errorResult = null;
    errorWireFrame = null;

    const requestPayload = {
      jsonrpc: "2.0",
      id: Math.floor(Math.random() * 10000),
      method: "help.rpc.echo",
      params: { simulate_error: true },
    };

    try {
      const res = await rpc.call("help.rpc.echo", requestPayload.params);
      errorResult = { success: true, data: res };
    } catch (err: any) {
      errorResult = {
        code: err.code || -32000,
        message: err.message || String(err),
      };
      errorWireFrame = {
        req: JSON.stringify(requestPayload, null, 2),
        res: JSON.stringify(
          {
            jsonrpc: "2.0",
            id: requestPayload.id,
            error: { code: err.code || -32000, message: err.message || String(err) },
          },
          null,
          2
        ),
      };
    } finally {
      errorLoading = false;
    }
  }

  async function runTabularTest() {
    tabularLoading = true;
    tabularResult = null;
    const t0 = performance.now();
    try {
      const res = await rpc.call("help.rpc.tabular_demo", { count: tabularCount });
      tabularRtt = Math.round((performance.now() - t0) * 10) / 10;
      tabularResult = res;
    } catch (err: any) {
      tabularResult = { error: String(err.message || err) };
    } finally {
      tabularLoading = false;
    }
  }

  async function runReverseRpcTest() {
    reverseLoading = true;
    reverseResult = null;
    try {
      const res = await rpc.call("help.rpc.reverse_call", {
        method: "client.get_environment",
        message: "Запрос характеристик браузера из ядра PyFerro",
      });
      reverseResult = res;
    } catch (err: any) {
      reverseResult = { error: String(err.message || err) };
    } finally {
      reverseLoading = false;
    }
  }
  async function checkMigrationStatus() {
    migrationLoading = true;
    try {
      const res = await rpc.call("help.migrations.status");
      migrationStatus = res;
    } catch (e: any) {
      migrationStatus = { error: e.message || String(e) };
    } finally {
      migrationLoading = false;
    }
  }

  async function runDryRunSimulation() {
    dryRunLoading = true;
    try {
      const res = await rpc.call("help.migrations.dry_run");
      dryRunResult = res;
    } catch (e: any) {
      dryRunResult = { error: e.message || String(e) };
    } finally {
      dryRunLoading = false;
    }
  }

  function openSectionDirectly(sectionKey: string) {
    openSections[sectionKey] = true;
    setTimeout(() => {
      const el = document.getElementById(`section-${sectionKey}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 50);
  }
</script>

<!-- Главный контейнер витрины -->
<div class="min-h-screen bg-slate-50 text-slate-800 py-8 px-4 font-sans relative">

  <!-- БОКОВОЙ ФРЕЙМ ВКЛАДОК (СЛЕВА НА ЭКРАНАХ >= 1560px) -->
  <aside class="showcase-sidebar">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-2">
      <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1 mb-2">
        Разделы Справки
      </div>

      <!-- Кнопка Вкладка 1: RPC -->
      <button
        onclick={() => (activeTab = "rpc")}
        class={`w-full text-left p-2.5 rounded-lg border transition-all ${
          activeTab === "rpc"
            ? "bg-blue-50/90 border-blue-300 text-blue-900 shadow-xs"
            : "border-transparent text-slate-600 hover:bg-slate-50"
        }`}
      >
        <div class="flex items-center justify-between">
          <span class="font-bold text-xs">⚡ 1. RPC-методы</span>
          <span class="text-[9px] font-mono px-1 py-0.2 rounded bg-blue-100 text-blue-700">WSRPC</span>
        </div>
        <p class="text-[11px] text-slate-500 mt-1">Синтаксис, стриминг, ошибки</p>
      </button>

      <!-- Кнопка Вкладка 2: Миграции -->
      <!-- Кнопка Вкладка 2: Миграции -->
      <button
        onclick={() => (activeTab = "migrations")}
        class={`w-full text-left p-2.5 rounded-lg border transition-all ${
          activeTab === "migrations"
            ? "bg-emerald-50/90 border-emerald-300 text-emerald-900 shadow-xs"
            : "border-transparent text-slate-600 hover:bg-slate-50"
        }`}
      >
        <div class="flex items-center justify-between">
          <span class="font-bold text-xs">🛡️ 2. Обновление схемы</span>
          <span class="text-[9px] font-mono px-1 py-0.2 rounded bg-emerald-100 text-emerald-700">Safe Evol</span>
        </div>
        <p class="text-[11px] text-slate-500 mt-1">Миграции, VACUUM, CLI</p>
      </button>

      <!-- Кнопка Вкладка 3: SEO & Индексация -->
      <button
        onclick={() => (activeTab = "seo")}
        class={`w-full text-left p-2.5 rounded-lg border transition-all ${
          activeTab === "seo"
            ? "bg-amber-50/90 border-amber-300 text-amber-900 shadow-xs"
            : "border-transparent text-slate-600 hover:bg-slate-50"
        }`}
      >
        <div class="flex items-center justify-between">
          <span class="font-bold text-xs">🌐 3. SEO и Поисковики</span>
          <span class="text-[9px] font-mono px-1 py-0.2 rounded bg-amber-100 text-amber-700">Dynamic</span>
        </div>
        <p class="text-[11px] text-slate-500 mt-1">Таблицы, ссылки, боты, GUI</p>
      </button>
    </div>

    <!-- Быстрая навигация по секциям активной вкладки -->
    <div class="mt-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm text-xs space-y-1">
      <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1 mb-1">
        Содержание:
      </div>
      {#if activeTab === "rpc"}
        <button
          onclick={() => openSectionDirectly("rpc_basic")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-blue-600">1</span>
          <span class="truncate">Базовый RPC</span>
        </button>
        <button
          onclick={() => openSectionDirectly("rpc_stream")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-emerald-600">2</span>
          <span class="truncate">Мультивывод (стриминг)</span>
        </button>
        <button
          onclick={() => openSectionDirectly("rpc_errors")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-rose-600">3</span>
          <span class="truncate">Контекст & RPCError</span>
        </button>
        <button
          onclick={() => openSectionDirectly("rpc_tabular")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-indigo-600">4</span>
          <span class="truncate">Табулярное сжатие</span>
        </button>
        <button
          onclick={() => openSectionDirectly("rpc_reverse")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-amber-600">5</span>
          <span class="truncate">Симметричный Reverse RPC</span>
        </button>
      {:else if activeTab === "migrations"}
        <button
          onclick={() => openSectionDirectly("mig_architecture")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-blue-600">1</span>
          <span class="truncate">Контракт версий</span>
        </button>
        <button
          onclick={() => openSectionDirectly("mig_snapshot")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-emerald-600">2</span>
          <span class="truncate">VACUUM & Двойная защита</span>
        </button>
        <button
          onclick={() => openSectionDirectly("mig_cli")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-purple-600">3</span>
          <span class="truncate">CLI команды pyferro</span>
        </button>
      {:else}
        <button
          onclick={() => openSectionDirectly("seo_intro")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-amber-600">1</span>
          <span class="truncate">Зачем SEO в SPA?</span>
        </button>
        <button
          onclick={() => openSectionDirectly("seo_tables")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-blue-600">2</span>
          <span class="truncate">Поля таблиц в базе</span>
        </button>
        <button
          onclick={() => openSectionDirectly("seo_url")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-emerald-600">3</span>
          <span class="truncate">Сборка адреса URL</span>
        </button>
        <button
          onclick={() => openSectionDirectly("seo_crawler")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-purple-600">4</span>
          <span class="truncate">Цепочка ссылок ботов</span>
        </button>
        <button
          onclick={() => openSectionDirectly("seo_gui")}
          class="w-full text-left px-2 py-1.5 rounded hover:bg-slate-50 text-slate-700 flex items-center space-x-2 transition-colors"
        >
          <span class="w-4 text-center font-mono font-bold text-rose-600">5</span>
          <span class="truncate">Настройка в Mission Control</span>
        </button>
      {/if}
    </div>
  </aside>

  <!-- ОСНОВНОЙ ФРЕЙМ: 1024px РОВНО ПО ЦЕНТРУ ЭКРАНА -->
  <div class="w-full max-w-[1024px] mx-auto">

    <!-- ВЕРХНЯЯ ПАНЕЛЬ / ШАПКА -->
    <header class="flex items-center justify-between border-b border-slate-200 pb-5 mb-6">
      <div>
        <div class="flex items-center space-x-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-xl shadow-sm">
            Fe
          </div>
          <div>
            <h1 class="text-2xl font-bold tracking-tight text-slate-900">
              PyFerro Admin Help <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">v0.7.0</span>
            </h1>
            <p class="text-sm text-slate-500">Живая интерактивная документация и тестовый полигон фреймворка</p>
          </div>
        </div>
      </div>

      <!-- Статус сокета и блок авторизации SSO -->
      <div class="flex items-center space-x-3">
        <div class="flex items-center space-x-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 shadow-sm text-xs">
          {#if connectionState === 'CONNECTED'}
            <span class="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
            <span class="font-medium text-emerald-700">WSRPC Online</span>
            {#if pingRttMs !== null}
              <span class="text-slate-400">|</span>
              <span class="font-mono text-slate-600">{pingRttMs} ms</span>
            {/if}
          {:else if connectionState === 'CONNECTING'}
            <span class="h-2.5 w-2.5 rounded-full bg-amber-400 animate-ping"></span>
            <span class="font-medium text-amber-700">Подключение...</span>
          {:else}
            <span class="h-2.5 w-2.5 rounded-full bg-rose-500"></span>
            <span class="font-medium text-rose-700">Offline</span>
          {/if}
        </div>

        {#if authUser && authUser.authenticated}
          <div class="flex items-center space-x-2">
            <div class="flex items-center space-x-1.5 rounded-full border border-emerald-500/30 bg-emerald-50 px-3 py-1 text-xs">
              <span class="h-2 w-2 rounded-full bg-emerald-500"></span>
              <span class="font-bold text-emerald-800">@{authUser.username}</span>
              {#if authUser.roles && authUser.roles.length > 0}
                <span class="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-700">
                  {authUser.roles[0]}
                </span>
              {/if}
            </div>

            <a
              href="/admin/"
              target="_blank"
              rel="noreferrer"
              class="flex items-center space-x-1 rounded-full bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 shadow-xs transition-colors"
              title="Перейти в панель управления /admin"
            >
              <span>⚙️ Панель /admin</span>
              <span>↗</span>
            </a>

            <button
              type="button"
              onclick={doLogout}
              class="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-500 hover:text-rose-600 hover:border-rose-200 transition-colors cursor-pointer"
              title="Выйти из системы"
            >
              ✕
            </button>
          </div>
        {:else}
          <button
            type="button"
            onclick={() => { isLoginModalOpen = true; loginError = ""; }}
            class="flex items-center space-x-1.5 rounded-full border border-blue-600/30 bg-blue-50 px-3.5 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 shadow-xs transition-colors cursor-pointer"
          >
            <span>👤</span>
            <span>Войти</span>
          </button>
        {/if}
      </div>
    </header>

    <!-- ВЕРХНИЕ ВКЛАДКИ (ПОЯВЛЯЮТСЯ СВЕРХУ, КОГДА НЕ ХВАТАЕТ ШИРИНЫ ДЛЯ БОКОВОЙ ПАНЕЛИ) -->
    <nav class="showcase-topbar space-x-2 border-b border-slate-200 mb-6" aria-label="Tabs">
      <button
        onclick={() => (activeTab = "rpc")}
        class={`flex items-center space-x-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors ${
          activeTab === "rpc"
            ? "border-blue-600 text-blue-600"
            : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
        }`}
      >
        <span>⚡ 1. RPC-методы (WSRPC)</span>
        <span class="text-[11px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">Синтаксис & Потоки</span>
      </button>

      <button
        onclick={() => (activeTab = "migrations")}
        class={`flex items-center space-x-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors ${
          activeTab === "migrations"
            ? "border-blue-600 text-blue-600"
            : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
        }`}
      >
        <span>🛡️ 2. Обновление схемы (Safe Evolution)</span>
        <span class="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5 rounded">Zero-Data-Loss</span>
      </button>

      <button
        onclick={() => (activeTab = "seo")}
        class={`flex items-center space-x-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors ${
          activeTab === "seo"
            ? "border-amber-600 text-amber-700 font-bold"
            : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
        }`}
      >
        <span>🌐 3. SEO и Поисковики</span>
        <span class="text-[11px] bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">Для людей</span>
      </button>
    </nav>
    <!-- ========================================================================= -->
    <!-- ВКЛАДКА 1: RPC-МЕТОДЫ (ЕДИНЫЙ ПОТОК: ОПИСАНИЕ -> КОД -> ЖИВОЙ ТЕСТ)       -->
    <!-- ========================================================================= -->
    {#if activeTab === "rpc"}
      <div class="space-y-6">
        
        <!-- Вводный блок -->
        <div class="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-xl font-bold text-slate-900 mb-2">Архитектура WSRPC в PyFerro</h2>
          <p class="text-sm text-slate-600 leading-relaxed">
            В отличие от традиционного REST, где каждое действие требует нового TCP-рукопожатия и HTTP-заголовков,
            <strong>PyFerro использует симметричный протокол JSON-RPC 2.0 поверх постоянного WebSocket (WSRPC)</strong>.
            Вызовы разрешаются за <strong>0.3–1.0 мс</strong>, а сервер может в любой момент слать асинхронные push-уведомления.
          </p>
        </div>

        <!-- СЕКЦИЯ 1: БАЗОВЫЙ ОБРАБОТЧИК RPC -->
        <div id="section-rpc_basic" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <!-- Заголовок / Аккордеон кликабелен -->
          <button
            onclick={() => toggleSection("rpc_basic")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-blue-700 font-bold text-xs">1</span>
                <h3 class="text-base font-bold text-slate-900">Базовый обработчик RPC & Простой вызов</h3>
                <span class="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono">@rpc_method</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Методы объявляются через простой декоратор. Функция принимает контекст <code>session</code> и словарь <code>params</code>.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["rpc_basic"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['rpc_basic'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          <!-- Развернутое тело секции: Код + Интерактивный тест прямо здесь -->
          {#if openSections["rpc_basic"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример кода на Python:</h4>
                <CodeBox
                  title="handlers.py — Базовый RPC метод"
                  code={`from pyferro.core.session import rpc_method, JsonRpcSession

@rpc_method("help.rpc.echo")
async def help_echo(session: JsonRpcSession, params: dict) -> dict:
    message = params.get("message", "Привет!")
    # Возвращаемый словарь автоматически упаковывается в JSON-RPC 2.0 result
    return {
        "echo": message,
        "length": len(message),
        "author": session.username
    }`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ ПРЯМО ВНУТРИ -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">🎯</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Вызов метода help.rpc.echo</span>
                  </div>
                  {#if echoRtt !== null}
                    <span class="text-xs font-mono bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded font-semibold">
                      RTT: {echoRtt} ms
                    </span>
                  {/if}
                </div>

                <div class="grid grid-cols-12 gap-4 items-end">
                  <div class="col-span-8">
                    <label for="echo-msg-field" class="block text-xs font-medium text-slate-600 mb-1">Параметр message:</label>
                    <input
                      id="echo-msg-field"
                      type="text"
                      bind:value={echoMessage}
                      class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                      placeholder="Введите сообщение для отправки серверу"
                    />
                  </div>
                  <div class="col-span-4">
                    <button
                      onclick={runEchoTest}
                      disabled={echoLoading}
                      class="w-full rounded-md bg-blue-600 py-2 px-4 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors disabled:opacity-50"
                    >
                      {echoLoading ? "Отправка..." : "🚀 Выполнить RPC-вызов"}
                    </button>
                  </div>
                </div>

                {#if echoResult}
                  <div class="mt-4 rounded-md border p-3 text-xs font-mono bg-emerald-50/60 border-emerald-200 text-emerald-950">
                    <div class="font-bold mb-1">✓ Результат ответа сервера (Result):</div>
                    <pre class="overflow-x-auto text-[12px] leading-relaxed">{JSON.stringify(echoResult.data, null, 2)}</pre>
                  </div>
                {/if}

                {#if echoWireFrame}
                  <div class="mt-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
                    <span class="font-semibold text-slate-700">Сетевой фрейм WebSocket (JSON-RPC 2.0 wire):</span>
                    <pre class="bg-slate-100 p-2.5 rounded text-[11px] font-mono text-slate-700 overflow-x-auto mt-1">--&gt; {echoWireFrame.req}
&lt;-- {echoWireFrame.res}</pre>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>

        <!-- СЕКЦИЯ 2: ПОТОКОВЫЙ МУЛЬТИВЫВОД (СТРИМИНГ) -->
        <div id="section-rpc_stream" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("rpc_stream")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs">2</span>
                <h3 class="text-base font-bold text-slate-900">Потоковый мультивывод & Стриминг чанков</h3>
                <span class="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded font-mono">send_notification</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Когда задача длится секунды (генерация отчета, парсинг, бэкап), сервер транслирует промежуточные события по сокету клиенту.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["rpc_stream"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['rpc_stream'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["rpc_stream"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример кода на Python:</h4>
                <CodeBox
                  title="handlers.py — Серверный стриминг прогресса"
                  code={`import asyncio
from pyferro.core.session import rpc_method, JsonRpcSession

@rpc_method("help.rpc.multi_output")
async def help_multi_output(session: JsonRpcSession, params: dict):
    steps = params.get("steps", 5)
    for i in range(1, steps + 1):
        await asyncio.sleep(0.15)
        # Отправляем легковесное push-уведомление клиенту по сокету:
        await session.send_notification("help.stream_chunk", {
            "step": i,
            "progress": int((i / steps) * 100),
            "status_text": f"Обработка блока #{i} из {steps}..."
        })

    # Финальный ответ на исходный RPC-запрос
    return {"status": "completed", "total_steps": steps}`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ МУЛЬТИВЫВОДА -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">🌊</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Прием серии серверных пуш-уведомлений</span>
                  </div>
                </div>

                <div class="space-y-4">
                  <div class="flex items-center space-x-4">
                    <span class="text-xs font-medium text-slate-600">Количество порций данных:</span>
                    <input
                      type="range"
                      min="3"
                      max="10"
                      bind:value={streamSteps}
                      class="w-48 accent-emerald-600"
                    />
                    <span class="font-mono font-bold text-xs text-slate-900 bg-slate-100 px-2 py-1 rounded">{streamSteps} шагов</span>

                    <button
                      onclick={runStreamTest}
                      disabled={streamRunning}
                      class="ml-auto rounded-md bg-emerald-600 py-2 px-5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50"
                    >
                      {streamRunning ? "Стриминг в процессе..." : "Запустить потоковый мультивывод"}
                    </button>
                  </div>

                  {#if streamRunning || streamEvents.length > 0}
                    <div class="space-y-2 mt-2">
                      <div class="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
                        <div
                          class="bg-emerald-600 h-2.5 transition-all duration-150 rounded-full"
                          style={`width: ${streamProgress}%`}
                        ></div>
                      </div>

                      <div class="max-h-48 overflow-y-auto space-y-1.5 rounded border border-slate-200 bg-slate-50 p-3 text-xs font-mono">
                        {#each streamEvents as evt}
                          <div class="flex items-center justify-between text-slate-700 border-b border-slate-100 last:border-0 pb-1">
                            <span class="text-emerald-700 font-semibold">{evt.text}</span>
                            <span class="text-slate-400">+{evt.elapsed} ms</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  {/if}

                  {#if streamFinalResult}
                    <div class="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-xs font-mono text-emerald-950">
                      <span class="font-bold">✓ Завершено: </span>
                      <span>{streamFinalResult.summary || JSON.stringify(streamFinalResult)}</span>
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          {/if}
        </div>

        <!-- СЕКЦИЯ 3: СЕССИОННЫЙ КОНТЕКСТ И ОШИБКИ RPCError -->
        <div id="section-rpc_errors" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("rpc_errors")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-rose-100 text-rose-700 font-bold text-xs">3</span>
                <h3 class="text-base font-bold text-slate-900">Контекст сессии & Ошибки бизнес-логики</h3>
                <span class="text-xs bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 rounded font-mono">raise RPCError</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Параметры читаются напрямую (ошибки валидации транслируются автоматически), а <code>RPCError</code> используется только для прикладных бизнес-правил.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["rpc_errors"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['rpc_errors'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["rpc_errors"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div class="rounded-lg bg-blue-50/70 border border-blue-200 p-4 text-xs text-slate-700 space-y-1.5 leading-relaxed">
                <div class="font-bold text-blue-900 flex items-center space-x-1.5">
                  <span>💡</span>
                  <span>Чистый Python без бойлерплейта:</span>
                </div>
                <p>
                  • <strong>Никаких ручных проверок:</strong> читайте обязательные параметры прямо из словаря: <code>order_id = params["order_id"]</code>. Если ключ отсутствует или имеет неверный тип, ядро PyFerro автоматически перехватит <code>KeyError</code> / <code>ValueError</code> и вернет клиенту спецификационный <code>Invalid params (-32602)</code>.
                </p>
                <p>
                  • <strong><code>raise RPCError(code, message)</code></strong> нужен <em>только</em> для правил предметной области (заказ уже передан курьеру, недостаточно средств на счете и т.д.).
                </p>
                <p>
                  • <strong>Системные сбои:</strong> непредвиденные баги и падения БД автоматически превращаются в безопасный <code>Internal server error (-32603)</code> без утечки приватных данных наружу.
                </p>
              </div>

              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример кода на Python:</h4>
                <CodeBox
                  title="handlers.py — Чистая бизнес-логика и точечный RPCError"
                  code={`from pyferro.core.session import rpc_method, RPCError, JsonRpcSession

@rpc_method("orders.cancel")
async def cancel_order(session: JsonRpcSession, params: dict):
    # 1. Параметры читаются напрямую (KeyError автоматически -> Invalid params -32602):
    order_id = params["order_id"]

    # 2. Доступ к авторизованному контексту пользователя:
    user_id = session.user_id
    user_roles = session.user_roles

    # 3. raise RPCError используется ТОЛЬКО для правил бизнес-правил:
    order = await get_order(order_id)
    if order.status == "shipped":
        raise RPCError(-32001, "Заказ уже отправлен курьеру и не может быть отменен")

    await order.cancel(by_user=user_id)
    return {"status": "cancelled", "order_id": order_id}`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ ОШИБКИ -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">⚠️</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Генерация стандартизированной ошибки RPCError(-32000)</span>
                  </div>
                </div>

                <div class="flex items-center space-x-4">
                  <p class="text-xs text-slate-600">
                    Нажатие кнопки отправит вызов <code>help.rpc.echo(simulate_error=True)</code>, чтобы сервер возбудил исключение <code>RPCError</code>.
                  </p>
                  <button
                    onclick={runErrorTest}
                    disabled={errorLoading}
                    class="ml-auto rounded-md bg-rose-600 py-2 px-4 text-xs font-semibold text-white shadow-sm hover:bg-rose-700 transition-colors disabled:opacity-50"
                  >
                    {errorLoading ? "Выполнение..." : "Сгенерировать ошибку"}
                  </button>
                </div>

                {#if errorResult}
                  <div class="mt-4 rounded-md border p-3 text-xs font-mono bg-rose-50/70 border-rose-200 text-rose-950">
                    <div class="font-bold mb-1">❌ Получен объект ошибки (JSON-RPC Error):</div>
                    <div>Код ошибки: <span class="font-bold">{errorResult.code}</span></div>
                    <div>Сообщение: <span class="font-bold">{errorResult.message}</span></div>
                  </div>
                {/if}

                {#if errorWireFrame}
                  <div class="mt-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
                    <span class="font-semibold text-slate-700">Сетевой фрейм WebSocket (JSON-RPC 2.0 wire error):</span>
                    <pre class="bg-slate-100 p-2.5 rounded text-[11px] font-mono text-slate-700 overflow-x-auto mt-1">--&gt; {errorWireFrame.req}
&lt;-- {errorWireFrame.res}</pre>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>
<!-- СЕКЦИЯ 4: ТАБУЛЯРНОЕ СЖАТИЕ ДАННЫХ (RFC 0002) -->
        <div id="section-rpc_tabular" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("rpc_tabular")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs">4</span>
                <h3 class="text-base font-bold text-slate-900">Табулярное сжатие данных (RFC 0002 Tabular Data)</h3>
                <span class="text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded font-mono">@tabular_response</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Устранение дублирования строковых ключей в коллекциях и экономия 60–80% полезной нагрузки сети.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["rpc_tabular"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['rpc_tabular'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["rpc_tabular"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div class="rounded-lg bg-indigo-50/70 border border-indigo-100 p-4 text-xs text-indigo-950 leading-relaxed">
                <div class="font-bold text-indigo-900 mb-1 flex items-center space-x-1.5">
                  <span>💡</span>
                  <span>Почему REST раздувает сетевой трафик:</span>
                </div>
                В стандартном JSON при отдаче массива объектов вида <code>[&lbrace; "id": 1, "service": "auth", "status": "active" &rbrace;, ...]</code>
                названия ключей (<code>"service"</code>, <code>"status"</code>) повторяются сотни раз.
                <strong>PyFerro упаковывает коллекцию в кортежную матрицу:</strong> <code>&lbrace;"$tabular": true, "fields": ["id", "service", "status"], "rows": [[1, "auth", "active"]]&rbrace;</code>.
                Браузерная библиотека <code>@wsrpc/wsrpc</code> распаковывает матрицу автоматически и прозрачно для фронтенд-разработчика.
              </div>

              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример кода на Python:</h4>
                <CodeBox
                  title="handlers.py — Использование @tabular_response"
                  code={`from pyferro.core.session import rpc_method, JsonRpcSession
from pyferro.core.tabular import tabular_response, pack_tabular

# Способ 1: Декоратор метода (авто-упаковка возвращаемого списка)
@rpc_method("help.rpc.tabular_demo")
@tabular_response
async def get_services(session: JsonRpcSession, params: dict) -> list[dict]:
    # Метод возвращает обычный список словарей:
    return await fetch_metrics()

# Способ 2: Прямая упаковка pack_tabular (для raw SQL tuples из cursor.fetchall)
packed = pack_tabular(cursor.fetchall(), fields=["id", "service", "host", "cpu"])`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ ТАБУЛЯРНОГО СЖАТИЯ -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">📊</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Бенчмарк размера сырого JSON vs Табулярного пакета</span>
                  </div>
                  {#if tabularRtt !== null}
                    <span class="text-xs font-mono bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded font-semibold">
                      RTT: {tabularRtt} ms
                    </span>
                  {/if}
                </div>

                <!-- Панель управления объёмом выборки -->
                <div class="flex flex-wrap items-center justify-between gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs mb-4">
                  <div class="flex items-center space-x-2">
                    <span class="font-semibold text-slate-700">Размер выборки записей:</span>
                    <div class="inline-flex rounded-md shadow-xs" role="group">
                      {#each [10, 25, 50, 100] as cnt}
                        <button
                          type="button"
                          onclick={() => (tabularCount = cnt)}
                          class={`px-3 py-1 font-semibold border text-xs transition-colors ${
                            tabularCount === cnt
                              ? 'bg-indigo-600 border-indigo-600 text-white first:rounded-l-md last:rounded-r-md'
                              : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-100 first:rounded-l-md last:rounded-r-md'
                          }`}
                        >
                          {cnt}
                        </button>
                      {/each}
                    </div>
                  </div>

                  <button
                    onclick={runTabularTest}
                    disabled={tabularLoading}
                    class="rounded-md bg-indigo-600 py-1.5 px-4 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center space-x-1.5"
                  >
                    <span>{tabularLoading ? "Генерация и сжатие..." : "🚀 Запросить и сравнить"}</span>
                  </button>
                </div>

                {#if tabularResult && !tabularResult.error}
                  <!-- СРАВНИТЕЛЬНЫЕ KPI КАРТОЧКИ -->
                  <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                    <div class="rounded-lg border border-slate-200 bg-slate-50/80 p-3.5 text-center">
                      <div class="text-[11px] font-bold text-slate-500 uppercase tracking-wide">Сырой JSON (REST)</div>
                      <div class="text-xl font-bold font-mono text-slate-800 mt-1">{tabularResult.raw_bytes} байт</div>
                      <div class="text-[10px] text-slate-400 mt-0.5">Повторение ключей в каждой строке</div>
                    </div>

                    <div class="rounded-lg border border-indigo-200 bg-indigo-50/50 p-3.5 text-center">
                      <div class="text-[11px] font-bold text-indigo-700 uppercase tracking-wide">RFC 0002 ($tabular)</div>
                      <div class="text-xl font-bold font-mono text-indigo-900 mt-1">{tabularResult.packed_bytes} байт</div>
                      <div class="text-[10px] text-indigo-600 mt-0.5">Единая схема + матрица значений</div>
                    </div>

                    <div class="rounded-lg border border-emerald-200 bg-emerald-50/70 p-3.5 text-center">
                      <div class="text-[11px] font-bold text-emerald-800 uppercase tracking-wide">Экономия трафика</div>
                      <div class="text-xl font-bold font-mono text-emerald-600 mt-1">-{tabularResult.saving_pct}%</div>
                      <div class="text-[10px] text-emerald-700 mt-0.5">Чистая компрессия без CPU gzip</div>
                    </div>
                  </div>

                  <!-- Переключение вида -->
                  <div class="border-b border-slate-200 mb-3 flex space-x-3 text-xs">
                    <button
                      onclick={() => (tabularViewTab = "preview")}
                      class={`pb-1.5 font-semibold transition-colors border-b-2 ${
                        tabularViewTab === "preview"
                          ? "border-indigo-600 text-indigo-700"
                          : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      Распакованные данные ({tabularResult.count} строк)
                    </button>
                    <button
                      onclick={() => (tabularViewTab = "wire_tabular")}
                      class={`pb-1.5 font-semibold transition-colors border-b-2 ${
                        tabularViewTab === "wire_tabular"
                          ? "border-indigo-600 text-indigo-700"
                          : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      Сетевой пакет $tabular
                    </button>
                    <button
                      onclick={() => (tabularViewTab = "wire_raw")}
                      class={`pb-1.5 font-semibold transition-colors border-b-2 ${
                        tabularViewTab === "wire_raw"
                          ? "border-indigo-600 text-indigo-700"
                          : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      Сырой JSON (традиционный)
                    </button>
                  </div>

                  {#if tabularViewTab === "preview"}
                    <div class="overflow-x-auto rounded border border-slate-200">
                      <table class="w-full text-[11px] text-left">
                        <thead class="bg-slate-100 text-slate-600 font-semibold uppercase">
                          <tr>
                            <th class="p-2 border-b">ID</th>
                            <th class="p-2 border-b">Сервис</th>
                            <th class="p-2 border-b">Хост</th>
                            <th class="p-2 border-b">CPU %</th>
                            <th class="p-2 border-b">RAM (MB)</th>
                            <th class="p-2 border-b">Статус</th>
                            <th class="p-2 border-b">Latency</th>
                          </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 font-mono">
                          {#each tabularResult.raw_records.slice(0, 6) as rec}
                            <tr class="hover:bg-slate-50/70">
                              <td class="p-2 text-slate-500">{rec.id}</td>
                              <td class="p-2 font-bold text-slate-800">{rec.service}</td>
                              <td class="p-2 text-slate-600">{rec.host}</td>
                              <td class="p-2 text-slate-700">{rec.cpu_usage}%</td>
                              <td class="p-2 text-slate-700">{rec.memory_mb} MB</td>
                              <td class="p-2">
                                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                  {rec.status}
                                </span>
                              </td>
                              <td class="p-2 text-slate-500">{rec.latency_ms} ms</td>
                            </tr>
                          {/each}
                        </tbody>
                      </table>
                    </div>
                    {#if tabularResult.raw_records.length > 6}
                      <p class="text-[10px] text-slate-400 mt-1 italic text-right">Показаны первые 6 строк из {tabularResult.count}</p>
                    {/if}
                  {:else if tabularViewTab === "wire_tabular"}
                    <pre class="bg-slate-900 text-indigo-200 p-3 rounded text-[11px] font-mono overflow-x-auto max-h-56">{JSON.stringify(tabularResult.tabular_package, null, 2)}</pre>
                  {:else}
                    <pre class="bg-slate-900 text-slate-300 p-3 rounded text-[11px] font-mono overflow-x-auto max-h-56">{JSON.stringify(tabularResult.raw_records.slice(0, 4), null, 2)}</pre>
                  {/if}
                {/if}
              </div>
            </div>
          {/if}
        </div>

        <!-- СЕКЦИЯ 5: ДВУНАПРАВЛЕННЫЙ REVERSE RPC -->
        <div id="section-rpc_reverse" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("rpc_reverse")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-amber-700 font-bold text-xs">5</span>
                <h3 class="text-base font-bold text-slate-900">Симметричный Reverse RPC (Вызов браузера сервером)</h3>
                <span class="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded font-mono">session.send_request</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Сервер может выступать в роли клиента и вызывать зарегистрированные функции прямо в JavaScript-рантайме браузера.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["rpc_reverse"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['rpc_reverse'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["rpc_reverse"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div class="rounded-lg bg-amber-50/70 border border-amber-200 p-4 text-xs text-amber-950 leading-relaxed">
                <div class="font-bold text-amber-900 mb-1 flex items-center space-x-1.5">
                  <span>🔄</span>
                  <span>Принцип симметричного WSRPC протокола:</span>
                </div>
                В обычных технологиях (HTTP REST, SSE) связь односторонняя: браузер шлёт запрос, сервер отвечает.
                В <strong>PyFerro сокет является двунаправленным симметричным каналом</strong>: сервер в любой момент может отправить
                запрос в браузер (<code>await session.send_request("method", params)</code>) и дождаться вычисления результата в JavaScript!
              </div>

              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример кода на Python и TypeScript:</h4>
                <CodeBox
                  title="handlers.py — Вызов браузерного метода с сервера"
                  code={`# Python (Сервер PyFerro):
@rpc_method("help.rpc.reverse_call")
async def request_browser_stats(session: JsonRpcSession, params: dict) -> dict:
    # Сервер отправляет запрос клиенту и асинхронно ждет return из JavaScript:
    client_env = await session.send_request("client.get_environment", {
        "prompt": "Запрос характеристик браузера"
    }, timeout=5.0)

    return {"status": "success", "client_env": client_env}`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ REVERSE RPC -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">⚡</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Сервер запрашивает разрешение экрана и таймзону из вашего браузера</span>
                  </div>
                  {#if reverseResult && reverseResult.reverse_rtt_ms}
                    <span class="text-xs font-mono bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded font-semibold">
                      Сквозной Reverse RTT: {reverseResult.reverse_rtt_ms} ms
                    </span>
                  {/if}
                </div>

                <!-- Диаграмма петли вызова -->
                <div class="bg-slate-50 p-3.5 rounded-lg border border-slate-200 mb-4">
                  <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Маршрут сквозного запроса (Roundtrip):</div>
                  <div class="flex items-center justify-between text-[11px] font-medium text-slate-600 gap-1 overflow-x-auto py-1">
                    <div class="px-2.5 py-1.5 rounded bg-white border border-slate-200 shadow-xs shrink-0 text-center">
                      <span class="block text-[9px] text-slate-400">Шаг 1</span>
                      Клик в UI
                    </div>
                    <span class="text-slate-400">➔</span>
                    <div class="px-2.5 py-1.5 rounded bg-blue-50 border border-blue-200 text-blue-900 shadow-xs shrink-0 text-center">
                      <span class="block text-[9px] text-blue-500">Шаг 2</span>
                      Вызов сервера
                    </div>
                    <span class="text-slate-400">➔</span>
                    <div class="px-2.5 py-1.5 rounded bg-amber-50 border border-amber-200 text-amber-900 shadow-xs shrink-0 text-center">
                      <span class="block text-[9px] text-amber-500">Шаг 3 (Reverse)</span>
                      send_request в браузер
                    </div>
                    <span class="text-slate-400">➔</span>
                    <div class="px-2.5 py-1.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-900 shadow-xs shrink-0 text-center">
                      <span class="block text-[9px] text-emerald-500">Шаг 4</span>
                      Ответ из JS ➔ Серверу
                    </div>
                  </div>
                </div>

                <div class="flex items-center justify-between mb-4">
                  <p class="text-xs text-slate-500">
                    Нажмите кнопку ниже: сервер вызовет функцию <code>client.get_environment</code>, которая прямо сейчас зарегистрирована в этом окне браузера.
                  </p>
                  <button
                    onclick={runReverseRpcTest}
                    disabled={reverseLoading}
                    class="rounded-md bg-amber-600 py-2 px-4 text-xs font-semibold text-white shadow-sm hover:bg-amber-700 transition-colors disabled:opacity-50 shrink-0 ml-3"
                  >
                    {reverseLoading ? "Выполняется обратный вызов..." : "⚡ Запустить Reverse RPC"}
                  </button>
                </div>

                {#if reverseResult}
                  {#if reverseResult.error}
                    <div class="rounded-md border p-3 text-xs font-mono bg-rose-50 border-rose-200 text-rose-900">
                      ❌ {reverseResult.error}
                    </div>
                  {:else}
                    <div class="rounded-lg border border-amber-200 bg-amber-50/40 p-4 space-y-3">
                      <div class="flex items-center justify-between text-xs">
                        <span class="font-bold text-amber-900">✓ Ответ успешно получен сервером из JavaScript:</span>
                        <span class="font-mono text-slate-500 text-[11px]">Метод: {reverseResult.invoked_method}</span>
                      </div>

                      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono bg-white p-3 rounded border border-amber-100">
                        <div>
                          <span class="text-[10px] text-slate-400 block font-sans">Разрешение окна:</span>
                          <span class="font-bold text-slate-800">{reverseResult.client_reported.screen_resolution}</span>
                        </div>
                        <div>
                          <span class="text-[10px] text-slate-400 block font-sans">Глубина цвета:</span>
                          <span class="font-bold text-slate-800">{reverseResult.client_reported.color_depth}</span>
                        </div>
                        <div>
                          <span class="text-[10px] text-slate-400 block font-sans">Таймзона:</span>
                          <span class="font-bold text-slate-800">{reverseResult.client_reported.timezone}</span>
                        </div>
                        <div>
                          <span class="text-[10px] text-slate-400 block font-sans">Язык браузера:</span>
                          <span class="font-bold text-slate-800">{reverseResult.client_reported.language}</span>
                        </div>
                        <div>
                          <span class="text-[10px] text-slate-400 block font-sans">Локальные часы:</span>
                          <span class="font-bold text-slate-800">{reverseResult.client_reported.client_clock}</span>
                        </div>
                        <div>
                          <span class="text-[10px] text-slate-400 block font-sans">User Agent:</span>
                          <span class="text-slate-600 truncate block">{reverseResult.client_reported.user_agent}</span>
                        </div>
                      </div>

                      <div class="text-[11px] text-amber-900 italic">
                        {reverseResult.server_note}
                      </div>
                    </div>
                  {/if}
                {/if}

                {#if reverseHistory.length > 0}
                  <div class="mt-4 border-t border-slate-100 pt-3">
                    <span class="block text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-2">Журнал входящих вызовов браузера (Reverse Invocations):</span>
                    <div class="space-y-1.5 font-mono text-[11px]">
                      {#each reverseHistory as item}
                        <div class="flex items-center justify-between bg-slate-50 p-2 rounded border border-slate-200">
                          <div class="flex items-center space-x-2">
                            <span class="text-amber-600 font-bold">📥 {item.method}</span>
                            <span class="text-slate-400 text-[10px]">({item.prompt})</span>
                          </div>
                          <span class="text-slate-400 text-[10px]">{item.time}</span>
                        </div>
                      {/each}
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- ========================================================================= -->
    <!-- ВКЛАДКА 2: ОБНОВЛЕНИЯ СХЕМЫ (SAFE EVOLUTION)                              -->
    <!-- ========================================================================= -->
    {#if activeTab === "migrations"}
      <div class="space-y-6">
        
        <!-- Вводный блок с инвариантом SemVer -->
        <div class="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-xl font-bold text-slate-900 mb-2">Safe Evolution Engine: Безопасные обновления PyFerro</h2>
          <p class="text-sm text-slate-600 leading-relaxed mb-4">
            Главный постулат фреймворка: <strong>Zero-Data-Loss</strong>. База данных никогда не должна ломаться
            или повреждаться при обновлении пакета фреймворка. 
            Система миграций строго изолирует системные таблицы (<code>pf_*</code>), автоматически выполняет моментальные снимки базы
            через SQLite <code>VACUUM INTO</code> и блокирует некорректные доисторические схемы.
          </p>

          <div class="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-xs text-emerald-950">
            <div class="font-bold text-emerald-900 flex items-center space-x-1.5 mb-1">
              <span>🛡️</span>
              <span>Архитектурный инвариант SemVer:</span>
            </div>
            <p class="leading-relaxed">
              <strong>Субминорные обновления (Patch: 0.33.12 ➔ 0.33.16) физически гарантируют отсутствие изменений схемы БД.</strong>
              Патчи можно накатывать в продакшене без малейшего риска задеть данные.
              Миграции требуются <strong>только</strong> при переходе между минорными версиями (<code>0.33.x ➔ 0.34.0</code>).
            </p>
          </div>
        </div>

        <!-- СЕКЦИЯ 1: КОНТРАКТ ВЕРСИОННОГО ШАГА И СТАТУС БАЗЫ -->
        <div id="section-mig_architecture" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("mig_architecture")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-blue-700 font-bold text-xs">1</span>
                <h3 class="text-base font-bold text-slate-900">Контракт версионного файла миграции & Проверка статуса</h3>
                <span class="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono">pre_check / upgrade / downgrade</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Каждый шаг изолирован, содержит проверку готовности окружения и зеркальный откат назад.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["mig_architecture"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['mig_architecture'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["mig_architecture"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример файла миграции на Python:</h4>
                <CodeBox
                  title="pyferro/migrations/versions/0002_add_user_bio.py"
                  code={`from pyferro.migrations.context import MigrationContext

VERSION = "0002_add_user_bio"
DESCRIPTION = "Добавление поля bio и индекса в pf_auth_user"

async def pre_check(ctx: MigrationContext) -> bool:
    """Фаза 1: Разведка (только чтение). Проверяем наличие таблицы."""
    return await ctx.has_table("pf_auth_user")

async def upgrade(ctx: MigrationContext) -> None:
    """Фаза 2: Накат изменений."""
    await ctx.report_progress(30, "Проверка и добавление колонки bio...")
    if not await ctx.has_column("pf_auth_user", "bio"):
        await ctx.add_column("pf_auth_user", "bio", "TEXT", nullable=True)

    await ctx.report_progress(70, "Создание индекса...")
    await ctx.create_index("ix_user_bio", "pf_auth_user", ["bio"])

async def downgrade(ctx: MigrationContext) -> None:
    """Фаза 3: Зеркальный откат назад."""
    await ctx.drop_index("ix_user_bio")
    await ctx.drop_column("pf_auth_user", "bio")`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ СТАТУСА СХЕМЫ -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">🔍</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Опрос состояния таблицы pf_schema_migrations</span>
                  </div>
                  <button
                    onclick={checkMigrationStatus}
                    disabled={migrationLoading}
                    class="rounded-md bg-blue-600 py-1.5 px-3.5 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors disabled:opacity-50"
                  >
                    {migrationLoading ? "Опрос схемы..." : "🔍 Проверить статус БД"}
                  </button>
                </div>

                {#if migrationStatus}
                  <div class="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2.5 text-xs">
                    <div class="flex items-center justify-between">
                      <span class="text-slate-600">Состояние схемы данных:</span>
                      <span class={`font-semibold px-2 py-0.5 rounded-full ${migrationStatus.is_up_to_date ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                        {migrationStatus.is_up_to_date ? '✓ Схема полностью актуальна' : '⏳ Требует наката'}
                      </span>
                    </div>

                    <div class="flex items-center justify-between">
                      <span class="text-slate-600">Последняя примененная ревизия:</span>
                      <span class="font-mono font-bold text-slate-900">{migrationStatus.latest_applied || 'нет'}</span>
                    </div>

                    <div class="flex items-center justify-between">
                      <span class="text-slate-600">Применено шагов:</span>
                      <span class="font-mono font-semibold text-slate-800">{migrationStatus.applied_count ?? 1}</span>
                    </div>

                    {#if migrationStatus.applied && migrationStatus.applied.length > 0}
                      <div class="mt-3 border-t border-slate-200 pt-2.5">
                        <span class="block text-xs font-bold text-slate-700 mb-2">История примененных ревизий в pf_schema_migrations:</span>
                        <div class="space-y-1.5">
                          {#each migrationStatus.applied as app}
                            <div class="flex items-center justify-between text-xs font-mono bg-white p-2 rounded border border-slate-200">
                              <span class="text-emerald-700 font-semibold">✓ {app.version}</span>
                              <span class="text-slate-400">{app.execution_time_ms} ms</span>
                            </div>
                          {/each}
                        </div>
                      </div>
                    {/if}
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>

        <!-- СЕКЦИЯ 2: НАТИВНЫЙ БЭКАП VACUUM INTO -->
        <div id="section-mig_snapshot" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("mig_snapshot")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs">2</span>
                <h3 class="text-base font-bold text-slate-900">Моментальный нативный снимок (SQLite VACUUM INTO)</h3>
                <span class="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded font-mono">Zero-Data-Loss</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Создание целостной дефрагментированной копии на лету без блокировки читателей и авто-ротация последних 5 снимков.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["mig_snapshot"] ? "Свернуть" : "Развернуть пример и тест"}</span>
              <span class="transform transition-transform duration-200 {openSections['mig_snapshot'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["mig_snapshot"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-5">
              <div>
                <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Пример кода на Python:</h4>
                <CodeBox
                  title="pyferro/migrations/context.py — Теневой снимок"
                  code={`# Нативная команда SQLite создает 100% целостный дефрагментированный файл:
snapshot_path = f".ferro_snapshots/snapshot_{timestamp}.db"
await ctx.execute_raw(f"VACUUM INTO '{snapshot_path}'")

# Авто-ротация снимков: система автоматически удаляет старые бэкапы (FIFO),
# сохраняя только последние 5 копий и защищая диск от переполнения.`}
                />
              </div>

              <!-- ЖИВОЙ ТЕСТ БЭКАПА -->
              <div class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">🛡️</span>
                    <span class="text-sm font-bold text-slate-900">Живой тест: Симуляция проверки целостности и готовности снимка</span>
                  </div>
                  <button
                    onclick={runDryRunSimulation}
                    disabled={dryRunLoading}
                    class="rounded-md bg-emerald-600 py-1.5 px-3.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50"
                  >
                    {dryRunLoading ? "Проверка..." : "🛡️ Симулировать проверку VACUUM INTO"}
                  </button>
                </div>

                {#if dryRunResult}
                  <div class="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4 text-xs text-emerald-950 font-mono space-y-1.5">
                    <div class="font-bold text-sm flex items-center space-x-1.5 text-emerald-900">
                      <span>✓</span>
                      <span>Целостность схемы подтверждена (за {dryRunResult.check_duration_ms} ms)</span>
                    </div>
                    <div class="text-xs text-emerald-800">{dryRunResult.message}</div>
                    <div class="text-[11px] text-emerald-700">Движок СУБД: {dryRunResult.target_engine}</div>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>

        <!-- СЕКЦИЯ 3: КОНСОЛЬНЫЕ КОМАНДЫ CLI -->
        <div id="section-mig_cli" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
          <button
            onclick={() => toggleSection("mig_cli")}
            class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
          >
            <div>
              <div class="flex items-center space-x-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-full bg-slate-200 text-slate-700 font-bold text-xs">3</span>
                <h3 class="text-base font-bold text-slate-900">Управление миграциями через консольный CLI</h3>
                <span class="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono">pyferro migrate</span>
              </div>
              <p class="text-xs text-slate-500 mt-1 ml-8">
                Удобные команды для CI/CD, Docker entrypoints и терминала администратора.
              </p>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["mig_cli"] ? "Свернуть" : "Развернуть команды"}</span>
              <span class="transform transition-transform duration-200 {openSections['mig_cli'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["mig_cli"]}
            <div class="p-6 bg-slate-50/40 border-t border-slate-100 space-y-4">
              <CodeBox
                language="bash"
                title="Терминал разработчика / CI/CD"
                code={`# 1. Посмотреть статус примененных и ожидающих миграций:
pyferro migrate status

# 2. Накатить все свежие миграции с автоматическим созданием бэкапа:
pyferro migrate up

# 3. Откатить последнюю миграцию назад:
pyferro migrate rollback

# 4. Зафиксировать ревизию как примененную (Stamp) без выполнения кода:
pyferro migrate stamp 0001_baseline_v0.7.0`}
              />
            </div>
          {/if}
        </div>

      </div>
    {/if}
    <!-- ========================================================================= -->
    <!-- ВКЛАДКА 3: SEO И ИНДЕКСАЦИЯ ДЛЯ ЛЮДЕЙ (ПОШАГОВЫЙ ГИД НА ПРИМЕРЕ ФОРУМА)      -->
    <!-- ========================================================================= -->
    {#if activeTab === "seo"}
      <div class="space-y-6">

        <!-- ВВОДНЫЙ БЛОК -->
        <div class="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center space-x-3">
              <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-800 font-bold text-lg">🌐</span>
              <div>
                <h2 class="text-xl font-bold text-slate-900">Поисковая оптимизация и Индексация (SEO)</h2>
                <p class="text-xs text-slate-500">Как подружить быстрое SPA-приложение с поисковиками Яндекс, Google и мессенджерами</p>
              </div>
            </div>
            <span class="text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
              Руководство без заумных терминов
            </span>
          </div>

          <p class="text-sm text-slate-600 leading-relaxed mt-2">
            В этом разделе мы простыми словами, на примере обычного <strong>Форума сообщества</strong>, разберем:
            откуда берутся страницы в поиске, как собираются ссылки, зачем нужно ключевое слово <code class="font-mono text-xs bg-slate-100 text-slate-800 px-1 py-0.5 rounded border border-slate-200">&#123;parent.slug&#125;</code>
            и как за пару кликов настроить поисковую оптимизацию в панели управления <strong>Mission Control</strong>.
          </p>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 pt-4 border-t border-slate-100 text-xs">
            <div class="p-3 rounded-lg bg-blue-50/60 border border-blue-100 text-blue-900">
              <div class="font-bold flex items-center space-x-1 mb-1">
                <span>⚡</span>
                <span>Для живых людей</span>
              </div>
              <p class="text-slate-600">Сайт открывается мгновенно как одностраничное приложение (SPA) — без перезагрузок и мерцания экрана.</p>
            </div>
            <div class="p-3 rounded-lg bg-emerald-50/60 border border-emerald-100 text-emerald-900">
              <div class="font-bold flex items-center space-x-1 mb-1">
                <span>🤖</span>
                <span>Для поисковых роботов</span>
              </div>
              <p class="text-slate-600">Сервер отдает чистый HTML со всеми заголовками, статьями и кликабельными ссылками для перехода вглубь.</p>
            </div>
            <div class="p-3 rounded-lg bg-purple-50/60 border border-purple-100 text-purple-900">
              <div class="font-bold flex items-center space-x-1 mb-1">
                <span>🧩</span>
                <span>Настройка без кода</span>
              </div>
              <p class="text-slate-600">Вся структура собирается визуально в панели управления — кликайте по подсказкам, система сделает остальное.</p>
            </div>
          </div>
        </div>

        <!-- КАРТОЧКА 1: ПРОБЛЕМА SPA И БОТОВ -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" id="seo_intro">
          <button
            onclick={() => toggleSection("seo_intro")}
            class="w-full flex items-center justify-between p-5 text-left bg-slate-50/60 hover:bg-slate-50 transition-colors"
          >
            <div class="flex items-center space-x-3">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 text-amber-700 font-bold text-sm">1</span>
              <div>
                <h3 class="text-base font-bold text-slate-900">В чем проблема современных сайтов (SPA) и зачем нужен SEO модуль?</h3>
                <p class="text-xs text-slate-500">Почему роботы Яндекса и Google без специального модуля видят пустой белый лист</p>
              </div>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["seo_intro"] ? "Свернуть" : "Развернуть"}</span>
              <span class="transform transition-transform duration-200 {openSections['seo_intro'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["seo_intro"]}
            <div class="p-6 border-t border-slate-100 space-y-5">
              <p class="text-sm text-slate-700 leading-relaxed">
                Большинство современных веб-сайтов (на React, Vue, Svelte) работают как <strong>SPA (Single Page Application)</strong>.
                Для человека за компьютером это очень удобно, но для поисковиков это катастрофа, если сервер не обучен отдавать контент роботам.
              </p>

              <!-- Сравнение: человек против робота -->
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Как видит человек -->
                <div class="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
                  <div class="flex items-center space-x-2 text-blue-900 font-bold text-sm mb-2">
                    <span class="text-lg">👨‍💻</span>
                    <span>Как видит человек в браузере:</span>
                  </div>
                  <p class="text-xs text-slate-600 mb-3 leading-relaxed">
                    Браузер (Chrome, Safari, Firefox) загружает JavaScript-движок и сам «рисует» на экране форум,
                    карточки тем, аватарки и кнопки. Всё летает, переходы между страницами происходят мгновенно без перезагрузки.
                  </p>
                  <div class="rounded-lg bg-white border border-blue-200 p-3 shadow-2xs">
                    <div class="text-[11px] font-bold text-slate-800 mb-1">Форум сообщества</div>
                    <div class="text-[10px] text-slate-500">Раздел: Архитектура и WebSockets</div>
                    <div class="mt-2 text-[10px] text-blue-600 font-semibold flex items-center space-x-1">
                      <span>✓ 12 тем</span>
                      <span>•</span>
                      <span>✓ 328 просмотров</span>
                      <span>•</span>
                      <span>✓ Кнопка «Создать тему»</span>
                    </div>
                  </div>
                </div>

                <!-- Как видит поисковый бот -->
                <div class="rounded-xl border border-rose-200 bg-rose-50/40 p-4">
                  <div class="flex items-center space-x-2 text-rose-900 font-bold text-sm mb-2">
                    <span class="text-lg">🤖</span>
                    <span>Как видит поисковый бот (без PyFerro SEO):</span>
                  </div>
                  <p class="text-xs text-slate-600 mb-3 leading-relaxed">
                    Роботы Яндекса, Google, Telegram и WhatsApp приходят забрать страницу быстро. Они не запускают сложный JavaScript.
                    Они скачивают исходный HTML и видят буквально <strong>пустой каркас</strong>:
                  </p>
                  <div class="rounded-lg bg-slate-900 p-3 font-mono text-[11px] text-rose-300">
                    &lt;div id="app"&gt;&lt;/div&gt;<br />
                    <span class="text-slate-500">&lt;!-- Пустота! Никакого текста форума нет --&gt;</span>
                  </div>
                  <div class="mt-2 text-[11px] text-rose-700 font-medium">
                    ⚠️ Итог: сайт не попадает в поиск Яндекса, а в Telegram ссылка выглядит серой безымянной строкой.
                  </div>
                </div>
              </div>

              <!-- Решение PyFerro -->
              <div class="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
                <div class="flex items-center space-x-2 text-emerald-900 font-bold text-sm mb-1">
                  <span>✅</span>
                  <span>Решение PyFerro: Умный динамический рендеринг (Dynamic Rendering)</span>
                </div>
                <p class="text-xs text-emerald-800 leading-relaxed">
                  Когда на сайт заходит человек — он получает сверхбыстрое интерактивное приложение.
                  А когда на сайт заглядывает поисковый робот или мессенджер — PyFerro перехватывает запрос и мгновенно
                  отдает ему <strong>чистый готовый HTML с живыми ссылками и статьями</strong>. Поисковик счастлив, а пользователи не теряют в скорости!
                </p>
              </div>
            </div>
          {/if}
        </div>

        <!-- КАРТОЧКА 2: ИСХОДНЫЕ ДАННЫЕ В БАЗЕ ДАННЫХ -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" id="seo_tables">
          <button
            onclick={() => toggleSection("seo_tables")}
            class="w-full flex items-center justify-between p-5 text-left bg-slate-50/60 hover:bg-slate-50 transition-colors"
          >
            <div class="flex items-center space-x-3">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 text-blue-700 font-bold text-sm">2</span>
              <div>
                <h3 class="text-base font-bold text-slate-900">Что хранится в базе данных? (Разбираем поля двух таблиц)</h3>
                <p class="text-xs text-slate-500">Наглядные карточки таблиц «Разделы форума» и «Темы форума» с реальными примерами</p>
              </div>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["seo_tables"] ? "Свернуть" : "Развернуть"}</span>
              <span class="transform transition-transform duration-200 {openSections['seo_tables'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["seo_tables"]}
            <div class="p-6 border-t border-slate-100 space-y-6">
              <p class="text-sm text-slate-700 leading-relaxed">
                Чтобы поисковик знал, какие страницы показывать людям, система берет данные прямо из вашей базы.
                Наш демонстрационный форум состоит всего из <strong>двух связанных таблиц</strong>:
              </p>

              <!-- ТАБЛИЦА 1: РАЗДЕЛЫ И ПОДРАЗДЕЛЫ ФОРУМА -->
              <div class="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
                <div class="flex items-center justify-between mb-3">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">📁</span>
                    <span class="font-bold text-sm text-slate-900">Таблица 1: Разделы и Подразделы</span>
                    <code class="text-xs font-mono bg-white px-2 py-0.5 rounded border border-slate-300 text-slate-700">pf_showcase_forum_category</code>
                  </div>
                  <span class="text-xs text-slate-500">Папки и вложенные подпапки</span>
                </div>

                <div class="overflow-x-auto">
                  <table class="w-full text-left text-xs bg-white rounded-lg border border-slate-200">
                    <thead class="bg-slate-100 text-slate-600 font-semibold border-b border-slate-200">
                      <tr>
                        <th class="p-2.5">Поле в таблице</th>
                        <th class="p-2.5">Что это означает простыми словами</th>
                        <th class="p-2.5">Пример 1: Главный раздел</th>
                        <th class="p-2.5">Пример 2: Вложенный подраздел</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-slate-700">
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-blue-600">id</td>
                        <td class="p-2.5">Уникальный номер строки в базе</td>
                        <td class="p-2.5 font-mono text-slate-900 font-bold">1</td>
                        <td class="p-2.5 font-mono text-slate-900 font-bold">2</td>
                      </tr>
                      <tr class="bg-purple-50/40">
                        <td class="p-2.5 font-mono font-bold text-purple-800">parent_id</td>
                        <td class="p-2.5 font-semibold text-purple-900">
                          📂 В какой папке лежит? (Если пусто — это главная папка!)
                        </td>
                        <td class="p-2.5 font-mono text-slate-400">NULL (Корневой)</td>
                        <td class="p-2.5 font-mono font-bold text-purple-800">1 (лежит внутри папки 1)</td>
                      </tr>
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-blue-600">name</td>
                        <td class="p-2.5">Красивое название на русском языке</td>
                        <td class="p-2.5 font-medium text-slate-900">«Разработка и Архитектура»</td>
                        <td class="p-2.5 font-medium text-slate-900">«Архитектура и WebSockets»</td>
                      </tr>
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-blue-600">slug</td>
                        <td class="p-2.5">Короткий хвостик для адреса ссылки латиницей</td>
                        <td class="p-2.5 font-mono font-bold text-sky-700">"development"</td>
                        <td class="p-2.5 font-mono font-bold text-amber-700">"architecture"</td>
                      </tr>
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-blue-600">description</td>
                        <td class="p-2.5">Описание раздела (увидят поисковики)</td>
                        <td class="p-2.5 text-slate-500">«Вопросы веб-разработки и бэкенда»</td>
                        <td class="p-2.5 text-slate-500">«Обсуждение RSGI, Granian и WSRPC»</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- ТАБЛИЦА 2: ТЕМЫ ФОРУМА -->
              <div class="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
                <div class="flex items-center justify-between mb-3">
                  <div class="flex items-center space-x-2">
                    <span class="text-base">📄</span>
                    <span class="font-bold text-sm text-slate-900">Таблица 2: Темы форума (Статьи)</span>
                    <code class="text-xs font-mono bg-white px-2 py-0.5 rounded border border-slate-300 text-slate-700">pf_showcase_forum_topic</code>
                  </div>
                  <span class="text-xs text-slate-500">Документы внутри подпапок</span>
                </div>

                <div class="overflow-x-auto">
                  <table class="w-full text-left text-xs bg-white rounded-lg border border-slate-200">
                    <thead class="bg-slate-100 text-slate-600 font-semibold border-b border-slate-200">
                      <tr>
                        <th class="p-2.5">Поле в таблице</th>
                        <th class="p-2.5">Что это означает простыми словами</th>
                        <th class="p-2.5">Пример записи в нашей базе</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-slate-700">
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-emerald-600">id</td>
                        <td class="p-2.5">Уникальный номер темы</td>
                        <td class="p-2.5 font-mono text-slate-900 font-bold">101</td>
                      </tr>
                      <tr class="bg-amber-50/40">
                        <td class="p-2.5 font-mono font-bold text-amber-800">category_id</td>
                        <td class="p-2.5 font-semibold text-amber-900">
                          🔗 В каком подразделе лежит тема (указывает на номер 2 выше!)
                        </td>
                        <td class="p-2.5 font-mono font-bold text-amber-800">2 (Архитектура)</td>
                      </tr>
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-emerald-600">title</td>
                        <td class="p-2.5">Заголовок статьи или вопроса</td>
                        <td class="p-2.5 font-medium text-slate-900">«Как устроен WSRPC в PyFerro по сравнению со стандартным REST?»</td>
                      </tr>
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-emerald-600">slug</td>
                        <td class="p-2.5">Короткий хвостик адреса темы латиницей</td>
                        <td class="p-2.5 font-mono font-bold text-emerald-700">"wsrpc-vs-rest-comparison"</td>
                      </tr>
                      <tr>
                        <td class="p-2.5 font-mono font-semibold text-emerald-600">first_post_text</td>
                        <td class="p-2.5">Текст первого сообщения (пойдет в превью поиска)</td>
                        <td class="p-2.5 text-slate-500">«В отличие от классического REST, WSRPC исключает постоянный TCP handshake...»</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- ВАЖНЫЙ ВЫВОД О РОДИТЕЛЕ И ДЕДУШКЕ -->
              <div class="rounded-xl border border-blue-200 bg-blue-50/50 p-4 flex items-start space-x-3">
                <span class="text-xl">💡</span>
                <div class="text-xs text-blue-900 space-y-1">
                  <div class="font-bold">Как работает вложенность: «Папка ➔ Вложенная папка ➔ Файл»</div>
                  <p class="leading-relaxed text-blue-800">
                    Это устроено точно так же, как папки на вашем компьютере:
                    <br />
                    1. <strong>Главная папка (root):</strong> Раздел «Разработка и Архитектура» (<code class="font-mono text-slate-800">parent_id = NULL</code>).
                    <br />
                    2. <strong>Вложенная папка (parent):</strong> Подраздел «Архитектура и WebSockets» (<code class="font-mono text-slate-800">parent_id = 1</code>).
                    <br />
                    3. <strong>Файл статьи (тема):</strong> «Как устроен WSRPC...» лежит в подпапке (<code class="font-mono text-slate-800">category_id = 2</code>).
                  </p>
                </div>
              </div>

            </div>
          {/if}
        </div>

        <!-- КАРТОЧКА 3: СБОРКА АДРЕСА URL ИЗ КИРПИЧИКОВ -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" id="seo_url">
          <button
            onclick={() => toggleSection("seo_url")}
            class="w-full flex items-center justify-between p-5 text-left bg-slate-50/60 hover:bg-slate-50 transition-colors"
          >
            <div class="flex items-center space-x-3">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700 font-bold text-sm">3</span>
              <div>
                <h3 class="text-base font-bold text-slate-900">Как собирается адрес ссылки (URL) из кирпичиков?</h3>
                <p class="text-xs text-slate-500">Разбираем формулу /forum/&#123;root.slug&#125;/&#123;parent.slug&#125;/&#123;slug&#125; на понятные цветные блоки</p>
              </div>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["seo_url"] ? "Свернуть" : "Развернуть"}</span>
              <span class="transform transition-transform duration-200 {openSections['seo_url'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["seo_url"]}
            <div class="p-6 border-t border-slate-100 space-y-6">
              <p class="text-sm text-slate-700 leading-relaxed">
                Мы хотим, чтобы адрес статьи в браузере отражал реальную иерархию папок и нравился поисковикам:
              </p>

              <!-- Итоговый адрес -->
              <div class="p-3.5 rounded-xl bg-slate-900 text-white font-mono text-sm flex items-center space-x-2 shadow-inner overflow-x-auto">
                <span class="text-slate-500">https://ваш-сайт.ру</span>
                <span class="text-sky-300 font-bold">/forum</span>
                <span class="text-slate-500">/</span>
                <span class="text-purple-300 font-bold">development</span>
                <span class="text-slate-500">/</span>
                <span class="text-amber-300 font-bold">architecture</span>
                <span class="text-slate-500">/</span>
                <span class="text-emerald-300 font-bold">wsrpc-vs-rest-comparison</span>
              </div>

              <!-- Формула шаблона -->
              <div class="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
                <div class="text-xs font-bold uppercase tracking-wider text-slate-400">Формула шаблона в PyFerro:</div>
                <div class="text-base font-mono font-bold text-slate-800 bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <span class="text-sky-600">/forum</span>/<span class="text-purple-600">&#123;root.slug&#125;</span>/<span class="text-amber-600">&#123;parent.slug&#125;</span>/<span class="text-emerald-600">&#123;slug&#125;</span>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-4 gap-3 pt-2 text-xs">
                  <!-- Кирпичик 1 -->
                  <div class="p-3 rounded-lg border border-sky-200 bg-sky-50/50">
                    <div class="font-bold text-sky-800 flex items-center space-x-1 mb-1">
                      <span>1. Корень:</span>
                      <code class="font-mono bg-white px-1 py-0.5 rounded text-sky-700">/forum</code>
                    </div>
                    <p class="text-slate-600 leading-relaxed">
                      Статичное слово. Все страницы сообщества начинаются с него.
                    </p>
                  </div>

                  <!-- Кирпичик 2 -->
                  <div class="p-3 rounded-lg border border-purple-200 bg-purple-50/50">
                    <div class="font-bold text-purple-800 flex items-center space-x-1 mb-1">
                      <span>2. Главная папка:</span>
                      <code class="font-mono bg-white px-1 py-0.5 rounded text-purple-700">&#123;root.slug&#125;</code>
                    </div>
                    <p class="text-slate-600 leading-relaxed">
                      Корневой раздел форума.<br />
                      В нашем примере подставится: <strong class="text-purple-800">development</strong>.
                    </p>
                  </div>

                  <!-- Кирпичик 3 -->
                  <div class="p-3 rounded-lg border border-amber-200 bg-amber-50/50">
                    <div class="font-bold text-amber-800 flex items-center space-x-1 mb-1">
                      <span>3. Подпапка:</span>
                      <code class="font-mono bg-white px-1 py-0.5 rounded text-amber-700">&#123;parent.slug&#125;</code>
                    </div>
                    <p class="text-slate-600 leading-relaxed">
                      Непосредственный подраздел темы.<br />
                      В нашем примере подставится: <strong class="text-amber-800">architecture</strong>.
                    </p>
                  </div>

                  <!-- Кирпичик 4 -->
                  <div class="p-3 rounded-lg border border-emerald-200 bg-emerald-50/50">
                    <div class="font-bold text-emerald-800 flex items-center space-x-1 mb-1">
                      <span>4. Сама статья:</span>
                      <code class="font-mono bg-white px-1 py-0.5 rounded text-emerald-700">&#123;slug&#125;</code>
                    </div>
                    <p class="text-slate-600 leading-relaxed">
                      Хвостик самой темы.<br />
                      В примере: <strong class="text-emerald-800">wsrpc-vs-rest-comparison</strong>.
                    </p>
                  </div>
                </div>
              </div>

              <!-- Универсальность -->
              <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div class="font-bold text-xs text-slate-900 mb-1">🎯 А как выглядят страницы промежуточных каталогов?</div>
                <div class="text-xs text-slate-600 space-y-1 leading-relaxed">
                  <div>• Страница главного раздела: <code class="font-mono font-bold bg-white px-1.5 py-0.5 rounded text-slate-800">/forum/development</code> (выводит список подразделов)</div>
                  <div>• Страница подраздела: <code class="font-mono font-bold bg-white px-1.5 py-0.5 rounded text-slate-800">/forum/development/architecture</code> (выводит список тем)</div>
                  <div>• Страница темы: <code class="font-mono font-bold bg-white px-1.5 py-0.5 rounded text-slate-800">/forum/development/architecture/wsrpc-vs-rest-comparison</code> (сама статья)</div>
                </div>
              </div>

            </div>
          {/if}
        </div>

        <!-- КАРТОЧКА 4: ЦЕПОЧКА ССЫЛОК ДЛЯ РОБОТА -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" id="seo_crawler">
          <button
            onclick={() => toggleSection("seo_crawler")}
            class="w-full flex items-center justify-between p-5 text-left bg-slate-50/60 hover:bg-slate-50 transition-colors"
          >
            <div class="flex items-center space-x-3">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 text-purple-700 font-bold text-sm">4</span>
              <div>
                <h3 class="text-base font-bold text-slate-900">Как поисковый робот ходит по сайту (Цепочка ссылок)</h3>
                <p class="text-xs text-slate-500">Пошаговый переход робота от главной страницы форума вглубь по иерархии</p>
              </div>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["seo_crawler"] ? "Свернуть" : "Развернуть"}</span>
              <span class="transform transition-transform duration-200 {openSections['seo_crawler'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["seo_crawler"]}
            <div class="p-6 border-t border-slate-100 space-y-6">
              <p class="text-sm text-slate-700 leading-relaxed">
                Поисковый робот ходит по сайту шаг за шагом, переходя по ссылкам <code class="font-mono text-xs bg-slate-100 text-slate-800 px-1 py-0.5 rounded border border-slate-200">&lt;a href="..."&gt;</code>.
                Вот как выглядит реальный маршрут краулера Яндекса или Google:
              </p>

              <!-- Цепочка шагов -->
              <div class="space-y-4">
                <!-- Шаг 1 -->
                <div class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div class="space-y-1">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-blue-100 text-blue-700 font-bold text-xs flex items-center justify-center">1</span>
                      <span class="font-bold text-xs text-slate-900">Робот приходит на каталог форума:</span>
                      <code class="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded text-blue-700 font-bold">/forum</code>
                    </div>
                    <p class="text-xs text-slate-500 pl-8">
                      Сервер отдает список главных разделов сообщества:
                    </p>
                  </div>
                  <div class="rounded-lg bg-slate-50 border border-slate-200 p-2.5 font-mono text-xs text-slate-800 shrink-0">
                    &lt;a href="<span class="text-blue-600 font-bold">/forum/development</span>"&gt;Разработка и Код&lt;/a&gt;<br />
                    &lt;a href="<span class="text-blue-600 font-bold">/forum/marketing</span>"&gt;Продвижение и Маркетинг&lt;/a&gt;
                  </div>
                </div>

                <!-- Стрелка вниз -->
                <div class="flex justify-center text-slate-400 font-bold text-sm">↓ робот кликает по ссылке /forum/development</div>

                <!-- Шаг 2 -->
                <div class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div class="space-y-1">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-purple-100 text-purple-700 font-bold text-xs flex items-center justify-center">2</span>
                      <span class="font-bold text-xs text-slate-900">Робот попадает в главный раздел:</span>
                      <code class="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded text-purple-700 font-bold">/forum/development</code>
                    </div>
                    <p class="text-xs text-slate-500 pl-8">
                      Сервер отдает список вложенных подразделов:
                    </p>
                  </div>
                  <div class="rounded-lg bg-slate-50 border border-slate-200 p-2.5 font-mono text-xs text-slate-800 shrink-0">
                    &lt;a href="<span class="text-purple-700 font-bold">/forum/development/architecture</span>"&gt;Архитектура&lt;/a&gt;<br />
                    &lt;a href="<span class="text-purple-700 font-bold">/forum/development/security</span>"&gt;Безопасность&lt;/a&gt;
                  </div>
                </div>

                <!-- Стрелка вниз -->
                <div class="flex justify-center text-slate-400 font-bold text-sm">↓ робот кликает по ссылке /forum/development/architecture</div>

                <!-- Шаг 3 -->
                <div class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div class="space-y-1">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-amber-100 text-amber-700 font-bold text-xs flex items-center justify-center">3</span>
                      <span class="font-bold text-xs text-slate-900">Робот попадает в подраздел:</span>
                      <code class="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded text-amber-700 font-bold">/forum/development/architecture</code>
                    </div>
                    <p class="text-xs text-slate-500 pl-8">
                      Сервер отдает список тем внутри этого подраздела:
                    </p>
                  </div>
                  <div class="rounded-lg bg-slate-50 border border-slate-200 p-2.5 font-mono text-xs text-slate-800 shrink-0">
                    &lt;a href="<span class="text-amber-700 font-bold">/forum/development/architecture/wsrpc-vs-rest-comparison</span>"&gt;<br />
                    &nbsp;&nbsp;Как устроен WSRPC по сравнению с REST?<br />
                    &lt;/a&gt;
                  </div>
                </div>

                <!-- Стрелка вниз -->
                <div class="flex justify-center text-slate-400 font-bold text-sm">↓ робот кликает по ссылке на тему форума</div>

                <!-- Шаг 4 -->
                <div class="rounded-xl border border-slate-200 bg-emerald-50/40 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div class="space-y-1">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center">4</span>
                      <span class="font-bold text-xs text-emerald-900">Робот открывает страницу статьи и читает текст:</span>
                      <code class="font-mono text-xs bg-white px-2 py-0.5 rounded text-emerald-700 font-bold">/forum/development/architecture/wsrpc-vs-rest-comparison</code>
                    </div>
                    <p class="text-xs text-slate-600 pl-8">
                      Сервер отдает полный текст статьи, автора, дату и мета-теги. Страница гарантированно проиндексирована!
                    </p>
                  </div>
                  <div class="rounded-lg bg-white border border-emerald-200 p-2.5 text-xs text-emerald-800 shrink-0 font-medium">
                    ✅ 100% готовность к индексации в Яндексе и Google
                  </div>
                </div>
              </div>

              <!-- Карта сайта sitemap.xml -->
              <div class="rounded-xl border border-slate-200 bg-white p-4">
                <div class="flex items-center justify-between">
                  <div class="space-y-1">
                    <div class="font-bold text-xs text-slate-900 flex items-center space-x-1.5">
                      <span>🗺️</span>
                      <span>Бонус: Автоматическая карта сайта sitemap.xml</span>
                    </div>
                    <p class="text-xs text-slate-500">
                      PyFerro сам генерирует стандартный файл <code class="font-mono text-slate-700">/sitemap.xml</code> по дереву сайта, включая все разделы, подразделы и темы.
                    </p>
                  </div>
                  <a
                    href="/sitemap.xml"
                    target="_blank"
                    class="px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors shrink-0"
                  >
                    Открыть sitemap.xml ↗
                  </a>
                </div>
              </div>

            </div>
          {/if}
        </div>

        <!-- КАРТОЧКА 5: ПОШАГОВАЯ НАСТРОЙКА В MISSION CONTROL GUI -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" id="seo_gui">
          <button
            onclick={() => toggleSection("seo_gui")}
            class="w-full flex items-center justify-between p-5 text-left bg-slate-50/60 hover:bg-slate-50 transition-colors"
          >
            <div class="flex items-center space-x-3">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-100 text-rose-700 font-bold text-sm">5</span>
              <div>
                <h3 class="text-base font-bold text-slate-900">Как настроить это в админке Mission Control (GUI) за 3 шага</h3>
                <p class="text-xs text-slate-500">Никакого кода — пошаговый процесс создания узлов дерева в веб-интерфейсе /admin#seo</p>
              </div>
            </div>
            <div class="flex items-center space-x-3 text-slate-400 text-sm">
              <span class="text-xs font-mono font-medium">{openSections["seo_gui"] ? "Свернуть" : "Развернуть"}</span>
              <span class="transform transition-transform duration-200 {openSections['seo_gui'] ? 'rotate-180' : ''}">▼</span>
            </div>
          </button>

          {#if openSections["seo_gui"]}
            <div class="p-6 border-t border-slate-100 space-y-6">
              <div class="flex items-center justify-between bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div>
                  <div class="font-bold text-xs text-slate-900">Где это настраивается?</div>
                  <p class="text-xs text-slate-500">В панели управления PyFerro Mission Control перейдите во вкладку «SEO и Роботы».</p>
                </div>
                <a
                  href="/admin#seo"
                  target="_blank"
                  class="px-3.5 py-2 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 shadow-xs transition-colors shrink-0"
                >
                  Перейти в /admin#seo ↗
                </a>
              </div>

              <!-- 3 Шага настройки -->
              <!-- 3 Шага настройки -->
              <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <!-- Шаг 1 -->
                <div class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col justify-between">
                  <div class="space-y-2">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-blue-100 text-blue-700 font-bold text-xs flex items-center justify-center">1</span>
                      <span class="font-bold text-xs text-slate-900">Задаем адрес страницы (URL)</span>
                    </div>
                    <p class="text-xs text-slate-600 leading-relaxed">
                      В левой колонке нажимаем <strong>«+ Добавить подраздел»</strong>:
                    </p>
                    <ul class="text-[11px] text-slate-600 space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                      <li>• <strong>Название:</strong> Форум сообщества</li>
                      <li>• <strong>Шаблон пути:</strong> <code class="font-mono text-blue-600">/forum</code></li>
                      <li>• <strong>Тип:</strong> Универсальная HTML + Jinja2 страница ✨</li>
                    </ul>
                  </div>
                  <div class="mt-3 text-[10px] text-slate-400">Любая страница может содержать несколько таблиц сразу</div>
                </div>

                <!-- Шаг 2 -->
                <div class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col justify-between">
                  <div class="space-y-2">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-amber-100 text-amber-700 font-bold text-xs flex items-center justify-center">2</span>
                      <span class="font-bold text-xs text-slate-900">Вставляем циклы Jinja2</span>
                    </div>
                    <p class="text-xs text-slate-600 leading-relaxed">
                      Кликаем кнопку <strong>«+ Вставить цикл по таблице»</strong>:
                    </p>
                    <ul class="text-[11px] text-slate-600 space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-100 font-mono">
                      <li>• {"{"}% for c in ForumCategory %{"}"}</li>
                      <li>• {"{"}% for t in ForumTopic[:5] %{"}"}</li>
                      <li>• {"{{"} t.category.slug {"}}"} / {"{{"} t.slug {"}}"}</li>
                    </ul>
                  </div>
                  <div class="mt-3 text-[10px] text-slate-400">Система автоматически проверяет синтаксис на лету</div>
                </div>

                <!-- Шаг 3 -->
                <div class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col justify-between">
                  <div class="space-y-2">
                    <div class="flex items-center space-x-2">
                      <span class="h-6 w-6 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center">3</span>
                      <span class="font-bold text-xs text-slate-900">Смотрим живой результат</span>
                    </div>
                    <p class="text-xs text-slate-600 leading-relaxed">
                      В правой колонке мгновенно обновляется внешний вид:
                    </p>
                    <ul class="text-[11px] text-slate-600 space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                      <li>• <strong>Telegram / Соцсети:</strong> сниппет с фото и описанием</li>
                      <li>• <strong>Робот:</strong> чистый семантический HTML со ссылками</li>
                      <li>• <strong>Статус:</strong> зеленая плашка «✓ Шаблон корректен»</li>
                    </ul>
                  </div>
                  <div class="mt-3 text-[10px] text-slate-400">Жмем кнопку «Сохранить дерево» — готово к поисковикам!</div>
                </div>
              </div>
              <div class="rounded-xl border border-slate-200 bg-slate-50/60 p-5 space-y-3">
                <div class="text-xs font-bold text-slate-800">Как выглядит готовая карточка в мессенджере (Telegram / WhatsApp):</div>

                <div class="max-w-md rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-2">
                  <div class="flex items-center space-x-2 text-[10px] text-blue-600 font-bold uppercase tracking-wider">
                    <span>💬 Telegram Ссылка-превью</span>
                  </div>
                  <div class="font-bold text-xs text-slate-900">
                    Как устроен WSRPC в PyFerro по сравнению со стандартным REST? — Форум
                  </div>
                  <p class="text-[11px] text-slate-600 leading-relaxed line-clamp-2">
                    В отличие от классического REST, WSRPC исключает постоянный TCP/TLS handshake оверхед, работает по единому сокету и поддерживает стриминг данных...
                  </p>
                  <div class="text-[10px] text-slate-400 font-mono">
                    ваш-сайт.ру/forum/architecture/wsrpc-vs-rest-comparison
                  </div>
                </div>
              </div>

            </div>
          {/if}
        </div>

      </div>
    {/if}
  <!-- МОДАЛЬНОЕ ОКНО АВТОРИЗАЦИИ ДЛЯ SHOWCASE / SSO -->
  {#if isLoginModalOpen}
    <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs">
      <div class="w-full max-w-sm bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-lg bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
              Fe
            </div>
            <h3 class="text-sm font-bold text-slate-900">Вход в PyFerro</h3>
          </div>
          <button
            type="button"
            onclick={() => (isLoginModalOpen = false)}
            class="text-slate-400 hover:text-slate-600 p-1 rounded-md text-xs cursor-pointer"
          >
            ✕
          </button>
        </div>

        {#if loginError}
          <div class="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
            {loginError}
          </div>
        {/if}

        <div class="flex flex-col gap-3">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Имя пользователя / Логин:</label>
            <input
              type="text"
              bind:value={loginUsername}
              placeholder="admin"
              class="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-hidden"
              onkeydown={(e) => { if (e.key === "Enter") doLogin(); }}
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Пароль:</label>
            <input
              type="password"
              bind:value={loginPassword}
              placeholder="••••••••••••"
              class="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-hidden"
              onkeydown={(e) => { if (e.key === "Enter") doLogin(); }}
            />
          </div>

          <p class="text-[11px] text-slate-400 leading-tight">
            💡 После входа активируется бесшовный SSO: вы сможете сразу перейти в панель управления <code class="font-mono text-blue-600">/admin/</code>.
          </p>

          <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onclick={() => (isLoginModalOpen = false)}
              class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 cursor-pointer"
            >
              Отмена
            </button>
            <button
              type="button"
              onclick={doLogin}
              disabled={loginLoading}
              class="px-4 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              {#if loginLoading}
                <span class="animate-spin text-xs">⏳</span>
                <span>Вход...</span>
              {:else}
                <span>Войти</span>
              {/if}
            </button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  </div>
</div>
