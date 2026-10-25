<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import {
    authState,
    canAccessAdminPanel,
    hasAdminSection,
    loginAdmin,
    logoutAdmin,
    refreshSession,
  } from "./auth.svelte.js";

  let activeTab = $state("permissions");
  let loginUser = $state("");
  let loginPass = $state("");
  let errorMsg = $state("");
  let statusMsg = $state("");

  // --- Раздел Матрицы Прав и Ролей (adm_roles / adm_rpc) ---
  let rolesList = $state([]);
  let allMethods = $state([]);
  let selectedRoleName = $state("user");
  let rolePermsSet = $state(new Set());
  let newRoleName = $state("");
  let newRoleDesc = $state("");

  // --- Раздел Пользователей (adm_users) ---
  let usersList = $state([]);
  let newUsername = $state("");
  let newUserPass = $state("");

  // --- Раздел Таблиц CRUD (adm_crud) ---
  let schemas = $state([]);
  let selectedModel = $state("");
  let tableRows = $state([]);
  let tableTotal = $state(0);
  let searchQuery = $state("");
  let newRecordData = $state({});

  onMount(async () => {
    await refreshSession();
    if (canAccessAdminPanel()) {
      pickInitialTab();
      await loadActiveTab();
    }
  });

  function pickInitialTab() {
    if (hasAdminSection("roles") || hasAdminSection("rpc")) {
      activeTab = "permissions";
    } else if (hasAdminSection("users")) {
      activeTab = "users";
    } else if (hasAdminSection("crud")) {
      activeTab = "crud";
    }
  }

  async function selectTab(tab) {
    activeTab = tab;
    errorMsg = "";
    statusMsg = "";
    await loadActiveTab();
  }

  async function loadActiveTab() {
    try {
      if (activeTab === "permissions" && (hasAdminSection("roles") || hasAdminSection("rpc"))) {
        await loadPermissionsMatrix();
      } else if (activeTab === "users" && hasAdminSection("users")) {
        await loadUsers();
      } else if (activeTab === "crud" && hasAdminSection("crud")) {
        await loadSchemas();
      }
    } catch (e) {
      errorMsg = e.message;
    }
  }

  // Группировка методов "Плашка.метод" по точке для карточек в GUI
  function groupedMethodCards() {
    const groups = new Map();
    for (const fullMethod of allMethods) {
      const dotIdx = fullMethod.indexOf(".");
      const cardName = dotIdx > 0 ? fullMethod.slice(0, dotIdx) : "other";
      const actionName = dotIdx > 0 ? fullMethod.slice(dotIdx + 1) : fullMethod;
      if (!groups.has(cardName)) {
        groups.set(cardName, []);
      }
      groups.get(cardName).push({ full: fullMethod, action: actionName });
    }
    return Array.from(groups.entries());
  }

  async function loadPermissionsMatrix() {
    const data = await rpc.call("admin.get_permissions_matrix");
    rolesList = data.roles || [];
    allMethods = data.methods || [];
    const current = rolesList.find((r) => r.name === selectedRoleName) || rolesList[0];
    if (current) {
      selectRoleForEdit(current);
    }
  }

  function selectRoleForEdit(roleObj) {
    selectedRoleName = roleObj.name;
    rolePermsSet = new Set(roleObj.permissions || []);
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

  async function saveRolePermissions() {
    errorMsg = "";
    statusMsg = "";
    try {
      await rpc.call("admin.set_role_permissions", {
        role_name: selectedRoleName,
        permissions: Array.from(rolePermsSet),
      });
      statusMsg = `Права роли «${selectedRoleName}» сохранены`;
      await loadPermissionsMatrix();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function createCustomRole() {
    if (!newRoleName.trim()) return;
    errorMsg = "";
    try {
      await rpc.call("Role.create", {
        data: { name: newRoleName.trim(), description: newRoleDesc.trim() },
      });
      newRoleName = "";
      newRoleDesc = "";
      await loadPermissionsMatrix();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function deleteCustomRole(roleObj) {
    if (roleObj.is_system) return;
    errorMsg = "";
    try {
      await rpc.call("Role.delete", { id: roleObj.id });
      selectedRoleName = "user";
      await loadPermissionsMatrix();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  // --- Пользователи ---
  async function loadUsers() {
    const uRes = await rpc.call("User.read", { limit: 100 });
    usersList = uRes.items || [];
    if (rolesList.length === 0 && (hasAdminSection("roles") || authState.isAdmin)) {
      const rRes = await rpc.call("Role.read", { limit: 100 });
      rolesList = rRes.items || [];
    }
  }

  async function createNewUser() {
    if (!newUsername.trim() || !newUserPass) return;
    errorMsg = "";
    try {
      await rpc.call("admin.create_user", {
        username: newUsername.trim(),
        password: newUserPass,
      });
      newUsername = "";
      newUserPass = "";
      await loadUsers();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function toggleUserRole(userObj, roleName, checked) {
    const current = new Set(userObj.roles || []);
    if (checked) current.add(roleName);
    else current.delete(roleName);
    try {
      await rpc.call("admin.set_user_roles", {
        user_id: userObj.id,
        roles: Array.from(current),
      });
      await loadUsers();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  // --- Таблицы CRUD ---
  async function loadSchemas() {
    schemas = await rpc.call("crud.schemas");
    if (schemas.length > 0 && !selectedModel) {
      await selectModel(schemas[0].name);
    } else if (selectedModel) {
      await loadModelRows();
    }
  }

  async function selectModel(modelName) {
    selectedModel = modelName;
    newRecordData = {};
    await loadModelRows();
  }

  async function loadModelRows() {
    if (!selectedModel) return;
    const res = await rpc.call(`${selectedModel}.read`, {
      search: searchQuery,
      limit: 50,
    });
    tableRows = res.items || [];
    tableTotal = res.total || 0;
  }

  async function createModelRow() {
    errorMsg = "";
    try {
      await rpc.call(`${selectedModel}.create`, { data: newRecordData });
      newRecordData = {};
      await loadModelRows();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function deleteModelRow(id) {
    errorMsg = "";
    try {
      await rpc.call(`${selectedModel}.delete`, { id });
      await loadModelRows();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function handleLoginSubmit(ev) {
    ev.preventDefault();
    errorMsg = "";
    try {
      await loginAdmin(loginUser, loginPass);
      loginPass = "";
      if (canAccessAdminPanel()) {
        pickInitialTab();
        await loadActiveTab();
      }
    } catch (e) {
      errorMsg = e.message;
    }
  }
</script>

{#if authState.loading}
  <div class="login-wrap">Загрузка сессии PyFerro 2.0...</div>
{:else if !authState.userId}
  <div class="login-wrap">
    <form class="login-box" onsubmit={handleLoginSubmit}>
      <h2 style="margin-top:0; color: var(--accent);">PyFerro 2.0 Admin</h2>
      <p style="color: var(--muted); font-size: 0.88rem;">Вход в панель управления (/pyferro_admin)</p>
      {#if errorMsg}
        <p style="color: var(--danger); font-size: 0.88rem;">{errorMsg}</p>
      {/if}
      <div style="display:flex; flex-direction:column; gap: 0.75rem; margin-top: 1rem;">
        <input class="input" placeholder="Имя пользователя" bind:value={loginUser} required />
        <input class="input" type="password" placeholder="Пароль" bind:value={loginPass} required />
        <button class="btn" type="submit">Войти</button>
      </div>
    </form>
  </div>
{:else if !canAccessAdminPanel()}
  <div class="login-wrap">
    <div class="login-box">
      <h3 style="margin-top:0; color: var(--danger);">Доступ запрещен</h3>
      <p style="color: var(--muted); font-size: 0.9rem;">
        Пользователь <b>{authState.username}</b> не имеет ролей администратора (<code>admin</code> или <code>adm_*</code>) и не может войти в <code>/pyferro_admin</code>.
      </p>
      <button class="btn btn-outline" onclick={logoutAdmin}>Выйти из аккаунта</button>
    </div>
  </div>
{:else}
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <span>PyFerro 2.0</span>
        <span class="badge badge-sys">{authState.username}</span>
      </div>

      {#if hasAdminSection("roles") || hasAdminSection("rpc")}
        <button
          class="nav-btn {activeTab === 'permissions' ? 'active' : ''}"
          onclick={() => selectTab("permissions")}
        >
          Матрица прав и Роли
        </button>
      {/if}

      {#if hasAdminSection("users")}
        <button
          class="nav-btn {activeTab === 'users' ? 'active' : ''}"
          onclick={() => selectTab("users")}
        >
          Пользователи
        </button>
      {/if}

      {#if hasAdminSection("crud")}
        <button
          class="nav-btn {activeTab === 'crud' ? 'active' : ''}"
          onclick={() => selectTab("crud")}
        >
          Таблицы (CRUD)
        </button>
      {/if}

      <div style="margin-top: auto; padding-top: 1rem; border-top: 1px solid var(--border);">
        <div style="font-size: 0.78rem; color: var(--muted); margin-bottom: 0.5rem;">
          Роли: {authState.roles.join(", ")}
        </div>
        <button class="btn btn-outline" style="width:100%;" onclick={logoutAdmin}>
          Выйти
        </button>
      </div>
    </aside>

    <main class="content">
      {#if errorMsg}
        <div class="card" style="border-color: var(--danger); margin-bottom: 1rem; color: #fca5a5;">
          {errorMsg}
        </div>
      {/if}
      {#if statusMsg}
        <div class="card" style="border-color: var(--success); margin-bottom: 1rem; color: #86efac;">
          {statusMsg}
        </div>
      {/if}

      {#if activeTab === "permissions"}
        <div class="row-between">
          <div>
            <h2 style="margin:0;">Роли и плашки прав (Плашка.метод)</h2>
            <small style="color: var(--muted);">
              Любая таблица и любой кастомный RPC-метод группируются по точке в единые карточки
            </small>
          </div>
          {#if selectedRoleName !== "admin"}
            <button class="btn" onclick={saveRolePermissions}>
              Сохранить права для «{selectedRoleName}»
            </button>
          {/if}
        </div>

        <div class="card" style="margin-bottom: 1.25rem;">
          <div style="display:flex; flex-wrap:wrap; gap: 0.5rem; align-items:center;">
            {#each rolesList as r}
              <button
                class="btn {selectedRoleName === r.name ? '' : 'btn-outline'}"
                onclick={() => selectRoleForEdit(r)}
              >
                {r.name}
                {#if r.is_system}
                  <span class="badge badge-sys" style="margin-left:0.35rem;">[Системная]</span>
                {/if}
              </button>
              {#if !r.is_system && selectedRoleName === r.name}
                <button class="btn btn-danger" onclick={() => deleteCustomRole(r)}>
                  Удалить роль
                </button>
              {/if}
            {/each}
          </div>

          <div style="display:flex; gap: 0.5rem; margin-top: 0.85rem;">
            <input class="input" placeholder="Новая роль (например manager)" bind:value={newRoleName} />
            <input class="input" placeholder="Описание роли" bind:value={newRoleDesc} />
            <button class="btn btn-outline" onclick={createCustomRole}>+ Создать роль</button>
          </div>
        </div>

        <div class="card-grid">
          {#each groupedMethodCards() as [cardName, methods]}
            <div class="card">
              <div class="card-header">
                <span>{cardName}</span>
                <span class="badge">{methods.length} RPC</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Метод</th>
                    <th style="text-align:center;">Разрешено</th>
                    <th style="text-align:center;">Только свои</th>
                  </tr>
                </thead>
                <tbody>
                  {#each methods as m}
                    <tr>
                      <td><code>.{m.action}</code></td>
                      <td style="text-align:center;">
                        <input
                          type="checkbox"
                          disabled={selectedRoleName === "admin"}
                          checked={selectedRoleName === "admin" || isMethodAllowed(m.full)}
                          onchange={(e) => toggleMethodAllowed(m.full, e.currentTarget.checked)}
                        />
                      </td>
                      <td style="text-align:center;">
                        <input
                          type="checkbox"
                          disabled={selectedRoleName === "admin"}
                          checked={selectedRoleName !== "admin" && isMethodOwnOnly(m.full)}
                          onchange={(e) => toggleMethodOwn(m.full, e.currentTarget.checked)}
                        />
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/each}
        </div>
      {:else if activeTab === "users"}
        <div class="row-between">
          <h2 style="margin:0;">Управление пользователями</h2>
          <div style="display:flex; gap: 0.5rem;">
            <input class="input" placeholder="Логин" bind:value={newUsername} />
            <input class="input" type="password" placeholder="Пароль" bind:value={newUserPass} />
            <button class="btn" onclick={createNewUser}>+ Создать пользователя</button>
          </div>
        </div>

        <div class="card">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Логин</th>
                <th>Роли пользователя</th>
              </tr>
            </thead>
            <tbody>
              {#each usersList as u}
                <tr>
                  <td>{u.id}</td>
                  <td><b>{u.username}</b></td>
                  <td>
                    <div style="display:flex; flex-wrap:wrap; gap: 0.65rem;">
                      {#each rolesList as r}
                        <label style="display:inline-flex; align-items:center; gap:0.25rem; font-size:0.84rem;">
                          <input
                            type="checkbox"
                            checked={(u.roles || []).includes(r.name)}
                            onchange={(e) => toggleUserRole(u, r.name, e.currentTarget.checked)}
                          />
                          <span>{r.name}</span>
                          {#if r.is_system}
                            <span class="badge badge-sys">[Системная]</span>
                          {/if}
                        </label>
                      {/each}
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else if activeTab === "crud"}
        <div class="row-between">
          <div style="display:flex; gap: 0.5rem; flex-wrap:wrap;">
            {#each schemas as s}
              <button
                class="btn {selectedModel === s.name ? '' : 'btn-outline'}"
                onclick={() => selectModel(s.name)}
              >
                {s.title} ({s.name})
              </button>
            {/each}
          </div>
          <div style="display:flex; gap: 0.5rem;">
            <input
              class="input"
              placeholder="Поиск..."
              bind:value={searchQuery}
              onkeydown={(e) => e.key === "Enter" && loadModelRows()}
            />
            <button class="btn btn-outline" onclick={loadModelRows}>Найти</button>
          </div>
        </div>

        {#if selectedModel}
          {@const currentSchema = schemas.find((x) => x.name === selectedModel)}
          {#if currentSchema}
            <div class="card" style="margin-bottom: 1rem;">
              <div class="card-header">
                <span>Создать запись ({selectedModel}.create)</span>
                <span class="badge">Всего записей: {tableTotal}</span>
              </div>
              <div style="display:flex; gap: 0.5rem; flex-wrap:wrap; align-items:center;">
                {#each currentSchema.fields.filter((f) => !f.readonly) as f}
                  <input
                    class="input"
                    placeholder={f.name}
                    bind:value={newRecordData[f.name]}
                  />
                {/each}
                <button class="btn" onclick={createModelRow}>+ Добавить</button>
              </div>
            </div>

            <div class="card">
              <table>
                <thead>
                  <tr>
                    {#each currentSchema.fields as f}
                      <th>{f.name}</th>
                    {/each}
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {#each tableRows as row}
                    <tr>
                      {#each currentSchema.fields as f}
                        <td>{row[f.name] ?? ""}</td>
                      {/each}
                      <td>
                        <button
                          class="btn btn-danger"
                          onclick={() => deleteModelRow(row.id)}
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        {/if}
      {/if}
    </main>
  </div>
{/if}
