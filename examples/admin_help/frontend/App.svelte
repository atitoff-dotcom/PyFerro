<script lang="ts">
  import { onMount } from "svelte";
  import { rpc, wsStatus } from "@wsrpc/wsrpc";
  import CodeBox from "./components/CodeBox.svelte";

  // Активная вкладка: "rpc" или "migrations"
  let activeTab = $state<"rpc" | "migrations">("rpc");

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
      const res = await rpc.call("login.whoami", {});
      if (res && res.authenticated) {
        authUser = res;
      } else {
        authUser = null;
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
      const res = await rpc.call("login.submit", {
        username: loginUsername.trim(),
        password: loginPassword,
      });
      if (res) {
        await checkAuth();
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
      await rpc.call("login.logout", {});
    } catch {}
    authUser = null;
    document.cookie = "ferro_crud_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "rpc_jwt=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT";
    await checkAuth();
  }

  onMount(() => {
    const unsub = wsStatus.subscribe((val) => {
      connectionState = val;
      if (val === "CONNECTED") {
        measurePing();
        checkAuth();
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
      {:else}
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
