<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import { Button, Input, Card, Badge, Modal, Checkbox, toast } from "./ui/index.js";
  import {
    Share2,
    Search,
    ExternalLink,
    Trash2,
    ShieldCheck,
    CheckCircle2,
    AlertCircle,
    RefreshCw,
    Link2,
    User,
    Mail,
    Send,
    Palette,
    KeyRound,
  } from "@lucide/svelte";

  let { onnotify = () => {} } = $props();

  // Брендинг
  let appTitle = $state("PyFerro 2.0 Admin");
  let appLogoSvg = $state("");
  let isSavingBranding = $state(false);

  // Регистрация и SMTP
  let allowRegistration = $state(true);
  let requireEmailVerification = $state(false);
  let smtpHost = $state("smtp.gmail.com");
  let smtpPort = $state(587);
  let smtpUser = $state("");
  let smtpPassword = $state("");
  let smtpFromEmail = $state("");
  let smtpUseSsl = $state(false);
  let isSavingSmtp = $state(false);
  let testEmailTarget = $state("");
  let isTestingSmtp = $state(false);

  // Провайдеры OAuth
  let providersConfig = $state({
    vk: { is_enabled: true, client_id: "54878944", client_secret: "", redirect_uri: "https://stage.agrita.ru/auth/callback" },
    yandex: { is_enabled: false, client_id: "", client_secret: "", redirect_uri: "https://stage.agrita.ru/auth/callback" },
    telegram: { is_enabled: false, bot_token: "", bot_username: "" },
    google: { is_enabled: false, client_id: "", client_secret: "", redirect_uri: "https://stage.agrita.ru/auth/callback" },
  });
  let isSavingProvider = $state({});

  // Таблица привязанных аккаунтов
  let accounts = $state([]);
  let totalAccounts = $state(0);
  let isLoading = $state(false);
  let searchQuery = $state("");
  let filterProvider = $state("");

  // Модалка удаления связки
  let showDeleteModal = $state(false);
  let accountToDelete = $state(null);
  let isDeleting = $state(false);

  async function loadAllConfigs() {
    try {
      const res = await rpc.call("oauth.admin_get_all_configs");
      if (!res) return;

      if (res.branding && res.branding.config) {
        appTitle = res.branding.config.app_title || "PyFerro 2.0 Admin";
        appLogoSvg = res.branding.config.app_logo_svg || "";
      }

      if (res.registration && res.registration.config) {
        allowRegistration = res.registration.config.allow_registration ?? true;
        requireEmailVerification = res.registration.config.require_email_verification ?? false;
      }

      if (res.smtp && res.smtp.config) {
        const s = res.smtp.config;
        smtpHost = s.host || "smtp.gmail.com";
        smtpPort = s.port || 587;
        smtpUser = s.user || "";
        smtpPassword = s.password || "";
        smtpFromEmail = s.from_email || "";
        smtpUseSsl = !!s.use_ssl;
      }

      for (const p of ["vk", "yandex", "telegram", "google"]) {
        if (res[p]) {
          providersConfig[p] = {
            is_enabled: !!res[p].is_enabled,
            ...res[p].config,
          };
        }
      }
    } catch (e) {
      console.warn("Failed to load oauth configs:", e);
    }
  }

  async function saveBranding() {
    isSavingBranding = true;
    try {
      await rpc.call("oauth.admin_update_config", {
        key: "branding",
        is_enabled: true,
        config: {
          app_title: appTitle.trim() || "PyFerro 2.0 Admin",
          app_logo_svg: appLogoSvg.trim(),
        },
      });
      toast.success("Брендинг успешно сохранен!");
    } catch (e) {
      toast.error(e.message || "Ошибка сохранения брендинга");
    } finally {
      isSavingBranding = false;
    }
  }

  function applyGmailPreset() {
    smtpHost = "smtp.gmail.com";
    smtpPort = 587;
    smtpUseSsl = false;
    if (smtpUser && !smtpFromEmail) {
      smtpFromEmail = smtpUser;
    }
    toast.info("Применен пресет Gmail (smtp.gmail.com:587 STARTTLS)");
  }

  async function saveSmtpAndRegistration() {
    isSavingSmtp = true;
    try {
      await rpc.call("oauth.admin_update_config", {
        key: "registration",
        is_enabled: true,
        config: {
          allow_registration: allowRegistration,
          require_email_verification: requireEmailVerification,
        },
      });

      await rpc.call("oauth.admin_update_config", {
        key: "smtp",
        is_enabled: !!(smtpHost && smtpUser),
        config: {
          host: smtpHost.trim(),
          port: Number(smtpPort) || 587,
          user: smtpUser.trim(),
          password: smtpPassword.trim(),
          from_email: smtpFromEmail.trim() || smtpUser.trim(),
          use_ssl: smtpUseSsl,
        },
      });

      toast.success("Настройки почты и регистрации сохранены!");
    } catch (e) {
      toast.error(e.message || "Ошибка сохранения настроек SMTP");
    } finally {
      isSavingSmtp = false;
    }
  }

  async function testSmtp() {
    if (!testEmailTarget) {
      toast.warning("Укажите email получателя для проверки");
      return;
    }
    isTestingSmtp = true;
    try {
      await rpc.call("oauth.admin_test_smtp", {
        target_email: testEmailTarget.trim(),
        smtp_config: {
          host: smtpHost.trim(),
          port: Number(smtpPort) || 587,
          user: smtpUser.trim(),
          password: smtpPassword.trim(),
          from_email: smtpFromEmail.trim() || smtpUser.trim(),
          use_ssl: smtpUseSsl,
        },
      });
      toast.success(`Тестовое письмо успешно отправлено на ${testEmailTarget}!`);
    } catch (e) {
      toast.error(e.message || "Ошибка отправки тестового письма");
    } finally {
      isTestingSmtp = false;
    }
  }

  async function saveProvider(provName) {
    isSavingProvider[provName] = true;
    try {
      const cfg = { ...providersConfig[provName] };
      const is_enabled = cfg.is_enabled;
      delete cfg.is_enabled;

      await rpc.call("oauth.admin_update_config", {
        key: provName,
        is_enabled: !!is_enabled,
        config: cfg,
      });
      toast.success(`Настройки ${provName.toUpperCase()} сохранены!`);
    } catch (e) {
      toast.error(e.message || `Ошибка сохранения ${provName}`);
    } finally {
      isSavingProvider[provName] = false;
    }
  }

  async function loadAccounts() {
    isLoading = true;
    try {
      const res = await rpc.call("oauth.admin_list", {
        search: searchQuery.trim(),
        provider: filterProvider,
        limit: 50,
        offset: 0,
      });
      accounts = res.items || [];
      totalAccounts = res.total || 0;
    } catch (e) {
      toast.error(e.message || "Ошибка загрузки привязанных аккаунтов");
    } finally {
      isLoading = false;
    }
  }

  async function testAuth(providerName) {
    try {
      const res = await rpc.call("oauth.get_auth_url", {
        provider: providerName,
        state: "admin_test",
      });
      if (res && res.url) {
        window.open(res.url, "_blank", "width=600,height=700");
      }
    } catch (e) {
      toast.error(e.message || "Не удалось получить URL авторизации");
    }
  }

  function confirmDelete(acc) {
    accountToDelete = acc;
    showDeleteModal = true;
  }

  async function executeDelete() {
    if (!accountToDelete) return;
    isDeleting = true;
    try {
      await rpc.call("oauth.admin_delete", { account_id: accountToDelete.id });
      toast.success(`Привязка ${accountToDelete.display_name} успешно удалена`);
      showDeleteModal = false;
      accountToDelete = null;
      await loadAccounts();
    } catch (e) {
      toast.error(e.message || "Не удалось удалить привязку");
    } finally {
      isDeleting = false;
    }
  }

  function formatDate(isoStr) {
    if (!isoStr) return "—";
    try {
      const d = new Date(isoStr);
      return d.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoStr;
    }
  }

  onMount(async () => {
    await Promise.all([loadAllConfigs(), loadAccounts()]);
  });
</script>

<div class="space-y-6">
  <!-- Заголовок страницы -->
  <div class="flex items-center justify-between flex-wrap gap-3 pb-2 border-b border-border">
    <div>
      <h1 class="text-xl font-bold text-text-bright flex items-center gap-2 m-0">
        <Link2 size={22} class="text-accent" />
        <span>Внешняя авторизация, брендинг и почта</span>
      </h1>
      <p class="text-xs text-muted mt-1 mb-0">
        Управление OAuth-провайдерами, регистрацией пользователей, SMTP-сервером (Gmail) и связками профилей.
      </p>
    </div>
    <div class="flex items-center gap-2">
      <Button variant="outline" size="sm" onclick={() => Promise.all([loadAllConfigs(), loadAccounts()])} disabled={isLoading}>
        <RefreshCw size={14} class={isLoading ? "animate-spin" : ""} />
        <span>Обновить</span>
      </Button>
    </div>
  </div>

  <!-- Блок 1: Брендинг и экран входа -->
  <Card class="p-4 border border-border">
    <div class="flex items-center gap-2 mb-3">
      <Palette size={18} class="text-accent" />
      <h2 class="text-sm font-bold text-text-bright uppercase tracking-wider m-0">
        Брендинг и экран входа
      </h2>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="space-y-3">
        <div>
          <label class="block text-xs font-medium text-text mb-1">
            Название приложения:
          </label>
          <Input
            placeholder="PyFerro 2.0 Admin"
            bind:value={appTitle}
            class="text-xs py-1.5"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-text mb-1">
            SVG-код логотипа (чистый вектор &lt;svg ...&gt;...&lt;/svg&gt;):
          </label>
          <textarea
            bind:value={appLogoSvg}
            placeholder="<svg viewBox='0 0 24 24'>...</svg>"
            rows={4}
            class="w-full bg-input border border-border text-xs text-text rounded p-2 font-mono focus:outline-none focus:border-accent"
          ></textarea>
        </div>

        <Button variant="primary" size="sm" onclick={saveBranding} disabled={isSavingBranding}>
          <span>{isSavingBranding ? "Сохранение..." : "Сохранить брендинг"}</span>
        </Button>
      </div>

      <!-- Живой предпросмотр -->
      <div class="bg-panel-header/40 border border-border rounded-lg p-4 flex flex-col justify-between">
        <div>
          <div class="text-xs font-semibold text-muted mb-2">Предпросмотр в шапке окна логина:</div>
          <div class="bg-panel border border-border rounded-md p-3 flex items-center gap-2">
            {#if appLogoSvg.trim()}
              <div class="w-6 h-6 text-accent flex items-center justify-center [&>svg]:w-full [&>svg]:h-full [&>svg]:fill-current">
                {@html appLogoSvg}
              </div>
            {:else}
              <div class="w-6 h-6 rounded bg-accent/20 text-accent flex items-center justify-center font-bold text-xs">
                PF
              </div>
            {/if}
            <span class="text-base font-bold text-accent">{appTitle || "PyFerro 2.0"}</span>
          </div>
        </div>
        <p class="text-[0.7rem] text-muted mt-3 mb-0">
          Подзаголовок «Вход в панель управления» скрыт. Логотип и имя динамически применяются сразу после сохранения.
        </p>
      </div>
    </div>
  </Card>

  <!-- Блок 2: Регистрация и SMTP-почта (Gmail) -->
  <Card class="p-4 border border-border">
    <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <Mail size={18} class="text-accent" />
        <h2 class="text-sm font-bold text-text-bright uppercase tracking-wider m-0">
          Регистрация и SMTP (Gmail / Любой хост)
        </h2>
      </div>
      <Button variant="outline" size="sm" onclick={applyGmailPreset}>
        <span>Заполнить для Gmail (587 STARTTLS)</span>
      </Button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
      <!-- Флаги регистрации -->
      <div class="space-y-3 bg-panel-header/20 p-3 rounded border border-border">
        <label class="flex items-center gap-2 cursor-pointer font-medium text-text">
          <input type="checkbox" bind:checked={allowRegistration} class="accent-accent" />
          <span>Разрешить самостоятельную регистрацию новых пользователей</span>
        </label>
        <p class="text-[0.7rem] text-muted ml-5 mt-0 mb-2">
          Если выключено — кнопка регистрации скрывается, а новые аккаунты из соцсетей блокируются.
        </p>

        <label class="flex items-center gap-2 cursor-pointer font-medium text-text">
          <input type="checkbox" bind:checked={requireEmailVerification} class="accent-accent" />
          <span>Требовать подтверждение Email (6-значный одноразовый код)</span>
        </label>
        <p class="text-[0.7rem] text-muted ml-5 mt-0 mb-0">
          Пользователь вводит 6-значный код из письма прямо в форме входа без перезагрузки страницы.
        </p>
      </div>

      <!-- Реквизиты SMTP -->
      <div class="space-y-2">
        <div class="grid grid-cols-3 gap-2">
          <div class="col-span-2">
            <label class="block text-[0.7rem] font-medium text-muted mb-0.5">SMTP Host:</label>
            <Input bind:value={smtpHost} placeholder="smtp.gmail.com" class="text-xs py-1" />
          </div>
          <div>
            <label class="block text-[0.7rem] font-medium text-muted mb-0.5">Порт:</label>
            <Input type="number" bind:value={smtpPort} placeholder="587" class="text-xs py-1" />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block text-[0.7rem] font-medium text-muted mb-0.5">Логин (Email):</label>
            <Input bind:value={smtpUser} placeholder="user@gmail.com" class="text-xs py-1" />
          </div>
          <div>
            <label class="block text-[0.7rem] font-medium text-muted mb-0.5">Пароль / App Password:</label>
            <Input type="password" bind:value={smtpPassword} placeholder="••••••••••••••••" class="text-xs py-1" />
          </div>
        </div>

        <div class="flex items-center justify-between gap-2 pt-1">
          <label class="flex items-center gap-2 cursor-pointer text-text">
            <input type="checkbox" bind:checked={smtpUseSsl} class="accent-accent" />
            <span>SSL (порт 465)</span>
          </label>
          <Button variant="primary" size="sm" onclick={saveSmtpAndRegistration} disabled={isSavingSmtp}>
            <span>{isSavingSmtp ? "Сохранение..." : "Сохранить почту"}</span>
          </Button>
        </div>
      </div>
    </div>

    <!-- Проверочная отправка письма -->
    <div class="mt-4 pt-3 border-t border-border flex items-center justify-between flex-wrap gap-2 text-xs">
      <div class="flex items-center gap-2 flex-grow max-w-md">
        <Input
          placeholder="Email для проверки отправки..."
          bind:value={testEmailTarget}
          class="text-xs py-1"
        />
        <Button variant="outline" size="sm" onclick={testSmtp} disabled={isTestingSmtp}>
          <Send size={13} class={isTestingSmtp ? "animate-spin" : ""} />
          <span>{isTestingSmtp ? "Отправка..." : "Тест SMTP"}</span>
        </Button>
      </div>
      <span class="text-[0.7rem] text-muted">
        Для Gmail создайте 16-значный «Пароль приложений» в настройках Google Security.
      </span>
    </div>
  </Card>

  <!-- Блок 3: Карточки OAuth-провайдеров -->
  <div>
    <h2 class="text-sm font-semibold text-text uppercase tracking-wider mb-3">
      Подключенные OAuth-провайдеры
    </h2>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- VK ID -->
      <Card class="flex flex-col justify-between p-4 border border-border">
        <div>
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <div class="w-6 h-6 rounded bg-[#0077FF] flex items-center justify-center text-white font-bold text-[10px]">
                VK
              </div>
              <span class="font-bold text-text-bright text-xs">VK ID</span>
            </div>
            <label class="flex items-center gap-1.5 cursor-pointer text-xs">
              <input type="checkbox" bind:checked={providersConfig.vk.is_enabled} class="accent-accent" />
              <span>Активен</span>
            </label>
          </div>

          <div class="space-y-1.5 text-xs mt-3">
            <div>
              <label class="text-[0.65rem] text-muted block">App ID:</label>
              <Input bind:value={providersConfig.vk.client_id} placeholder="54878944" class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Защищенный ключ:</label>
              <Input type="password" bind:value={providersConfig.vk.client_secret} placeholder="••••••••" class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Redirect URL:</label>
              <Input bind:value={providersConfig.vk.redirect_uri} placeholder="/auth/callback" class="text-xs py-0.5" />
            </div>
          </div>
        </div>

        <div class="mt-3 pt-2 border-t border-border flex justify-between gap-2">
          <Button variant="outline" size="sm" onclick={() => testAuth("vk")}>
            <ExternalLink size={12} />
            <span>Тест</span>
          </Button>
          <Button variant="primary" size="sm" onclick={() => saveProvider("vk")} disabled={isSavingProvider["vk"]}>
            <span>Сохранить</span>
          </Button>
        </div>
      </Card>

      <!-- Яндекс ID -->
      <Card class="flex flex-col justify-between p-4 border border-border">
        <div>
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <div class="w-6 h-6 rounded bg-[#FC3F1D] flex items-center justify-center text-white font-bold text-[10px]">
                Я
              </div>
              <span class="font-bold text-text-bright text-xs">Яндекс ID</span>
            </div>
            <label class="flex items-center gap-1.5 cursor-pointer text-xs">
              <input type="checkbox" bind:checked={providersConfig.yandex.is_enabled} class="accent-accent" />
              <span>Активен</span>
            </label>
          </div>

          <div class="space-y-1.5 text-xs mt-3">
            <div>
              <label class="text-[0.65rem] text-muted block">Client ID:</label>
              <Input bind:value={providersConfig.yandex.client_id} placeholder="ID приложения Яндекса" class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Client Secret:</label>
              <Input type="password" bind:value={providersConfig.yandex.client_secret} placeholder="••••••••" class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Redirect URL:</label>
              <Input bind:value={providersConfig.yandex.redirect_uri} placeholder="/auth/callback" class="text-xs py-0.5" />
            </div>
          </div>
        </div>

        <div class="mt-3 pt-2 border-t border-border flex justify-between gap-2">
          <Button variant="outline" size="sm" onclick={() => testAuth("yandex")}>
            <ExternalLink size={12} />
            <span>Тест</span>
          </Button>
          <Button variant="primary" size="sm" onclick={() => saveProvider("yandex")} disabled={isSavingProvider["yandex"]}>
            <span>Сохранить</span>
          </Button>
        </div>
      </Card>

      <!-- Telegram -->
      <Card class="flex flex-col justify-between p-4 border border-border">
        <div>
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <div class="w-6 h-6 rounded bg-[#2AABEE] flex items-center justify-center text-white font-bold text-[10px]">
                TG
              </div>
              <span class="font-bold text-text-bright text-xs">Telegram</span>
            </div>
            <label class="flex items-center gap-1.5 cursor-pointer text-xs">
              <input type="checkbox" bind:checked={providersConfig.telegram.is_enabled} class="accent-accent" />
              <span>Активен</span>
            </label>
          </div>

          <div class="space-y-1.5 text-xs mt-3">
            <div>
              <label class="text-[0.65rem] text-muted block">Bot Token:</label>
              <Input type="password" bind:value={providersConfig.telegram.bot_token} placeholder="123456:ABC-DEF..." class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Bot Username:</label>
              <Input bind:value={providersConfig.telegram.bot_username} placeholder="@MyAuthBot" class="text-xs py-0.5" />
            </div>
            <p class="text-[0.65rem] text-muted mt-2">
              Валидация HMAC-SHA256 без исходящих HTTP-запросов.
            </p>
          </div>
        </div>

        <div class="mt-3 pt-2 border-t border-border flex justify-end">
          <Button variant="primary" size="sm" onclick={() => saveProvider("telegram")} disabled={isSavingProvider["telegram"]}>
            <span>Сохранить</span>
          </Button>
        </div>
      </Card>

      <!-- Google -->
      <Card class="flex flex-col justify-between p-4 border border-border">
        <div>
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <div class="w-6 h-6 rounded bg-[#4285F4] flex items-center justify-center text-white font-bold text-[10px]">
                G
              </div>
              <span class="font-bold text-text-bright text-xs">Google</span>
            </div>
            <label class="flex items-center gap-1.5 cursor-pointer text-xs">
              <input type="checkbox" bind:checked={providersConfig.google.is_enabled} class="accent-accent" />
              <span>Активен</span>
            </label>
          </div>

          <div class="space-y-1.5 text-xs mt-3">
            <div>
              <label class="text-[0.65rem] text-muted block">Client ID:</label>
              <Input bind:value={providersConfig.google.client_id} placeholder="Google OAuth Client ID" class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Client Secret:</label>
              <Input type="password" bind:value={providersConfig.google.client_secret} placeholder="••••••••" class="text-xs py-0.5" />
            </div>
            <div>
              <label class="text-[0.65rem] text-muted block">Redirect URL:</label>
              <Input bind:value={providersConfig.google.redirect_uri} placeholder="/auth/callback" class="text-xs py-0.5" />
            </div>
          </div>
        </div>

        <div class="mt-3 pt-2 border-t border-border flex justify-between gap-2">
          <Button variant="outline" size="sm" onclick={() => testAuth("google")}>
            <ExternalLink size={12} />
            <span>Тест</span>
          </Button>
          <Button variant="primary" size="sm" onclick={() => saveProvider("google")} disabled={isSavingProvider["google"]}>
            <span>Сохранить</span>
          </Button>
        </div>
      </Card>
    </div>
  </div>

  <!-- Блок 4: Таблица привязанных профилей пользователей (pf_auth_oauth) -->
  <Card class="p-0 overflow-hidden border border-border">
    <div class="p-4 border-b border-border flex items-center justify-between flex-wrap gap-3 bg-panel-header">
      <div>
        <h3 class="text-sm font-semibold text-text-bright m-0">
          Привязанные профили пользователей (pf_auth_oauth)
        </h3>
        <p class="text-xs text-muted mt-0.5 mb-0">
          Всего привязок: <b class="text-text">{totalAccounts}</b>
        </p>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <select
          class="bg-input border border-border text-xs text-text rounded px-2.5 py-1.5 focus:outline-none focus:border-accent"
          bind:value={filterProvider}
          onchange={loadAccounts}
        >
          <option value="">Все провайдеры</option>
          <option value="vk">VK ID</option>
          <option value="yandex">Яндекс ID</option>
          <option value="telegram">Telegram</option>
          <option value="google">Google</option>
        </select>

        <div class="flex items-center gap-1">
          <Input
            placeholder="Поиск по логину, email, ID..."
            bind:value={searchQuery}
            class="text-xs py-1"
            onkeydown={(e) => e.key === "Enter" && loadAccounts()}
          />
          <Button variant="outline" size="sm" onclick={loadAccounts}>
            <Search size={14} />
          </Button>
        </div>
      </div>
    </div>

    <!-- Содержимое таблицы -->
    <div class="overflow-x-auto">
      {#if isLoading && accounts.length === 0}
        <div class="p-8 text-center text-xs text-muted">
          Загрузка привязанных профилей...
        </div>
      {:else if accounts.length === 0}
        <div class="p-8 text-center text-xs text-muted">
          {searchQuery ? "По запросу ничего не найдено" : "Пока нет привязанных профилей соцсетей"}
        </div>
      {:else}
        <table class="w-full text-xs text-left border-collapse">
          <thead>
            <tr class="border-b border-border bg-panel-header/50 text-muted font-medium">
              <th class="p-3">ID</th>
              <th class="p-3">Пользователь PyFerro</th>
              <th class="p-3">Провайдер</th>
              <th class="p-3">Профиль в соцсети</th>
              <th class="p-3">Email</th>
              <th class="p-3">Дата привязки</th>
              <th class="p-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each accounts as acc (acc.id)}
              <tr class="hover:bg-panel-hover transition-colors">
                <td class="p-3 text-muted font-mono">{acc.id}</td>
                <td class="p-3">
                  <div class="font-medium text-text-bright">{acc.username || "—"}</div>
                  <div class="text-[0.7rem] text-muted">ID: {acc.user_id}</div>
                </td>
                <td class="p-3">
                  {#if acc.provider === "vk"}
                    <Badge variant="accent" class="bg-[#0077FF]/15 text-[#0077FF] border-[#0077FF]/30">VK ID</Badge>
                  {:else if acc.provider === "yandex"}
                    <Badge variant="accent" class="bg-[#FC3F1D]/15 text-[#FC3F1D] border-[#FC3F1D]/30">Яндекс</Badge>
                  {:else if acc.provider === "telegram"}
                    <Badge variant="accent" class="bg-[#2AABEE]/15 text-[#2AABEE] border-[#2AABEE]/30">Telegram</Badge>
                  {:else}
                    <Badge variant="default">{acc.provider.toUpperCase()}</Badge>
                  {/if}
                </td>
                <td class="p-3">
                  <div class="flex items-center gap-2">
                    {#if acc.avatar_url}
                      <img src={acc.avatar_url} alt="" class="w-6 h-6 rounded-full object-cover border border-border" />
                    {:else}
                      <div class="w-6 h-6 rounded-full bg-muted/20 flex items-center justify-center text-muted">
                        <User size={12} />
                      </div>
                    {/if}
                    <div>
                      <div class="font-medium text-text-bright">{acc.display_name || "—"}</div>
                      <div class="text-[0.7rem] text-muted font-mono">{acc.provider_user_id}</div>
                    </div>
                  </div>
                </td>
                <td class="p-3 text-muted">{acc.email || "—"}</td>
                <td class="p-3 text-muted">{formatDate(acc.created_at)}</td>
                <td class="p-3 text-right">
                  <Button variant="danger" size="sm" onclick={() => confirmDelete(acc)} title="Отвязать аккаунт">
                    <Trash2 size={13} />
                    <span>Отвязать</span>
                  </Button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </Card>

  <!-- Модальное окно подтверждения удаления -->
  <Modal
    open={showDeleteModal}
    onclose={() => { showDeleteModal = false; accountToDelete = null; }}
    title="Отвязать аккаунт соцсети?"
    maxWidth="max-w-md"
  >
    {#if accountToDelete}
      <div class="space-y-3 text-xs text-text">
        <p>
          Вы уверены, что хотите отвязать профиль <b>{accountToDelete.display_name}</b> ({accountToDelete.provider.toUpperCase()} ID: {accountToDelete.provider_user_id}) от пользователя <b>{accountToDelete.username}</b>?
        </p>
        <p class="text-muted">
          Пользователь больше не сможет входить через этот аккаунт соцсети до повторной привязки.
        </p>
      </div>
    {/if}

    {#snippet footer()}
      <Button variant="outline" size="sm" onclick={() => { showDeleteModal = false; accountToDelete = null; }}>
        Отмена
      </Button>
      <Button variant="danger" size="sm" disabled={isDeleting} onclick={executeDelete}>
        {isDeleting ? "Удаление..." : "Отвязать"}
      </Button>
    {/snippet}
  </Modal>
</div>
