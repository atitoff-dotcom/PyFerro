<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import {
    Button,
    Input,
    Card,
    Badge,
    Toggle,
    Checkbox,
    Select,
    Modal,
    toast,
  } from "./ui/index.js";
  import {
    Save,
    RotateCcw,
    Trash2,
    Search,
    ChevronDown,
    ChevronRight,
    HardDrive,
    Zap,
    Image,
    WifiOff,
    RefreshCw,
    CheckCircle2,
  } from "@lucide/svelte";

  let { onnotify = () => {}, ondirtychange = () => {} } = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let isPurging = $state(false);
  let showPurgeModal = $state(false);

  let config = $state({
    enabled: true,
    liefi_timeout_ms: 2500,
    max_media_mb: 250,
    max_rpc_entries: 2000,
    cache_epoch: 1,
  });

  let stats = $state({
    l1_entries: 0,
    tracked_tables: [],
    hits: 0,
    misses: 0,
    not_modified_hits: 0,
    invalidations: 0,
    hit_rate_pct: 0,
    cache_epoch: 1,
  });

  let methodsList = $state([]);
  let originalSnapshot = $state("");
  let searchQuery = $state("");
  let filterMode = $state("all"); // "all" | "cached" | "outbox"
  let collapsedMap = $state({});

  const STRATEGY_OPTIONS = [
    { value: "auto", label: "Авто (ETag + SQLAlchemy)" },
    { value: "ttl", label: "По таймеру (TTL)" },
  ];

  function buildSnapshot(cfg, methods) {
    return JSON.stringify({
      enabled: Boolean(cfg.enabled),
      liefi_timeout_ms: Number(cfg.liefi_timeout_ms),
      max_media_mb: Number(cfg.max_media_mb),
      max_rpc_entries: Number(cfg.max_rpc_entries),
      rules: methods.map((m) => ({
        method_name: m.name,
        cache_enabled: Boolean(m.cache_enabled),
        strategy: m.strategy || "auto",
        ttl_sec: Number(m.ttl_sec || 300),
        prefetch_media: Boolean(m.prefetch_media),
        preload_on_boot: Boolean(m.preload_on_boot),
        offline_outbox: Boolean(m.offline_outbox),
      })),
    });
  }

  let hasUnsavedChanges = $derived(
    !isLoading && originalSnapshot !== "" && buildSnapshot(config, methodsList) !== originalSnapshot
  );

  $effect(() => {
    ondirtychange(hasUnsavedChanges);
  });

  onMount(async () => {
    await loadSettings();
  });

  async function loadSettings() {
    isLoading = true;
    try {
      const res = await rpc.call("cache.get_settings");
      if (res && res.config) {
        config = { ...res.config };
      }
      if (res && Array.isArray(res.methods)) {
        methodsList = res.methods.map((m) => ({ ...m }));
      }
      if (res && res.stats) {
        stats = { ...res.stats };
      }
      originalSnapshot = buildSnapshot(config, methodsList);
    } catch (e) {
      toast.error(`Ошибка загрузки настроек кеша: ${e.message}`);
    } finally {
      isLoading = false;
    }
  }

  async function saveSettings() {
    isSaving = true;
    try {
      const rulesPayload = methodsList.map((m) => ({
        method_name: m.name,
        cache_enabled: Boolean(m.cache_enabled),
        strategy: m.strategy || "auto",
        ttl_sec: Number(m.ttl_sec || 300),
        prefetch_media: Boolean(m.prefetch_media),
        preload_on_boot: Boolean(m.preload_on_boot),
        offline_outbox: Boolean(m.offline_outbox),
      }));
      const res = await rpc.call("cache.save_settings", {
        config: {
          enabled: Boolean(config.enabled),
          liefi_timeout_ms: Number(config.liefi_timeout_ms),
          max_media_mb: Number(config.max_media_mb),
          max_rpc_entries: Number(config.max_rpc_entries),
        },
        rules: rulesPayload,
      });
      if (res && res.stats) {
        stats = { ...res.stats };
      }
      originalSnapshot = buildSnapshot(config, methodsList);
      toast.success("Политика кеширования и оффлайна успешно сохранена!");
      onnotify("Политика кеширования сохранена");
    } catch (e) {
      toast.error(`Ошибка сохранения: ${e.message}`);
    } finally {
      isSaving = false;
    }
  }

  async function confirmPurgeAll() {
    isPurging = true;
    try {
      const res = await rpc.call("cache.purge_all");
      if (res) {
        config.cache_epoch = res.cache_epoch;
        if (res.stats) stats = { ...res.stats };
      }
      showPurgeModal = false;
      toast.success(`Кеш сброшен! Новая эпоха: v${config.cache_epoch}`);
    } catch (e) {
      toast.error(`Ошибка сброса кеша: ${e.message}`);
    } finally {
      isPurging = false;
    }
  }

  let groupedCards = $derived.by(() => {
    const q = searchQuery.trim().toLowerCase();
    const map = new Map();

    for (const m of methodsList) {
      if (filterMode === "cached" && !m.cache_enabled) continue;
      if (filterMode === "outbox" && !m.offline_outbox) continue;
      if (q && !m.name.toLowerCase().includes(q)) continue;

      const dotIdx = m.name.indexOf(".");
      const cardName = dotIdx > 0 ? m.name.slice(0, dotIdx) : "Общие";
      const shortName = dotIdx > 0 ? m.name.slice(dotIdx + 1) : m.name;

      if (!map.has(cardName)) {
        map.set(cardName, []);
      }
      map.get(cardName).push({ item: m, shortName });
    }

    return Array.from(map.entries()).map(([cardName, items]) => ({
      cardName,
      items,
      activeCount: items.filter((x) => x.item.cache_enabled || x.item.offline_outbox).length,
    }));
  });

  function toggleCardCollapse(cardName) {
    collapsedMap[cardName] = !collapsedMap[cardName];
  }

  function enableReadMethodsForCard(card) {
    const readPrefixes = ["get", "list", "read", "find", "search", "load", "fetch", "my_", "topics", "threads"];
    for (const { item, shortName } of card.items) {
      const low = shortName.toLowerCase();
      const isRead =
        low === "read" ||
        readPrefixes.some((p) => low.startsWith(p)) ||
        (!low.startsWith("create") &&
          !low.startsWith("update") &&
          !low.startsWith("delete") &&
          !low.startsWith("save") &&
          !low.startsWith("add") &&
          !low.startsWith("remove") &&
          !low.startsWith("set"));

      if (isRead) {
        item.cache_enabled = true;
        item.prefetch_media = true;
      } else {
        item.offline_outbox = true;
      }
    }
  }

  function clearCardRules(card) {
    for (const { item } of card.items) {
      item.cache_enabled = false;
      item.prefetch_media = false;
      item.preload_on_boot = false;
      item.offline_outbox = false;
    }
  }
</script>

<div class="space-y-4">
  <!-- Заголовок и кнопки сохранения -->
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div>
      <h2 class="m-0 text-xl font-bold text-text-bright flex items-center gap-2">
        <HardDrive size={22} class="text-accent" />
        <span>Кеширование, Offline-First и Медиа-кеш (IndexedDB)</span>
      </h2>
      <p class="text-xs text-muted mt-1 mb-0">
        Централизованное управление серверным L1-кешем, авто-инвалидацией SQLAlchemy и клиентской базой <code>IndexedDB</code> (включая картинки <code>/files/...</code>).
      </p>
    </div>

    <div class="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        onclick={loadSettings}
        disabled={isLoading || isSaving}
        title="Обновить статистику и настройки"
      >
        <RefreshCw size={14} />
        <span>Обновить</span>
      </Button>

      <Button
        variant="danger"
        size="sm"
        onclick={() => (showPurgeModal = true)}
        disabled={isLoading || isPurging}
      >
        <Trash2 size={14} />
        <span>Сбросить кеш (v{config.cache_epoch})</span>
      </Button>

      {#if hasUnsavedChanges}
        <Button
          variant="outline"
          size="sm"
          onclick={loadSettings}
          disabled={isSaving}
        >
          <RotateCcw size={14} />
          <span>Отменить</span>
        </Button>
      {/if}

      <Button
        variant="primary"
        size="sm"
        onclick={saveSettings}
        disabled={!hasUnsavedChanges || isSaving}
      >
        <Save size={14} />
        <span>{isSaving ? "Сохранение..." : "Сохранить политику"}</span>
      </Button>
    </div>
  </div>

  <!-- Статистика серверного L1-кеша -->
  <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
    <Card class="p-3">
      <div class="text-[0.7rem] uppercase tracking-wider text-muted">Записей в L1 RAM</div>
      <div class="text-xl font-bold text-text-bright mt-1">{stats.l1_entries}</div>
      <div class="text-[0.7rem] text-muted mt-0.5">Эпоха: v{stats.cache_epoch}</div>
    </Card>

    <Card class="p-3">
      <div class="text-[0.7rem] uppercase tracking-wider text-muted">Hit Rate (L1)</div>
      <div class="text-xl font-bold text-emerald-500 mt-1">{stats.hit_rate_pct}%</div>
      <div class="text-[0.7rem] text-muted mt-0.5">Hits: {stats.hits} / Miss: {stats.misses}</div>
    </Card>

    <Card class="p-3">
      <div class="text-[0.7rem] uppercase tracking-wider text-muted">ETag 304 (Трафик)</div>
      <div class="text-xl font-bold text-accent mt-1">{stats.not_modified_hits}</div>
      <div class="text-[0.7rem] text-muted mt-0.5">Ответов $not_modified</div>
    </Card>

    <Card class="p-3">
      <div class="text-[0.7rem] uppercase tracking-wider text-muted">Авто-инвалидаций</div>
      <div class="text-xl font-bold text-amber-500 mt-1">{stats.invalidations}</div>
      <div class="text-[0.7rem] text-muted mt-0.5">По COMMIT в SQLAlchemy</div>
    </Card>

    <Card class="p-3">
      <div class="text-[0.7rem] uppercase tracking-wider text-muted">Таблиц под контролем</div>
      <div class="text-xl font-bold text-text-bright mt-1">{stats.tracked_tables?.length || 0}</div>
      <div class="text-[0.7rem] text-muted mt-0.5 truncate" title={(stats.tracked_tables || []).join(", ")}>
        {(stats.tracked_tables || []).join(", ") || "Ожидание запросов"}
      </div>
    </Card>
  </div>

  <!-- Глобальные параметры IndexedDB и сети -->
  <Card>
    <div class="flex flex-wrap items-center justify-between gap-4 pb-3 mb-3 border-b border-border-subtle">
      <div class="flex items-center gap-3">
        <Toggle bind:checked={config.enabled} />
        <div>
          <div class="font-bold text-sm text-text-bright">Включить подсистему кеширования и Offline-First</div>
          <div class="text-xs text-muted">
            Все ответы и изображения сохраняются на клиенте строго в <code>IndexedDB (pyferro2_storage)</code>.
          </div>
        </div>
      </div>
      <Badge variant={config.enabled ? "success" : "default"}>
        {config.enabled ? "Активно" : "Выключено"}
      </Badge>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div>
        <label class="block text-xs font-medium text-muted mb-1">
          Таймаут медленной сети (Lie-Fi Timeout, мс)
        </label>
        <Input
          type="number"
          min={500}
          max={30000}
          step={250}
          bind:value={config.liefi_timeout_ms}
        />
        <span class="text-[0.7rem] text-muted">
          Если сеть не отвечает за это время, клиент мгновенно отдает копию из IndexedDB.
        </span>
      </div>

      <div>
        <label class="block text-xs font-medium text-muted mb-1">
          Лимит медиа-кеша картинок в IndexedDB (МБ)
        </label>
        <Input
          type="number"
          min={10}
          max={2048}
          step={10}
          bind:value={config.max_media_mb}
        />
        <span class="text-[0.7rem] text-muted">
          Хранилище <code>files_cache</code> для оффлайн-картинок статей, форума и дневников (LRU).
        </span>
      </div>

      <div>
        <label class="block text-xs font-medium text-muted mb-1">
          Макс. записей ответов в IndexedDB (rpc_cache)
        </label>
        <Input
          type="number"
          min={100}
          max={50000}
          step={100}
          bind:value={config.max_rpc_entries}
        />
        <span class="text-[0.7rem] text-muted">
          При превышении старые неиспользуемые ответы удаляются автоматически.
        </span>
      </div>
    </div>
  </Card>

  <!-- Панель фильтрации и поиска по плашкам -->
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex items-center gap-2 flex-1 min-w-[240px]">
      <div class="relative flex-1 max-w-md">
        <Input
          placeholder="Поиск плашки или метода (например, Calculator, Articles, Forum)..."
          bind:value={searchQuery}
        />
      </div>
      <div class="flex items-center gap-1">
        <Button
          variant={filterMode === "all" ? "primary" : "outline"}
          size="sm"
          onclick={() => (filterMode = "all")}
        >
          Все ({methodsList.length})
        </Button>
        <Button
          variant={filterMode === "cached" ? "primary" : "outline"}
          size="sm"
          onclick={() => (filterMode = "cached")}
        >
          Кешируемые ({methodsList.filter((m) => m.cache_enabled).length})
        </Button>
        <Button
          variant={filterMode === "outbox" ? "primary" : "outline"}
          size="sm"
          onclick={() => (filterMode = "outbox")}
        >
          Outbox ({methodsList.filter((m) => m.offline_outbox).length})
        </Button>
      </div>
    </div>
  </div>

  <!-- Список плашек и методов -->
  {#if isLoading}
    <Card class="p-6 text-center text-muted text-sm">
      Загрузка списка плашек и правил кеширования...
    </Card>
  {:else if groupedCards.length === 0}
    <Card class="p-6 text-center text-muted text-sm">
      Методы по вашему запросу не найдены.
    </Card>
  {:else}
    <div class="space-y-3">
      {#each groupedCards as card (card.cardName)}
        <Card class="p-0 overflow-hidden">
          <!-- Шапка плашки -->
          <div class="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 bg-bg/50 border-b border-border-subtle">
            <button
              type="button"
              class="flex items-center gap-2 bg-transparent border-0 p-0 cursor-pointer text-left text-text-bright font-bold text-sm"
              onclick={() => toggleCardCollapse(card.cardName)}
            >
              {#if collapsedMap[card.cardName]}
                <ChevronRight size={16} class="text-muted" />
              {:else}
                <ChevronDown size={16} class="text-muted" />
              {/if}
              <span>Плашка <code class="text-accent">{card.cardName}</code></span>
              <Badge variant={card.activeCount > 0 ? "accent" : "default"}>
                Активно: {card.activeCount} / {card.items.length}
              </Badge>
            </button>

            <div class="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                class="text-xs py-1"
                onclick={() => enableReadMethodsForCard(card)}
                title="Автоматически включить кеш + картинки для методов чтения и Outbox для записи"
              >
                <Zap size={13} />
                <span>Авто-настройка плашки</span>
              </Button>
              {#if card.activeCount > 0}
                <Button
                  variant="outline"
                  size="sm"
                  class="text-xs py-1"
                  onclick={() => clearCardRules(card)}
                >
                  Очистить
                </Button>
              {/if}
            </div>
          </div>

          {#if !collapsedMap[card.cardName]}
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-xs text-muted border-b border-border-subtle">
                    <th class="py-2 px-3">Метод</th>
                    <th class="py-2 px-3">Scope</th>
                    <th class="py-2 px-3">Кешировать (IndexedDB + L1)</th>
                    <th class="py-2 px-3">Стратегия свежести</th>
                    <th class="py-2 px-3">Картинки (/files)</th>
                    <th class="py-2 px-3">При старте (Boot)</th>
                    <th class="py-2 px-3">Оффлайн-запись (Outbox)</th>
                  </tr>
                </thead>
                <tbody>
                  {#each card.items as { item, shortName } (item.name)}
                    <tr class="border-b border-border-subtle/50 hover:bg-bg/30">
                      <td class="py-2 px-3 font-mono text-xs">
                        <span class="text-muted">{card.cardName}.</span><b class="text-text-bright">{shortName}</b>
                      </td>
                      <td class="py-2 px-3">
                        <Badge variant={item.scope === "public" ? "success" : "default"}>
                          {item.scope === "public" ? "Public (Общий)" : "User (Личный)"}
                        </Badge>
                      </td>
                      <td class="py-2 px-3">
                        <Checkbox
                          bind:checked={item.cache_enabled}
                          label={item.cache_enabled ? "Вкл" : "Выкл"}
                        />
                      </td>
                      <td class="py-2 px-3">
                        {#if item.cache_enabled}
                          <div class="flex items-center gap-2">
                            <Select
                              options={STRATEGY_OPTIONS}
                              bind:value={item.strategy}
                              class="text-xs min-w-[170px]"
                            />
                            {#if item.strategy === "ttl"}
                              <Input
                                type="number"
                                min={1}
                                max={604800}
                                bind:value={item.ttl_sec}
                                class="w-20 text-xs"
                                title="Время жизни в секундах"
                              />
                              <span class="text-xs text-muted">с</span>
                            {/if}
                          </div>
                        {:else}
                          <span class="text-xs text-muted">—</span>
                        {/if}
                      </td>
                      <td class="py-2 px-3">
                        <Checkbox
                          bind:checked={item.prefetch_media}
                          disabled={!item.cache_enabled}
                          label="Кешировать фото"
                        />
                      </td>
                      <td class="py-2 px-3">
                        <Checkbox
                          bind:checked={item.preload_on_boot}
                          disabled={!item.cache_enabled || item.has_required_params}
                          label={item.has_required_params ? "Нужны аргументы" : "Прогрев на старте"}
                        />
                      </td>
                      <td class="py-2 px-3">
                        <Checkbox
                          bind:checked={item.offline_outbox}
                          label="Очередь Outbox"
                        />
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </Card>
      {/each}
    </div>
  {/if}
</div>

<Modal
  open={showPurgeModal}
  onclose={() => (showPurgeModal = false)}
  title="Сбросить серверный и клиентский кеш?"
  maxWidth="max-w-md"
>
  <div class="space-y-2 text-sm text-text">
    <p>
      Это действие очистит серверный L1-кеш в оперативной памяти и увеличит глобальную эпоху кеша до <b>v{config.cache_epoch + 1}</b>.
    </p>
    <p class="text-xs text-muted">
      Все подключенные клиенты автоматически обновят свои закешированные данные в <code>IndexedDB</code>.
    </p>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (showPurgeModal = false)}>
      Отмена
    </Button>
    <Button variant="danger" onclick={confirmPurgeAll} disabled={isPurging}>
      {isPurging ? "Сброс..." : "Сбросить весь кеш"}
    </Button>
  {/snippet}
</Modal>
