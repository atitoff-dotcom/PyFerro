<script lang="ts">
  import { onMount } from "svelte";

  interface Props {
    lang?: "ru" | "en";
    rpcClient: any;
    onnotify?: (msg: string, type: "success" | "error" | "info") => void;
  }

  let { lang = "ru", rpcClient, onnotify }: Props = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let isPinging = $state(false);
  let errorMsg = $state("");

  // Подразделы
  let activeSubTab = $state<"general" | "models" | "sitemap">("general");

  // Редактируемые параметры
  let siteName = $state("PyFerro Platform");
  let siteUrl = $state("http://localhost:8080");
  let defaultTitle = $state("Современное веб-приложение");
  let defaultDescription = $state("Высокопроизводительное SPA-приложение с реактивными WebSocket-каналами и нулевой задержкой.");
  let defaultOgImage = $state("");
  let enableSitemap = $state(true);
  let sitemapModels = $state<string[]>([]);
  let availableModels = $state<Array<{
    key: string;
    verbose_name: string;
    table_name: string;
    url_pattern: string;
    fields: Array<{ name: string; type: string; label: string; primary_key: boolean }>;
    relations: Array<{
      relation_name: string;
      fk_field: string;
      target_model: string;
      fields: Array<{ name: string; chip: string; label: string; type: string }>;
    }>;
  }>>([]);
  let indexnowKey = $state("");
  let botRoutesCount = $state(0);

  // Правила моделей
  interface BreadcrumbItem {
    title: string;
    url: string;
  }

  interface ModelRule {
    model_key: string;
    url_pattern: string;
    title_template: string;
    description_template: string;
    og_image_template: string;
    schema_type: "DiscussionForumPosting" | "Product" | "Article" | "WebPage";
    sitemap_enabled: boolean;
    sitemap_priority: number;
    sitemap_changefreq: string;
    breadcrumbs: BreadcrumbItem[];
  }

  let modelRules = $state<ModelRule[]>([]);
  let selectedRuleIndex = $state<number>(0);

  // Живой симулятор для моделей
  let modelRecords = $state<Array<{ id: any; label: string }>>([]);
  let selectedRecordId = $state<any>(null);
  let modelPreviewData = $state<any>(null);
  let isModelPreviewLoading = $state(false);

  // Вкладка интерактивного превью (Telegram / Google)
  let previewTab = $state<"telegram" | "google">("telegram");

  const t = $derived({
    headerTitle: lang === "ru" ? "Превью в соцсетях и Поисковая оптимизация" : "Social Previews & Search Engines",
    headerSubtitle: lang === "ru" ? "Настройка отображения ссылок в Telegram, VK, WhatsApp и индексации в Google/Яндекс" : "Configure Telegram/VK/WhatsApp card previews and search engine indexing",
    tabGeneral: lang === "ru" ? "💬 Общие и Соцсети" : "💬 General & Social",
    tabModels: lang === "ru" ? "⚡ Динамические правила моделей (No-Code)" : "⚡ Dynamic Model Rules (No-Code)",
    tabSitemap: lang === "ru" ? "🗺️ Карта сайта & IndexNow" : "🗺️ Sitemap & IndexNow",
    refreshBtn: lang === "ru" ? "Обновить" : "Refresh",
    applyBtn: lang === "ru" ? "Сохранить настройки онлайн" : "Save Settings Online",
    applying: lang === "ru" ? "Сохранение..." : "Saving...",
    sectionSocial: lang === "ru" ? "1. Превью ссылки при отправке в мессенджеры (Telegram, VK, WhatsApp)" : "1. Link Preview in Messengers (Telegram, VK, WhatsApp)",
    sectionSocialDesc: lang === "ru" ? "Когда вы или пользователи делитесь ссылкой в чате, мессенджер формирует привлекательную карточку" : "When you share a link in a chat, the messenger displays this visual preview card",
    siteNameLabel: lang === "ru" ? "Название проекта / сайта:" : "Project / Site Name:",
    siteUrlLabel: lang === "ru" ? "Базовый адрес сайта (URL):" : "Base Website URL:",
    titleLabel: lang === "ru" ? "Заголовок страницы (Title):" : "Page Title:",
    descLabel: lang === "ru" ? "Краткое описание (Description):" : "Short Description:",
    imageLabel: lang === "ru" ? "Ссылка на обложку / логотип (OG Image):" : "Cover / Logo Image URL (OG Image):",
    imagePlaceholder: "https://example.com/logo.png",
    sectionSitemap: lang === "ru" ? "2. Карта сайта для поисковиков (Sitemap.xml)" : "2. Search Engine Sitemap (Sitemap.xml)",
    sectionSitemapDesc: lang === "ru" ? "Помогает Яндексу и Google автоматически обходить и индексировать все публичные страницы" : "Helps Yandex and Google automatically discover and index all public URLs",
    enableSitemapLabel: lang === "ru" ? "Включить автоматическую генерацию /sitemap.xml" : "Enable automatic /sitemap.xml generation",
    includeModelsLabel: lang === "ru" ? "Включить страницы сущностей в sitemap:" : "Include entity pages in sitemap:",
    openSitemapLink: lang === "ru" ? "Открыть sitemap.xml ↗" : "Open sitemap.xml ↗",
    sectionIndexNow: lang === "ru" ? "3. Мгновенная индексация (IndexNow: Яндекс, Bing)" : "3. Instant Indexing (IndexNow: Yandex, Bing)",
    sectionIndexNowDesc: lang === "ru" ? "Позволяет поисковикам узнавать об изменениях за секунды, не дожидаясь обхода роботами" : "Notifies search engines within seconds of content creation without waiting for crawls",
    indexNowKeyLabel: lang === "ru" ? "API-ключ проверки IndexNow:" : "IndexNow Verification Key:",
    generateKeyBtn: lang === "ru" ? "Сгенерировать ключ" : "Generate Key",
    pingIndexNowBtn: lang === "ru" ? "⚡ Отправить страницы на обход прямо сейчас" : "⚡ Push URLs to IndexNow Now",
    pinging: lang === "ru" ? "Отправка..." : "Pushing...",
    livePreviewTitle: lang === "ru" ? "Живой симулятор внешнего вида" : "Live Visual Simulator",
    livePreviewDesc: lang === "ru" ? "Реагирует на изменение любого поля в реальном времени" : "Updates in real time as you edit the fields",
    saveSuccess: lang === "ru" ? "Настройки превью и поисковой оптимизации успешно сохранены!" : "Preview and SEO settings successfully saved!",
    pingSuccess: lang === "ru" ? "Запрос на мгновенную индексацию успешно передан поисковым системам!" : "Instant indexing request successfully sent to search engines!",
  });

  async function loadConfig() {
    isLoading = true;
    errorMsg = "";
    try {
      const cfg = await rpcClient.call("admin.seo_get_config");
      if (cfg) {
        siteName = cfg.site_name || "PyFerro Platform";
        siteUrl = cfg.site_url || "http://localhost:8080";
        defaultTitle = cfg.default_title || "Современное веб-приложение";
        defaultDescription = cfg.default_description || "Высокопроизводительное SPA-приложение.";
        defaultOgImage = cfg.default_og_image || "";
        enableSitemap = cfg.enable_sitemap !== undefined ? !!cfg.enable_sitemap : true;
        sitemapModels = cfg.sitemap_models || [];
        availableModels = cfg.available_models || [];
        indexnowKey = cfg.indexnow_key || "";
        botRoutesCount = cfg.bot_routes_count || 0;

        // Инициализируем правила моделей
        if (cfg.model_rules && cfg.model_rules.length > 0) {
          modelRules = cfg.model_rules;
        } else {
          // Создаем дефолтное правило для ветки форума или первой модели
          const forumMeta = availableModels.find(m => m.key === "ForumTopic" || m.table_name?.includes("forum_topic"));
          if (forumMeta) {
            modelRules = [
              {
                model_key: forumMeta.key,
                url_pattern: "/forum/{category.slug}/{slug}",
                title_template: "{title} — раздел «{category.name}» | Форум",
                description_template: "{first_post_text}",
                og_image_template: "",
                schema_type: "DiscussionForumPosting",
                sitemap_enabled: true,
                sitemap_priority: 0.9,
                sitemap_changefreq: "daily",
                breadcrumbs: [
                  { title: "Главная", url: "/" },
                  { title: "{category.name}", url: "/forum/{category.slug}" },
                  { title: "{title}", url: "" },
                ],
              },
            ];
          }
        }

        if (modelRules.length > 0) {
          await selectRule(0);
        }
      }
    } catch (e: any) {
      errorMsg = e.message || String(e);
    } finally {
      isLoading = false;
    }
  }

  async function selectRule(index: number) {
    selectedRuleIndex = index;
    if (modelRules[index]) {
      await loadModelRecords(modelRules[index].model_key);
    }
  }

  async function loadModelRecords(modelKey: string) {
    if (!modelKey) return;
    try {
      const records = await rpcClient.call("admin.seo_get_model_records", {
        model_key: modelKey,
        limit: 15,
      });
      modelRecords = records || [];
      if (modelRecords.length > 0) {
        selectedRecordId = modelRecords[0].id;
      } else {
        selectedRecordId = null;
      }
      await refreshModelPreview();
    } catch {
      modelRecords = [];
      await refreshModelPreview();
    }
  }

  async function refreshModelPreview() {
    if (modelRules.length === 0 || selectedRuleIndex < 0 || selectedRuleIndex >= modelRules.length) {
      modelPreviewData = null;
      return;
    }
    const rule = modelRules[selectedRuleIndex];
    isModelPreviewLoading = true;
    try {
      const res = await rpcClient.call("admin.seo_preview_model_rule", {
        model_key: rule.model_key,
        rule,
        sample_id: selectedRecordId,
      });
      modelPreviewData = res;
    } catch (e) {
      console.warn("Preview error:", e);
    } finally {
      isModelPreviewLoading = false;
    }
  }

  function addModelRule() {
    const defaultModel = availableModels.find(m => !modelRules.some(r => r.model_key === m.key)) || availableModels[0];
    const key = defaultModel ? defaultModel.key : "CustomModel";
    const newRule: ModelRule = {
      model_key: key,
      url_pattern: `/${key.toLowerCase()}s/{id}`,
      title_template: "{title}",
      description_template: "{description}",
      og_image_template: "",
      schema_type: "WebPage",
      sitemap_enabled: true,
      sitemap_priority: 0.8,
      sitemap_changefreq: "weekly",
      breadcrumbs: [
        { title: "Главная", url: "/" },
        { title: "{title}", url: "" },
      ],
    };
    modelRules = [...modelRules, newRule];
    selectRule(modelRules.length - 1);
  }

  function removeModelRule(idx: number) {
    modelRules = modelRules.filter((_, i) => i !== idx);
    if (selectedRuleIndex >= modelRules.length) {
      selectedRuleIndex = Math.max(0, modelRules.length - 1);
    }
    if (modelRules.length > 0) {
      selectRule(selectedRuleIndex);
    } else {
      modelPreviewData = null;
    }
  }

  function insertChip(targetField: "url_pattern" | "title_template" | "description_template" | "og_image_template", chip: string) {
    if (!modelRules[selectedRuleIndex]) return;
    const currentVal = modelRules[selectedRuleIndex][targetField] || "";
    modelRules[selectedRuleIndex][targetField] = currentVal ? `${currentVal} {${chip}}` : `{${chip}}`;
    refreshModelPreview();
  }

  function addBreadcrumbLevel() {
    if (!modelRules[selectedRuleIndex]) return;
    modelRules[selectedRuleIndex].breadcrumbs = [
      ...modelRules[selectedRuleIndex].breadcrumbs,
      { title: "{title}", url: "" },
    ];
    refreshModelPreview();
  }

  function removeBreadcrumbLevel(bIdx: number) {
    if (!modelRules[selectedRuleIndex]) return;
    modelRules[selectedRuleIndex].breadcrumbs = modelRules[selectedRuleIndex].breadcrumbs.filter((_, i) => i !== bIdx);
    refreshModelPreview();
  }

  async function saveConfig() {
    isSaving = true;
    try {
      await rpcClient.call("admin.seo_update_config", {
        site_name: siteName,
        site_url: siteUrl,
        default_title: defaultTitle,
        default_description: defaultDescription,
        default_og_image: defaultOgImage || null,
        enable_sitemap: enableSitemap,
        sitemap_models: sitemapModels,
        model_rules: modelRules,
        indexnow_key: indexnowKey || null,
      });
      if (onnotify) onnotify(t.saveSuccess, "success");
    } catch (e: any) {
      if (onnotify) onnotify(e.message || String(e), "error");
    } finally {
      isSaving = false;
    }
  }

  function toggleModelInSitemap(key: string) {
    if (sitemapModels.includes(key)) {
      sitemapModels = sitemapModels.filter(k => k !== key);
    } else {
      sitemapModels = [...sitemapModels, key];
    }
  }

  function generateRandomKey() {
    const chars = "abcdef0123456789";
    let key = "";
    for (let i = 0; i < 32; i++) {
      key += chars[Math.floor(Math.random() * chars.length)];
    }
    indexnowKey = key;
  }

  async function pushIndexNow() {
    if (!indexnowKey) {
      generateRandomKey();
    }
    isPinging = true;
    try {
      await rpcClient.call("admin.seo_ping_indexnow", {
        urls: [siteUrl + "/", siteUrl + "/showcase"],
      });
      if (onnotify) onnotify(t.pingSuccess, "success");
    } catch (e: any) {
      if (onnotify) onnotify(e.message || String(e), "error");
    } finally {
      isPinging = false;
    }
  }

  let activeModelMeta = $derived(() => {
    if (modelRules.length === 0 || selectedRuleIndex < 0 || selectedRuleIndex >= modelRules.length) return null;
    const rule = modelRules[selectedRuleIndex];
    return availableModels.find(m => m.key === rule.model_key) || null;
  });

  let displayDomain = $derived(() => {
    try {
      const u = new URL(siteUrl);
      return u.hostname;
    } catch {
      return "example.com";
    }
  });

  onMount(() => {
    loadConfig();
  });
</script>

<div class="flex-1 flex flex-col p-6 gap-6 overflow-y-auto">
  <!-- Верхняя шапка -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-xs">
    <div class="flex flex-col">
      <div class="flex items-center gap-2">
        <h1 class="text-lg font-bold text-foreground flex items-center gap-2">
          <span>🚀</span>
          <span>{t.headerTitle}</span>
        </h1>
        <span class="text-2xs font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
          No-Code Engine
        </span>
      </div>
      <p class="text-xs text-muted-foreground mt-0.5">{t.headerSubtitle}</p>
    </div>

    <div class="flex items-center gap-2">
      <button
        type="button"
        onclick={loadConfig}
        disabled={isLoading || isSaving}
        class="px-3 py-1.5 rounded-lg text-xs font-medium border border-border bg-card hover:bg-muted text-muted-foreground transition-colors cursor-pointer"
      >
        {t.refreshBtn}
      </button>

      <button
        type="button"
        onclick={saveConfig}
        disabled={isLoading || isSaving}
        class="px-4 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-xs flex items-center gap-2 cursor-pointer"
      >
        {#if isSaving}
          <span class="animate-spin text-xs">⏳</span>
          <span>{t.applying}</span>
        {:else}
          <span>💾</span>
          <span>{t.applyBtn}</span>
        {/if}
      </button>
    </div>
  </div>

  <!-- Вкладки подразделов (Общие / Динамические правила моделей / Sitemap) -->
  <div class="flex items-center gap-2 border-b border-border pb-2">
    <button
      type="button"
      onclick={() => (activeSubTab = "general")}
      class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer {activeSubTab === 'general' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
    >
      {t.tabGeneral}
    </button>
    <button
      type="button"
      onclick={() => (activeSubTab = "models")}
      class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 {activeSubTab === 'models' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
    >
      <span>{t.tabModels}</span>
      <span class="text-2xs px-1.5 py-0.2 rounded-full {activeSubTab === 'models' ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted-foreground/15 text-muted-foreground'}">
        {modelRules.length}
      </span>
    </button>
    <button
      type="button"
      onclick={() => (activeSubTab = "sitemap")}
      class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer {activeSubTab === 'sitemap' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
    >
      {t.tabSitemap}
    </button>
  </div>

  {#if isLoading}
    <div class="flex items-center justify-center p-12">
      <div class="flex items-center gap-3 text-muted-foreground text-sm font-medium">
        <span class="animate-spin text-lg">⏳</span>
        <span>Загрузка параметров поисковой оптимизации...</span>
      </div>
    </div>
  {:else if errorMsg}
    <div class="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-xs">
      {errorMsg}
    </div>
  {:else if activeSubTab === "general"}
    <!-- ВКЛАДКА 1: ОБЩИЕ ПАРАМЕТРЫ И СОЦСЕТИ -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      <!-- Левая колонка: форма параметров -->
      <div class="lg:col-span-7 flex flex-col gap-6">
        <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
          <div class="flex flex-col gap-1">
            <h2 class="text-sm font-bold text-foreground">{t.sectionSocial}</h2>
            <p class="text-2xs text-muted-foreground">{t.sectionSocialDesc}</p>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-2xs font-semibold text-muted-foreground mb-1">{t.siteNameLabel}</label>
              <input
                type="text"
                bind:value={siteName}
                placeholder="Например: Мой Магазин / Форум"
                class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground focus:ring-1 focus:ring-primary focus:outline-hidden"
              />
            </div>
            <div>
              <label class="block text-2xs font-semibold text-muted-foreground mb-1">{t.siteUrlLabel}</label>
              <input
                type="text"
                bind:value={siteUrl}
                placeholder="https://mysite.ru"
                class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-hidden"
              />
            </div>
          </div>

          <div>
            <label class="block text-2xs font-semibold text-muted-foreground mb-1">{t.titleLabel}</label>
            <input
              type="text"
              bind:value={defaultTitle}
              placeholder="Главный заголовок сайта при отправке ссылки..."
              class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-medium focus:ring-1 focus:ring-primary focus:outline-hidden"
            />
          </div>

          <div>
            <label class="block text-2xs font-semibold text-muted-foreground mb-1">{t.descLabel}</label>
            <textarea
              bind:value={defaultDescription}
              rows={3}
              placeholder="Краткое привлекательное описание..."
              class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground focus:ring-1 focus:ring-primary focus:outline-hidden resize-none"
            ></textarea>
          </div>

          <div>
            <label class="block text-2xs font-semibold text-muted-foreground mb-1">{t.imageLabel}</label>
            <input
              type="text"
              bind:value={defaultOgImage}
              placeholder={t.imagePlaceholder}
              class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-hidden"
            />
          </div>
        </div>
      </div>

      <!-- Правая колонка: симулятор превью -->
      <div class="lg:col-span-5 flex flex-col gap-4">
        <div class="flex items-center justify-between">
          <div class="flex flex-col">
            <h3 class="text-xs font-bold text-foreground">{t.livePreviewTitle}</h3>
            <span class="text-2xs text-muted-foreground">{t.livePreviewDesc}</span>
          </div>

          <div class="flex items-center bg-muted p-0.5 rounded-lg text-2xs font-semibold">
            <button
              type="button"
              onclick={() => (previewTab = "telegram")}
              class="px-2.5 py-1 rounded-md transition-colors cursor-pointer {previewTab === 'telegram' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}"
            >
              📱 Telegram
            </button>
            <button
              type="button"
              onclick={() => (previewTab = "google")}
              class="px-2.5 py-1 rounded-md transition-colors cursor-pointer {previewTab === 'google' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}"
            >
              🔍 Google / Яндекс
            </button>
          </div>
        </div>

        {#if previewTab === "telegram"}
          <div class="p-4 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Вид в чате Telegram:</div>
            <div class="max-w-[340px] bg-white dark:bg-slate-800 rounded-2xl rounded-tl-sm p-3 shadow-md border border-slate-200/80 dark:border-slate-700/80 flex flex-col gap-2">
              <div class="text-xs text-blue-600 dark:text-blue-400 font-mono break-all hover:underline cursor-pointer">
                {siteUrl}/
              </div>
              <div class="flex flex-col border-l-2 border-blue-500 pl-2.5 py-0.5 gap-1.5 bg-blue-50/40 dark:bg-blue-950/20 rounded-r-lg p-2">
                <span class="text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                  {siteName || "Сайт проекта"}
                </span>
                <span class="text-xs font-bold text-slate-900 dark:text-slate-100 leading-tight">
                  {defaultTitle || "Заголовок страницы"}
                </span>
                <p class="text-[11px] text-slate-600 dark:text-slate-300 line-clamp-3 leading-snug">
                  {defaultDescription || "Описание страницы появится здесь..."}
                </p>
                {#if defaultOgImage}
                  <div class="mt-1 w-full h-32 rounded-lg overflow-hidden bg-slate-200 dark:bg-slate-700">
                    <img src={defaultOgImage} alt="OpenGraph Preview" class="w-full h-full object-cover" />
                  </div>
                {:else}
                  <div class="mt-1 w-full h-24 rounded-lg bg-slate-200/80 dark:bg-slate-700/80 flex items-center justify-center text-slate-400 text-xs font-medium">
                    🖼️ [Логотип / Обложка]
                  </div>
                {/if}
                <div class="text-[10px] text-slate-400 mt-0.5 font-mono">{displayDomain()}</div>
              </div>
              <div class="text-[9px] text-slate-400 text-right flex items-center justify-end gap-1">
                <span>12:45</span>
                <span class="text-blue-500 font-bold">✓✓</span>
              </div>
            </div>
          </div>
        {:else}
          <div class="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex flex-col gap-2 font-sans">
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Сниппет в поисковике:</div>
            <div class="flex items-center gap-2">
              <div class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 font-bold flex items-center justify-center text-xs">Fe</div>
              <div class="flex flex-col leading-none">
                <span class="text-xs font-semibold text-slate-900 dark:text-slate-200">{siteName || "Сайт"}</span>
                <span class="text-[11px] text-slate-400 font-mono">{siteUrl}/</span>
              </div>
            </div>
            <a href="#preview" class="text-base text-blue-600 dark:text-blue-400 hover:underline font-medium leading-tight">
              {defaultTitle || "Заголовок страницы"} — {siteName || "PyFerro"}
            </a>
            <p class="text-xs text-slate-600 dark:text-slate-300 leading-snug line-clamp-2">
              {defaultDescription || "Описание страницы..."}
            </p>
          </div>
        {/if}
      </div>
    </div>
  {:else if activeSubTab === "models"}
    <!-- ВКЛАДКА 2: ДИНАМИЧЕСКИЕ ПРАВИЛА МОДЕЛЕЙ (NO-CODE SEO) -->
    <div class="flex flex-col gap-6">
      <!-- Архитектурная подсказка: почему и как это работает -->
      <div class="p-4 rounded-xl bg-card border border-primary/20 shadow-xs flex flex-col gap-2.5">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-base">💡</span>
            <h3 class="text-xs font-bold text-foreground">Архитектурная справка: многоуровневое SEO без кода в PyFerro</h3>
          </div>
          <span class="text-2xs font-semibold px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            Relational Introspection Active
          </span>
        </div>
        <p class="text-2xs text-muted-foreground leading-relaxed">
          PyFerro автоматически анализирует структуру базы данных и связи между таблицами (Foreign Keys).
          Например, для темы форума связь <code class="text-primary font-mono">category_id</code> позволяет прямо в шаблоне использовать поля категории через точку:
          <code class="text-primary font-mono">&#123;category.name&#125;</code> и <code class="text-primary font-mono">&#123;category.slug&#125;</code>.
          Хлебные крошки и Schema.org разметка генерируются на лету. Робот получает готовый HTML5, а люди — реактивное SPA!
        </p>
      </div>

      <!-- Конструктор правил моделей -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <!-- Список правил слева -->
        <div class="lg:col-span-4 flex flex-col gap-3">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-foreground">Сконфигурированные правила:</span>
            <button
              type="button"
              onclick={addModelRule}
              class="px-2.5 py-1 text-2xs font-semibold rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors flex items-center gap-1 cursor-pointer"
            >
              <span>+</span>
              <span>Добавить правило</span>
            </button>
          </div>

          <div class="flex flex-col gap-2">
            {#each modelRules as rule, idx}
              <div
                class="p-3 rounded-xl border transition-all cursor-pointer flex flex-col gap-1.5 {selectedRuleIndex === idx ? 'bg-card border-primary ring-1 ring-primary shadow-xs' : 'bg-card/60 border-border hover:border-border/80'}"
                onclick={() => selectRule(idx)}
              >
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold text-foreground">{rule.model_key}</span>
                  <div class="flex items-center gap-1">
                    <span class="text-[10px] font-mono px-1.5 py-0.2 rounded-md bg-muted text-muted-foreground">
                      {rule.schema_type}
                    </span>
                    <button
                      type="button"
                      onclick={(e) => { e.stopPropagation(); removeModelRule(idx); }}
                      class="text-muted-foreground hover:text-destructive p-1 rounded-md text-xs cursor-pointer"
                      title="Удалить правило"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                <span class="text-2xs font-mono text-muted-foreground truncate">{rule.url_pattern}</span>
              </div>
            {/each}

            {#if modelRules.length === 0}
              <div class="p-6 rounded-xl border border-dashed border-border text-center text-xs text-muted-foreground">
                Нет добавленных правил. Нажмите «+ Добавить правило», чтобы настроить SEO для любой таблицы.
              </div>
            {/if}
          </div>
        </div>

        <!-- Редактор выбранного правила по центру/справа -->
        {#if modelRules[selectedRuleIndex]}
          {@const rule = modelRules[selectedRuleIndex]}
          {@const meta = activeModelMeta()}
          <div class="lg:col-span-8 flex flex-col gap-5">
            <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
              <!-- Заголовок карточки -->
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-bold text-foreground">Правило для сущности:</span>
                  <select
                    bind:value={rule.model_key}
                    onchange={() => { loadModelRecords(rule.model_key); }}
                    class="px-2.5 py-1 text-xs rounded-lg border border-input bg-background text-foreground font-semibold"
                  >
                    {#each availableModels as m}
                      <option value={m.key}>{m.verbose_name || m.key} ({m.table_name})</option>
                    {/each}
                  </select>
                </div>

                <div class="flex items-center gap-2">
                  <label class="text-2xs text-muted-foreground font-semibold flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      bind:checked={rule.sitemap_enabled}
                      onchange={refreshModelPreview}
                      class="rounded text-primary focus:ring-primary"
                    />
                    <span>Включать в sitemap.xml</span>
                  </label>
                </div>
              </div>

              <!-- Доступные переменные (чипсы быстрой вставки) -->
              {#if meta}
                <div class="p-3 rounded-lg bg-muted/40 border border-border/60 flex flex-col gap-2">
                  <div class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    Доступные поля сущности (кликните, чтобы вставить в шаблон):
                  </div>
                  <div class="flex flex-wrap gap-1.5">
                    {#each meta.fields as f}
                      <button
                        type="button"
                        onclick={() => insertChip("title_template", f.name)}
                        class="px-2 py-0.5 rounded-md bg-background border border-border text-2xs font-mono text-foreground hover:border-primary hover:text-primary transition-colors cursor-pointer"
                        title="Вставить {f.name}"
                      >
                        +{'{' + f.name + '}'}
                      </button>
                    {/each}
                    {#each meta.relations as rel}
                      {#each rel.fields as rf}
                        <button
                          type="button"
                          onclick={() => insertChip("title_template", rf.chip)}
                          class="px-2 py-0.5 rounded-md bg-primary/10 border border-primary/30 text-2xs font-mono text-primary hover:bg-primary/20 transition-colors cursor-pointer"
                          title="{rf.label}"
                        >
                          +{'{' + rf.chip + '}'}
                        </button>
                      {/each}
                    {/each}
                  </div>
                </div>
              {/if}

              <!-- URL Pattern -->
              <div>
                <div class="flex items-center justify-between mb-1">
                  <label class="text-2xs font-semibold text-muted-foreground">Шаблон адреса страницы (URL Pattern):</label>
                  <span class="text-[10px] text-muted-foreground">Например: /forum/{'{category.slug}'}/{'{slug}'}</span>
                </div>
                <input
                  type="text"
                  bind:value={rule.url_pattern}
                  oninput={refreshModelPreview}
                  placeholder="/forum/{'{category.slug}'}/{'{slug}'}"
                  class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-hidden"
                />
              </div>

              <!-- Title & Description Templates -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-2xs font-semibold text-muted-foreground mb-1">Шаблон Title (Заголовок):</label>
                  <input
                    type="text"
                    bind:value={rule.title_template}
                    oninput={refreshModelPreview}
                    placeholder="{'{title}'} — {'{category.name}'}"
                    class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground focus:ring-1 focus:ring-primary focus:outline-hidden"
                  />
                </div>
                <div>
                  <label class="block text-2xs font-semibold text-muted-foreground mb-1">Тип разметки Schema.org:</label>
                  <select
                    bind:value={rule.schema_type}
                    onchange={refreshModelPreview}
                    class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-medium"
                  >
                    <option value="DiscussionForumPosting">💬 Ветка форума (DiscussionForumPosting)</option>
                    <option value="Product">🛍️ Карточка товара (Product)</option>
                    <option value="Article">📰 Статья / Новость (Article)</option>
                    <option value="WebPage">📄 Веб-страница (WebPage)</option>
                  </select>
                </div>
              </div>

              <div>
                <label class="block text-2xs font-semibold text-muted-foreground mb-1">Шаблон Description (Описание):</label>
                <textarea
                  bind:value={rule.description_template}
                  oninput={refreshModelPreview}
                  rows={2}
                  placeholder="{'{first_post_text}'} или {'{description}'}"
                  class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground focus:ring-1 focus:ring-primary focus:outline-hidden resize-none"
                ></textarea>
              </div>

              <!-- Цепочка хлебных крошек (Breadcrumbs) -->
              <div class="flex flex-col gap-2 pt-2 border-t border-border">
                <div class="flex items-center justify-between">
                  <div class="flex flex-col">
                    <span class="text-xs font-bold text-foreground">Цепочка хлебных крошек (Breadcrumbs):</span>
                    <span class="text-[10px] text-muted-foreground">Формирует путь и Schema.org BreadcrumbList для сниппета</span>
                  </div>
                  <button
                    type="button"
                    onclick={addBreadcrumbLevel}
                    class="px-2 py-1 text-2xs font-semibold rounded-md bg-muted text-foreground hover:bg-muted/80 cursor-pointer"
                  >
                    + Добавить уровень
                  </button>
                </div>

                <div class="flex flex-col gap-1.5">
                  {#each rule.breadcrumbs as bc, bIdx}
                    <div class="flex items-center gap-2">
                      <span class="text-2xs font-mono text-muted-foreground w-6">#{bIdx + 1}</span>
                      <input
                        type="text"
                        bind:value={bc.title}
                        oninput={refreshModelPreview}
                        placeholder="Название (напр. {'{category.name}'})"
                        class="flex-1 px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground focus:ring-1 focus:ring-primary focus:outline-hidden"
                      />
                      <input
                        type="text"
                        bind:value={bc.url}
                        oninput={refreshModelPreview}
                        placeholder="URL (напр. /forum/{'{category.slug}'})"
                        class="flex-1 px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-hidden"
                      />
                      <button
                        type="button"
                        onclick={() => removeBreadcrumbLevel(bIdx)}
                        class="text-muted-foreground hover:text-destructive p-1 rounded-md text-xs cursor-pointer"
                      >
                        ✕
                      </button>
                    </div>
                  {/each}
                </div>
              </div>
            </div>

            <!-- Живой симулятор конкретной записи -->
            <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
                <div class="flex flex-col">
                  <h4 class="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <span>🔬</span>
                    <span>Живая проверка с реальной записью из БД:</span>
                  </h4>
                  <span class="text-2xs text-muted-foreground">Выберите конкретную строку из таблицы для предпросмотра</span>
                </div>

                <div class="flex items-center gap-2">
                  <select
                    bind:value={selectedRecordId}
                    onchange={refreshModelPreview}
                    class="px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground max-w-[260px] truncate"
                  >
                    {#each modelRecords as rec}
                      <option value={rec.id}>#{rec.id}: {rec.label}</option>
                    {/each}
                    {#if modelRecords.length === 0}
                      <option value={null}>Демонстрационный мок (таблица пуста)</option>
                    {/if}
                  </select>
                </div>
              </div>

              {#if isModelPreviewLoading}
                <div class="py-6 flex items-center justify-center text-xs text-muted-foreground gap-2">
                  <span class="animate-spin">⏳</span>
                  <span>Генерация превью записи...</span>
                </div>
              {:else if modelPreviewData}
                <div class="flex flex-col gap-4">
                  <!-- Карточка превью -->
                  <div class="p-4 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                    <div class="max-w-[420px] bg-white dark:bg-slate-800 rounded-2xl rounded-tl-sm p-3 shadow-md border border-slate-200/80 dark:border-slate-700/80 flex flex-col gap-2">
                      <div class="text-xs text-blue-600 dark:text-blue-400 font-mono break-all hover:underline cursor-pointer">
                        {siteUrl}{modelPreviewData.url}
                      </div>
                      <div class="flex flex-col border-l-2 border-blue-500 pl-2.5 py-0.5 gap-1.5 bg-blue-50/40 dark:bg-blue-950/20 rounded-r-lg p-2">
                        <span class="text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                          {siteName}
                        </span>
                        <span class="text-xs font-bold text-slate-900 dark:text-slate-100 leading-tight">
                          {modelPreviewData.title}
                        </span>
                        <p class="text-[11px] text-slate-600 dark:text-slate-300 line-clamp-3 leading-snug">
                          {modelPreviewData.description}
                        </p>
                        {#if modelPreviewData.og_image}
                          <div class="mt-1 w-full h-32 rounded-lg overflow-hidden bg-slate-200 dark:bg-slate-700">
                            <img src={modelPreviewData.og_image} alt="OG" class="w-full h-full object-cover" />
                          </div>
                        {/if}
                        <div class="text-[10px] text-slate-400 mt-0.5 font-mono">{displayDomain()}</div>
                      </div>
                    </div>
                  </div>

                  <!-- Хлебные крошки и ссылка проверки ботом -->
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-2xs">
                    <div class="p-3 rounded-lg bg-muted/40 border border-border/60 flex flex-col gap-1">
                      <span class="font-bold text-foreground">Хлебные крошки для поисковика:</span>
                      <div class="flex flex-wrap items-center gap-1 font-medium text-primary">
                        {#each modelPreviewData.breadcrumbs as bc, i}
                          <span>{bc.title}</span>
                          {#if i < modelPreviewData.breadcrumbs.length - 1}
                            <span class="text-muted-foreground/40">›</span>
                          {/if}
                        {/each}
                      </div>
                    </div>

                    <div class="p-3 rounded-lg bg-muted/40 border border-border/60 flex flex-col gap-1">
                      <span class="font-bold text-foreground">Проверка роботом в браузере:</span>
                      <a
                        href="{siteUrl}{modelPreviewData.url}?bot=1"
                        target="_blank"
                        rel="noreferrer"
                        class="text-primary hover:underline font-mono truncate"
                      >
                        {siteUrl}{modelPreviewData.url}?bot=1 ↗
                      </a>
                    </div>
                  </div>
                </div>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    </div>
  {:else if activeSubTab === "sitemap"}
    <!-- ВКЛАДКА 3: SITEMAP & INDEXNOW -->
    <div class="flex flex-col gap-6">
      <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
        <div class="flex items-center justify-between border-b border-border pb-3">
          <div class="flex flex-col">
            <h2 class="text-sm font-bold text-foreground">{t.sectionSitemap}</h2>
            <p class="text-2xs text-muted-foreground">{t.sectionSitemapDesc}</p>
          </div>
          <a
            href="{siteUrl}/sitemap.xml"
            target="_blank"
            rel="noreferrer"
            class="text-xs font-semibold text-primary hover:underline"
          >
            {t.openSitemapLink}
          </a>
        </div>

        <label class="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer">
          <input
            type="checkbox"
            bind:checked={enableSitemap}
            class="rounded text-primary focus:ring-primary"
          />
          <span>{t.enableSitemapLabel}</span>
        </label>

        <div class="flex flex-col gap-2 pt-2">
          <span class="text-2xs font-semibold text-muted-foreground">{t.includeModelsLabel}</span>
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {#each availableModels as m}
              <label class="flex items-center gap-2 p-2.5 rounded-lg border border-border hover:bg-muted/40 cursor-pointer text-xs font-medium text-foreground">
                <input
                  type="checkbox"
                  checked={sitemapModels.includes(m.key)}
                  onchange={() => toggleModelInSitemap(m.key)}
                  class="rounded text-primary focus:ring-primary"
                />
                <div class="flex flex-col leading-tight">
                  <span class="font-semibold">{m.verbose_name || m.key}</span>
                  <span class="text-[10px] text-muted-foreground font-mono">{m.url_pattern}</span>
                </div>
              </label>
            {/each}
          </div>
        </div>
      </div>

      <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
        <div class="flex flex-col gap-1 border-b border-border pb-3">
          <h2 class="text-sm font-bold text-foreground">{t.sectionIndexNow}</h2>
          <p class="text-2xs text-muted-foreground">{t.sectionIndexNowDesc}</p>
        </div>

        <div class="flex flex-col gap-3">
          <div>
            <label class="block text-2xs font-semibold text-muted-foreground mb-1">{t.indexNowKeyLabel}</label>
            <div class="flex items-center gap-2">
              <input
                type="text"
                bind:value={indexnowKey}
                placeholder="Сгенерируйте или введите ключ..."
                class="flex-1 px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-hidden"
              />
              <button
                type="button"
                onclick={generateRandomKey}
                class="px-3 py-2 text-xs font-semibold rounded-lg bg-muted hover:bg-muted/80 text-foreground cursor-pointer"
              >
                {t.generateKeyBtn}
              </button>
            </div>
          </div>

          <div class="pt-2">
            <button
              type="button"
              onclick={pushIndexNow}
              disabled={isPinging}
              class="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition-colors flex items-center gap-2 cursor-pointer"
            >
              {#if isPinging}
                <span class="animate-spin">⏳</span>
                <span>{t.pinging}</span>
              {:else}
                <span>{t.pingIndexNowBtn}</span>
              {/if}
            </button>
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>
