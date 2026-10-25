<script lang="ts">
  import { onMount } from "svelte";
  import { rpc, wsStatus as canonicalWsStatus } from "@wsrpc/wsrpc";
  import PermissionsModal from "./components/PermissionsModal.svelte";
  import RpcCatalogView from "./components/RpcCatalogView.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import DelegationsView from "./components/DelegationsView.svelte";
  import SeoAdminView from "./components/SeoAdminView.svelte";
  import PyFerroLogo from "./components/PyFerroLogo.svelte";

  let wsStatus = $state<"CONNECTING" | "CONNECTED" | "DISCONNECTED">("DISCONNECTED");

  // 7 главных разделов Mission Control (/admin/crud, /admin/seo, /admin/users, etc.)
  type MainNav = "database" | "rpc" | "users" | "roles" | "delegations" | "seo" | "settings";
  let currentNav = $state<MainNav>("database");
  let dbTab = $state<"app" | "framework">("app");

  let userRoles = $state<string[]>([]);
  let isSuperadmin = $state(false);
  let isRolesLoaded = $state(false);

  function isNavAllowed(nav: string): boolean {
    if (!isRolesLoaded) return true;
    if (isSuperadmin || userRoles.includes("admin") || userRoles.includes("adm_all")) return true;
    if (nav === "help") return true;
    if (nav === "database" && (userRoles.includes("adm_crud") || userRoles.includes("adm_database"))) return true;
    return userRoles.includes(`adm_${nav}`);
  }

  function getNavFromPathname(): MainNav | null {
    try {
      const pathname = window.location.pathname.replace(/\/+$/, "");
      const parts = pathname.split("/");
      const segment = parts[parts.length - 1];
      if (segment === "crud" || segment === "database") return "database";
      if (["rpc", "users", "roles", "delegations", "seo", "settings"].includes(segment)) {
        return segment as MainNav;
      }
      const hash = window.location.hash.replace("#", "") as MainNav;
      if (["database", "rpc", "users", "roles", "delegations", "seo", "settings"].includes(hash)) {
        return hash;
      }
    } catch {}
    return null;
  }

  function setSection(nav: MainNav) {
    selectNav(nav);
  }
  // Тема (светлая / темно-серая)
  let isDarkMode = $state(false);

  function toggleTheme() {
    isDarkMode = !isDarkMode;
    if (isDarkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("crud_admin_theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("crud_admin_theme", "light");
    }
  }

  // Язык интерфейса (RU / EN)
  type Lang = "ru" | "en";
  let lang = $state<Lang>("ru");

  function toggleLang() {
    lang = lang === "ru" ? "en" : "ru";
    localStorage.setItem("crud_admin_lang", lang);
  }

  const i18n = {
    ru: {
      title: "CRUD Admin",
      modelLabel: "Модель:",
      searchPlaceholder: "Поиск по строкам (Enter)...",
      refresh: "Обновить",
      create: "Создать",
      archiveOn: "Архив: Вкл",
      archiveOff: "Архив: Выкл",
      actions: "Действия",
      loadingRows: "Загрузка строк...",
      noRecords: "Записей не найдено",
      yes: "Да",
      no: "Нет",
      editCell: "Редактировать ячейку",
      deleteRecord: "Удалить",
      confirmDeleteTitle: "Подтверждение удаления",
      confirmDeleteText: (id: any) => `Вы уверены, что хотите удалить запись #${id}? Действие необратимо.`,
      cancel: "Отмена",
      delete: "Удалить",
      deleting: "Удаление...",
      createTitle: (model: string) => `Создать: ${model}`,
      save: "Сохранить",
      creating: "Создание...",
      totalRecords: "Всего записей:",
      page: "Стр.",
      of: "из",
      prev: "Назад",
      next: "Вперед",
      cellSaved: "Ячейка сохранена",
      statusUpdated: "Статус обновлен",
      recordDeleted: (id: any) => `Запись #${id} удалена`,
      recordCreated: "Запись успешно создана",
      wsOnline: "WSRPC Онлайн",
      wsConnecting: "Подключение...",
      schemaLoading: "Загрузка схемы моделей...",
      noModels: "Нет доступных моделей для отображения.",
      schemaError: (msg: string) => `Ошибка схемы: ${msg}`,
      loadError: (msg: string) => `Ошибка загрузки данных: ${msg}`,
      saveError: (msg: string) => `Ошибка сохранения: ${msg}`,
      deleteError: (msg: string) => `Ошибка удаления: ${msg}`,
      themeLight: "Включить светлую тему",
      themeDark: "Включить темно-серую тему",
      switchLang: "Switch to English",
      accessSection: "Безопасность и доступ",
      navDatabase: "База данных",
      navRpc: "RPC методы",
      navUsers: "Пользователи",
      navRoles: "Роли",
      navDelegations: "Делегирование",
      navSeo: "Соцсети и SEO",
      navSettings: "Настройки",
      navHelp: "Справка и API",
      tabAppTables: "Таблицы приложения",
      tabFrameworkTables: "Таблицы фреймворка",
      noAppTables: "Нет доступных таблиц приложения",
      noFrameworkTables: "Нет доступных таблиц фреймворка",
      adminPermissionsDisabled: "Администратор обладает полным доступом ко всей системе",
      roleAdminPermissionsDisabled: "Роль admin обладает полным доступом ко всей системе",
      permissions: "Разрешения",
      navGuests: "Гости",
      dataSection: "Таблицы данных",
      models: {
        showcase_tasks: "Задачи",
        showcase_documents: "Документы",
        auth_rpc_permission: "Права RPC-методов",
        auth_role: "Роли",
        auth_user: "Пользователи",
        pf_auth_rpc_permission: "Права RPC-методов",
        pf_auth_role: "Роли",
        pf_auth_user: "Пользователи",
        Task: "Задачи",
        Document: "Документы",
        "RPC Permission": "Права RPC-методов",
        Role: "Роли",
        User: "Пользователи",
      } as Record<string, string>,
      fields: {
        id: "ID",
        name: "Название",
        title: "Заголовок",
        description: "Описание",
        is_public: "Публичный (гостям)",
        completed: "Завершено",
        priority: "Приоритет",
        owner_id: "Владелец (ID)",
        category: "Категория",
        views: "Просмотры",
        content: "Контент",
        created_at: "Создано",
        updated_at: "Обновлено",
        login: "Логин",
        email: "Email",
      } as Record<string, string>,
    },
    en: {
      title: "CRUD Admin",
      modelLabel: "Model:",
      searchPlaceholder: "Search rows (Enter)...",
      refresh: "Refresh",
      create: "Create",
      archiveOn: "Archive: On",
      archiveOff: "Archive: Off",
      actions: "Actions",
      loadingRows: "Loading rows...",
      noRecords: "No records found",
      yes: "Yes",
      no: "No",
      editCell: "Edit cell",
      deleteRecord: "Delete",
      confirmDeleteTitle: "Confirm Deletion",
      confirmDeleteText: (id: any) => `Are you sure you want to delete record #${id}? This action cannot be undone.`,
      cancel: "Cancel",
      delete: "Delete",
      deleting: "Deleting...",
      createTitle: (model: string) => `Create: ${model}`,
      save: "Save",
      creating: "Creating...",
      totalRecords: "Total records:",
      page: "Page",
      of: "of",
      prev: "Prev",
      next: "Next",
      cellSaved: "Cell saved",
      statusUpdated: "Status updated",
      recordDeleted: (id: any) => `Record #${id} deleted`,
      recordCreated: "Record created successfully",
      wsOnline: "WSRPC Online",
      wsConnecting: "Connecting...",
      schemaLoading: "Loading model schema...",
      noModels: "No models available for display.",
      schemaError: (msg: string) => `Schema error: ${msg}`,
      loadError: (msg: string) => `Data load error: ${msg}`,
      saveError: (msg: string) => `Save error: ${msg}`,
      deleteError: (msg: string) => `Delete error: ${msg}`,
      themeLight: "Switch to light theme",
      themeDark: "Switch to dark theme",
      switchLang: "Переключить на русский",
      accessSection: "Access & Security",
      navDatabase: "Database",
      navRpc: "RPC Methods",
      navUsers: "Users",
      navRoles: "Roles",
      navDelegations: "Delegations",
      navSeo: "Social & SEO",
      navSettings: "Settings",
      navHelp: "Help & API",
      tabAppTables: "Application Tables",
      tabFrameworkTables: "Framework Tables",
      noAppTables: "No application tables available",
      noFrameworkTables: "No framework tables available",
      adminPermissionsDisabled: "Administrator has unrestricted full access to all resources",
      roleAdminPermissionsDisabled: "Admin role has unrestricted full access to all resources",
      permissions: "Permissions",
      navGuests: "Guests",
      dataSection: "Data Tables",
      models: {
        showcase_tasks: "Tasks",
        showcase_documents: "Documents",
        auth_rpc_permission: "RPC Permissions",
        auth_role: "Roles",
        auth_user: "Users",
        pf_auth_rpc_permission: "RPC Permissions",
        pf_auth_role: "Roles",
        pf_auth_user: "Users",
        Task: "Tasks",
        Document: "Documents",
        "RPC Permission": "RPC Permissions",
        Role: "Roles",
        User: "Users",
      } as Record<string, string>,
      fields: {
        id: "ID",
        name: "Name",
        title: "Title",
        description: "Description",
        is_public: "Public (guests)",
        completed: "Completed",
        priority: "Priority",
        owner_id: "Owner ID",
        category: "Category",
        views: "Views",
        content: "Content",
        created_at: "Created at",
        updated_at: "Updated at",
        login: "Login",
        email: "Email",
      } as Record<string, string>,
    },
  };

  let t = $derived(i18n[lang]);

  function getModelDisplayName(m: any) {
    if (!m) return "";
    if (t.models[m.key]) return t.models[m.key];
    if (m.verbose_name_plural && t.models[m.verbose_name_plural]) return t.models[m.verbose_name_plural];
    return m.verbose_name_plural || m.key;
  }

  function getFieldDisplayName(col: any) {
    if (!col) return "";
    if (t.fields[col.name]) return t.fields[col.name];
    return col.label || col.name;
  }

  // Модели и схема
  let models = $state<any[]>([]);
  let allowGuests = $state(true);
  let selectedModelName = $state<string>("");
  let currentSchema = $derived(models.find((m) => m.key === selectedModelName) || null);
  let isLoadingSchema = $state(true);

  let userModel = $derived(models.find((m) => m.key === "User" || m.table_name === "pf_auth_user" || m.table_name === "auth_user" || m.key === "auth_user" || m.key === "pf_auth_user"));
  let roleModel = $derived(models.find((m) => m.key === "Role" || m.table_name === "pf_auth_role" || m.table_name === "auth_role" || m.key === "auth_role" || m.key === "pf_auth_role"));

  let appModels = $derived(models.filter((m) => m !== userModel && m !== roleModel && !m.is_framework && !m.table_name?.startsWith("pf_") && !m.table_name?.startsWith("auth_")));
  let frameworkModels = $derived(models.filter((m) => m !== userModel && m !== roleModel && (m.is_framework || m.table_name?.startsWith("pf_") || m.table_name?.startsWith("auth_"))));

  function selectNav(nav: MainNav) {
    currentNav = nav;
    const slug = nav === "database" ? "crud" : nav;
    try {
      if (typeof window !== "undefined") {
        const targetPath = `/admin/${slug}`;
        if (window.location.pathname !== targetPath) {
          window.history.pushState({}, "", targetPath);
        }
      }
    } catch {}
    if (nav === "users") {
      if (userModel) selectedModelName = userModel.key;
    } else if (nav === "roles") {
      if (roleModel) selectedModelName = roleModel.key;
    } else if (nav === "database") {
      const list = dbTab === "app" ? appModels : frameworkModels;
      if (list.length > 0 && !list.some(m => m.key === selectedModelName)) {
        selectedModelName = list[0].key;
      }
    }
  }

  function selectDbTab(tab: "app" | "framework") {
    dbTab = tab;
    const list = tab === "app" ? appModels : frameworkModels;
    if (list.length > 0) {
      selectedModelName = list[0].key;
    }
  }

  function selectModel(modelKey: string) {
    selectedModelName = modelKey;
  }

  // Таблица данных
  let rows = $state<any[][]>([]);
  let fields = $state<string[]>([]);
  let total = $state(0);
  let page = $state(1);
  let pageSize = $state(25);
  let sortField = $state<string>("");
  let sortDir = $state<"asc" | "desc">("desc");
  let searchQuery = $state("");
  let showArchived = $state(false);
  let isLoadingData = $state(false);

  // Инлайн редактирование
  let editingCell = $state<{ id: any; field: string; value: any } | null>(null);
  let isSavingCell = $state(false);

  // Модалка создания
  let isCreateModalOpen = $state(false);
  let createFormData = $state<Record<string, any>>({});
  let isCreating = $state(false);
  let createError = $state<string>("");

  // Модалка удаления
  let recordToDelete = $state<any | null>(null);
  let isDeleting = $state(false);

  // Модалка разрешений (CRUD + RPC)
  let permissionsModalOpen = $state(false);
  let permissionsTargetType = $state<"role" | "user" | "guest">("role");
  let permissionsTargetId = $state<number>(0);
  let permissionsTargetName = $state<string>("");

  let isRoleModel = $derived(selectedModelName === "pf_auth_role" || selectedModelName === "auth_role" || selectedModelName === "Role");
  let isUserModel = $derived(selectedModelName === "pf_auth_user" || selectedModelName === "auth_user" || selectedModelName === "User");
  let isRoleOrUserModel = $derived(isRoleModel || isUserModel);

  function isUserAdmin(row: any[]): boolean {
    if (!fields.includes("roles")) return false;
    const val = row[fields.indexOf("roles")];
    if (Array.isArray(val)) {
      return val.some((r: any) => (typeof r === "string" ? r === "admin" : r?.name === "admin"));
    }
    return false;
  }

  function isRoleAdmin(row: any[]): boolean {
    if (!fields.includes("name")) return false;
    return String(row[fields.indexOf("name")]).toLowerCase() === "admin";
  }

  function isRoleGuest(row: any[]): boolean {
    if (!fields.includes("name")) return false;
    return String(row[fields.indexOf("name")]).toLowerCase() === "guest";
  }

  function openPermissions(row: any[], recId: any) {
    if (currentNav === "roles" || isRoleModel) {
      const nameIdx = fields.indexOf("name");
      const roleName = nameIdx !== -1 && row[nameIdx] ? String(row[nameIdx]) : "role";
      if (roleName === "admin") return;
      permissionsTargetId = Number(recId);
      permissionsTargetType = roleName === "guest" ? "guest" : "role";
      permissionsTargetName = roleName;
      permissionsModalOpen = true;
    } else if (currentNav === "users" || isUserModel) {
      if (isUserAdmin(row)) return;
      const nameIdx = fields.indexOf("name");
      const loginIdx = fields.indexOf("login");
      let userName = "";
      if (loginIdx !== -1 && row[loginIdx]) userName = String(row[loginIdx]);
      else if (nameIdx !== -1 && row[nameIdx]) userName = String(row[nameIdx]);
      else userName = `user_${recId}`;
      permissionsTargetId = Number(recId);
      permissionsTargetType = "user";
      permissionsTargetName = userName;
      permissionsModalOpen = true;
    }
  }

  // Определение справочных колонок (даты, технический аудит)
  function isRefColumn(colName: string): boolean {
    return colName === "created_at" || colName === "updated_at" || colName === "creator_id" || colName === "team_id" || colName === "owner_id";
  }

  // Упорядочивание колонок таблицы: основные бизнес-поля слева, справочные — справа
  let displayColumns = $derived.by(() => {
    if (!currentSchema?.fields) return [];
    const mainCols: any[] = [];
    const refCols: any[] = [];
    for (const f of currentSchema.fields) {
      if (isRefColumn(f.name)) {
        refCols.push(f);
      } else {
        mainCols.push(f);
      }
    }
    refCols.sort((a, b) => {
      const order = ["creator_id", "team_id", "owner_id", "created_at", "updated_at"];
      return order.indexOf(a.name) - order.indexOf(b.name);
    });
    return [...mainCols, ...refCols];
  });

  // Лаконичное форматирование значений ячеек (краткая дата/время без микросекунд)
  function formatCellValue(val: any, col: any): string {
    if (val === null || val === undefined) return "—";
    if (
      col.type === "datetime" ||
      col.type === "date" ||
      col.name.endsWith("_at") ||
      col.name.endsWith("_date") ||
      (typeof val === "string" && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(val))
    ) {
      try {
        const d = new Date(val);
        if (!isNaN(d.getTime())) {
          const pad = (n: number) => String(n).padStart(2, "0");
          return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        }
      } catch {}
    }
    return String(val);
  }

  // Индекс ID колонки
  let idColIdx = $derived.by(() => {
    if (fields.indexOf("id") !== -1) return fields.indexOf("id");
    if (fields.indexOf("key") !== -1) return fields.indexOf("key");
    const pkIdx = currentSchema?.fields.findIndex((f) => f.primary_key);
    if (pkIdx !== undefined && pkIdx !== -1) return pkIdx;
    return 0;
  });

  function getRowId(row: any[], rowIdx: number = 0): any {
    if (!row || !Array.isArray(row)) return `row-${rowIdx}`;
    let val: any = undefined;
    if (currentSchema && fields.length > 0) {
      const pkFields = currentSchema.fields.filter((f) => f.primary_key);
      if (pkFields.length > 1) {
        val = pkFields
          .map((f) => {
            const idx = fields.indexOf(f.name);
            return idx !== -1 && row[idx] !== undefined ? row[idx] : "";
          })
          .join("_");
      } else if (pkFields.length === 1) {
        const idx = fields.indexOf(pkFields[0].name);
        if (idx !== -1 && row[idx] !== undefined && row[idx] !== null) {
          val = row[idx];
        }
      }
    }
    if (val === undefined || val === null || val === "") {
      if (idColIdx >= 0 && idColIdx < row.length && row[idColIdx] !== undefined && row[idColIdx] !== null) {
        val = row[idColIdx];
      }
    }
    if (val === undefined || val === null || val === "") {
      return `row-${rowIdx}`;
    }
    return val;
  }

  // Уведомления (toast)
  let toastMsg = $state<{ text: string; type: "success" | "error" } | null>(null);
  let toastTimer: any = null;
  function showToast(text: string, type: "success" | "error" = "success") {
    toastMsg = { text, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastMsg = null;
    }, 4000);
  }

  // Кэш лукапов для ForeignKey и M2M связей
  let lookupCache = $state<Record<string, { id: any; label: string }[]>>({});

  async function loadLookupOptions(modelName: string) {
    if (!modelName) return [];
    if (lookupCache[modelName] && lookupCache[modelName].length > 0) {
      return lookupCache[modelName];
    }
    try {
      const res = await rpc.call("crud.lookup", { model: modelName });
      if (res && res.items) {
        lookupCache[modelName] = res.items;
        return res.items;
      }
    } catch (e: any) {
      console.warn(`[CRUD UI] Ошибка lookup для ${modelName}:`, e);
    }
    return [];
  }

  function getTargetModelFromFk(fk: any): string | null {
    if (!fk) return null;
    if (fk.target_model && models.some((m) => m.key === fk.target_model)) {
      return fk.target_model;
    }
    const found = models.find((m) => m.table_name === fk.target_table);
    return found ? found.key : null;
  }

  function openCreateModal() {
    createFormData = {};
    createError = "";
    isCreateModalOpen = true;
    if (currentSchema) {
      for (const col of currentSchema.fields) {
        if (col.type === "m2m" && col.target_model) {
          createFormData[col.name] = [];
          loadLookupOptions(col.target_model);
        } else if (col.type === "fk" || col.foreign_key) {
          const target = getTargetModelFromFk(col.foreign_key);
          if (target) loadLookupOptions(target);
        }
      }
    }
  }

  async function loadSchema() {
    isLoadingSchema = true;
    console.info("[CRUD Admin] 📋 Загрузка схемы моделей (crud.schema)...");
    try {
      try {
        const whoami = await rpc.call("login.whoami", {});
        if (whoami && whoami.authenticated) {
          userRoles = whoami.roles || [];
          isSuperadmin = Boolean(whoami.is_superadmin || whoami.role === "admin" || userRoles.includes("admin"));
        } else {
          isSuperadmin = true;
        }
      } catch {
        isSuperadmin = true;
      }
      isRolesLoaded = true;

      const targetNav = getNavFromPathname();
      if (targetNav && isNavAllowed(targetNav)) {
        selectNav(targetNav);
      } else if (!isNavAllowed(currentNav)) {
        const allNavs: MainNav[] = ["database", "rpc", "users", "roles", "delegations", "seo", "settings"];
        const first = allNavs.find(n => isNavAllowed(n)) || "database";
        selectNav(first);
      }

      const res = await rpc.call("crud.schema", {});
      console.info("[CRUD Admin] ✅ Схема получена:", res);
      if (res) {
        if (res.allow_guests !== undefined) {
          allowGuests = Boolean(res.allow_guests);
        }
        if (res.models) {
          models = res.models;
          if (!selectedModelName) {
            if (currentNav === "users" && userModel) {
              selectedModelName = userModel.key;
            } else if (currentNav === "roles" && roleModel) {
              selectedModelName = roleModel.key;
            } else if (appModels.length > 0) {
              selectedModelName = appModels[0].key;
            } else if (frameworkModels.length > 0) {
              selectedModelName = frameworkModels[0].key;
            } else if (models.length > 0) {
              selectedModelName = models[0].key;
            }
          }
        }
      }
    } catch (e: any) {
      console.error("[CRUD Admin] ❌ Ошибка загрузки схемы:", e);
      showToast(t.schemaError(e.message), "error");
    } finally {
      isLoadingSchema = false;
    }
  }

  async function loadData() {
    if (!selectedModelName) return;
    isLoadingData = true;
    console.info(`[CRUD Admin] 📊 Загрузка данных для модели "${selectedModelName}" (стр. ${page}, pageSize: ${pageSize})...`);
    try {
      const res = await rpc.call("crud.list", {
        model: selectedModelName,
        page,
        page_size: pageSize,
        sort_field: sortField || undefined,
        sort_dir: sortDir,
        search: searchQuery.trim() || undefined,
        show_archived: showArchived,
      });

      console.info(`[CRUD Admin] ✅ Данные получены для "${selectedModelName}":`, res);
      if (res && res.$tabular) {
        fields = res.fields || [];
        rows = res.rows || [];
        total = res.total || 0;
      }
    } catch (e: any) {
      console.error(`[CRUD Admin] ❌ Ошибка загрузки данных для "${selectedModelName}":`, e);
      showToast(t.loadError(e.message), "error");
    } finally {
      isLoadingData = false;
    }
  }

  function handleSort(colName: string) {
    if (sortField === colName) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortField = colName;
      sortDir = "asc";
    }
    loadData();
  }

  async function saveInlineCell() {
    if (!editingCell || isSavingCell) return;
    isSavingCell = true;
    const { id, field, value } = editingCell;

    try {
      await rpc.call("crud.update_cell", {
        model: selectedModelName,
        id,
        field,
        value,
      });

      // Обновляем строку локально
      const targetRow = rows.find((r) => getRowId(r) === id);
      if (targetRow) {
        const cIdx = fields.indexOf(field);
        if (cIdx !== -1) targetRow[cIdx] = value;
        rows = [...rows];
      }
      showToast(t.cellSaved);
      editingCell = null;
    } catch (e: any) {
      showToast(t.saveError(e.message), "error");
    } finally {
      isSavingCell = false;
    }
  }

  async function toggleBool(recordId: any, fieldName: string, curVal: boolean) {
    try {
      const nextVal = !curVal;
      await rpc.call("crud.update_cell", {
        model: selectedModelName,
        id: recordId,
        field: fieldName,
        value: nextVal,
      });
      const targetRow = rows.find((r) => getRowId(r) === recordId);
      if (targetRow) {
        const cIdx = fields.indexOf(fieldName);
        if (cIdx !== -1) targetRow[cIdx] = nextVal;
        rows = [...rows];
      }
      showToast(t.statusUpdated);
    } catch (e: any) {
      showToast(`Error: ${e.message}`, "error");
    }
  }

  async function confirmDelete() {
    if (!recordToDelete || isDeleting) return;
    isDeleting = true;
    try {
      await rpc.call("crud.delete", {
        model: selectedModelName,
        id: recordToDelete,
      });
      rows = rows.filter((r) => getRowId(r) !== recordToDelete);
      total = Math.max(0, total - 1);
      showToast(t.recordDeleted(recordToDelete));
      recordToDelete = null;
    } catch (e: any) {
      showToast(t.deleteError(e.message), "error");
    } finally {
      isDeleting = false;
    }
  }

  async function submitCreate() {
    isCreating = true;
    createError = "";
    try {
      await rpc.call("crud.create", {
        model: selectedModelName,
        data: createFormData,
      });
      showToast(t.recordCreated);
      isCreateModalOpen = false;
      createFormData = {};
      loadData();
    } catch (e: any) {
      createError = e.message || String(e);
    } finally {
      isCreating = false;
    }
  }

  function handleCachePatch(params: any) {
    console.info("[CRUD Admin] 🔔 Получен cache/crud патч:", params);
    if (!params || params.model !== selectedModelName) return;
    const recId = params.id;

    if (params.kind === "deleted" || params.deleted) {
      console.info(`[CRUD Admin] 🗑 Удалена запись #${recId} из локального кэша`);
      rows = rows.filter((r) => getRowId(r) !== recId);
      total = Math.max(0, total - 1);
      return;
    }

    if (params.kind === "created" || params.created) {
      console.info("[CRUD Admin] ➕ Создана новая запись, перезагрузка данных...");
      loadData();
      return;
    }

    if (params.kind === "updated" || params.changes) {
      const targetRow = rows.find((r) => getRowId(r) === recId);
      if (targetRow) {
        if (params.changes) {
          console.info(`[CRUD Admin] ✏️ Обновлены поля для #${recId}:`, params.changes);
          for (const [k, v] of Object.entries(params.changes)) {
            const cIdx = fields.indexOf(k);
            if (cIdx !== -1) targetRow[cIdx] = v;
          }
          rows = [...rows];
        } else {
          rpc.call("crud.get", { model: selectedModelName, id: recId })
            .then((res: any) => {
              if (res && res.record) {
                const rIdx = rows.findIndex((r) => getRowId(r) === recId);
                if (rIdx !== -1) {
                  rows[rIdx] = fields.map((f) => res.record[f]);
                  rows = [...rows];
                }
              }
            })
            .catch(() => {});
        }
      }
    }
  }

  onMount(() => {
    console.info("[CRUD Admin] 🚀 onMount инициализирован");
    console.info("[CRUD Admin] rpc клиент:", rpc, "typeof rpc.on:", typeof (rpc as any)?.on);

    const savedTheme = localStorage.getItem("crud_admin_theme");
    if (savedTheme === "dark") {
      isDarkMode = true;
      document.documentElement.classList.add("dark");
    }
    const savedLang = localStorage.getItem("crud_admin_lang") as Lang;
    if (savedLang === "en" || savedLang === "ru") {
      lang = savedLang;
    }

    const initialNav = getNavFromPathname();
    if (initialNav) {
      currentNav = initialNav;
    }

    const onPopState = () => {
      const target = getNavFromPathname();
      if (target && isNavAllowed(target)) {
        currentNav = target;
      }
    };
    window.addEventListener("popstate", onPopState);

    const onHashChange = () => {
      const h = window.location.hash.replace("#", "") as MainNav;
      const validNavs: MainNav[] = ["database", "rpc", "users", "roles", "delegations", "seo", "settings"];
      if (validNavs.includes(h)) selectNav(h);
    };
    window.addEventListener("hashchange", onHashChange);
    const unsubStatus = canonicalWsStatus.subscribe((s) => {
      console.info("[CRUD Admin] 📶 Смена статуса WebSocket:", s);
      wsStatus = s;
      if (s === "CONNECTED") {
        console.info("[CRUD Admin] ✅ Соединение установлено, вызываем loadSchema()...");
        loadSchema();
      }
    });

    const unsubCache = rpc.on("cache.invalidate", (params: any) => {
      handleCachePatch(params);
    });

    const unsubCrud = rpc.on("crud.event", (params: any) => {
      handleCachePatch(params);
    });

    console.info("[CRUD Admin] 🔌 Вызов rpc.connect()...");
    rpc.connect();

    return () => {
      console.info("[CRUD Admin] 🛑 onMount cleanup (отписка и отключение)");
      window.removeEventListener("hashchange", onHashChange);
      unsubStatus();
      unsubCache();
      unsubCrud();
      rpc.disconnect();
    };
  });

  $effect(() => {
    if (selectedModelName && wsStatus === "CONNECTED") {
      page = 1;
      editingCell = null;
      rows = [];
      fields = [];
      loadData();
    }
  });
</script>

<div class="min-h-screen bg-background text-foreground flex flex-col font-sans transition-colors duration-200">
  <!-- Верхняя панель (Header) -->
  <header class="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur-md px-6 py-2.5 flex items-center justify-between shadow-2xs">
    <div class="flex items-center gap-6">
      <div class="flex items-center gap-3">
        <PyFerroLogo size={36} class="drop-shadow-xs" />
        <div class="flex flex-col">
          <span class="text-sm font-bold tracking-tight text-foreground leading-tight">Mission Control</span>
          <span class="text-2xs text-primary font-mono font-bold leading-none tracking-wide">PyFerro engine</span>
        </div>
      </div>

      <!-- Заголовок активного раздела -->
      <div class="hidden sm:flex items-center gap-2 px-3 py-1 rounded-lg bg-muted/40 border border-border/60 text-xs text-muted-foreground font-medium">
        <span>PyFerro</span>
        <span class="text-muted-foreground/40">/</span>
        <span class="text-foreground font-semibold">
          {#if currentNav === 'database'}{t.navDatabase}
          {:else if currentNav === 'rpc'}{t.navRpc}
          {:else if currentNav === 'users'}{t.navUsers}
          {:else if currentNav === 'roles'}{t.navRoles}
          {:else if currentNav === 'delegations'}{t.navDelegations}
          {:else if currentNav === 'seo'}{t.navSeo}
          {:else if currentNav === 'settings'}{t.navSettings}
          {/if}
        </span>
      </div>
    </div>
    <!-- Правая часть: статус подключения, переключатель языка и темы -->
    <div class="flex items-center gap-2.5">
      <!-- Статус сокета -->
      <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-2xs font-semibold border {wsStatus === 'CONNECTED' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400'}">
        <span class="h-2 w-2 rounded-full {wsStatus === 'CONNECTED' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}"></span>
        <span>{wsStatus === 'CONNECTED' ? t.wsOnline : t.wsConnecting}</span>
      </div>

      <!-- Переключатель языка RU / EN -->
      <button
        type="button"
        onclick={toggleLang}
        class="flex h-8 px-2.5 items-center justify-center rounded-lg border border-border bg-muted/60 text-foreground font-bold text-xs hover:bg-muted transition-colors cursor-pointer"
        title={t.switchLang}
      >
        🌐 {lang.toUpperCase()}
      </button>

      <!-- Переключатель светлой / темно-серой темы -->
      <button
        type="button"
        onclick={toggleTheme}
        class="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/60 text-foreground hover:bg-muted transition-colors cursor-pointer"
        title={isDarkMode ? t.themeLight : t.themeDark}
      >
        {#if isDarkMode}
          <span class="text-sm">☀️</span>
        {:else}
          <span class="text-sm">🌙</span>
        {/if}
      </button>
    </div>
  </header>

  <div class="flex-1 flex overflow-hidden">
    <!-- Боковая панель навигации слева (Sidebar) -->
    <aside class="w-60 border-r border-border bg-card/50 flex flex-col p-3 gap-1 shrink-0 overflow-y-auto">
      <div class="px-3 py-2 text-2xs font-bold uppercase tracking-wider text-muted-foreground/70">
        PyFerro Admin
      </div>

      <!-- 1. База данных -->
      {#if isNavAllowed("database")}
        <button
          type="button"
          onclick={() => selectNav("database")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'database' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
          <span class="flex-1 truncate">{t.navDatabase}</span>
          <span class="text-2xs px-1.5 py-0.5 rounded-full {currentNav === 'database' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'}">{appModels.length + frameworkModels.length}</span>
        </button>
      {/if}

      <!-- 2. RPC методы -->
      {#if isNavAllowed("rpc")}
        <button
          type="button"
          onclick={() => selectNav("rpc")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'rpc' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <polyline points="16 18 22 12 16 6"/>
            <polyline points="8 6 2 12 8 18"/>
          </svg>
          <span class="flex-1 truncate">{t.navRpc}</span>
          <span class="text-2xs px-1.5 py-0.5 rounded-full {currentNav === 'rpc' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'}">API</span>
        </button>
      {/if}

      <!-- 3. Пользователи -->
      {#if isNavAllowed("users")}
        <button
          type="button"
          onclick={() => selectNav("users")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'users' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          <span class="flex-1 truncate">{t.navUsers}</span>
        </button>
      {/if}

      <!-- 4. Роли -->
      {#if isNavAllowed("roles")}
        <button
          type="button"
          onclick={() => selectNav("roles")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'roles' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <span class="flex-1 truncate">{t.navRoles}</span>
        </button>
      {/if}

      <!-- 5. Делегирование -->
      {#if isNavAllowed("delegations")}
        <button
          type="button"
          onclick={() => selectNav("delegations")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'delegations' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
          </svg>
          <span class="flex-1 truncate">{t.navDelegations}</span>
        </button>
      {/if}

      <!-- 6. Соцсети и SEO -->
      {#if isNavAllowed("seo")}
        <button
          type="button"
          onclick={() => selectNav("seo")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'seo' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <span class="flex-1 truncate">{t.navSeo}</span>
        </button>
      {/if}

      <!-- 7. Настройки -->
      {#if isNavAllowed("settings")}
        <button
          type="button"
          onclick={() => selectNav("settings")}
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer {currentNav === 'settings' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-foreground hover:bg-muted/80'}"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span class="flex-1 truncate">{t.navSettings}</span>
        </button>
      {/if}

      <!-- 8. Справка и API (/admin/help) -->
      {#if isNavAllowed("help")}
        <a
          href="/admin/help/"
          target="_blank"
          rel="noreferrer"
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left cursor-pointer text-foreground hover:bg-muted/80 group mt-1 border-t border-border/40 pt-3"
        >
          <svg class="h-4 w-4 shrink-0 text-blue-600 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3m.08 4h.01"/>
          </svg>
          <span class="flex-1 truncate">{t.navHelp}</span>
          <span class="text-[10px] text-muted-foreground group-hover:text-foreground">↗</span>
        </a>
      {/if}
    </aside>

    <!-- Основное содержимое -->
    <main class="flex-1 p-6 overflow-y-auto w-full flex flex-col gap-5">
      {#if currentNav === "rpc"}
        <RpcCatalogView {lang} rpcClient={rpc} />
      {:else if currentNav === "delegations"}
        <DelegationsView {lang} rpcClient={rpc} onnotify={(msg, type) => showToast(msg, type)} />
      {:else if currentNav === "seo"}
        <SeoAdminView {lang} rpcClient={rpc} onnotify={(msg, type) => showToast(msg, type)} />
      {:else if currentNav === "settings"}
        <SettingsView {lang} rpcClient={rpc} onnotify={(msg, type) => showToast(msg, type)} />
        <div class="flex h-64 items-center justify-center text-sm text-muted-foreground">
          {t.schemaLoading}
        </div>
      {:else}
        {#if currentNav === "database"}
          <!-- Вкладки: Таблицы приложения | Таблицы фреймворка -->
          <div class="flex flex-col gap-3">
            <div class="flex items-center gap-2 border-b border-border pb-2">
              <button
                type="button"
                onclick={() => selectDbTab("app")}
                class="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer {dbTab === 'app' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
              >
                <span>📦</span>
                <span>{t.tabAppTables}</span>
                <span class="text-2xs px-1.5 py-0.5 rounded-full {dbTab === 'app' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'}">{appModels.length}</span>
              </button>

              <button
                type="button"
                onclick={() => selectDbTab("framework")}
                class="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer {dbTab === 'framework' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'}"
              >
                <span>⚙️</span>
                <span>{t.tabFrameworkTables}</span>
                <span class="text-2xs px-1.5 py-0.5 rounded-full {dbTab === 'framework' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'}">{frameworkModels.length}</span>
              </button>
            </div>

            <!-- Горизонтальные пилюли выбора таблицы -->
            {#if (dbTab === 'app' ? appModels : frameworkModels).length > 0}
              <div class="flex flex-wrap items-center gap-1.5">
                {#each (dbTab === 'app' ? appModels : frameworkModels) as m}
                  <button
                    type="button"
                    onclick={() => selectModel(m.key)}
                    class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer {selectedModelName === m.key ? 'bg-card text-foreground border-2 border-primary shadow-xs font-bold' : 'bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted border border-border'}"
                  >
                    <span>{getModelDisplayName(m)}</span>
                    {#if m.table_name}
                      <span class="text-2xs opacity-60 font-mono ml-1">({m.table_name})</span>
                    {/if}
                  </button>
                {/each}
              </div>
            {:else}
              <div class="p-6 text-center text-xs text-muted-foreground italic border border-dashed border-border rounded-xl">
                {dbTab === 'app' ? t.noAppTables : t.noFrameworkTables}
              </div>
            {/if}
          </div>
        {:else if currentNav === "users"}
          <div class="flex items-center justify-between pb-1">
            <div class="flex items-center gap-2.5">
              <span class="text-lg">👥</span>
              <h2 class="text-base font-bold text-foreground">{t.navUsers}</h2>
              <span class="text-xs text-muted-foreground">({userModel ? getModelDisplayName(userModel) : 'pf_auth_user'})</span>
            </div>
          </div>
        {:else if currentNav === "roles"}
          <div class="flex items-center justify-between pb-1">
            <div class="flex items-center gap-2.5">
              <span class="text-lg">🛡️</span>
              <h2 class="text-base font-bold text-foreground">{t.navRoles}</h2>
              <span class="text-xs text-muted-foreground">({roleModel ? getModelDisplayName(roleModel) : 'pf_auth_role'})</span>
            </div>
          </div>
        {/if}

        {#if currentNav === "database" && dbTab === "app"}
          <div class="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-700 dark:text-amber-400">
            <span class="text-base">👁️</span>
            <div>
              <span class="font-semibold">{lang === 'ru' ? 'Режим инспекции (только чтение):' : 'Inspection Mode (Read-Only):'}</span>
              <span class="text-muted-foreground ml-1.5">{lang === 'ru' ? 'Таблицы приложения доступны для чтения и анализа. Изменение данных производится через специализированные пользовательские интерфейсы.' : 'Application tables are view-only. Data modifications are handled through dedicated application interfaces.'}</span>
            </div>
          </div>
        {/if}

        {#if currentSchema}
          <div class=flex flex-wrap items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-xs>
            <div class=flex items-center gap-3 flex-1 max-w-md>
            <input
              type="text"
              bind:value={searchQuery}
              onkeydown={(e) => { if (e.key === 'Enter') loadData(); }}
              placeholder={t.searchPlaceholder}
              class="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary shadow-2xs"
            />
          {#if searchQuery}
            <button
              type="button"
              onclick={() => { searchQuery = ''; loadData(); }}
              class="text-xs text-muted-foreground hover:text-foreground cursor-pointer"
            >
              ✕
            </button>
          {/if}
        </div>

        <div class="flex items-center gap-2.5">
          {#if currentSchema.is_archivable}
            <button
              type="button"
              onclick={() => { showArchived = !showArchived; loadData(); }}
              class="px-3 py-1.5 rounded-lg text-xs font-medium border cursor-pointer transition-colors {showArchived ? 'bg-secondary text-secondary-foreground border-border' : 'bg-background text-muted-foreground border-input hover:text-foreground'}"
            >
              {showArchived ? t.archiveOn : t.archiveOff}
            </button>
          {/if}

          <button
            type="button"
            onclick={loadData}
            class="px-3 py-1.5 rounded-lg text-xs font-medium border border-input bg-background hover:bg-muted text-foreground cursor-pointer transition-colors"
            title={t.refresh}
          >
            ↻ {t.refresh}
          </button>

          {#if currentSchema.permissions?.can_create}
            <button
              type="button"
              onclick={openCreateModal}
              class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-2xs cursor-pointer transition-colors"
            >
              + {t.create}
            </button>
          {/if}
        </div>
      </div>

      <!-- Таблица данных -->
      <div class="rounded-xl border border-border bg-card overflow-hidden shadow-xs flex flex-col">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-foreground border-collapse">
            <thead class="border-b border-border bg-muted/40 font-semibold text-muted-foreground">
              <tr>
                {#each displayColumns as col}
                  <th
                    scope="col"
                    class="px-4 py-3 cursor-pointer hover:bg-muted/80 transition-colors select-none {isRefColumn(col.name) ? 'text-muted-foreground/70 font-normal' : ''}"
                    onclick={() => handleSort(col.name)}
                  >
                    <div class="flex items-center gap-1">
                      <span>{getFieldDisplayName(col)}</span>
                      {#if sortField === col.name}
                        <span class="text-primary font-bold">{sortDir === 'asc' ? '▲' : '▼'}</span>
                      {/if}
                    </div>
                  </th>
                {/each}
                {#if currentSchema.permissions?.can_delete || isRoleOrUserModel}
                  <th scope="col" class="px-4 py-3 text-right">{t.actions}</th>
                {/if}
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              {#if isLoadingData && rows.length === 0}
                <tr>
                  <td colspan="100" class="h-40 text-center text-muted-foreground">
                    {t.loadingRows}
                  </td>
                </tr>
              {:else if rows.length === 0}
                <tr>
                  <td colspan="100" class="h-40 text-center text-muted-foreground italic">
                    {t.noRecords}
                  </td>
                </tr>
              {:else}
                {#each rows as row, rowIdx (getRowId(row, rowIdx))}
                  {@const recId = getRowId(row, rowIdx)}
                  <tr class="hover:bg-muted/30 transition-colors">
                    {#each displayColumns as col}
                      {@const cIdx = fields.indexOf(col.name)}
                      {@const val = row[cIdx]}
                      {@const isEditing = editingCell?.id === recId && editingCell?.field === col.name}

                      <td class="px-4 py-2.5 whitespace-nowrap">
                        {#if isEditing && editingCell}
                          {#if col.type === "m2m"}
                            <div class="flex flex-col gap-1.5 p-2 rounded-lg border border-primary bg-background shadow-lg z-20 min-w-48">
                              <div class="flex flex-wrap gap-1 max-h-36 overflow-y-auto">
                                {#each (lookupCache[col.target_model] || []) as opt}
                                  <label class="flex items-center gap-1.5 text-2xs px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted cursor-pointer border border-border">
                                    <input
                                      type="checkbox"
                                      checked={Array.isArray(editingCell.value) && (editingCell.value.includes(opt.id) || editingCell.value.includes(opt.label))}
                                      onchange={(e) => {
                                        const cur = Array.isArray(editingCell.value) ? [...editingCell.value] : [];
                                        if (e.currentTarget.checked) {
                                          if (!cur.includes(opt.id) && !cur.includes(opt.label)) cur.push(opt.id);
                                        } else {
                                          const idxId = cur.indexOf(opt.id);
                                          if (idxId !== -1) cur.splice(idxId, 1);
                                          const idxLabel = cur.indexOf(opt.label);
                                          if (idxLabel !== -1) cur.splice(idxLabel, 1);
                                        }
                                        editingCell.value = cur;
                                      }}
                                      class="h-3 w-3 rounded text-primary"
                                    />
                                    <span>{opt.label}</span>
                                  </label>
                                {/each}
                              </div>
                              <div class="flex justify-end gap-1.5 pt-1 border-t border-border">
                                <button type="button" onclick={saveInlineCell} class="px-2 py-0.5 rounded bg-primary text-primary-foreground text-2xs font-semibold cursor-pointer">✓ Сохранить</button>
                                <button type="button" onclick={() => (editingCell = null)} class="px-2 py-0.5 rounded bg-muted text-foreground text-2xs cursor-pointer">✕</button>
                              </div>
                            </div>
                          {:else}
                            <div class="flex items-center gap-1">
                              <input
                                type="text"
                                bind:value={editingCell.value}
                                onkeydown={(e) => {
                                  if (e.key === 'Enter') saveInlineCell();
                                  if (e.key === 'Escape') editingCell = null;
                                }}
                                class="rounded border border-primary bg-background px-2 py-0.5 text-xs text-foreground focus:outline-none"
                              />
                              <button
                                type="button"
                                onclick={saveInlineCell}
                                disabled={isSavingCell}
                                class="px-1.5 py-0.5 rounded bg-primary text-primary-foreground text-2xs cursor-pointer"
                              >
                                ✓
                              </button>
                              <button
                                type="button"
                                onclick={() => (editingCell = null)}
                                class="px-1.5 py-0.5 rounded bg-muted text-foreground text-2xs cursor-pointer"
                              >
                                ✕
                              </button>
                            </div>
                          {/if}
                        {:else}
                          <div class="flex items-center justify-between gap-2 group">
                            {#if typeof val === "boolean"}
                              {@const canEditBool = col.editable && currentSchema?.permissions?.can_update}
                              {#if canEditBool}
                                <button
                                  type="button"
                                  onclick={() => toggleBool(recId, col.name, val)}
                                  class="cursor-pointer font-semibold px-2 py-0.5 rounded text-2xs {val ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-muted text-muted-foreground'}"
                                >
                                  {val ? t.yes : t.no}
                                </button>
                              {:else}
                                <span
                                  class="inline-block font-semibold px-2 py-0.5 rounded text-2xs {val ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-muted text-muted-foreground'}"
                                >
                                  {val ? t.yes : t.no}
                                </span>
                              {/if}
                            {:else if Array.isArray(val)}
                              <div class="flex flex-wrap gap-1 items-center">
                                {#each val as item}
                                  <span class="inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium bg-primary/10 text-primary border border-primary/20">
                                    {typeof item === 'object' ? (item.label || item.name || item.id) : item}
                                  </span>
                                {/each}
                                {#if val.length === 0}
                                  <span class="text-muted-foreground/40 text-xs">—</span>
                                {/if}
                              </div>
                            {:else if val === null || val === undefined}
                              <span class="text-muted-foreground/40">—</span>
                            {:else}
                              <span class="truncate max-w-xs {isRefColumn(col.name) ? 'text-muted-foreground/80 font-mono text-2xs' : ''}">
                                {formatCellValue(val, col)}
                              </span>
                            {/if}

                            {#if col.editable && currentSchema?.permissions?.can_update && typeof val !== "boolean"}
                              <button
                                type="button"
                                onclick={() => {
                                  if (col.type === "m2m" && col.target_model) loadLookupOptions(col.target_model);
                                  editingCell = { id: recId, field: col.name, value: val ?? [] };
                                }}
                                class="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-primary transition-opacity text-2xs cursor-pointer"
                                title={t.editCell}
                              >
                                ✎
                              </button>
                            {/if}
                          </div>
                        {/if}
                      </td>
                    {/each}

                    {#if currentSchema.permissions?.can_delete || isRoleOrUserModel}
                      {@const isRowAdminRole = isRoleModel && isRoleAdmin(row)}
                      {@const isRowAdminUser = isUserModel && isUserAdmin(row)}
                      {@const isRowGuestRole = isRoleModel && isRoleGuest(row)}
                      {@const isRowAdmin = isRowAdminRole || isRowAdminUser}
                      <td class="px-4 py-2.5 text-right whitespace-nowrap">
                        <div class="inline-flex items-center justify-end gap-1.5">
                          {#if isRoleOrUserModel}
                            {#if isRowAdmin}
                              <button
                                type="button"
                                disabled
                                class="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-muted/60 text-muted-foreground/50 border border-border/50 cursor-not-allowed select-none opacity-60"
                                title={isRowAdminRole ? t.roleAdminPermissionsDisabled : t.adminPermissionsDisabled}
                              >
                                <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                </svg>
                                <span>{t.permissions}</span>
                              </button>
                            {:else}
                              <button
                                type="button"
                                onclick={() => openPermissions(row, recId)}
                                class="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors cursor-pointer font-medium"
                                title={isRowGuestRole ? (lang === 'ru' ? 'Настроить публичные разрешения гостя' : 'Configure guest public permissions') : (lang === 'ru' ? 'Настроить разрешения (CRUD + RPC)' : 'Configure permissions (CRUD + RPC)')}
                              >
                                <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                </svg>
                                <span>{t.permissions}</span>
                              </button>
                            {/if}
                          {/if}
                          {#if currentSchema.permissions?.can_delete}
                            {#if !isRowAdminRole}
                              <button
                                type="button"
                                onclick={() => (recordToDelete = recId)}
                                class="text-rose-500 hover:text-rose-600 dark:text-rose-400 p-1.5 rounded hover:bg-rose-500/10 transition-colors cursor-pointer"
                                title={t.deleteRecord}
                              >
                                <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                  <polyline points="3 6 5 6 21 6"/>
                                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                </svg>
                              </button>
                            {/if}
                          {/if}
                        </div>
                      </td>
                    {/if}
                  </tr>
                {/each}
              {/if}
            </tbody>
          </table>
        </div>

        <!-- Подвал пагинации -->
        <div class="flex items-center justify-between border-t border-border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
          <div>
            {t.totalRecords} <strong class="text-foreground">{total}</strong>
          </div>
          <div class="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onclick={() => { page--; loadData(); }}
              class="px-2.5 py-1 rounded border border-input bg-background hover:bg-muted disabled:opacity-40 cursor-pointer text-foreground"
            >
              {t.prev}
            </button>
            <span>{t.page} {page} {t.of} {Math.ceil(total / pageSize) || 1}</span>
            <button
              type="button"
              disabled={page * pageSize >= total}
              onclick={() => { page++; loadData(); }}
              class="px-2.5 py-1 rounded border border-input bg-background hover:bg-muted disabled:opacity-40 cursor-pointer text-foreground"
            >
              {t.next}
            </button>
          </div>
        </div>
      </div>
    {:else}
      <div class=flex h-64 items-center justify-center text-sm text-muted-foreground>
        {t.noModels}
      </div>
    {/if}
    {/if}
  </main>
</div>

  <!-- Модальное окно создания -->
  {#if isCreateModalOpen && currentSchema}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in">
      <div class="w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl flex flex-col gap-4 text-foreground">
        <div class="flex items-center justify-between border-b border-border pb-3">
          <h3 class="text-sm font-bold text-foreground">
            {t.createTitle(getModelDisplayName(currentSchema))}
          </h3>
          <button
            type="button"
            onclick={() => (isCreateModalOpen = false)}
            class="text-muted-foreground hover:text-foreground cursor-pointer text-sm"
          >
            ✕
          </button>
        </div>

        {#if createError}
          <div class="p-3 rounded-lg border border-destructive/30 bg-destructive/10 text-destructive text-xs">
            {createError}
          </div>
        {/if}

        <div class="flex flex-col gap-3.5 max-h-[60vh] overflow-y-auto pr-1">
          {#each currentSchema.fields as col}
            {#if col.editable && !col.primary_key && col.name !== "creator_id"}
              <div class="flex flex-col gap-1">
                <label for={`create-field-${col.name}`} class="text-xs font-semibold text-muted-foreground">
                  {getFieldDisplayName(col)} {#if !col.nullable}<span class="text-rose-500">*</span>{/if}
                </label>
                {#if col.type === "boolean"}
                  <label class="flex items-center gap-2 cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      bind:checked={createFormData[col.name]}
                      class="h-4 w-4 rounded border-border text-primary accent-primary"
                    />
                    <span class="text-xs font-medium">{createFormData[col.name] ? t.yes : t.no}</span>
                  </label>
                {:else if col.type === "m2m"}
                  {@const targetModel = col.target_model}
                  {@const opts = targetModel && lookupCache[targetModel] ? lookupCache[targetModel] : []}
                  <div class="flex flex-wrap gap-2 pt-1 p-2 rounded-lg border border-input bg-background/50 max-h-36 overflow-y-auto">
                    {#if opts.length === 0}
                      <span class="text-xs text-muted-foreground italic">Загрузка опций или список пуст...</span>
                    {:else}
                      {#each opts as opt}
                        <label class="flex items-center gap-1.5 px-2 py-1 rounded bg-muted/60 hover:bg-muted text-xs cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={Array.isArray(createFormData[col.name]) && createFormData[col.name].includes(opt.id)}
                            onchange={(e) => {
                              const arr = Array.isArray(createFormData[col.name]) ? [...createFormData[col.name]] : [];
                              if (e.currentTarget.checked) {
                                if (!arr.includes(opt.id)) arr.push(opt.id);
                              } else {
                                const idx = arr.indexOf(opt.id);
                                if (idx !== -1) arr.splice(idx, 1);
                              }
                              createFormData[col.name] = arr;
                            }}
                            class="h-3.5 w-3.5 rounded border-border text-primary accent-primary"
                          />
                          <span>{opt.label}</span>
                        </label>
                      {/each}
                    {/if}
                  </div>
                {:else if col.type === "fk" || col.foreign_key}
                  {@const targetModel = getTargetModelFromFk(col.foreign_key)}
                  {@const opts = targetModel && lookupCache[targetModel] ? lookupCache[targetModel] : []}
                  <select
                    id={`create-field-${col.name}`}
                    bind:value={createFormData[col.name]}
                    class="rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value={null}>-- Выберите {getFieldDisplayName(col)} --</option>
                    {#each opts as opt}
                      <option value={opt.id}>{opt.label} (ID: {opt.id})</option>
                    {/each}
                  </select>
                {:else if col.type === "integer"}
                  <input
                    id={`create-field-${col.name}`}
                    type="number"
                    step="1"
                    bind:value={createFormData[col.name]}
                    placeholder={getFieldDisplayName(col)}
                    class="rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                {:else if col.type === "datetime" || col.type === "date"}
                  <input
                    id={`create-field-${col.name}`}
                    type={col.type === "date" ? "date" : "datetime-local"}
                    bind:value={createFormData[col.name]}
                    class="rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                {:else}
                  <input
                    id={`create-field-${col.name}`}
                    type="text"
                    bind:value={createFormData[col.name]}
                    placeholder={getFieldDisplayName(col)}
                    class="rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                {/if}
              </div>
            {/if}
          {/each}
        </div>

        <div class="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onclick={() => (isCreateModalOpen = false)}
            class="px-3.5 py-1.5 rounded-lg border border-input bg-background hover:bg-muted text-xs font-medium text-foreground cursor-pointer"
          >
            {t.cancel}
          </button>
          <button
            type="button"
            onclick={submitCreate}
            disabled={isCreating}
            class="px-4 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-semibold cursor-pointer disabled:opacity-50"
          >
            {isCreating ? t.creating : t.save}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Модальное окно удаления -->
  {#if recordToDelete !== null}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in">
      <div class="w-full max-w-sm rounded-xl border border-border bg-card p-5 shadow-xl flex flex-col gap-4 text-foreground">
        <h3 class="text-sm font-bold text-foreground">{t.confirmDeleteTitle}</h3>
        <p class="text-xs text-muted-foreground">
          {t.confirmDeleteText(recordToDelete)}
        </p>
        <div class="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onclick={() => (recordToDelete = null)}
            class="px-3 py-1.5 rounded-lg border border-input bg-background hover:bg-muted text-xs font-medium text-foreground cursor-pointer"
          >
            {t.cancel}
          </button>
          <button
            type="button"
            onclick={confirmDelete}
            disabled={isDeleting}
            class="px-3.5 py-1.5 rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 text-xs font-semibold cursor-pointer disabled:opacity-50"
          >
            {isDeleting ? t.deleting : t.delete}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Всплывающие уведомления (Toast) -->
  {#if toastMsg}
    <div class="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg border text-xs font-medium animate-in slide-in-from-bottom-3 {toastMsg.type === 'error' ? 'bg-rose-600 text-white border-rose-700' : 'bg-emerald-600 text-white border-emerald-700'}">
      <span>{toastMsg.text}</span>
    </div>
  {/if}

  <!-- Модальное окно управления разрешениями -->
  {#if permissionsModalOpen}
    <PermissionsModal
      open={permissionsModalOpen}
      targetType={permissionsTargetType}
      targetId={permissionsTargetId}
      targetName={permissionsTargetName}
      {lang}
      rpcClient={rpc}
      onclose={() => (permissionsModalOpen = false)}
      onsaved={() => {
        showToast(lang === "ru" ? "Разрешения успешно обновлены" : "Permissions updated successfully", "success");
        loadData();
      }}
    />
  {/if}
</div>
