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
  import OAuthView from "./OAuthView.svelte";
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
    Link2,
  } from "@lucide/svelte";

  let activeTab = $state("permissions");
  let loginUser = $state("");
  let loginPass = $state("");
  let errorMsg = $state("");
  let statusMsg = $state("");
  let helpSlug = $state("");

  let authMode = $state("login"); // "login" | "register" | "verify"
  let regEmail = $state("");
  let regPass = $state("");
  let regUsername = $state("");
  let verifyCode = $state("");
  let publicConfig = $state({
    app_title: "PyFerro 2.0 Admin",
    app_logo_svg: "",
    allow_registration: true,
    require_email_verification: false,
    providers: [],
  });
  let pendingProvider = $state(null);
  let isOAuthLoading = $state(false);

  async function loadPublicConfig() {
    try {
      const res = await rpc.call("system.get_public_config");
      if (res) publicConfig = res;
    } catch (e) {
      console.warn("Failed to load public config:", e);
    }
  }

  function handleOAuthMessage(event) {
    if (event.data && event.data.type === "oauth_callback") {
      if (event.data.error) {
        toast.error(`Ошибка авторизации: ${event.data.error}`);
        isOAuthLoading = false;
        pendingProvider = null;
        return;
      }
      if ((event.data.code || event.data.payload) && pendingProvider) {
        finishOAuthLogin(pendingProvider, event.data.code, event.data.payload);
      }
    }
  }

  async function finishOAuthLogin(provider, code, payload) {
    isOAuthLoading = true;
    try {
      const args = { provider };
      if (code) args.code = code;
      if (payload) args.payload = payload;
      const res = await rpc.call("oauth.login", args);
      if (res && res.user) {
        toast.success(`Добро пожаловать, ${res.user.username}!`);
        await refreshSession();
        if (canAccessAdminPanel()) {
          pickInitialTab();
          await loadActiveTab();
        }
      }
    } catch (err) {
      toast.error(err.message || "Ошибка входа через внешнего провайдера");
    } finally {
      isOAuthLoading = false;
      pendingProvider = null;
    }
  }

  async function startOAuth(provName) {
    pendingProvider = provName;
    try {
      const res = await rpc.call("oauth.get_auth_url", { provider: provName });
      if (res && res.url) {
        window.open(res.url, "oauth_popup", "width=600,height=700");
      }
    } catch (err) {
      toast.error(err.message || "Не удалось открыть окно авторизации");
      pendingProvider = null;
    }
  }

  async function handleRegisterSubmit(ev) {
    ev.preventDefault();
    errorMsg = "";
    try {
      const res = await rpc.call("auth.register", {
        email: regEmail.trim(),
        password: regPass,
        username: regUsername.trim(),
      });
      if (res.status === "verification_required") {
        authMode = "verify";
        toast.info("Мы отправили 6-значный код на вашу почту");
      } else if (res.status === "registered") {
        toast.success("Регистрация успешна!");
        await refreshSession();
        if (canAccessAdminPanel()) {
          pickInitialTab();
          await loadActiveTab();
        }
      }
    } catch (e) {
      errorMsg = e.message || "Ошибка регистрации";
    }
  }

  async function handleVerifySubmit(ev) {
    ev.preventDefault();
    errorMsg = "";
    try {
      const res = await rpc.call("auth.verify_email_code", {
        email: regEmail.trim(),
        code: verifyCode.trim(),
      });
      if (res.status === "verified") {
        toast.success("Email подтвержден! Вход выполнен.");
        await refreshSession();
        if (canAccessAdminPanel()) {
          pickInitialTab();
          await loadActiveTab();
        }
      }
    } catch (e) {
      errorMsg = e.message || "Неверный код подтверждения";
    }
  }
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
    window.addEventListener("message", handleOAuthMessage);
    await loadPublicConfig();

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
    <div class="w-full max-w-sm bg-panel border border-border rounded-lg p-6 shadow-md">
      <!-- Шапка окна входа -->
      <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-2">
          {#if publicConfig.app_logo_svg}
            <div class="w-6 h-6 flex items-center justify-center text-accent [&>svg]:w-full [&>svg]:h-full [&>svg]:fill-current">
              {@html publicConfig.app_logo_svg}
            </div>
          {:else}
            <Boxes size={22} class="text-accent" />
          {/if}
          <h2 class="m-0 text-xl font-bold text-accent">{publicConfig.app_title || "PyFerro 2.0 Admin"}</h2>
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

      {#if errorMsg}
        <div class="p-2.5 mb-3 rounded border border-danger/40 bg-danger-subtle text-danger text-sm font-medium">
          {errorMsg}
        </div>
      {/if}

      {#if authMode === "login"}
        <form class="flex flex-col gap-3" onsubmit={handleLoginSubmit}>
          <Input
            placeholder="Имя пользователя или email"
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

          {#if publicConfig.allow_registration}
            <div class="text-center pt-1 text-xs">
              <span class="text-muted">Нет аккаунта?</span>
              <button
                type="button"
                class="text-accent hover:underline font-medium ml-1 bg-transparent border-0 p-0 cursor-pointer"
                onclick={() => { authMode = "register"; errorMsg = ""; }}
              >
                Зарегистрироваться
              </button>
            </div>
          {/if}
        </form>

      {:else if authMode === "register"}
        <form class="flex flex-col gap-3" onsubmit={handleRegisterSubmit}>
          <Input
            type="email"
            placeholder="Email"
            bind:value={regEmail}
            required
          />
          <Input
            type="password"
            placeholder="Пароль (минимум 6 символов)"
            bind:value={regPass}
            required
          />
          <Input
            placeholder="Имя пользователя (опционально)"
            bind:value={regUsername}
          />
          <Button type="submit" variant="primary" class="w-full justify-center">
            Зарегистрироваться
          </Button>

          <div class="text-center pt-1 text-xs">
            <span class="text-muted">Уже есть аккаунт?</span>
            <button
              type="button"
              class="text-accent hover:underline font-medium ml-1 bg-transparent border-0 p-0 cursor-pointer"
              onclick={() => { authMode = "login"; errorMsg = ""; }}
            >
              Войти
            </button>
          </div>
        </form>

      {:else if authMode === "verify"}
        <form class="flex flex-col gap-3" onsubmit={handleVerifySubmit}>
          <p class="text-xs text-muted m-0">
            Мы отправили 6-значный код подтверждения на <b>{regEmail}</b>. Введите его ниже:
          </p>
          <Input
            placeholder="000000"
            bind:value={verifyCode}
            class="text-center text-lg tracking-widest font-mono"
            required
            maxlength={6}
          />
          <Button type="submit" variant="primary" class="w-full justify-center">
            Подтвердить и войти
          </Button>

          <div class="text-center pt-1 text-xs">
            <button
              type="button"
              class="text-muted hover:underline bg-transparent border-0 p-0 cursor-pointer"
              onclick={() => { authMode = "login"; errorMsg = ""; }}
            >
              Вернуться ко входу
            </button>
          </div>
        </form>
      {/if}

      <!-- Кнопки внешних провайдеров (OAuth / SSO) -->
      {#if publicConfig.providers && publicConfig.providers.some(p => p.is_enabled)}
        <div class="relative my-4">
          <div class="absolute inset-0 flex items-center"><span class="w-full border-t border-border"></span></div>
          <div class="relative flex justify-center text-[0.7rem] uppercase"><span class="bg-panel px-2 text-muted">или войти через</span></div>
        </div>

        <div class="grid grid-cols-2 gap-2">
          {#each publicConfig.providers.filter(p => p.is_enabled) as prov}
            <Button
              variant="outline"
              size="sm"
              class="w-full justify-center text-xs py-1.5"
              disabled={isOAuthLoading}
              onclick={() => startOAuth(prov.name)}
            >
              {#if prov.name === "vk"}
                <span class="font-bold text-[#0077FF] mr-1">VK</span>
              {:else if prov.name === "yandex"}
                <span class="font-bold text-[#FC3F1D] mr-1">Я</span>
              {:else if prov.name === "telegram"}
                <span class="font-bold text-[#2AABEE] mr-1">TG</span>
              {:else}
                <span class="font-bold text-[#4285F4] mr-1">G</span>
              {/if}
              <span>{prov.title}</span>
            </Button>
          {/each}
        </div>
      {/if}
    </div>
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
          {#if publicConfig.app_logo_svg}
            <div class="w-5 h-5 flex items-center justify-center text-accent [&>svg]:w-full [&>svg]:h-full [&>svg]:fill-current">
              {@html publicConfig.app_logo_svg}
            </div>
          {:else}
            <Boxes size={20} class="brand-title" />
          {/if}
          <span class="brand-title font-bold">{publicConfig.app_title || "PyFerro 2.0"}</span>
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

      {#if hasAdminSection("oauth")}
        <button
          class="nav-btn {activeTab === 'oauth' ? 'active' : ''}"
          onclick={() => selectTab("oauth")}
        >
          <Link2 size={17} />
          <span>Внешняя авторизация</span>
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
      {:else if activeTab === "oauth"}
        <OAuthView onnotify={handleNotify} />
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
