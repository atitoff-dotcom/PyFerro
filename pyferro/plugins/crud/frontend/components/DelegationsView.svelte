<script lang="ts">
  import { onMount } from "svelte";

  interface Props {
    lang?: "ru" | "en";
    rpcClient: any;
    onnotify?: (msg: string, type: "success" | "error" | "info") => void;
  }

  let { lang = "ru", rpcClient, onnotify }: Props = $props();

  interface DelegationItem {
    id: number;
    from_user_id: number;
    from_user_name: string;
    from_user_login: string;
    to_user_id: number;
    to_user_name: string;
    to_user_login: string;
    model_name: string | null;
    valid_from: string | null;
    valid_to: string | null;
    is_active: boolean;
    status: "active" | "scheduled" | "expired" | "disabled";
    created_at: string | null;
  }

  interface UserOption {
    id: number;
    login: string;
    name: string;
  }

  interface ModelOption {
    key: string;
    verbose_name: string;
  }

  let delegations = $state<DelegationItem[]>([]);
  let usersList = $state<UserOption[]>([]);
  let modelsList = $state<ModelOption[]>([]);
  let isLoading = $state(true);
  let errorMsg = $state("");
  let searchQuery = $state("");
  let statusFilter = $state<"all" | "active" | "scheduled" | "expired" | "disabled">("all");

  // Состояние модалки создания
  let showCreateModal = $state(false);
  let isCreating = $state(false);
  let createError = $state("");

  let newFromUserId = $state<number | "">("");
  let newToUserId = $state<number | "">("");
  let newModelName = $state<string>("");
  let useDateRange = $state(false);
  let newValidFrom = $state("");
  let newValidTo = $state("");

  const t = $derived({
    title: lang === "ru" ? "Замещения и делегирование" : "Delegations & Substitutions",
    desc: lang === "ru" ? "Сквозной реестр временной передачи полномочий между сотрудниками (UserDelegation)" : "Enterprise registry of temporary role and record authority delegation",
    newBtn: lang === "ru" ? "+ Назначить замещение" : "+ New Delegation",
    refreshBtn: lang === "ru" ? "Обновить" : "Refresh",
    searchPlaceholder: lang === "ru" ? "Поиск по имени или логину..." : "Search by name or login...",
    filterAll: lang === "ru" ? "Все статусы" : "All Statuses",
    filterActive: lang === "ru" ? "Активные" : "Active",
    filterScheduled: lang === "ru" ? "Запланированные" : "Scheduled",
    filterExpired: lang === "ru" ? "Истекшие" : "Expired",
    filterDisabled: lang === "ru" ? "Отключенные" : "Disabled",
    colFrom: lang === "ru" ? "Кого замещают" : "Delegator (From)",
    colTo: lang === "ru" ? "Кто замещает" : "Substitute (To)",
    colScope: lang === "ru" ? "Область полномочий" : "Scope / Model",
    colDates: lang === "ru" ? "Срок действия" : "Validity Period",
    colStatus: lang === "ru" ? "Статус" : "Status",
    colActions: lang === "ru" ? "Действия" : "Actions",
    allModels: lang === "ru" ? "Все модели 🌐" : "All Models 🌐",
    permanent: lang === "ru" ? "Бессрочно" : "Permanent",
    empty: lang === "ru" ? "Замещений не найдено" : "No delegations found",
    loading: lang === "ru" ? "Загрузка реестра замещений..." : "Loading delegations...",
    statusActive: lang === "ru" ? "Активно" : "Active",
    statusScheduled: lang === "ru" ? "Запланировано" : "Scheduled",
    statusExpired: lang === "ru" ? "Истекло" : "Expired",
    statusDisabled: lang === "ru" ? "Выключено" : "Disabled",
    modalTitle: lang === "ru" ? "Назначить замещение полномочий" : "Delegate Authority",
    modalFromUser: lang === "ru" ? "Сотрудник (кого замещают):" : "Delegator (absent employee):",
    modalToUser: lang === "ru" ? "Заместитель (кто замещает):" : "Substitute (who will act):",
    modalScope: lang === "ru" ? "Область делегирования:" : "Delegation Scope:",
    modalDatesToggle: lang === "ru" ? "Ограничить период действия (отпуск / командировка)" : "Limit time window (vacation / sick leave)",
    modalFromDate: lang === "ru" ? "Дата начала:" : "Start Date:",
    modalToDate: lang === "ru" ? "Дата окончания:" : "End Date:",
    modalCancel: lang === "ru" ? "Отмена" : "Cancel",
    modalSubmit: lang === "ru" ? "Создать замещение" : "Create Delegation",
    modalSubmitting: lang === "ru" ? "Создание..." : "Creating...",
    deleteConfirm: lang === "ru" ? "Удалить это замещение полномочий?" : "Delete this delegation permanently?",
    successToggled: lang === "ru" ? "Статус замещения обновлен" : "Delegation status updated",
    successCreated: lang === "ru" ? "Замещение успешно создано" : "Delegation created successfully",
    successDeleted: lang === "ru" ? "Замещение удалено" : "Delegation deleted",
  });

  async function loadData() {
    isLoading = true;
    errorMsg = "";
    try {
      const [delList, opts] = await Promise.all([
        rpcClient.call("admin.delegations_list", {}),
        rpcClient.call("admin.delegation_options", {}),
      ]);
      delegations = delList || [];
      usersList = opts?.users || [];
      modelsList = opts?.models || [];
    } catch (e: any) {
      errorMsg = e?.message || String(e);
      if (onnotify) onnotify(errorMsg, "error");
    } finally {
      isLoading = false;
    }
  }

  async function toggleActive(item: DelegationItem) {
    try {
      const res = await rpcClient.call("admin.delegation_toggle", { id: item.id });
      item.is_active = res.is_active;
      if (!item.is_active) {
        item.status = "disabled";
      } else {
        const now = new Date();
        if (item.valid_from && new Date(item.valid_from) > now) item.status = "scheduled";
        else if (item.valid_to && new Date(item.valid_to) < now) item.status = "expired";
        else item.status = "active";
      }
      if (onnotify) onnotify(t.successToggled, "success");
    } catch (e: any) {
      if (onnotify) onnotify(e?.message || String(e), "error");
    }
  }

  async function deleteItem(id: number) {
    if (!confirm(t.deleteConfirm)) return;
    try {
      await rpcClient.call("admin.delegation_delete", { id });
      delegations = delegations.filter(d => d.id !== id);
      if (onnotify) onnotify(t.successDeleted, "success");
    } catch (e: any) {
      if (onnotify) onnotify(e?.message || String(e), "error");
    }
  }

  function openCreateModal() {
    newFromUserId = "";
    newToUserId = "";
    newModelName = "";
    useDateRange = false;
    newValidFrom = "";
    newValidTo = "";
    createError = "";
    showCreateModal = true;
  }

  async function handleCreateSubmit() {
    if (!newFromUserId || !newToUserId) {
      createError = lang === "ru" ? "Выберите обоих сотрудников" : "Please select both employees";
      return;
    }
    if (newFromUserId === newToUserId) {
      createError = lang === "ru" ? "Сотрудник не может замещать самого себя" : "An employee cannot substitute themselves";
      return;
    }
    isCreating = true;
    createError = "";
    try {
      await rpcClient.call("admin.delegation_create", {
        from_user_id: Number(newFromUserId),
        to_user_id: Number(newToUserId),
        model_name: newModelName || undefined,
        valid_from: useDateRange && newValidFrom ? newValidFrom : undefined,
        valid_to: useDateRange && newValidTo ? newValidTo : undefined,
        is_active: true,
      });
      showCreateModal = false;
      if (onnotify) onnotify(t.successCreated, "success");
      await loadData();
    } catch (e: any) {
      createError = e?.message || String(e);
    } finally {
      isCreating = false;
    }
  }

  const filteredDelegations = $derived.by(() => {
    let list = delegations;
    const q = searchQuery.toLowerCase().trim();
    if (q) {
      list = list.filter(d =>
        d.from_user_name.toLowerCase().includes(q) ||
        d.from_user_login.toLowerCase().includes(q) ||
        d.to_user_name.toLowerCase().includes(q) ||
        d.to_user_login.toLowerCase().includes(q) ||
        (d.model_name && d.model_name.toLowerCase().includes(q))
      );
    }
    if (statusFilter !== "all") {
      list = list.filter(d => d.status === statusFilter);
    }
    return list;
  });

  onMount(() => {
    loadData();
  });
</script>

<div class="flex-1 flex flex-col p-6 gap-6 overflow-y-auto">
  <!-- Верхний заголовок -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card p-5 rounded-2xl border border-border shadow-xs">
    <div>
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold">
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
          </svg>
        </div>
        <div>
          <h2 class="text-base font-bold text-foreground">{t.title}</h2>
          <p class="text-xs text-muted-foreground mt-0.5">{t.desc}</p>
        </div>
      </div>
    </div>
    <div class="flex items-center gap-2">
      <button
        type="button"
        onclick={loadData}
        class="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-xl border border-border bg-card text-foreground hover:bg-muted transition-colors cursor-pointer"
      >
        <svg class="h-3.5 w-3.5 {isLoading ? 'animate-spin' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {t.refreshBtn}
      </button>
      <button
        type="button"
        onclick={openCreateModal}
        class="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs cursor-pointer"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        {t.newBtn}
      </button>
    </div>
  </div>

  <!-- Панель фильтров -->
  <div class="flex flex-col sm:flex-row gap-3">
    <div class="relative flex-1">
      <svg class="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <input
        type="text"
        bind:value={searchQuery}
        placeholder={t.searchPlaceholder}
        class="w-full pl-10 pr-4 py-2 text-xs rounded-xl border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
      />
    </div>
    <div class="flex items-center gap-1.5 overflow-x-auto">
      {#each ["all", "active", "scheduled", "expired", "disabled"] as const as st}
        <button
          type="button"
          onclick={() => statusFilter = st}
          class="px-3 py-1.5 text-xs rounded-xl font-medium transition-colors cursor-pointer {statusFilter === st ? 'bg-primary text-primary-foreground font-semibold shadow-2xs' : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'}"
        >
          {st === "all" ? t.filterAll : st === "active" ? t.filterActive : st === "scheduled" ? t.filterScheduled : st === "expired" ? t.filterExpired : t.filterDisabled}
        </button>
      {/each}
    </div>
  </div>

  <!-- Таблица делегирований -->
  <div class="bg-card rounded-2xl border border-border overflow-hidden shadow-xs">
    {#if isLoading}
      <div class="p-12 text-center text-xs text-muted-foreground flex items-center justify-center gap-3">
        <svg class="animate-spin h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg>
        {t.loading}
      </div>
    {:else if filteredDelegations.length === 0}
      <div class="p-12 text-center text-xs text-muted-foreground">
        <div class="w-12 h-12 mx-auto mb-3 rounded-full bg-muted/60 flex items-center justify-center text-muted-foreground">
          <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        {t.empty}
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead class="bg-muted/50 border-b border-border text-muted-foreground uppercase text-2xs font-semibold tracking-wider">
            <tr>
              <th class="px-5 py-3.5">{t.colFrom}</th>
              <th class="px-3 py-3.5 text-center w-8"></th>
              <th class="px-5 py-3.5">{t.colTo}</th>
              <th class="px-5 py-3.5">{t.colScope}</th>
              <th class="px-5 py-3.5">{t.colDates}</th>
              <th class="px-5 py-3.5">{t.colStatus}</th>
              <th class="px-5 py-3.5 text-right">{t.colActions}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each filteredDelegations as item (item.id)}
              <tr class="hover:bg-muted/30 transition-colors">
                <!-- От кого -->
                <td class="px-5 py-4">
                  <div class="flex items-center gap-2.5">
                    <div class="w-7 h-7 rounded-lg bg-primary/10 text-primary font-bold text-xs flex items-center justify-center">
                      {(item.from_user_name || item.from_user_login || "U").charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div class="font-semibold text-foreground">{item.from_user_name}</div>
                      <div class="text-2xs text-muted-foreground">@{item.from_user_login}</div>
                    </div>
                  </div>
                </td>

                <!-- Стрелка -->
                <td class="px-3 py-4 text-center text-muted-foreground">
                  <svg class="h-4 w-4 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </td>

                <!-- Кому -->
                <td class="px-5 py-4">
                  <div class="flex items-center gap-2.5">
                    <div class="w-7 h-7 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-bold text-xs flex items-center justify-center">
                      {(item.to_user_name || item.to_user_login || "U").charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div class="font-semibold text-foreground">{item.to_user_name}</div>
                      <div class="text-2xs text-muted-foreground">@{item.to_user_login}</div>
                    </div>
                  </div>
                </td>

                <!-- Модель / Скоуп -->
                <td class="px-5 py-4">
                  {#if item.model_name}
                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-2xs font-semibold bg-primary/10 text-primary border border-primary/20">
                      📦 {item.model_name}
                    </span>
                  {:else}
                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-2xs font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                      🌐 {t.allModels}
                    </span>
                  {/if}
                </td>

                <!-- Период дат -->
                <td class="px-5 py-4">
                  {#if item.valid_from || item.valid_to}
                    <div class="text-2xs space-y-0.5">
                      {#if item.valid_from}
                        <div class="text-muted-foreground">С: <span class="text-foreground font-medium">{new Date(item.valid_from).toLocaleDateString()}</span></div>
                      {/if}
                      {#if item.valid_to}
                        <div class="text-muted-foreground">По: <span class="text-foreground font-medium">{new Date(item.valid_to).toLocaleDateString()}</span></div>
                      {/if}
                    </div>
                  {:else}
                    <span class="text-2xs text-muted-foreground font-medium">{t.permanent}</span>
                  {/if}
                </td>

                <!-- Статус -->
                <td class="px-5 py-4">
                  {#if item.status === "active"}
                    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                      <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                      {t.statusActive}
                    </span>
                  {:else if item.status === "scheduled"}
                    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                      <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                      {t.statusScheduled}
                    </span>
                  {:else if item.status === "expired"}
                    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-semibold bg-zinc-500/10 text-zinc-500 border border-zinc-500/20">
                      {t.statusExpired}
                    </span>
                  {:else}
                    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-semibold bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20">
                      {t.statusDisabled}
                    </span>
                  {/if}
                </td>

                <!-- Действия -->
                <td class="px-5 py-4 text-right">
                  <div class="flex items-center justify-end gap-3">
                    <label class="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={item.is_active}
                        onchange={() => toggleActive(item)}
                        class="sr-only peer"
                      />
                      <div class="w-8 h-4 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
                    </label>

                    <button
                      type="button"
                      onclick={() => deleteItem(item.id)}
                      class="text-muted-foreground hover:text-red-600 p-1 rounded-lg hover:bg-red-500/10 transition-colors cursor-pointer"
                      title="Удалить"
                    >
                      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>

<!-- Модальное окно создания замещения -->
{#if showCreateModal}
  <div class="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
    <div class="bg-card w-full max-w-lg rounded-2xl border border-border shadow-xl overflow-hidden">
      <div class="p-6 border-b border-border flex items-center justify-between">
        <h3 class="text-sm font-bold text-foreground flex items-center gap-2">
          <svg class="h-4 w-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
          </svg>
          {t.modalTitle}
        </h3>
        <button
          type="button"
          onclick={() => showCreateModal = false}
          class="text-muted-foreground hover:text-foreground text-sm cursor-pointer"
        >
          ✕
        </button>
      </div>

      <div class="p-6 space-y-4">
        {#if createError}
          <div class="p-3 text-xs rounded-xl bg-destructive/10 text-destructive border border-destructive/20 font-medium">
            {createError}
          </div>
        {/if}

        <div>
          <label class="block text-2xs uppercase tracking-wider font-semibold text-muted-foreground mb-1.5">{t.modalFromUser}</label>
          <select
            bind:value={newFromUserId}
            class="w-full px-3 py-2 text-xs rounded-xl border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="" disabled>-- Выберите сотрудника --</option>
            {#each usersList as u}
              <option value={u.id}>{u.name} (@{u.login})</option>
            {/each}
          </select>
        </div>

        <div>
          <label class="block text-2xs uppercase tracking-wider font-semibold text-muted-foreground mb-1.5">{t.modalToUser}</label>
          <select
            bind:value={newToUserId}
            class="w-full px-3 py-2 text-xs rounded-xl border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="" disabled>-- Выберите заместителя --</option>
            {#each usersList as u}
              <option value={u.id}>{u.name} (@{u.login})</option>
            {/each}
          </select>
        </div>

        <div>
          <label class="block text-2xs uppercase tracking-wider font-semibold text-muted-foreground mb-1.5">{t.modalScope}</label>
          <select
            bind:value={newModelName}
            class="w-full px-3 py-2 text-xs rounded-xl border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="">🌐 {t.allModels}</option>
            {#each modelsList as m}
              <option value={m.key}>📦 {m.verbose_name} ({m.key})</option>
            {/each}
          </select>
        </div>

        <div class="pt-2">
          <label class="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              bind:checked={useDateRange}
              class="rounded border-border text-primary focus:ring-primary/20"
            />
            <span class="text-xs font-medium text-foreground">{t.modalDatesToggle}</span>
          </label>
        </div>

        {#if useDateRange}
          <div class="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label class="block text-2xs text-muted-foreground mb-1">{t.modalFromDate}</label>
              <input
                type="date"
                bind:value={newValidFrom}
                class="w-full px-3 py-1.5 text-xs rounded-xl border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div>
              <label class="block text-2xs text-muted-foreground mb-1">{t.modalToDate}</label>
              <input
                type="date"
                bind:value={newValidTo}
                class="w-full px-3 py-1.5 text-xs rounded-xl border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
          </div>
        {/if}
      </div>

      <div class="p-4 bg-muted/30 border-t border-border flex items-center justify-end gap-2">
        <button
          type="button"
          onclick={() => showCreateModal = false}
          class="px-4 py-2 text-xs font-medium rounded-xl border border-border bg-card text-foreground hover:bg-muted transition-colors cursor-pointer"
        >
          {t.modalCancel}
        </button>
        <button
          type="button"
          disabled={isCreating}
          onclick={handleCreateSubmit}
          class="px-4 py-2 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs cursor-pointer disabled:opacity-50"
        >
          {isCreating ? t.modalSubmitting : t.modalSubmit}
        </button>
      </div>
    </div>
  </div>
{/if}
