<script lang="ts">
  import { onMount } from "svelte";
  import Button from "./ui/Button.svelte";
  import Input from "./ui/Input.svelte";
  import Badge from "./ui/Badge.svelte";
  import Checkbox from "./ui/Checkbox.svelte";
  import RpcHelpModal, { type RpcMethodDoc } from "./RpcHelpModal.svelte";

  interface Props {
    lang?: "ru" | "en";
    rpcClient: any;
    onnotify?: (msg: string, type: "success" | "error") => void;
  }

  let {
    lang = "ru",
    rpcClient,
    onnotify
  }: Props = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let activeTab = $state<"rpc" | "crud">("rpc");
  let rpcSearch = $state("");
  let modelSearch = $state("");
  let successMessage = $state("");
  let errorMessage = $state("");

  interface RpcMethodItem extends RpcMethodDoc {}

  interface ModelItem {
    key: string;
    verbose_name: string;
    table_name: string;
    is_row_secure?: boolean;
  }

  let availableRpcs = $state<RpcMethodItem[]>([]);
  let availableModels = $state<ModelItem[]>([]);
  let rpcPerms = $state<Set<string>>(new Set());
  let crudPerms = $state<Record<string, boolean>>({});

  let helpModalOpen = $state(false);
  let selectedHelpMethod = $state<RpcMethodDoc | null>(null);

  function openHelp(m: RpcMethodItem) {
    selectedHelpMethod = m;
    helpModalOpen = true;
  }

  const t = $derived({
    ru: {
      title: "🌐 Разрешения для гостей",
      subtitle: "Управление действиями и каталогами, доступными посетителям без авторизации (роль guest / CQRS).",
      tabRpc: "⚡ Команды и RPC-методы",
      tabCrud: "📊 Таблицы данных (Каталоги)",
      searchRpc: "Поиск действия или процедуры...",
      searchModel: "Поиск таблицы или каталога...",
      selectAll: "Выбрать всю группу",
      deselectAll: "Снять выбор",
      save: "Сохранить изменения",
      saving: "Сохранение...",
      loading: "Загрузка разрешений...",
      noRpcs: "Функции не найдены",
      noModels: "Таблицы не найдены",
      systemLogin: "Системный вход",
      savedOk: "Разрешения для гостей успешно сохранены",
      presetFull: "Открыть всё",
      presetReset: "Сбросить к системным",
      totalRpcs: "Всего функций",
      openRpcs: "Открыто гостям",
      totalModels: "Всего таблиц",
      openModels: "Публичное чтение",
      crudReadLabel: "Публичное чтение (can_read)",
      crudReadDesc: "Разрешает гостям выборку каталогов через crud.list ($tabular) и просмотр карточек через crud.get.",
      crudPublicBadge: "✓ Публичный каталог",
      crudClosedBadge: "— Закрыто"
    },
    en: {
      title: "🌐 Guest Permissions",
      subtitle: "Configure actions and catalogs available to unauthenticated visitors (guest role / CQRS).",
      tabRpc: "⚡ Commands & RPC API",
      tabCrud: "📊 Data Tables (Catalogs)",
      searchRpc: "Search action or procedure...",
      searchModel: "Search table or catalog...",
      selectAll: "Select group",
      deselectAll: "Deselect group",
      save: "Save Changes",
      saving: "Saving...",
      loading: "Loading permissions...",
      noRpcs: "No functions found",
      noModels: "No tables found",
      systemLogin: "System Login",
      savedOk: "Guest permissions saved successfully",
      presetFull: "Open All",
      presetReset: "Reset to default",
      totalRpcs: "Total functions",
      openRpcs: "Open to guests",
      totalModels: "Total tables",
      openModels: "Public read",
      crudReadLabel: "Public reading (can_read)",
      crudReadDesc: "Allows guests to query catalogs via crud.list ($tabular) and view records via crud.get.",
      crudPublicBadge: "✓ Public Catalog",
      crudClosedBadge: "— Closed"
    }
  }[lang]);

  async function loadData() {
    isLoading = true;
    errorMessage = "";
    successMessage = "";
    try {
      // 1. Получаем общую схему
      const schema = await rpcClient.call("permissions.get_schema");
      availableRpcs = schema.rpc_methods || [];
      availableModels = schema.models || [];

      // 2. Получаем текущие права для гостей
      const data = await rpcClient.call("permissions.get", {
        target_type: "guest",
        target_id: 0
      });

      const publicSet = new Set<string>(data.rpc_permissions || []);
      for (const m of availableRpcs) {
        if (m.name.startsWith("login.")) {
          publicSet.add(m.name);
        }
      }
      rpcPerms = publicSet;

      // Загружаем CRUD-права
      const cPerms: Record<string, boolean> = {};
      const receivedCrud = data.crud_permissions || {};
      for (const m of availableModels) {
        cPerms[m.key] = Boolean(receivedCrud[m.key]?.can_read);
      }
      crudPerms = cPerms;
    } catch (e: any) {
      errorMessage = e.message || "Ошибка загрузки разрешений";
    } finally {
      isLoading = false;
    }
  }

  function isSystemMethod(name: string): boolean {
    return name.startsWith("login.");
  }

  function toggleRpcMethod(name: string) {
    if (isSystemMethod(name)) return;
    const next = new Set(rpcPerms);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    rpcPerms = next;
  }

  function toggleRpcGroup(methods: RpcMethodItem[]) {
    const next = new Set(rpcPerms);
    const nonSystem = methods.filter((m) => !isSystemMethod(m.name));
    const allSelected = nonSystem.every((m) => next.has(m.name));
    if (allSelected) {
      for (const m of nonSystem) next.delete(m.name);
    } else {
      for (const m of nonSystem) next.add(m.name);
    }
    rpcPerms = next;
  }

  function toggleModelRead(key: string) {
    crudPerms = {
      ...crudPerms,
      [key]: !crudPerms[key]
    };
  }

  function presetOpenAll() {
    if (activeTab === "rpc") {
      const next = new Set(rpcPerms);
      for (const m of availableRpcs) {
        next.add(m.name);
      }
      rpcPerms = next;
    } else {
      const next: Record<string, boolean> = {};
      for (const m of availableModels) {
        next[m.key] = true;
      }
      crudPerms = next;
    }
  }

  function presetReset() {
    if (activeTab === "rpc") {
      const next = new Set<string>();
      for (const m of availableRpcs) {
        if (isSystemMethod(m.name)) {
          next.add(m.name);
        }
      }
      rpcPerms = next;
    } else {
      const next: Record<string, boolean> = {};
      for (const m of availableModels) {
        next[m.key] = false;
      }
      crudPerms = next;
    }
  }

  let rpcGroups = $derived(() => {
    const q = rpcSearch.toLowerCase().trim();
    const filtered = availableRpcs.filter(
      (m) => m.name.toLowerCase().includes(q) || (m.description && m.description.toLowerCase().includes(q))
    );

    const groups: Record<string, RpcMethodItem[]> = {};
    for (const m of filtered) {
      if (!groups[m.group]) groups[m.group] = [];
      groups[m.group].push(m);
    }

    return Object.entries(groups)
      .map(([group, methods]) => ({ group, methods }))
      .sort((a, b) => a.group.localeCompare(b.group));
  });

  let filteredModels = $derived(() => {
    const q = modelSearch.toLowerCase().trim();
    if (!q) return availableModels;
    return availableModels.filter(
      (m) =>
        m.key.toLowerCase().includes(q) ||
        (m.verbose_name && m.verbose_name.toLowerCase().includes(q)) ||
        (m.table_name && m.table_name.toLowerCase().includes(q))
    );
  });

  let activeCrudCount = $derived(() => {
    return Object.values(crudPerms).filter(Boolean).length;
  });

  async function handleSave() {
    isSaving = true;
    errorMessage = "";
    successMessage = "";
    try {
      const crudPayload: Record<string, any> = {};
      for (const [mName, canRead] of Object.entries(crudPerms)) {
        if (canRead) {
          crudPayload[mName] = {
            can_read: true,
            can_create: false,
            can_update: false,
            can_delete: false,
            read_global: true
          };
        }
      }

      await rpcClient.call("permissions.save", {
        target_type: "guest",
        target_id: 0,
        crud_permissions: crudPayload,
        rpc_permissions: Array.from(rpcPerms)
      });
      successMessage = t.savedOk;
      if (onnotify) onnotify(t.savedOk, "success");
    } catch (e: any) {
      errorMessage = e.message || "Ошибка сохранения";
      if (onnotify) onnotify(errorMessage, "error");
    } finally {
      isSaving = false;
    }
  }

  onMount(() => {
    loadData();
  });
</script>

<div class="flex flex-col gap-5 max-w-5xl w-full">
  <!-- Заголовок и панель действий -->
  <div class="flex flex-wrap items-center justify-between gap-4 bg-card p-5 rounded-xl border border-border shadow-xs">
    <div>
      <h2 class="text-base font-bold text-foreground flex items-center gap-2">
        <span>{t.title}</span>
      </h2>
      <p class="text-xs text-muted-foreground mt-0.5">
        {t.subtitle}
      </p>
    </div>

    <div class="flex items-center gap-2.5">
      <Button variant="secondary" size="sm" onclick={presetOpenAll}>
        {t.presetFull}
      </Button>
      <Button variant="ghost" size="sm" onclick={presetReset}>
        {t.presetReset}
      </Button>
      <Button variant="primary" size="sm" onclick={handleSave} disabled={isSaving || isLoading}>
        {#if isSaving}
          <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent mr-1.5"></span>
          {t.saving}
        {:else}
          💾 {t.save}
        {/if}
      </Button>
    </div>
  </div>

  <!-- Вкладки: RPC API vs CRUD Каталоги -->
  <div class="flex items-center gap-2 border-b border-border pb-1">
    <button
      type="button"
      class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer {activeTab === 'rpc' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
      onclick={() => (activeTab = "rpc")}
    >
      {t.tabRpc} ({rpcPerms.size})
    </button>
    <button
      type="button"
      class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer {activeTab === 'crud' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
      onclick={() => (activeTab = "crud")}
    >
      {t.tabCrud} ({activeCrudCount()})
    </button>
  </div>

  {#if successMessage}
    <div class="p-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 rounded-lg text-xs font-semibold flex items-center gap-2">
      <span>✅</span>
      <span>{successMessage}</span>
    </div>
  {/if}

  {#if errorMessage}
    <div class="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 rounded-lg text-xs font-semibold flex items-center gap-2">
      <span>⚠️</span>
      <span>{errorMessage}</span>
    </div>
  {/if}

  {#if activeTab === "rpc"}
    <!-- Панель поиска RPC -->
    <div class="flex items-center justify-between gap-4 bg-card px-4 py-3 rounded-xl border border-border shadow-2xs">
      <div class="w-72">
        <Input
          bind:value={rpcSearch}
          placeholder={t.searchRpc}
          size="sm"
        />
      </div>
      <div class="text-xs text-muted-foreground">
        {t.totalRpcs}: <span class="font-bold text-foreground">{availableRpcs.length}</span> • 
        {t.openRpcs}: <span class="font-bold text-emerald-600 dark:text-emerald-400">{rpcPerms.size}</span>
      </div>
    </div>

    <!-- Список методов по группам -->
    {#if isLoading}
      <div class="flex h-64 items-center justify-center text-sm text-muted-foreground">
        {t.loading}
      </div>
    {:else if rpcGroups().length === 0}
      <div class="bg-card p-12 text-center text-muted-foreground rounded-xl border border-border">
        {t.noRpcs}
      </div>
    {:else}
      <div class="flex flex-col gap-4">
        {#each rpcGroups() as groupItem}
          {@const nonSys = groupItem.methods.filter((m) => !isSystemMethod(m.name))}
          {@const allInGroupSelected = nonSys.length > 0 && nonSys.every((m) => rpcPerms.has(m.name))}
          <div class="bg-card border border-border rounded-xl p-4 shadow-2xs">
            <!-- Заголовок группы -->
            <div class="flex items-center justify-between pb-3 mb-3 border-b border-border">
              <div class="flex items-center gap-2">
                <span class="font-bold text-foreground text-sm tracking-tight font-mono">
                  {groupItem.group}.*
                </span>
                <Badge variant="neutral" size="xs">
                  {groupItem.methods.length}
                </Badge>
              </div>
              {#if nonSys.length > 0}
                <Button
                  variant="ghost"
                  size="sm"
                  onclick={() => toggleRpcGroup(groupItem.methods)}
                >
                  {allInGroupSelected ? t.deselectAll : t.selectAll}
                </Button>
              {/if}
            </div>

            <!-- Список методов -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {#each groupItem.methods as method}
                {@const isChecked = rpcPerms.has(method.name)}
                {@const isSys = isSystemMethod(method.name)}
                <div class="flex items-start gap-2.5 p-2 rounded-lg border border-border/40 hover:bg-muted/50 transition-colors select-none {isChecked ? 'bg-primary/5 border-primary/20' : 'bg-background/40'}">
                  <Checkbox
                    checked={isChecked}
                    disabled={isSys}
                    onchange={() => toggleRpcMethod(method.name)}
                  />
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-1.5 flex-wrap">
                      <span class="font-mono text-xs font-semibold text-foreground truncate">
                        {method.name}
                      </span>
                      <div class="flex items-center gap-1">
                        {#if isSys}
                          <Badge variant="neutral" size="xs">🔒 {t.systemLogin}</Badge>
                        {:else if isChecked}
                          <Badge variant="success" size="xs">✓ Открыто</Badge>
                        {/if}
                        <button
                          type="button"
                          class="inline-flex items-center justify-center w-5 h-5 rounded hover:bg-muted text-muted-foreground hover:text-foreground text-xs transition-colors cursor-pointer"
                          onclick={(e) => {
                            e.stopPropagation();
                            openHelp(method);
                          }}
                          title="Справка по методу"
                        >
                          ℹ️
                        </button>
                      </div>
                    </div>
                    {#if method.description}
                      <p class="text-2xs text-muted-foreground mt-0.5 truncate">
                        {method.description}
                      </p>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {:else}
    <!-- Вкладка: CRUD Таблицы данных -->
    <div class="flex items-center justify-between gap-4 bg-card px-4 py-3 rounded-xl border border-border shadow-2xs">
      <div class="w-72">
        <Input
          bind:value={modelSearch}
          placeholder={t.searchModel}
          size="sm"
        />
      </div>
      <div class="text-xs text-muted-foreground">
        {t.totalModels}: <span class="font-bold text-foreground">{availableModels.length}</span> • 
        {t.openModels}: <span class="font-bold text-emerald-600 dark:text-emerald-400">{activeCrudCount()}</span>
      </div>
    </div>

    {#if isLoading}
      <div class="flex h-64 items-center justify-center text-sm text-muted-foreground">
        {t.loading}
      </div>
    {:else if filteredModels().length === 0}
      <div class="bg-card p-12 text-center text-muted-foreground rounded-xl border border-border">
        {t.noModels}
      </div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        {#each filteredModels() as model}
          {@const isReadAllowed = Boolean(crudPerms[model.key])}
          <div
            class="flex items-start gap-3 p-3.5 rounded-xl border transition-all cursor-pointer select-none {isReadAllowed ? 'bg-primary/5 border-primary/30 shadow-2xs' : 'bg-card border-border hover:border-border/80'}"
            onclick={() => toggleModelRead(model.key)}
          >
            <div class="pt-0.5" onclick={(e) => e.stopPropagation()}>
              <Checkbox
                checked={isReadAllowed}
                onchange={() => toggleModelRead(model.key)}
              />
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center justify-between gap-2">
                <span class="font-bold text-sm text-foreground truncate">
                  {model.verbose_name || model.key}
                </span>
                {#if isReadAllowed}
                  <Badge variant="success" size="xs">{t.crudPublicBadge}</Badge>
                {:else}
                  <Badge variant="neutral" size="xs">{t.crudClosedBadge}</Badge>
                {/if}
              </div>
              <div class="flex items-center gap-1.5 mt-0.5">
                <span class="font-mono text-2xs text-muted-foreground">
                  {model.key}
                </span>
                {#if model.table_name && model.table_name !== model.key}
                  <span class="text-2xs text-muted-foreground/60">•</span>
                  <span class="font-mono text-2xs text-muted-foreground/60">
                    {model.table_name}
                  </span>
                {/if}
              </div>
              <p class="text-2xs text-muted-foreground mt-2 leading-relaxed">
                {t.crudReadDesc}
              </p>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}

  <RpcHelpModal
    open={helpModalOpen}
    method={selectedHelpMethod}
    onclose={() => {
      helpModalOpen = false;
      selectedHelpMethod = null;
    }}
  />
</div>
