<script>
  import { onMount } from "svelte";
  import {
    authState,
    canAccessAdminPanel,
    hasAdminSection,
    loginAdmin,
    logoutAdmin,
    refreshSession,
  } from "./auth.svelte.js";
  import { rpc } from "./rpc.js";
  import SeoView from "./SeoView.svelte";
  import HelpView from "./HelpView.svelte";
  import UsersView from "./UsersView.svelte";
  import PermissionsView from "./PermissionsView.svelte";
  import { initTheme, toggleTheme, isDark } from "./theme.svelte.js";
  import {
    Button,
    Input,
    Card,
    Badge,
    Checkbox,
    Modal,
    ToastContainer,
    toast,
  } from "./ui/index.js";
  import {
    Boxes,
    Sun,
    Moon,
    KeyRound,
    Users,
    Database,
    Network,
    BookOpen,
    LogOut,
    Plus,
    Search,
    Trash2,
  } from "@lucide/svelte";

  let activeTab = $state("permissions");
  let loginUser = $state("");
  let loginPass = $state("");
  let errorMsg = $state("");
  let statusMsg = $state("");
  let helpSlug = $state("");

  function parseUrlRoute() {
    if (typeof window === "undefined") return null;
    const path = window.location.pathname;
    if (path.startsWith("/pyferro_admin/help")) {
      const slugPart = path.replace("/pyferro_admin/help", "").replace(/^\/+/, "");
      return { tab: "help", slug: slugPart || "" };
    }
    return null;
  }
  // --- Раздел Таблиц CRUD (adm_crud) ---
  let schemas = $state([]);
  let selectedModel = $state("");
  let tableRows = $state([]);
  let tableTotal = $state(0);
  let searchQuery = $state("");
  let newRecordData = $state({});

  onMount(async () => {
    initTheme();
    window.addEventListener("popstate", () => {
      const route = parseUrlRoute();
      if (route && route.tab === "help" && hasAdminSection("help")) {
        activeTab = "help";
        helpSlug = route.slug;
      }
    });

    await refreshSession();
    if (canAccessAdminPanel()) {
      pickInitialTab();
      await loadActiveTab();
    }
  });

  function pickInitialTab() {
    const route = parseUrlRoute();
    if (route && route.tab === "help" && hasAdminSection("help")) {
      activeTab = "help";
      helpSlug = route.slug;
      return;
    }
    if (hasAdminSection("roles") || hasAdminSection("rpc")) {
      activeTab = "permissions";
    } else if (hasAdminSection("users")) {
      activeTab = "users";
    } else if (hasAdminSection("crud")) {
      activeTab = "crud";
    } else if (hasAdminSection("seo")) {
      activeTab = "seo";
    } else if (hasAdminSection("help")) {
      activeTab = "help";
    }
  }

  let permissionsDirty = $state(false);
  let showSidebarUnsavedModal = $state(false);
  let pendingTab = $state(null);

  async function selectTab(tab) {
    if (activeTab === tab) return;

    if (activeTab === "permissions" && permissionsDirty) {
      pendingTab = tab;
      showSidebarUnsavedModal = true;
      return;
    }

    await doSwitchTab(tab);
  }

  async function doSwitchTab(tab) {
    activeTab = tab;
    if (tab === "help") {
      const targetUrl = helpSlug
        ? `/pyferro_admin/help/${helpSlug}`
        : "/pyferro_admin/help";
      if (window.location.pathname !== targetUrl) {
        window.history.pushState(null, "", targetUrl);
      }
    } else {
      if (window.location.pathname.startsWith("/pyferro_admin/help")) {
        window.history.pushState(null, "", "/pyferro_admin/");
      }
    }
    await loadActiveTab();
  }

  function confirmSidebarTabSwitch() {
    showSidebarUnsavedModal = false;
    permissionsDirty = false;
    if (pendingTab) {
      const target = pendingTab;
      pendingTab = null;
      doSwitchTab(target);
    }
  }

  function handleHelpNavigate(slug) {
    helpSlug = slug;
    const targetUrl = `/pyferro_admin/help/${slug}`;
    if (window.location.pathname !== targetUrl) {
      window.history.pushState(null, "", targetUrl);
    }
  }

  async function loadActiveTab() {
    try {
      if (activeTab === "crud" && hasAdminSection("crud")) {
        await loadSchemas();
      }
    } catch (e) {
      toast.error(e.message || "Ошибка загрузки данных раздела");
    }
  }

  function handleNotify(msg, type = "info") {
    if (type === "error" || type === "danger") {
      toast.error(msg);
    } else if (type === "success") {
      toast.success(msg);
    } else if (type === "warning") {
      toast.warning(msg);
    } else {
      toast.info(msg);
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
  <div class="flex min-h-screen items-center justify-center p-4 text-muted">
    Загрузка сессии PyFerro 2.0...
  </div>
{:else if !authState.userId}
  <div class="flex min-h-screen items-center justify-center p-4">
    <form class="w-full max-w-sm bg-panel border border-border rounded-lg p-6 shadow-md" onsubmit={handleLoginSubmit}>
      <div class="flex justify-between items-center mb-2">
        <div class="flex items-center gap-2">
          <Boxes size={22} class="text-accent" />
          <h2 class="m-0 text-xl font-bold text-accent">PyFerro 2.0 Admin</h2>
        </div>
        <Button
          variant="outline"
          size="icon"
          onclick={toggleTheme}
          title={isDark() ? "Переключить на светлую тему" : "Переключить на тёмную тему"}
          aria-label="Переключить тему"
        >
          {#if isDark()}
            <Sun size={16} />
          {:else}
            <Moon size={16} />
          {/if}
        </Button>
      </div>
      <p class="text-muted text-sm mt-0 mb-4">
        Вход в панель управления (/pyferro_admin)
      </p>
      {#if errorMsg}
        <div class="p-2.5 mb-3 rounded border border-danger/40 bg-danger-subtle text-danger text-sm font-medium">
          {errorMsg}
        </div>
      {/if}
      <div class="flex flex-col gap-3">
        <Input
          placeholder="Имя пользователя"
          bind:value={loginUser}
          required
        />
        <Input
          type="password"
          placeholder="Пароль"
          bind:value={loginPass}
          required
        />
        <Button type="submit" variant="primary" class="w-full justify-center">
          Войти
        </Button>
      </div>
    </form>
  </div>
{:else if !canAccessAdminPanel()}
  <div class="flex min-h-screen items-center justify-center p-4">
    <div class="w-full max-w-md bg-panel border border-border rounded-lg p-6 shadow-md">
      <h3 class="mt-0 text-danger text-lg font-bold">Доступ запрещен</h3>
      <p class="text-muted text-sm my-3">
        Пользователь <b class="text-text-bright">{authState.username}</b> не имеет ролей администратора (<code class="bg-bg px-1 py-0.5 rounded text-accent">admin</code> или <code class="bg-bg px-1 py-0.5 rounded text-accent">adm_*</code>) и не может войти в <code>/pyferro_admin</code>.
      </p>
      <Button variant="outline" onclick={logoutAdmin}>
        Выйти из аккаунта
      </Button>
    </div>
  </div>
{:else}
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-left">
          <Boxes size={20} class="brand-title" />
          <span class="brand-title font-bold">PyFerro 2.0</span>
        </div>
        <Button
          variant="outline"
          size="icon"
          onclick={toggleTheme}
          title={isDark() ? "Переключить на светлую тему" : "Переключить на тёмную тему"}
          aria-label="Переключить тему"
        >
          {#if isDark()}
            <Sun size={15} />
          {:else}
            <Moon size={15} />
          {/if}
        </Button>
      </div>

      <div class="text-xs text-muted mb-2.5 flex items-center justify-between">
        <span class="text-[0.72rem] uppercase tracking-wider text-muted">Пользователь</span>
        <Badge variant="accent">{authState.username}</Badge>
      </div>

      {#if hasAdminSection("roles") || hasAdminSection("rpc")}
        <button
          class="nav-btn {activeTab === 'permissions' ? 'active' : ''}"
          onclick={() => selectTab("permissions")}
        >
          <KeyRound size={17} />
          <span>Матрица прав и Роли</span>
        </button>
      {/if}

      {#if hasAdminSection("users")}
        <button
          class="nav-btn {activeTab === 'users' ? 'active' : ''}"
          onclick={() => selectTab("users")}
        >
          <Users size={17} />
          <span>Пользователи</span>
        </button>
      {/if}

      {#if hasAdminSection("crud")}
        <button
          class="nav-btn {activeTab === 'crud' ? 'active' : ''}"
          onclick={() => selectTab("crud")}
        >
          <Database size={17} />
          <span>Таблицы</span>
        </button>
      {/if}

      {#if hasAdminSection("seo")}
        <button
          class="nav-btn {activeTab === 'seo' ? 'active' : ''}"
          onclick={() => selectTab("seo")}
        >
          <Network size={17} />
          <span>SEO и Дерево сайта</span>
        </button>
      {/if}

      {#if hasAdminSection("help")}
        <button
          class="nav-btn {activeTab === 'help' ? 'active' : ''}"
          onclick={() => selectTab("help")}
        >
          <BookOpen size={17} />
          <span>Справочник</span>
        </button>
      {/if}

      <div class="mt-auto pt-3 border-t border-border">
        <div class="text-xs text-muted mb-2 break-all">
          <div class="text-[0.72rem] uppercase tracking-wider text-muted mb-1">Роли:</div>
          {authState.roles.join(", ")}
        </div>
        <Button
          variant="outline"
          class="w-full justify-center"
          onclick={logoutAdmin}
        >
          <LogOut size={15} />
          <span>Выйти</span>
        </Button>
      </div>
    </aside>

    <main class="content">
      {#if activeTab === "permissions"}
        <PermissionsView
          onnotify={handleNotify}
          ondirtychange={(dirty) => (permissionsDirty = dirty)}
        />
      {:else if activeTab === "users"}
        <UsersView onnotify={handleNotify} />
      {:else if activeTab === "crud"}
        <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div class="flex gap-2 flex-wrap">
            {#each schemas as s}
              <Button
                variant={selectedModel === s.name ? "primary" : "outline"}
                onclick={() => selectModel(s.name)}
              >
                {s.title} ({s.name})
              </Button>
            {/each}
          </div>
          <div class="flex gap-2">
            <Input
              placeholder="Поиск..."
              bind:value={searchQuery}
              onkeydown={(e) => e.key === "Enter" && loadModelRows()}
            />
            <Button variant="outline" onclick={loadModelRows}>
              <Search size={15} />
              <span>Найти</span>
            </Button>
          </div>
        </div>

        {#if selectedModel}
          {@const currentSchema = schemas.find((x) => x.name === selectedModel)}
          {#if currentSchema}
            <Card class="mb-4">
              <div class="flex items-center justify-between pb-2 mb-3 border-b border-border-subtle font-bold text-sm text-text-bright">
                <span>Создать запись ({selectedModel}.create)</span>
                <Badge variant="default">Всего записей: {tableTotal}</Badge>
              </div>
              <div class="flex gap-2 flex-wrap items-center">
                {#each currentSchema.fields.filter((f) => !f.readonly) as f}
                  <Input
                    placeholder={f.name}
                    bind:value={newRecordData[f.name]}
                  />
                {/each}
                <Button variant="primary" onclick={createModelRow}>
                  <Plus size={15} />
                  <span>Добавить</span>
                </Button>
              </div>
            </Card>

            <Card>
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
                        <Button
                          variant="danger"
                          size="sm"
                          onclick={() => deleteModelRow(row.id)}
                        >
                          <Trash2 size={14} />
                          <span>Удалить</span>
                        </Button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </Card>
          {/if}
        {/if}
      {:else if activeTab === "seo"}
        <SeoView onnotify={handleNotify} />
      {:else if activeTab === "help"}
        <HelpView currentSlug={helpSlug} onNavigate={handleHelpNavigate} />
      {/if}

      <!-- Модальное окно подтверждения при смене вкладки сайдбара -->
      <Modal
        open={showSidebarUnsavedModal}
        onclose={() => { showSidebarUnsavedModal = false; pendingTab = null; }}
        title="Несохраненные изменения"
        maxWidth="max-w-md"
      >
        <div class="space-y-2 text-sm text-text">
          <p>
            В разделе матрицы прав есть несохраненные изменения.
          </p>
          <p class="text-xs text-muted">
            Вы действительно хотите перейти в другой раздел? Несохраненные изменения прав будут потеряны.
          </p>
        </div>

        {#snippet footer()}
          <Button
            variant="outline"
            onclick={() => { showSidebarUnsavedModal = false; pendingTab = null; }}
          >
            Отмена
          </Button>
          <Button
            variant="danger"
            onclick={confirmSidebarTabSwitch}
          >
            Не сохранять
          </Button>
        {/snippet}
      </Modal>
    </main>
  </div>
{/if}

<ToastContainer />
