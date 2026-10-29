<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import {
    Button,
    Input,
    Card,
    Badge,
    Toggle,
    Modal,
    Checkbox,
    toast,
  } from "./ui/index.js";
  import {
    Plus,
    Trash2,
    Save,
    RotateCcw,
    ChevronDown,
    ChevronRight,
    ShieldCheck,
    ShieldX,
  } from "@lucide/svelte";

  let { onnotify = () => {}, ondirtychange = () => {} } = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);

  let rolesList = $state([]);
  let allMethods = $state([]);

  // Выбранная прикладная роль (по умолчанию user)
  let selectedRoleName = $state("user");
  let rolePermsSet = $state(new Set());
  let originalPermsSet = $state(new Set());

  // Поиск по плашкам и методам
  let searchQuery = $state("");

  // Состояние сворачивания плашек: { [cardName]: boolean }
  let collapsedMap = $state({});

  // Предотвращение потери несохраненных данных при смене роли
  let showUnsavedModal = $state(false);
  let pendingRole = $state(null);

  // Модальное окно создания роли
  let showCreateModal = $state(false);
  let newRoleName = $state("");
  let newRoleDesc = $state("");
  let isCreatingRole = $state(false);

  // Модальное окно подтверждения удаления роли
  let showDeleteModal = $state(false);
  let roleToDelete = $state(null);
  let isDeletingRole = $state(false);

  // Стандартные пояснения к действиям CRUD
  const ACTION_LABELS = {
    read: "Чтение и получение записей",
    create: "Создание новых записей",
    update: "Редактирование записей",
    delete: "Удаление записей",
  };

  onMount(async () => {
    await loadData();
  });

  // Перехват события закрытия или перезагрузки окна браузера при несохраненных изменениях
  $effect(() => {
    const handleBeforeUnload = (e) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  });

  // Уведомление родительского контейнера об изменении статуса несохраненных данных
  $effect(() => {
    ondirtychange(hasUnsavedChanges);
  });

  async function loadData() {
    isLoading = true;
    try {
      const data = await rpc.call("admin.get_permissions_matrix");
      rolesList = data.roles || [];
      allMethods = data.methods || [];

      // В матрице прав настраиваются исключительно пользовательские роли (user, guest, custom)
      const userRoles = rolesList.filter(
        (r) => r.name !== "admin" && !r.name.startsWith("adm_")
      );

      const current =
        userRoles.find((r) => r.name === selectedRoleName) ||
        userRoles.find((r) => r.name === "user") ||
        userRoles[0];

      if (current) {
        selectRole(current);
      }
    } catch (e) {
      toast.error(e.message || "Ошибка загрузки матрицы прав");
    } finally {
      isLoading = false;
    }
  }

  // Пользовательские роли (исключаем admin и adm_*, сортируем: user, guest, далее кастомные)
  let editableRoles = $derived(
    rolesList
      .filter((r) => r.name !== "admin" && !r.name.startsWith("adm_"))
      .sort((a, b) => {
        if (a.name === "user") return -1;
        if (b.name === "user") return 1;
        if (a.name === "guest") return -1;
        if (b.name === "guest") return 1;
        return a.name.localeCompare(b.name);
      })
  );

  // Текущий объект выбранной роли
  let selectedRole = $derived(
    editableRoles.find((r) => r.name === selectedRoleName) || null
  );

  // Проверка несохраненных изменений
  let hasUnsavedChanges = $derived.by(() => {
    if (rolePermsSet.size !== originalPermsSet.size) return true;
    for (const p of rolePermsSet) {
      if (!originalPermsSet.has(p)) return true;
    }
    return false;
  });

  // Подсчет разрешенных методов для текущей роли
  let allowedMethodsCount = $derived.by(() => {
    let count = 0;
    for (const m of allMethods) {
      if (rolePermsSet.has(m) || rolePermsSet.has(`${m}_own`)) {
        count++;
      }
    }
    return count;
  });

  function selectRole(roleObj) {
    selectedRoleName = roleObj.name;
    const perms = new Set(roleObj.permissions || []);
    rolePermsSet = new Set(perms);
    originalPermsSet = new Set(perms);
  }

  // Клик по роли с проверкой несохраненных изменений
  function handleRoleClick(roleObj) {
    if (selectedRoleName === roleObj.name) return;
    if (hasUnsavedChanges) {
      pendingRole = roleObj;
      showUnsavedModal = true;
    } else {
      selectRole(roleObj);
    }
  }

  function discardAndSwitchRole() {
    showUnsavedModal = false;
    if (pendingRole) {
      selectRole(pendingRole);
      pendingRole = null;
    }
  }

  async function saveAndSwitchRole() {
    const target = pendingRole;
    await savePermissions();
    showUnsavedModal = false;
    if (target) {
      selectRole(target);
      pendingRole = null;
    }
  }

  function isMethodAllowed(fullMethod) {
    return rolePermsSet.has(fullMethod) || rolePermsSet.has(`${fullMethod}_own`);
  }

  function isMethodOwnOnly(fullMethod) {
    return rolePermsSet.has(`${fullMethod}_own`);
  }

  function toggleMethodAllowed(fullMethod, checked) {
    const next = new Set(rolePermsSet);
    next.delete(fullMethod);
    next.delete(`${fullMethod}_own`);
    if (checked) {
      next.add(fullMethod);
    }
    rolePermsSet = next;
  }

  function toggleMethodOwn(fullMethod, checked) {
    const next = new Set(rolePermsSet);
    next.delete(fullMethod);
    next.delete(`${fullMethod}_own`);
    if (checked) {
      next.add(`${fullMethod}_own`);
    } else {
      next.add(fullMethod);
    }
    rolePermsSet = next;
  }

  // Быстрые действия над плашкой
  function enableCardMethods(methods) {
    const next = new Set(rolePermsSet);
    for (const m of methods) {
      next.delete(`${m.full}_own`);
      next.add(m.full);
    }
    rolePermsSet = next;
  }

  function disableCardMethods(methods) {
    const next = new Set(rolePermsSet);
    for (const m of methods) {
      next.delete(m.full);
      next.delete(`${m.full}_own`);
    }
    rolePermsSet = next;
  }

  // Глобальные быстрые действия
  function enableAllMethods() {
    rolePermsSet = new Set(allMethods);
  }

  function disableAllMethods() {
    rolePermsSet = new Set();
  }

  function resetChanges() {
    rolePermsSet = new Set(originalPermsSet);
  }

  // Сворачивание и разворачивание плашек (по умолчанию все свернуты)
  function isCollapsed(cardName) {
    if (cardName in collapsedMap) {
      return collapsedMap[cardName];
    }
    return true;
  }

  function toggleCollapse(cardName) {
    const current = isCollapsed(cardName);
    collapsedMap[cardName] = !current;
  }

  function expandAllCards() {
    const map = {};
    for (const [cardName] of groupedMethodCards) {
      map[cardName] = false;
    }
    collapsedMap = map;
  }

  function collapseAllCards() {
    const map = {};
    for (const [cardName] of groupedMethodCards) {
      map[cardName] = true;
    }
    collapsedMap = map;
  }

  // Сохранение прав
  async function savePermissions() {
    isSaving = true;
    try {
      await rpc.call("admin.set_role_permissions", {
        role_name: selectedRoleName,
        permissions: Array.from(rolePermsSet),
      });
      originalPermsSet = new Set(rolePermsSet);
      toast.success(`Права для роли «${selectedRoleName}» успешно сохранены`);
      await loadData();
    } catch (e) {
      toast.error(e.message || "Ошибка сохранения прав");
    } finally {
      isSaving = false;
    }
  }

  // Создание роли
  function openCreateModal() {
    newRoleName = "";
    newRoleDesc = "";
    showCreateModal = true;
  }

  async function handleCreateRole() {
    const trimmedName = newRoleName.trim();
    if (!trimmedName) {
      toast.warning("Имя роли обязательно");
      return;
    }
    isCreatingRole = true;
    try {
      await rpc.call("Role.create", {
        data: {
          name: trimmedName,
          description: newRoleDesc.trim() || null,
        },
      });
      showCreateModal = false;
      toast.success(`Роль «${trimmedName}» успешно создана`);
      selectedRoleName = trimmedName;
      await loadData();
    } catch (e) {
      toast.error(e.message || "Ошибка при создании роли");
    } finally {
      isCreatingRole = false;
    }
  }

  // Удаление роли
  function openDeleteModal(role) {
    roleToDelete = role;
    showDeleteModal = true;
  }

  async function handleDeleteRole() {
    if (!roleToDelete || roleToDelete.is_system) return;
    isDeletingRole = true;
    try {
      await rpc.call("Role.delete", { id: roleToDelete.id });
      showDeleteModal = false;
      toast.success(`Роль «${roleToDelete.name}» удалена`);
      selectedRoleName = "user";
      roleToDelete = null;
      await loadData();
    } catch (e) {
      toast.error(e.message || "Ошибка при удалении роли");
    } finally {
      isDeletingRole = false;
    }
  }

  // Группировка методов по плашкам с учетом поиска
  let groupedMethodCards = $derived.by(() => {
    const q = searchQuery.trim().toLowerCase();
    const groups = new Map();

    for (const fullMethod of allMethods) {
      const dotIdx = fullMethod.indexOf(".");
      const cardName = dotIdx > 0 ? fullMethod.slice(0, dotIdx) : "other";
      const actionName = dotIdx > 0 ? fullMethod.slice(dotIdx + 1) : fullMethod;

      if (
        q &&
        !cardName.toLowerCase().includes(q) &&
        !fullMethod.toLowerCase().includes(q) &&
        !actionName.toLowerCase().includes(q)
      ) {
        continue;
      }

      if (!groups.has(cardName)) {
        groups.set(cardName, []);
      }
      groups.get(cardName).push({
        full: fullMethod,
        action: actionName,
        label: ACTION_LABELS[actionName] || actionName,
      });
    }

    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  });

  // Две вертикальные категории:
  // 1. Левая колонка: плашки, где у роли ЕСТЬ права (хотя бы один метод разрешен)
  let allowedCards = $derived(
    groupedMethodCards.filter(([_, methods]) =>
      methods.some((m) => isMethodAllowed(m.full))
    )
  );

  // 2. Правая колонка: плашки, где у роли НЕТ прав (ни один метод не разрешен)
  let disallowedCards = $derived(
    groupedMethodCards.filter(
      ([_, methods]) => !methods.some((m) => isMethodAllowed(m.full))
    )
  );
</script>

{#snippet renderMethodCard(cardName, methods, isDisallowed)}
  {@const cardAllowedCount = methods.filter((m) => isMethodAllowed(m.full)).length}
  {@const collapsed = isCollapsed(cardName)}
  <Card class="flex flex-col p-0 overflow-hidden transition-all duration-150 border-border-subtle">
    <!-- Заголовок плашки (кликабельный для сворачивания) -->
    <div
      class="flex items-center justify-between px-3.5 py-2.5 bg-panel border-b border-border-subtle cursor-pointer select-none hover:bg-panel-hover transition-colors"
      onclick={() => toggleCollapse(cardName)}
      role="button"
      tabindex="0"
      onkeydown={(e) => (e.key === "Enter" || e.key === " ") && toggleCollapse(cardName)}
    >
      <div class="flex items-center gap-2 min-w-0">
        <div class="text-muted flex items-center justify-center flex-shrink-0">
          {#if collapsed}
            <ChevronRight size={15} />
          {:else}
            <ChevronDown size={15} />
          {/if}
        </div>

        <span class="font-bold text-sm text-text-bright truncate">{cardName}</span>

        <Badge variant={cardAllowedCount > 0 ? "accent" : "default"}>
          {cardAllowedCount}/{methods.length}
        </Badge>
      </div>

      <div class="flex items-center gap-1 flex-shrink-0">
        <button
          type="button"
          title="Разрешить все методы в плашке"
          onclick={(e) => { e.stopPropagation(); enableCardMethods(methods); }}
          class="text-[11px] text-muted hover:text-accent font-medium px-1.5 py-0.5 rounded hover:bg-panel-alt cursor-pointer transition-colors"
        >
          Все
        </button>
        <span class="text-border-subtle">|</span>
        <button
          type="button"
          title="Отключить все методы в плашке"
          onclick={(e) => { e.stopPropagation(); disableCardMethods(methods); }}
          class="text-[11px] text-muted hover:text-danger font-medium px-1.5 py-0.5 rounded hover:bg-panel-alt cursor-pointer transition-colors"
        >
          Снять
        </button>
      </div>
    </div>

    <!-- Список методов внутри плашки (виден только если плашка развернута) -->
    {#if !collapsed}
      <div class="divide-y divide-border-subtle flex-1 bg-panel-alt">
        {#each methods as m}
          {@const allowed = isMethodAllowed(m.full)}
          {@const ownOnly = isMethodOwnOnly(m.full)}
          <div class="px-3.5 py-2 flex items-center justify-between hover:bg-panel-hover transition-colors gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5">
                <code class="text-xs font-semibold text-accent font-mono">
                  .{m.action}
                </code>
                {#if ownOnly}
                  <Badge variant="warning" class="text-[10px] px-1 py-0">
                    только свои
                  </Badge>
                {/if}
              </div>
              <span class="text-[11px] text-muted block truncate mt-0.5" title={m.label}>
                {m.label}
              </span>
            </div>

            <div class="flex items-center gap-3 flex-shrink-0 min-h-8">
              {#if allowed}
                <!-- Флаг «Свои» отображается ТОЛЬКО если метод активен -->
                <label
                  class="flex items-center gap-1.5 cursor-pointer select-none text-[11px] text-muted hover:text-text transition-all"
                  title="Ограничить доступ только к собственным записям пользователя"
                >
                  <Checkbox
                    checked={ownOnly}
                    onchange={(e) => toggleMethodOwn(m.full, e.currentTarget.checked)}
                  />
                  <span>Свои</span>
                </label>
              {/if}

              <!-- Тоггл Разрешено -->
              <Toggle
                checked={allowed}
                onchange={(val) => toggleMethodAllowed(m.full, val)}
                aria-label={`Метод ${m.full}`}
              />
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </Card>
{/snippet}

<div class="space-y-4">
  <!-- Верхняя шапка -->
  <div class="flex items-center justify-between flex-wrap gap-3">
    <div>
      <h2 class="m-0 text-lg font-bold text-text-bright">Роли и матрица прав</h2>
      <p class="m-0 text-xs text-muted">
        Настройка прав доступа для прикладных ролей пользователей (user, guest, кастомные роли)
      </p>
    </div>
    <div class="flex items-center gap-2">
      <Button variant="outline" onclick={openCreateModal}>
        <Plus size={16} />
        <span>Создать роль</span>
      </Button>

      <Button
        variant="primary"
        onclick={savePermissions}
        disabled={isSaving}
        class={hasUnsavedChanges ? "ring-2 ring-accent" : ""}
      >
        <Save size={16} />
        <span>{isSaving ? "Сохранение..." : `Сохранить для «${selectedRoleName}»`}</span>
      </Button>
    </div>
  </div>

  <!-- Секция выбора прикладной роли -->
  <Card class="space-y-3">
    <div class="flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-border-subtle">
      <span class="text-xs font-semibold uppercase tracking-wider text-muted">
        Пользовательские роли для настройки прав
      </span>

      <div class="text-xs text-muted flex items-center gap-1.5">
        <span>Всего ролей:</span>
        <b class="text-text-bright">{editableRoles.length}</b>
      </div>
    </div>

    <!-- Чипы пользовательских ролей -->
    <div class="flex flex-wrap gap-2 pt-1">
      {#each editableRoles as r}
        {@const isSelected = selectedRoleName === r.name}
        <button
          type="button"
          onclick={() => handleRoleClick(r)}
          class="min-h-8 px-3.5 py-1.5 rounded text-sm font-medium transition-all flex items-center gap-2 cursor-pointer select-none border {isSelected ? 'bg-accent text-accent-fg border-accent ring-2 ring-accent/30' : 'bg-panel-alt text-text border-border-subtle hover:bg-panel-hover hover:text-text-bright'}"
        >
          <span>{r.name}</span>
          <Badge
            variant={isSelected ? "default" : (r.is_system ? "accent" : "default")}
            class={isSelected ? "bg-accent-fg/20 text-accent-fg border-transparent" : ""}
          >
            {r.is_system ? "Базовая" : "Кастомная"}
          </Badge>
        </button>
      {/each}
    </div>
  </Card>

  <!-- Информационная карточка выбранной роли -->
  {#if selectedRole}
    <div class="bg-panel border border-border-subtle rounded-md p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div class="space-y-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs text-muted uppercase tracking-wider font-semibold">Настройка прав роли:</span>
          <span class="text-base font-bold text-text-bright">{selectedRole.name}</span>
          <Badge variant={selectedRole.is_system ? "accent" : "default"}>
            {selectedRole.is_system ? "Базовая роль" : "Кастомная роль"}
          </Badge>
          {#if hasUnsavedChanges}
            <Badge variant="warning">Есть несохраненные изменения</Badge>
          {/if}
        </div>
        {#if selectedRole.description}
          <p class="m-0 text-xs text-muted">
            {selectedRole.description}
          </p>
        {/if}
      </div>

      <div class="flex items-center gap-3 flex-wrap">
        <div class="text-xs bg-panel-alt px-3 py-1.5 rounded border border-border-subtle">
          <span class="text-muted">Разрешено методов:</span>
          <b class="text-text-bright ml-1">{allowedMethodsCount} / {allMethods.length}</b>
        </div>

        {#if !selectedRole.is_system}
          <Button
            variant="danger"
            size="sm"
            onclick={() => openDeleteModal(selectedRole)}
          >
            <Trash2 size={14} />
            <span>Удалить роль</span>
          </Button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Панель поиска и быстрых действий -->
  <div class="flex items-center justify-between flex-wrap gap-3">
    <div class="flex items-center gap-2 flex-1 max-w-md">
      <Input
        placeholder="Поиск плашки или метода (например: User, .read, ping)..."
        bind:value={searchQuery}
        class="w-full"
      />
    </div>

    <div class="flex items-center gap-2 flex-wrap text-xs">
      <Button variant="outline" size="sm" onclick={expandAllCards}>
        Развернуть все
      </Button>
      <Button variant="outline" size="sm" onclick={collapseAllCards}>
        Свернуть все
      </Button>
      <Button variant="outline" size="sm" onclick={enableAllMethods}>
        Разрешить все
      </Button>
      <Button variant="outline" size="sm" onclick={disableAllMethods}>
        Снять все
      </Button>
      {#if hasUnsavedChanges}
        <Button variant="outline" size="sm" onclick={resetChanges}>
          <RotateCcw size={13} />
          <span>Сбросить</span>
        </Button>
      {/if}
    </div>
  </div>

  <!-- Две категории плашек по вертикали (колонки): Слева — Есть права, Справа — Нет прав -->
  {#if groupedMethodCards.length === 0}
    <div class="p-12 text-center text-sm text-muted bg-panel-alt border border-border-subtle rounded-md">
      По запросу «{searchQuery}» методов не найдено
    </div>
  {:else}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
      <!-- ─── ЛЕВАЯ КОЛОНКА: Есть права у роли ─── -->
      <div class="space-y-3">
        <div class="flex items-center justify-between pb-2 border-b border-success/40">
          <div class="flex items-center gap-2">
            <ShieldCheck size={18} class="text-success" />
            <span class="font-bold text-sm text-text-bright">Есть доступ</span>
            <Badge variant="success">{allowedCards.length}</Badge>
          </div>
          <span class="text-xs text-muted">
            Плашек: <b class="text-text-bright">{allowedCards.length}</b>
          </span>
        </div>

        {#if allowedCards.length === 0}
          <div class="p-8 text-center text-xs text-muted bg-panel-alt border border-dashed border-border-subtle rounded-md">
            <p class="font-medium text-text mb-1">Нет назначенных прав</p>
            <span>Включите нужные методы в правой колонке («Нет доступа»), чтобы предоставить доступ.</span>
          </div>
        {:else}
          <div class="space-y-3">
            {#each allowedCards as [cardName, methods] (cardName)}
              {@render renderMethodCard(cardName, methods, false)}
            {/each}
          </div>
        {/if}
      </div>

      <!-- ─── ПРАВАЯ КОЛОНКА: Нет прав у роли ─── -->
      <div class="space-y-3">
        <div class="flex items-center justify-between pb-2 border-b border-border-subtle">
          <div class="flex items-center gap-2">
            <ShieldX size={18} class="text-muted" />
            <span class="font-bold text-sm text-text-bright">Нет доступа</span>
            <Badge variant="default">{disallowedCards.length}</Badge>
          </div>
          <span class="text-xs text-muted">
            Без прав: <b class="text-text-bright">{disallowedCards.length}</b>
          </span>
        </div>

        {#if disallowedCards.length === 0}
          <div class="p-8 text-center text-xs text-muted bg-panel-alt border border-dashed border-border-subtle rounded-md">
            <p class="font-medium text-text mb-1">Все разделы активны</p>
            <span>Для роли «{selectedRoleName}» разрешены методы во всех доступных разделах.</span>
          </div>
        {:else}
          <div class="space-y-3">
            {#each disallowedCards as [cardName, methods] (cardName)}
              {@render renderMethodCard(cardName, methods, true)}
            {/each}
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Модальное окно предупреждения о несохраненных изменениях при смене роли -->
  <Modal
    open={showUnsavedModal}
    onclose={() => { showUnsavedModal = false; pendingRole = null; }}
    title="Несохраненные изменения"
    maxWidth="max-w-md"
  >
    <div class="space-y-2 text-sm text-text">
      <p>
        У роли <b class="text-text-bright">{selectedRoleName}</b> есть несохраненные изменения прав.
      </p>
      <p class="text-xs text-muted">
        Сохранить изменения перед переходом к роли <b class="text-accent">{pendingRole?.name}</b> или уйти без сохранения?
      </p>
    </div>

    {#snippet footer()}
      <Button
        variant="outline"
        onclick={() => { showUnsavedModal = false; pendingRole = null; }}
      >
        Отмена
      </Button>
      <Button
        variant="danger"
        onclick={discardAndSwitchRole}
      >
        Не сохранять
      </Button>
      <Button
        variant="primary"
        onclick={saveAndSwitchRole}
        disabled={isSaving}
      >
        {isSaving ? "Сохранение..." : "Сохранить"}
      </Button>
    {/snippet}
  </Modal>

  <!-- Модальное окно создания роли -->
  <Modal
    open={showCreateModal}
    onclose={() => (showCreateModal = false)}
    title="Создать новую прикладную роль"
    maxWidth="max-w-md"
  >
    <form onsubmit={(e) => { e.preventDefault(); handleCreateRole(); }} class="space-y-4">
      <div>
        <label for="new-role-name" class="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
          Системное имя роли (латиница) *
        </label>
        <Input
          id="new-role-name"
          placeholder="например: manager, editor, moderator"
          bind:value={newRoleName}
          autofocus
        />
        <small class="text-muted text-[11px] block mt-1">
          Короткий уникальный идентификатор роли в нижнем регистре
        </small>
      </div>

      <div>
        <label for="new-role-desc" class="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
          Описание роли
        </label>
        <Input
          id="new-role-desc"
          placeholder="например: Управление статьями и каталогом"
          bind:value={newRoleDesc}
        />
      </div>
    </form>

    {#snippet footer()}
      <Button
        variant="outline"
        onclick={() => (showCreateModal = false)}
        disabled={isCreatingRole}
      >
        Отмена
      </Button>
      <Button
        variant="primary"
        onclick={handleCreateRole}
        disabled={isCreatingRole || !newRoleName.trim()}
      >
        {isCreatingRole ? "Создание..." : "Создать роль"}
      </Button>
    {/snippet}
  </Modal>

  <!-- Модальное окно подтверждения удаления роли -->
  <Modal
    open={showDeleteModal}
    onclose={() => (showDeleteModal = false)}
    title="Удаление роли"
    maxWidth="max-w-md"
  >
    {#if roleToDelete}
      <div class="text-sm text-text space-y-2">
        <p>
          Вы действительно хотите удалить роль <b class="text-danger">{roleToDelete.name}</b>?
        </p>
        <p class="text-xs text-muted">
          Пользователи с этой ролью потеряют назначенные права доступа. Это действие необратимо.
        </p>
      </div>
    {/if}

    {#snippet footer()}
      <Button
        variant="outline"
        onclick={() => (showDeleteModal = false)}
        disabled={isDeletingRole}
      >
        Отмена
      </Button>
      <Button
        variant="danger"
        onclick={handleDeleteRole}
        disabled={isDeletingRole}
      >
        {isDeletingRole ? "Удаление..." : "Удалить роль"}
      </Button>
    {/snippet}
  </Modal>
</div>
