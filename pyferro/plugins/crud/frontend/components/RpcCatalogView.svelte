<script lang="ts">
  import { onMount } from "svelte";

  interface Props {
    lang?: "ru" | "en";
    rpcClient: any;
  }

  let { lang = "ru", rpcClient }: Props = $props();

  interface RpcParam {
    type?: string;
    required?: boolean;
    default?: any;
    description?: string;
  }

  interface RpcItem {
    name: string;
    group: string;
    is_public: boolean;
    is_framework: boolean;
    description: string;
    help: string;
    params?: Record<string, RpcParam>;
  }

  let activeTab = $state<"app" | "framework">("app");
  let searchQuery = $state("");
  let selectedGroup = $state("all");
  let isLoading = $state(true);
  let errorMsg = $state("");
  let rpcMethods = $state<RpcItem[]>([]);

  const t = $derived({
    tabApp: lang === "ru" ? "RPC приложения" : "Application RPC",
    tabFramework: lang === "ru" ? "RPC фреймворка" : "Framework RPC",
    searchPlaceholder: lang === "ru" ? "Поиск методов по имени или описанию..." : "Search methods by name or description...",
    allGroups: lang === "ru" ? "Все группы" : "All Groups",
    publicBadge: lang === "ru" ? "Публичный (гостям)" : "Public (Guests)",
    authBadge: lang === "ru" ? "Требуется авторизация" : "Auth Required",
    noMethods: lang === "ru" ? "Методов не найдено" : "No RPC methods found",
    loading: lang === "ru" ? "Загрузка каталога RPC..." : "Loading RPC catalog...",
    readOnlyNotice: lang === "ru" ? "Режим инспекции: вызов методов из админки отключен для защиты целостности данных" : "Inspection mode: direct execution disabled to prevent accidental state mutation",
    parameters: lang === "ru" ? "Параметры" : "Parameters",
    noParams: lang === "ru" ? "Без параметров" : "No parameters",
    paramName: lang === "ru" ? "Параметр" : "Parameter",
    paramType: lang === "ru" ? "Тип" : "Type",
    paramRequired: lang === "ru" ? "Обязателен" : "Required",
    paramDefault: lang === "ru" ? "По умолчанию" : "Default",
    docDetails: lang === "ru" ? "Документация" : "Documentation",
  });

  async function loadRpcCatalog() {
    isLoading = true;
    errorMsg = "";
    try {
      const res = await rpcClient.call("permissions.get_schema", { all: true });
      rpcMethods = res.rpc_methods || [];
    } catch (e: any) {
      errorMsg = e.message || String(e);
    } finally {
      isLoading = false;
    }
  }

  onMount(() => {
    loadRpcCatalog();
  });

  const appMethods = $derived(rpcMethods.filter(m => !m.is_framework));
  const frameworkMethods = $derived(rpcMethods.filter(m => m.is_framework));

  const currentList = $derived(activeTab === "app" ? appMethods : frameworkMethods);

  const groups = $derived.by(() => {
    const set = new Set<string>();
    for (const m of currentList) {
      if (m.group) set.add(m.group);
    }
    return Array.from(set).sort();
  });

  const filteredMethods = $derived.by(() => {
    const q = searchQuery.toLowerCase().trim();
    return currentList.filter(m => {
      if (selectedGroup !== "all" && m.group !== selectedGroup) return false;
      if (!q) return true;
      return (
        m.name.toLowerCase().includes(q) ||
        (m.description && m.description.toLowerCase().includes(q)) ||
        (m.help && m.help.toLowerCase().includes(q))
      );
    });
  });
</script>

<div class="flex-1 flex flex-col p-6 gap-5 overflow-y-auto">
  <!-- Верхняя плашка: табы App vs Framework и инфо-уведомление -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-xs">
    <div class="flex items-center gap-2 p-1 rounded-lg bg-muted/60 border border-border">
      <button
        type="button"
        onclick={() => { activeTab = "app"; selectedGroup = "all"; }}
        class="flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer {activeTab === 'app' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}"
      >
        <span>{t.tabApp}</span>
        <span class="px-1.5 py-0.2 rounded-full text-2xs {activeTab === 'app' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'}">{appMethods.length}</span>
      </button>

      <button
        type="button"
        onclick={() => { activeTab = "framework"; selectedGroup = "all"; }}
        class="flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer {activeTab === 'framework' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}"
      >
        <span>{t.tabFramework}</span>
        <span class="px-1.5 py-0.2 rounded-full text-2xs {activeTab === 'framework' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'}">{frameworkMethods.length}</span>
      </button>
    </div>

    <div class="flex items-center gap-2 text-2xs text-muted-foreground bg-muted/30 px-3 py-1.5 rounded-lg border border-border/50">
      <svg class="w-3.5 h-3.5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <span>{t.readOnlyNotice}</span>
    </div>
  </div>

  <!-- Панель фильтрации и поиска -->
  <div class="flex flex-wrap items-center gap-3">
    <div class="flex-1 min-w-[260px] relative">
      <input
        type="text"
        bind:value={searchQuery}
        placeholder={t.searchPlaceholder}
        class="w-full rounded-lg border border-input bg-card px-3.5 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary shadow-2xs"
      />
      {#if searchQuery}
        <button
          type="button"
          onclick={() => { searchQuery = ""; }}
          class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
        >
          ✕
        </button>
      {/if}
    </div>

    {#if groups.length > 0}
      <select
        bind:value={selectedGroup}
        class="rounded-lg border border-input bg-card px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer shadow-2xs"
      >
        <option value="all">{t.allGroups} ({currentList.length})</option>
        {#each groups as g}
          <option value={g}>{g}</option>
        {/each}
      </select>
    {/if}

    <button
      type="button"
      onclick={loadRpcCatalog}
      class="px-3.5 py-2 rounded-lg border border-border bg-card text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer shadow-2xs"
    >
      ↻
    </button>
  </div>

  <!-- Список методов -->
  {#if isLoading}
    <div class="flex flex-col items-center justify-center p-12 text-sm text-muted-foreground gap-2">
      <div class="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
      <span>{t.loading}</span>
    </div>
  {:else if errorMsg}
    <div class="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-xs">
      {errorMsg}
    </div>
  {:else if filteredMethods.length === 0}
    <div class="p-12 text-center text-sm text-muted-foreground border border-dashed border-border rounded-xl">
      {t.noMethods}
    </div>
  {:else}
    <div class="grid grid-cols-1 gap-3.5">
      {#each filteredMethods as m}
        <div class="flex flex-col gap-3 p-4 rounded-xl bg-card border border-border shadow-xs hover:border-primary/40 transition-colors">
          <div class="flex flex-wrap items-center justify-between gap-2.5">
            <div class="flex items-center gap-2.5">
              <span class="font-mono font-bold text-xs text-primary">{m.name}</span>
              <span class="px-2 py-0.5 rounded-md text-2xs font-semibold bg-muted text-muted-foreground border border-border/60">
                {m.group}
              </span>
            </div>

            <div class="flex items-center gap-2">
              {#if m.is_public}
                <span class="px-2.5 py-0.5 rounded-full text-2xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                  {t.publicBadge}
                </span>
              {:else}
                <span class="px-2.5 py-0.5 rounded-full text-2xs font-semibold bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/30">
                  {t.authBadge}
                </span>
              {/if}
            </div>
          </div>

          {#if m.description}
            <p class="text-xs text-muted-foreground leading-relaxed">
              {m.description}
            </p>
          {/if}

          <!-- Параметры метода (если есть) -->
          {#if m.params && Object.keys(m.params).length > 0}
            <div class="mt-1 pt-2.5 border-t border-border/50 flex flex-col gap-1.5">
              <span class="text-2xs font-bold uppercase tracking-wider text-muted-foreground/80">{t.parameters}:</span>
              <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                {#each Object.entries(m.params) as [pName, pInfo]}
                  <div class="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md bg-muted/40 border border-border/40 text-2xs">
                    <div class="flex items-center gap-1.5">
                      <span class="font-mono font-bold text-foreground">{pName}</span>
                      {#if pInfo.type}
                        <span class="text-muted-foreground font-mono">({pInfo.type})</span>
                      {/if}
                    </div>
                    {#if pInfo.required}
                      <span class="text-rose-500 font-bold">*</span>
                    {:else if pInfo.default !== undefined}
                      <span class="text-muted-foreground/80 font-mono text-3xs">={JSON.stringify(pInfo.default)}</span>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- Полный docstring (если длиннее описания) -->
          {#if m.help && m.help.length > (m.description ? m.description.length + 10 : 0)}
            <details class="text-2xs text-muted-foreground/90 mt-1 cursor-pointer">
              <summary class="hover:text-foreground font-medium">{t.docDetails}</summary>
              <pre class="mt-2 p-2.5 rounded-lg bg-muted/50 border border-border/60 text-2xs font-mono whitespace-pre-wrap text-foreground/90 leading-relaxed overflow-x-auto">{m.help}</pre>
            </details>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>