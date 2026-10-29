<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import { Button, Input, Card, Badge, Toggle, Modal } from "./ui/index.js";
  import { UserPlus, Menu, AlertCircle, CheckCircle2 } from "@lucide/svelte";

  let { onnotify = () => {} } = $props();

  let usersList = $state([]);
  let rolesList = $state([]);
  let isLoading = $state(false);
  let errorMsg = $state("");
  let statusMsg = $state("");

  // Модальное окно создания пользователя
  let showCreateModal = $state(false);
  let newUsername = $state("");
  let newUserPass = $state("");
  let newFullName = $state("");
  let newEmail = $state("");
  let isCreating = $state(false);

  // Модальное окно назначения ролей
  let showRolesModal = $state(false);
  let selectedUser = $state(null);
  let userRoleSelection = $state({});
  let isSavingRoles = $state(false);
  let roleModalTab = $state("admin");

  // Доступные для ручного назначения роли (исключаем guest и user)
  let assignableRoles = $derived(
    rolesList.filter((r) => r.name !== "guest" && r.name !== "user")
  );

  // Административные роли (admin ВСЕГДА самый верхний, затем adm_*)
  let adminRoles = $derived(
    assignableRoles
      .filter((r) => r.name === "admin" || r.name.startsWith("adm_"))
      .sort((a, b) => {
        if (a.name === "admin") return -1;
        if (b.name === "admin") return 1;
        return a.name.localeCompare(b.name);
      })
  );

  // Пользовательские роли (все остальные)
  let customUserRoles = $derived(
    assignableRoles
      .filter((r) => r.name !== "admin" && !r.name.startsWith("adm_"))
      .sort((a, b) => a.name.localeCompare(b.name))
  );

  // Подсчет активных (выбранных) ролей
  let activeAdminCount = $derived(
    adminRoles.filter((r) => !!userRoleSelection[r.name]).length
  );

  let activeCustomUserCount = $derived(
    customUserRoles.filter((r) => !!userRoleSelection[r.name]).length
  );

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    isLoading = true;
    errorMsg = "";
    try {
      const [uRes, rRes] = await Promise.all([
        rpc.call("User.read", { limit: 100 }),
        rpc.call("Role.read", { limit: 100 }),
      ]);
      usersList = uRes.items || [];
      rolesList = rRes.items || [];
    } catch (e) {
      errorMsg = e.message || "Ошибка загрузки пользователей";
    } finally {
      isLoading = false;
    }
  }

  // Фильтруем роли для отображения в таблице (guest и user скрыты всегда)
  function getDisplayRoles(roles) {
    return (roles || []).filter((r) => r !== "guest" && r !== "user");
  }

  // Определение цветового варианта бейджа
  function getRoleVariant(roleName) {
    if (roleName === "admin") {
      return "danger";
    }
    if (roleName.startsWith("adm_")) {
      return "warning";
    }
    return "default";
  }

  // --- Диалог создания нового пользователя ---
  function openCreateModal() {
    newUsername = "";
    newUserPass = "";
    newFullName = "";
    newEmail = "";
    errorMsg = "";
    showCreateModal = true;
  }

  async function handleCreateUser() {
    if (!newUsername.trim() || !newUserPass) {
      errorMsg = "Поля 'Логин' и 'Пароль' обязательны для заполнения";
      return;
    }
    isCreating = true;
    errorMsg = "";
    try {
      await rpc.call("admin.create_user", {
        username: newUsername.trim(),
        password: newUserPass,
        full_name: newFullName.trim(),
        email: newEmail.trim() || null,
      });
      showCreateModal = false;
      statusMsg = `Пользователь '${newUsername.trim()}' успешно создан`;
      onnotify(statusMsg, "success");
      await loadData();
    } catch (e) {
      errorMsg = e.message || "Ошибка при создании пользователя";
    } finally {
      isCreating = false;
    }
  }

  // --- Диалог назначения ролей ---
  function openRolesModal(user) {
    selectedUser = user;
    roleModalTab = "admin";
    const currentRoles = new Set(user.roles || []);
    const selection = {};
    for (const r of assignableRoles) {
      selection[r.name] = currentRoles.has(r.name);
    }
    userRoleSelection = selection;
    errorMsg = "";
    showRolesModal = true;
  }

  function toggleRole(roleName, checked) {
    userRoleSelection[roleName] = checked;
  }

  async function handleSaveRoles() {
    if (!selectedUser) return;
    isSavingRoles = true;
    errorMsg = "";
    try {
      // Собираем все включенные роли из диалога
      const chosenRoles = Object.entries(userRoleSelection)
        .filter(([_, isChecked]) => isChecked)
        .map(([name]) => name);

      // Гарантируем сохранение базовой роли 'user' у зарегистрированного пользователя
      const currentSet = new Set(selectedUser.roles || []);
      if (currentSet.has("user") || !chosenRoles.includes("user")) {
        chosenRoles.push("user");
      }

      const finalRoles = Array.from(new Set(chosenRoles));

      await rpc.call("admin.set_user_roles", {
        user_id: selectedUser.id,
        roles: finalRoles,
      });

      showRolesModal = false;
      statusMsg = `Роли пользователя '${selectedUser.username}' успешно обновлены`;
      onnotify(statusMsg, "success");
      await loadData();
    } catch (e) {
      errorMsg = e.message || "Ошибка при обновлении ролей";
    } finally {
      isSavingRoles = false;
    }
  }
</script>

<div class="space-y-4">
  <div class="flex items-center justify-between flex-wrap gap-3">
    <div>
      <h2 class="m-0 text-lg font-bold text-text-bright">Пользователи</h2>
      <p class="m-0 text-xs text-muted">Управление учетными записями и правами доступа</p>
    </div>
    <Button variant="primary" onclick={openCreateModal}>
      <UserPlus size={16} />
      <span>Создать пользователя</span>
    </Button>
  </div>

  {#if errorMsg}
    <div class="p-3 rounded bg-danger-subtle text-danger border border-danger text-sm flex items-center gap-2">
      <AlertCircle size={16} />
      <span>{errorMsg}</span>
    </div>
  {/if}

  {#if statusMsg}
    <div class="p-3 rounded bg-success-subtle text-success border border-success text-sm flex items-center gap-2">
      <CheckCircle2 size={16} />
      <span>{statusMsg}</span>
    </div>
  {/if}

  <Card class="p-0 overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full">
        <thead>
          <tr>
            <th class="w-1/4">Логин</th>
            <th class="w-1/3">Имя</th>
            <th>Роли</th>
            <th class="w-16 text-right"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-subtle">
          {#if isLoading}
            <tr>
              <td colspan="4" class="text-center py-8 text-muted">
                Загрузка списка пользователей...
              </td>
            </tr>
          {:else if usersList.length === 0}
            <tr>
              <td colspan="4" class="text-center py-8 text-muted">
                Пользователи не найдены
              </td>
            </tr>
          {:else}
            {#each usersList as u}
              <tr class="hover:bg-panel-hover transition-colors">
                <td class="align-middle">
                  <span class="font-semibold text-text-bright text-sm">{u.username}</span>
                </td>
                <td class="align-middle">
                  <div class="flex flex-col">
                    <span class="text-sm font-medium text-text">{u.full_name || "—"}</span>
                    {#if u.email}
                      <a
                        href="mailto:{u.email}"
                        class="text-xs text-accent hover:underline inline-block mt-0.5"
                      >
                        {u.email}
                      </a>
                    {/if}
                  </div>
                </td>
                <td class="align-middle">
                  <div class="flex flex-wrap gap-1.5 items-center">
                    {#each getDisplayRoles(u.roles) as roleName}
                      <Badge variant={getRoleVariant(roleName)}>
                        {roleName}
                      </Badge>
                    {:else}
                      <span class="text-xs text-muted-light italic">—</span>
                    {/each}
                  </div>
                </td>
                <td class="align-middle text-right">
                  <Button
                    variant="outline"
                    size="icon"
                    onclick={() => openRolesModal(u)}
                    title="Назначить роли"
                    class="border-border-subtle hover:border-accent hover:text-accent"
                  >
                    <Menu size={16} />
                  </Button>
                </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  </Card>
</div>

<!-- Диалог создания нового пользователя -->
<Modal
  open={showCreateModal}
  onclose={() => (showCreateModal = false)}
  title="Создание нового пользователя"
  maxWidth="max-w-md"
>
  <form
    onsubmit={(e) => {
      e.preventDefault();
      handleCreateUser();
    }}
    class="space-y-4"
  >
    <div>
      <label
        for="create-username"
        class="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5"
      >
        Логин <span class="text-danger">*</span>
      </label>
      <Input
        id="create-username"
        placeholder="Введите логин (например, alice)"
        bind:value={newUsername}
        required
      />
    </div>

    <div>
      <label
        for="create-password"
        class="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5"
      >
        Пароль <span class="text-danger">*</span>
      </label>
      <Input
        id="create-password"
        type="password"
        placeholder="Введите пароль"
        bind:value={newUserPass}
        required
      />
    </div>

    <div>
      <label
        for="create-fullname"
        class="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5"
      >
        Полное имя
      </label>
      <Input
        id="create-fullname"
        placeholder="Иван Иванов"
        bind:value={newFullName}
      />
    </div>

    <div>
      <label
        for="create-email"
        class="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5"
      >
        Email
      </label>
      <Input
        id="create-email"
        type="email"
        placeholder="user@example.com"
        bind:value={newEmail}
      />
    </div>
  </form>

  {#snippet footer()}
    <Button
      variant="outline"
      onclick={() => (showCreateModal = false)}
      disabled={isCreating}
    >
      Отмена
    </Button>
    <Button
      variant="primary"
      onclick={handleCreateUser}
      disabled={isCreating}
    >
      {isCreating ? "Создание..." : "Создать"}
    </Button>
  {/snippet}
</Modal>

<!-- Диалог назначения ролей пользователю -->
<Modal
  open={showRolesModal}
  onclose={() => (showRolesModal = false)}
  title={`Назначение ролей: ${selectedUser ? selectedUser.username : ""}`}
  maxWidth="max-w-2xl"
>
  {#if selectedUser}
    <div class="mb-3 text-xs text-muted flex items-center justify-between">
      <span>
        Пользователь: <b class="text-text-bright">{selectedUser.username}</b>
        {#if selectedUser.full_name}
          ({selectedUser.full_name})
        {/if}
      </span>
      <span class="flex items-center gap-1.5">
        <span>Всего выбрано:</span>
        <Badge variant={activeAdminCount + activeCustomUserCount > 0 ? "accent" : "default"}>
          {activeAdminCount + activeCustomUserCount}
        </Badge>
      </span>
    </div>

    <!-- Вкладки категорий ролей: Административные и Пользовательские с указанием количества активных ролей -->
    <div class="flex items-center gap-2 border-b border-border-subtle mb-3">
      <button
        type="button"
        class="min-h-8 px-3.5 py-1.5 text-xs font-semibold uppercase tracking-wider border-b-2 -mb-px flex items-center gap-2 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t {roleModalTab === 'admin' ? 'border-accent text-accent bg-panel-alt/60' : 'border-transparent text-muted hover:text-text hover:bg-panel-hover'}"
        onclick={() => (roleModalTab = "admin")}
      >
        <span>Административные</span>
        <Badge variant={activeAdminCount > 0 ? "warning" : "default"}>
          {activeAdminCount}
        </Badge>
      </button>

      <button
        type="button"
        class="min-h-8 px-3.5 py-1.5 text-xs font-semibold uppercase tracking-wider border-b-2 -mb-px flex items-center gap-2 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t {roleModalTab === 'user' ? 'border-accent text-accent bg-panel-alt/60' : 'border-transparent text-muted hover:text-text hover:bg-panel-hover'}"
        onclick={() => (roleModalTab = "user")}
      >
        <span>Пользовательские</span>
        <Badge variant={activeCustomUserCount > 0 ? "accent" : "default"}>
          {activeCustomUserCount}
        </Badge>
      </button>
    </div>

    {@const displayedRoles = roleModalTab === "admin" ? adminRoles : customUserRoles}

    {#if displayedRoles.length === 0}
      <div class="p-8 text-center text-sm text-muted bg-panel-alt border border-border-subtle rounded-md">
        {#if roleModalTab === "admin"}
          Нет доступных административных ролей
        {:else}
          Нет пользовательских ролей. Новые роли можно создать во вкладке «Матрица прав и Роли».
        {/if}
      </div>
    {:else}
      <div class="border border-border-subtle rounded-md divide-y divide-border-subtle bg-panel-alt overflow-hidden max-h-[420px] overflow-y-auto">
        {#each displayedRoles as role}
          <div
            class="flex items-center justify-between px-4 py-3 hover:bg-panel-hover transition-colors gap-3"
          >
            <div class="flex-1 min-w-0 pr-2">
              <span
                class="text-sm font-medium text-text block truncate"
                title={role.description || role.name}
              >
                {role.description || role.name}
              </span>
            </div>

            <div class="flex-shrink-0">
              <Badge variant={getRoleVariant(role.name)}>
                {role.name}
              </Badge>
            </div>

            <div class="flex-shrink-0 pl-2 flex items-center">
              <Toggle
                checked={!!userRoleSelection[role.name]}
                onchange={(val) => toggleRole(role.name, val)}
                aria-label={`Роль ${role.name}`}
              />
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}

  {#snippet footer()}
    <Button
      variant="outline"
      onclick={() => (showRolesModal = false)}
      disabled={isSavingRoles}
    >
      Отмена
    </Button>
    <Button
      variant="primary"
      onclick={handleSaveRoles}
      disabled={isSavingRoles}
    >
      {isSavingRoles ? "Сохранение..." : "Сохранить"}
    </Button>
  {/snippet}
</Modal>
