<script lang="ts">
  import { onMount } from "svelte";
  import Prism from "prismjs";
  import "prismjs/components/prism-markup-templating.js";
  import "prismjs/components/prism-django.js";
  interface Props {
    lang?: "ru" | "en";
    rpcClient: any;
    onnotify?: (msg: string, type: "success" | "error" | "info") => void;
  }

  let { lang = "ru", rpcClient, onnotify }: Props = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let isPinging = $state(false);
  let isPreviewLoading = $state(false);
  let isApplyingPreset = $state(false);
  let showPresetsModal = $state(false);
  let errorMsg = $state("");

  // Общие настройки сайта
  let siteName = $state("PyFerro Platform");
  let siteUrl = $state("http://localhost:8080");
  let defaultOgImage = $state("");
  let indexnowKey = $state("");

  interface StructurePreset {
    key: string;
    title: string;
    description: string;
    icon: string;
  }

  let availablePresets = $state<StructurePreset[]>([]);

  // Дерево сайта
  // Дерево сайта
  interface SiteTreeNode {
    id: string;
    title: string;
    url_pattern: string;
    node_type?: "static" | "collection" | "detail";
    template?: string;
    meta_title: string;
    meta_description: string;
    og_image: string;
    schema_type: string;
    model_key?: string | null;
    children_links_mode?: string;
    item_link_pattern?: string | null;
    item_title_pattern?: string | null;
    item_desc_pattern?: string | null;
    filter_field?: string | null;
    filter_parent_param?: string | null;
    sitemap_enabled?: boolean;
    sitemap_priority?: number;
    sitemap_changefreq?: string;
    children: SiteTreeNode[];
  }

  let siteTree = $state<SiteTreeNode>({
    id: "root",
    title: "Главная страница",
    url_pattern: "/",
    node_type: "static",
    template: "",
    meta_title: "PyFerro Platform",
    meta_description: "Современное реактивное веб-приложение",
    og_image: "",
    schema_type: "WebPage",
    sitemap_enabled: true,
    sitemap_priority: 1.0,
    sitemap_changefreq: "daily",
    children: []
  });

  let selectedNodeId = $state<string>("root");
  let availableModels = $state<Array<{
    key: string;
    verbose_name: string;
    table_name: string;
    fields: Array<{ name: string; type: string; label: string; primary_key: boolean }>;
    relations: Array<{
      relation_name: string;
      fk_field: string;
      target_model: string;
      fields: Array<{ name: string; chip: string; label: string; type: string }>;
    }>;
  }>>([]);

  // Превью
  let previewTab = $state<"telegram" | "google" | "robot">("telegram");
  let previewData = $state<{
    title?: string;
    description?: string;
    url?: string;
    og_image?: string;
    schema_type?: string;
    breadcrumbs?: Array<{ title: string; url: string }>;
    body_html?: string;
  } | null>(null);

  // Валидация и подсветка шаблона Jinja2
  let templateError = $state<string | null>(null);
  let templateValid = $state<boolean>(true);
  let showModelSelectorForLoop = $state<boolean>(false);
  let editorMode = $state<"highlight" | "plain">("highlight");
  let preElement = $state<HTMLPreElement | null>(null);
  let textareaElement = $state<HTMLTextAreaElement | null>(null);

  let highlightedTemplate = $derived.by(() => {
    const raw = currentNode?.template || "";
    if (!raw) return "";
    try {
      return Prism.highlight(raw, Prism.languages.django, "django");
    } catch {
      return raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
  });

  function syncScroll(e?: Event) {
    if (textareaElement && preElement) {
      preElement.scrollTop = textareaElement.scrollTop;
      preElement.scrollLeft = textareaElement.scrollLeft;
    }
  }

  $effect(() => {
    if (highlightedTemplate !== undefined && preElement && textareaElement) {
      requestAnimationFrame(() => {
        if (preElement && textareaElement) {
          preElement.scrollTop = textareaElement.scrollTop;
          preElement.scrollLeft = textareaElement.scrollLeft;
        }
      });
    }
  });

  function handleEditorKeydown(e: KeyboardEvent) {
    if (e.key === "Tab") {
      e.preventDefault();
      const textarea = e.currentTarget as HTMLTextAreaElement;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const val = textarea.value;
      textarea.value = val.substring(0, start) + "  " + val.substring(end);
      textarea.selectionStart = textarea.selectionEnd = start + 2;
      if (currentNode) {
        currentNode.template = textarea.value;
      }
      triggerTemplateValidationDebounced();
      triggerPreviewDebounced();
    }
  }

  // Фокусированное поле для вставки чипсов
  let activeField = $state<"meta_title" | "meta_description" | "url_pattern" | "template" | "item_link_pattern" | "item_title_pattern">("template");
  // Тексты интерфейса
  const t = $derived({
    headerTitle: lang === "ru" ? "Структура сайта и SEO (Универсальное дерево)" : "Site Tree & SEO Structure",
    headerSubtitle: lang === "ru" ? "Управление иерархией страниц, сквозные переходы для роботов и живой предпросмотр" : "Manage page hierarchy, crawler link traversal, and rich snippet previews",
    refreshBtn: lang === "ru" ? "Обновить" : "Refresh",
    saveBtn: lang === "ru" ? "Сохранить дерево" : "Save Site Tree",
    saving: lang === "ru" ? "Сохранение..." : "Saving...",
    presetsBtn: lang === "ru" ? "✨ Шаблоны структуры" : "✨ Structure Presets",
    sitemapLink: lang === "ru" ? "Открыть sitemap.xml ↗" : "Open sitemap.xml ↗",
    indexnowBtn: lang === "ru" ? "Пинг IndexNow ⚡" : "Ping IndexNow ⚡",
    treeTitle: lang === "ru" ? "Иерархия страниц сайта" : "Page Hierarchy Tree",
    treeSubtitle: lang === "ru" ? "Нажмите на узел для редактирования" : "Click a node to inspect and edit",
    addNodeBtn: lang === "ru" ? "+ Добавить подраздел" : "+ Add Child Node",
    deleteNodeBtn: lang === "ru" ? "Удалить узел" : "Delete Node",
    inspectorTitle: lang === "ru" ? "Настройки узла:" : "Node Settings:",
    typeStatic: lang === "ru" ? "📄 Статическая" : "📄 Static Page",
    typeCollection: lang === "ru" ? "📁 Раздел / Каталог" : "📁 Collection Hub",
    typeDetail: lang === "ru" ? "🏷️ Карточка записи" : "🏷️ Detail Page",
    previewTitle: lang === "ru" ? "Живой симулятор внешнего вида" : "Live Visual Simulator",
    tabTelegram: lang === "ru" ? "💬 Telegram / Соцсети" : "💬 Social Preview",
    tabGoogle: lang === "ru" ? "🔍 Поисковик (Google/Яндекс)" : "🔍 Search Snippet",
    tabRobot: lang === "ru" ? "🤖 Исходный HTML" : "🤖 Raw HTML",
    testBotLink: lang === "ru" ? "Проверить эту страницу ботом в новой вкладке (?bot=1) ↗" : "Test as bot in new tab (?bot=1) ↗",
  });

  // Вспомогательный поиск узла и цепочки родителей
  function findNodeAndParents(root: SiteTreeNode, targetId: string, parents: SiteTreeNode[] = []): { node: SiteTreeNode; parents: SiteTreeNode[] } | null {
    if (root.id === targetId) {
      return { node: root, parents };
    }
    for (const child of root.children || []) {
      const res = findNodeAndParents(child, targetId, [...parents, root]);
      if (res) return res;
    }
    return null;
  }

  let currentSelection = $derived.by(() => {
    return findNodeAndParents(siteTree, selectedNodeId) || { node: siteTree, parents: [] };
  });

  let currentNode = $derived(currentSelection.node);
  let currentParents = $derived(currentSelection.parents);

  let currentModelMeta = $derived.by(() => {
    if (!currentNode || !currentNode.model_key) return null;
    return availableModels.find(m => m.key === currentNode.model_key) || null;
  });

  let immediateParent = $derived.by(() => {
    if (!currentParents || currentParents.length === 0) return null;
    return currentParents[currentParents.length - 1];
  });

  let parentModelMeta = $derived.by(() => {
    if (!immediateParent || !immediateParent.model_key) return null;
    return availableModels.find(m => m.key === immediateParent.model_key) || null;
  });
  // Загрузка дерева с бэкенда
  async function loadTree() {
    isLoading = true;
    errorMsg = "";
    try {
      const res = await rpcClient.call("admin.seo_get_tree");
      if (res) {
        if (res.tree) siteTree = res.tree;
        if (res.site_url) siteUrl = res.site_url;
        if (res.site_name) siteName = res.site_name;
        if (res.default_og_image) defaultOgImage = res.default_og_image;
        if (res.indexnow_key) indexnowKey = res.indexnow_key;
        if (res.available_models) availableModels = res.available_models;
        if (res.presets) availablePresets = res.presets;
        await refreshPreview();
      }
    } catch (e: any) {
      errorMsg = e.message || String(e);
    } finally {
      isLoading = false;
    }
  }

  // Применение универсального пресета
  async function applyPreset(presetKey: string) {
    isApplyingPreset = true;
    try {
      const res = await rpcClient.call("admin.seo_apply_preset", { preset_key: presetKey });
      if (res && res.tree) {
        siteTree = res.tree;
        selectedNodeId = "root";
        showPresetsModal = false;
        if (onnotify) onnotify(res.message || "Шаблон применен!", "success");
        await refreshPreview();
      }
    } catch (e: any) {
      if (onnotify) onnotify(e.message || String(e), "error");
    } finally {
      isApplyingPreset = false;
    }
  }

  // Сохранение дерева
  async function saveTree() {
    isSaving = true;
    try {
      await rpcClient.call("admin.seo_save_tree", {
        tree: siteTree,
        site_url: siteUrl,
        site_name: siteName,
        indexnow_key: indexnowKey
      });
      if (onnotify) onnotify(lang === "ru" ? "Дерево сайта успешно сохранено!" : "Site tree saved successfully!", "success");
      await refreshPreview();
    } catch (e: any) {
      const err = e.message || String(e);
      if (onnotify) onnotify(err, "error");
    } finally {
      isSaving = false;
    }
  }

  // Обновление живого превью
  let previewTimer: any = null;
  function triggerPreviewDebounced() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 300);
  }

  async function refreshPreview() {
    if (!currentNode) return;
    isPreviewLoading = true;
    try {
      const res = await rpcClient.call("admin.seo_preview_tree_node", {
        node: currentNode,
        parents: currentParents,
      });
      previewData = res;
    } catch (e) {
      console.warn("Preview error:", e);
    } finally {
      isPreviewLoading = false;
    }
  }

  // Добавление дочернего узла к текущему
  function addChildNode() {
    if (!currentNode) return;
    const newId = "node_" + Math.random().toString(36).substr(2, 6);
    const parentUrl = currentNode.url_pattern === "/" ? "" : currentNode.url_pattern;

    const newNode: SiteTreeNode = {
      id: newId,
      title: "Новый подраздел",
      url_pattern: `${parentUrl}/page`,
      node_type: "static",
      meta_title: "Новый раздел",
      meta_description: "Описание нового раздела",
      og_image: "",
      schema_type: "WebPage",
      sitemap_enabled: true,
      sitemap_priority: 0.7,
      sitemap_changefreq: "weekly",
      children: []
    };

    if (!currentNode.children) currentNode.children = [];
    currentNode.children.push(newNode);
    selectedNodeId = newId;
    triggerPreviewDebounced();
  }

  // Удаление узла
  function deleteNode(targetId: string) {
    if (targetId === "root") return;

    function removeRecursive(parent: SiteTreeNode): boolean {
      if (!parent.children) return false;
      const idx = parent.children.findIndex(c => c.id === targetId);
      if (idx !== -1) {
        parent.children.splice(idx, 1);
        return true;
      }
      for (const child of parent.children) {
        if (removeRecursive(child)) return true;
      }
      return false;
    }

    if (removeRecursive(siteTree)) {
      selectedNodeId = "root";
      triggerPreviewDebounced();
      if (onnotify) onnotify(lang === "ru" ? "Узел удален" : "Node deleted", "info");
    }
  }

  // Валидация шаблона Jinja2
  let validateTimeout: any = null;
  function triggerTemplateValidationDebounced() {
    clearTimeout(validateTimeout);
    validateTimeout = setTimeout(validateTemplate, 350);
  }

  async function validateTemplate() {
    if (!currentNode || !currentNode.template || !currentNode.template.trim()) {
      templateError = null;
      templateValid = true;
      return;
    }
    try {
      const res = await rpcClient.call("admin.seo_validate_template", {
        template: currentNode.template
      });
      if (res.valid) {
        templateError = null;
        templateValid = true;
      } else {
        templateError = res.error || "Синтаксическая ошибка в шаблоне";
        templateValid = false;
      }
    } catch (e: any) {
      templateError = e.message || String(e);
      templateValid = false;
    }
  }

  // Вставка переменной-чипса в активное поле
  // Вставка переменной-чипса в активное поле
  function insertChip(tokenExpr: string) {
    if (!currentNode) return;
    if (activeField === "url_pattern" || activeField === "item_link_pattern") {
      const urlVar = tokenExpr.replace(/^record\./, "");
      const cur = currentNode[activeField] || "";
      const sep = cur.endsWith("/") || cur === "" ? "" : "/";
      currentNode[activeField] = cur + sep + "{" + urlVar + "}";
    } else if (activeField === "template") {
      const token = `{{ ${tokenExpr} }}`;
      currentNode.template = (currentNode.template || "") + (currentNode.template ? " " : "") + token;
      triggerTemplateValidationDebounced();
    } else if (activeField === "meta_title") {
      currentNode.meta_title = (currentNode.meta_title || "") + (currentNode.meta_title ? " " : "") + "{{ " + tokenExpr + " }}";
    } else if (activeField === "meta_description") {
      currentNode.meta_description = (currentNode.meta_description || "") + (currentNode.meta_description ? " " : "") + "{{ " + tokenExpr + " }}";
    } else if (activeField === "item_title_pattern") {
      const cleanVar = tokenExpr.replace(/^record\./, "");
      currentNode.item_title_pattern = (currentNode.item_title_pattern || "") + (currentNode.item_title_pattern ? " " : "") + "{" + cleanVar + "}";
    }
    triggerPreviewDebounced();
  }

  // Вставка цикла перебора по выбранной таблице
  function insertTemplateLoop(modelKey: string, verboseName?: string) {
    if (!currentNode) return;
    showModelSelectorForLoop = false;
    const nameStr = verboseName || modelKey;
    const loopSnippet = `\n<h2>${nameStr}:</h2>\n<ul>\n{% for item in ${modelKey} %}\n  <li><a href="/.../{{ item.slug }}">{{ item.title or item.name }}</a></li>\n{% endfor %}\n</ul>\n`;
    currentNode.template = (currentNode.template || "") + loopSnippet;
    triggerTemplateValidationDebounced();
    triggerPreviewDebounced();
  }

  // Вставка базового каркаса страницы
  function insertStarterTemplate() {
    if (!currentNode) return;
    let snippet = `<h1>{{ title }}</h1>\n<p>{{ description }}</p>\n`;
    if (availableModels.length > 0) {
      const first = availableModels[0];
      snippet += `\n<h2>${first.verbose_name || first.key}:</h2>\n<ul>\n{% for item in ${first.key} %}\n  <li><a href="/.../{{ item.slug }}">{{ item.title or item.name }}</a></li>\n{% endfor %}\n</ul>\n`;
    }
    currentNode.template = snippet;
    triggerTemplateValidationDebounced();
    triggerPreviewDebounced();
  }

  // Отправка в IndexNow
  async function pingIndexNow() {
    isPinging = true;
    try {
      const res = await rpcClient.call("admin.seo_ping_indexnow");
      if (onnotify) onnotify(res.message || "IndexNow ping sent!", "success");
    } catch (e: any) {
      if (onnotify) onnotify(e.message || String(e), "error");
    } finally {
      isPinging = false;
    }
  }

  let displayDomain = $derived(() => {
    try {
      return new URL(siteUrl).hostname;
    } catch {
      return "example.com";
    }
  });

  onMount(() => {
    loadTree();
  });
</script>

<div class="flex-1 flex flex-col p-6 gap-6 overflow-y-auto">
  <!-- Верхняя шапка -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-xs">
    <div class="flex flex-col">
      <div class="flex items-center gap-2">
        <h1 class="text-lg font-bold text-foreground flex items-center gap-2">
          <span>🌲</span>
          <span>{t.headerTitle}</span>
        </h1>
        <span class="text-2xs font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          Universal Tree Engine
        </span>
      </div>
      <p class="text-xs text-muted-foreground mt-0.5">{t.headerSubtitle}</p>
    </div>

    <div class="flex items-center gap-2 flex-wrap">
      <button
        type="button"
        onclick={() => showPresetsModal = true}
        class="px-3 py-1.5 rounded-lg text-xs font-semibold text-primary hover:bg-primary/10 border border-primary/30 transition-colors flex items-center gap-1.5 cursor-pointer"
      >
        <span>{t.presetsBtn}</span>
      </button>

      <a
        href="/sitemap.xml"
        target="_blank"
        rel="noreferrer"
        class="px-3 py-1.5 rounded-lg text-xs font-semibold text-primary hover:underline border border-border bg-card hover:bg-muted transition-colors flex items-center gap-1.5"
      >
        <span>🗺️</span>
        <span>{t.sitemapLink}</span>
      </a>

      <a
        href="/?bot=1"
        target="_blank"
        rel="noreferrer"
        class="px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-600 dark:text-emerald-400 hover:underline border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 transition-colors flex items-center gap-1.5"
        title="Открыть сайт глазами поискового робота (Яндекс / Google)"
      >
        <span>🤖</span>
        <span>Просмотр как бот ↗</span>
      </a>
      <button
        type="button"
        onclick={pingIndexNow}
        disabled={isPinging}
        class="px-3 py-1.5 rounded-lg text-xs font-medium border border-border bg-card hover:bg-muted text-foreground transition-colors cursor-pointer flex items-center gap-1.5"
      >
        <span>⚡</span>
        <span>{isPinging ? "Пинг..." : t.indexnowBtn}</span>
      </button>

      <button
        type="button"
        onclick={loadTree}
        disabled={isLoading || isSaving}
        class="px-3 py-1.5 rounded-lg text-xs font-medium border border-border bg-card hover:bg-muted text-muted-foreground transition-colors cursor-pointer"
      >
        {t.refreshBtn}
      </button>

      <button
        type="button"
        onclick={saveTree}
        disabled={isLoading || isSaving}
        class="px-4 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-xs flex items-center gap-2 cursor-pointer"
      >
        {#if isSaving}
          <span class="animate-spin text-xs">⏳</span>
          <span>{t.saving}</span>
        {:else}
          <span>💾</span>
          <span>{t.saveBtn}</span>
        {/if}
      </button>
    </div>
  </div>

  {#if isLoading}
    <div class="flex items-center justify-center p-16">
      <div class="flex items-center gap-3 text-muted-foreground text-sm font-medium">
        <span class="animate-spin text-xl">⏳</span>
        <span>Загрузка структуры дерева сайта...</span>
      </div>
    </div>
  {:else if errorMsg}
    <div class="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-xs">
      {errorMsg}
    </div>
  {:else}
    <!-- ОСНОВНАЯ РАБОЧАЯ ОБЛАСТЬ: 2 КОЛОНКИ -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      <!-- ЛЕВАЯ КОЛОНКА (5 колонок): ДЕРЕВО САЙТА И ОБЩИЕ НАСТРОЙКИ -->
      <div class="lg:col-span-5 flex flex-col gap-5">
        <div class="p-4 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-3">
          <div class="flex items-center justify-between border-b border-border pb-2.5">
            <div class="flex flex-col">
              <span class="text-xs font-bold text-foreground">{t.treeTitle}</span>
              <span class="text-2xs text-muted-foreground">{t.treeSubtitle}</span>
            </div>
            <button
              type="button"
              onclick={addChildNode}
              class="px-2.5 py-1 text-2xs font-semibold rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors flex items-center gap-1 cursor-pointer"
            >
              <span>+</span>
              <span>Добавить узел</span>
            </button>
          </div>

          <!-- Рекурсивный рендер узлов дерева -->
          <div class="flex flex-col gap-1.5">
            {#snippet renderTreeNode(node: SiteTreeNode, depth: number)}
              <div
                class="flex items-center justify-between p-2 rounded-lg border transition-all cursor-pointer {selectedNodeId === node.id ? 'bg-primary/10 border-primary ring-1 ring-primary shadow-xs' : 'bg-card/70 border-border hover:border-border/80 hover:bg-muted/30'}"
                style="margin-left: {depth * 16}px;"
                onclick={() => { selectedNodeId = node.id; refreshPreview(); }}
              >
                <div class="flex items-center gap-2 truncate">
                  <span class="text-xs">
                    {#if node.node_type === 'static'}📄
                    {:else if node.node_type === 'collection'}📁
                    {:else}🏷️{/if}
                  </span>
                  <div class="flex flex-col leading-tight truncate">
                    <span class="text-xs font-semibold text-foreground truncate">{node.title}</span>
                    <span class="text-2xs font-mono text-muted-foreground truncate">{node.url_pattern}</span>
                  </div>
                </div>

                <div class="flex items-center gap-1 shrink-0">
                  <span class="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground">
                    {node.node_type}
                  </span>
                  {#if node.id !== "root"}
                    <button
                      type="button"
                      onclick={(e) => { e.stopPropagation(); deleteNode(node.id); }}
                      class="text-muted-foreground hover:text-destructive p-1 rounded-md text-xs cursor-pointer"
                      title="Удалить узел"
                    >
                      ✕
                    </button>
                  {/if}
                </div>
              </div>

              {#if node.children && node.children.length > 0}
                {#each node.children as child}
                  {@render renderTreeNode(child, depth + 1)}
                {/each}
              {/if}
            {/snippet}

            {@render renderTreeNode(siteTree, 0)}
          </div>
        </div>

        <!-- Общие параметры проекта -->
        <div class="p-4 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-3">
          <span class="text-xs font-bold text-foreground">🌐 Общие параметры сайта:</span>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-2xs font-semibold text-muted-foreground mb-1">Имя проекта / сайта:</label>
              <input
                type="text"
                bind:value={siteName}
                oninput={triggerPreviewDebounced}
                class="w-full px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground"
              />
            </div>
            <div>
              <label class="block text-2xs font-semibold text-muted-foreground mb-1">Базовый адрес (URL):</label>
              <input
                type="text"
                bind:value={siteUrl}
                oninput={triggerPreviewDebounced}
                class="w-full px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground font-mono"
              />
            </div>
          </div>
          <div>
            <label class="block text-2xs font-semibold text-muted-foreground mb-1">API-ключ IndexNow (для мгновенных оповещений Яндекса/Bing):</label>
            <input
              type="text"
              bind:value={indexnowKey}
              placeholder="Введите ключ IndexNow..."
              class="w-full px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground font-mono"
            />
          </div>
        </div>
      </div>

      <!-- ПРАВАЯ КОЛОНКА (7 колонок): ИНСПЕКТОР УЗЛА И ЖИВОЙ СИМУЛЯТОР -->
      <div class="lg:col-span-7 flex flex-col gap-5">
        {#if currentNode}
          <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
            <!-- Шапка инспектора -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-foreground">
                  {t.inspectorTitle} <span class="text-primary">{currentNode.title}</span>
                </span>
                <span class="text-2xs font-mono px-2 py-0.5 rounded-md bg-muted text-muted-foreground">
                  ID: {currentNode.id}
                </span>
              </div>

              <!-- Индикатор шаблона Jinja2 -->
              <div class="flex items-center gap-2">
                <span class="text-2xs font-semibold px-2.5 py-1 rounded-md bg-primary/10 text-primary border border-primary/20 flex items-center gap-1.5">
                  <span>✨</span>
                  <span>HTML + Jinja2 Страница</span>
                </span>
              </div>
            </div>

            <!-- Имя узла и URL pattern -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-2xs font-semibold text-muted-foreground mb-1">Название узла в структуре:</label>
                <input
                  type="text"
                  bind:value={currentNode.title}
                  class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground"
                />
              </div>

              <div>
                <label class="block text-2xs font-semibold text-muted-foreground mb-1">Шаблон адреса (URL Pattern):</label>
                <input
                  type="text"
                  bind:value={currentNode.url_pattern}
                  onfocus={() => activeField = "url_pattern"}
                  oninput={triggerPreviewDebounced}
                  placeholder="/page или /catalog/{'{parent.slug}'}"
                  class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground font-mono"
                />
              </div>
            </div>

            <!-- Если узел динамический: привязка к модели БД -->
            {#if currentNode.node_type !== "static"}
              <div class="p-4 rounded-xl bg-primary/5 border border-primary/20 flex flex-col gap-3">
                <div class="flex flex-col gap-2">
                  <div class="flex items-center justify-between flex-wrap gap-2">
                    <span class="text-xs font-bold text-foreground">Привязка к таблице базы данных:</span>
                    <select
                      bind:value={currentNode.model_key}
                      onchange={triggerPreviewDebounced}
                      class="px-2.5 py-1 text-xs rounded-lg border border-input bg-background text-foreground font-semibold"
                    >
                      <option value={null}>-- Выберите таблицу/модель --</option>
                      {#each availableModels as m}
                        <option value={m.key}>{m.key} — {m.verbose_name || m.key} (таблица: {m.table_name})</option>
                      {/each}
                    </select>
                  </div>
                  {#if currentModelMeta}
                    <div class="text-2xs text-muted-foreground flex items-center gap-1.5 flex-wrap px-1">
                      <strong class="font-mono font-bold text-primary text-xs bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded">
                        {currentModelMeta.key}
                      </strong>
                      <span>— {currentModelMeta.verbose_name || currentModelMeta.key}</span>
                      <span class="text-muted-foreground/70 font-mono">(таблица: {currentModelMeta.table_name})</span>
                    </div>
                  {/if}
                </div>
                <!-- Разделенные чипсы: Поля текущей записи, Поля родителя и Общие параметры -->
                <div class="flex flex-col gap-3 pt-2 border-t border-border/40">
                  {#if currentModelMeta}
                    <!-- 1. Поля текущей записи (record) -->
                    <div class="flex flex-col gap-1.5 p-2.5 rounded-lg bg-card/60 border border-border/60">
                      <div class="flex items-center justify-between text-[11px] font-bold text-foreground">
                        <span class="flex items-center gap-1.5">
                          <span>📄</span>
                          <span>Поля текущей записи: <code class="text-primary font-mono font-bold">record</code></span>
                        </span>
                        <span class="text-2xs text-muted-foreground font-normal">
                          Таблица: <span class="font-semibold text-foreground">{currentModelMeta.verbose_name || currentModelMeta.key}</span>
                        </span>
                      </div>
                      <div class="flex flex-wrap gap-1.5">
                        {#each currentModelMeta.fields as f}
                          <button
                            type="button"
                            onclick={() => insertChip('record.' + f.name)}
                            class="px-2 py-0.5 rounded-md bg-background border border-border text-2xs font-mono text-foreground hover:border-primary hover:text-primary transition-all cursor-pointer flex items-center gap-1 shadow-2xs group"
                            title="{f.label}"
                          >
                            <span class="font-bold text-primary group-hover:underline">
                              {activeField === 'url_pattern' || activeField === 'item_link_pattern' ? '+{' + f.name + '}' : '+{{ record.' + f.name + ' }}'}
                            </span>
                            <span class="text-[10px] text-muted-foreground font-sans">({f.label})</span>
                          </button>
                        {/each}
                      </div>
                    </div>
                  {/if}

                  <!-- 2. Поля родительской записи (parent) - ТОЛЬКО если у непосредственного родителя есть модель в БД -->
                  {#if parentModelMeta}
                    <div class="flex flex-col gap-1.5 p-2.5 rounded-lg bg-primary/5 border border-primary/20">
                      <div class="flex items-center justify-between text-[11px] font-bold text-primary">
                        <span class="flex items-center gap-1.5">
                          <span>🔗</span>
                          <span>Поля родительского раздела: <code class="font-mono font-bold">parent</code></span>
                        </span>
                        <span class="text-2xs text-muted-foreground font-normal">
                          Таблица: <span class="font-semibold text-foreground">{parentModelMeta.verbose_name || parentModelMeta.key}</span>
                        </span>
                      </div>
                      <div class="flex flex-wrap gap-1.5">
                        {#each parentModelMeta.fields as f}
                          <button
                            type="button"
                            onclick={() => insertChip('parent.' + f.name)}
                            class="px-2 py-0.5 rounded-md bg-background border border-primary/30 text-2xs font-mono text-foreground hover:border-primary hover:text-primary transition-all cursor-pointer flex items-center gap-1 shadow-2xs group"
                            title="{f.label}"
                          >
                            <span class="font-bold text-primary group-hover:underline">
                              {activeField === 'url_pattern' || activeField === 'item_link_pattern' ? '+{parent.' + f.name + '}' : '+{{ parent.' + f.name + ' }}'}
                            </span>
                            <span class="text-[10px] text-muted-foreground font-sans">({f.label})</span>
                          </button>
                        {/each}
                      </div>
                    </div>
                  {/if}

                  <!-- 3. Общие свойства страницы и навигации -->
                  <div class="flex flex-col gap-1.5 p-2.5 rounded-lg bg-muted/30 border border-border/50">
                    <span class="text-[11px] font-bold text-muted-foreground flex items-center gap-1.5">
                      <span>🧭</span>
                      <span>Общие свойства страницы и навигации:</span>
                    </span>
                    <div class="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        onclick={() => insertChip('title')}
                        class="px-2 py-0.5 rounded-md bg-background border border-border text-2xs font-mono text-foreground hover:border-primary hover:text-primary transition-colors cursor-pointer"
                        title="Название этой страницы"
                      >
                        <span class="font-bold text-primary">+{"{{ title }}"}</span> <span class="text-[10px] text-muted-foreground font-sans">(Заголовок страницы)</span>
                      </button>
                      <button
                        type="button"
                        onclick={() => insertChip('description')}
                        class="px-2 py-0.5 rounded-md bg-background border border-border text-2xs font-mono text-foreground hover:border-primary hover:text-primary transition-colors cursor-pointer"
                        title="Описание этой страницы"
                      >
                        <span class="font-bold text-primary">+{"{{ description }}"}</span> <span class="text-[10px] text-muted-foreground font-sans">(Описание страницы)</span>
                      </button>
                      <button
                        type="button"
                        onclick={() => insertChip('current_path')}
                        class="px-2 py-0.5 rounded-md bg-background border border-border text-2xs font-mono text-foreground hover:border-primary hover:text-primary transition-colors cursor-pointer"
                        title="Текущий адрес URL страницы"
                      >
                        <span class="font-bold text-primary">+{"{{ current_path }}"}</span> <span class="text-[10px] text-muted-foreground font-sans">(Текущий URL)</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            {/if}

            <!-- Title & Description -->
            <div>
              <label class="block text-2xs font-semibold text-muted-foreground mb-1">Заголовок страницы (Title):</label>
              <input
                type="text"
                bind:value={currentNode.meta_title}
                onfocus={() => activeField = "meta_title"}
                oninput={triggerPreviewDebounced}
                placeholder="Заголовок для сниппета и карточки..."
                class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground"
              />
            </div>

            <div>
              <label class="block text-2xs font-semibold text-muted-foreground mb-1">Описание страницы (Description):</label>
              <textarea
                bind:value={currentNode.meta_description}
                onfocus={() => activeField = "meta_description"}
                oninput={triggerPreviewDebounced}
                rows={2}
                placeholder="Краткое описание для поисковика..."
                class="w-full px-3 py-2 text-xs rounded-lg border border-input bg-background text-foreground resize-none"
              ></textarea>
            </div>

            <!-- Редактор HTML / Jinja2 Шаблона страницы -->
            <div class="flex flex-col gap-2.5 p-4 rounded-xl bg-muted/20 border border-border">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/60 pb-2.5">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <span>📄</span>
                    <span>HTML / Jinja2 Шаблон страницы (содержимое для поисковиков):</span>
                  </span>
                  {#if templateError}
                    <span class="text-2xs font-semibold px-2 py-0.5 rounded-md bg-destructive/10 text-destructive border border-destructive/20 animate-pulse">
                      ⚠️ Ошибка синтаксиса
                    </span>
                  {:else if currentNode.template && currentNode.template.trim()}
                    <span class="text-2xs font-semibold px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                      ✓ Шаблон корректен
                    </span>
                  {/if}
                </div>

                <div class="flex items-center gap-2 relative">
                  <!-- Кнопка вставки цикла перебора по таблице -->
                  <div class="relative">
                    <button
                      type="button"
                      onclick={() => showModelSelectorForLoop = !showModelSelectorForLoop}
                      class="px-2.5 py-1 rounded-lg text-2xs font-bold bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 transition-all flex items-center gap-1 cursor-pointer"
                    >
                      <span>🔄</span>
                      <span>+ Вставить цикл по таблице ▾</span>
                    </button>

                    {#if showModelSelectorForLoop}
                      <div class="absolute right-0 top-full mt-1 w-64 bg-card rounded-xl border border-border shadow-xl z-50 p-2 flex flex-col gap-1">
                        <span class="text-[10px] font-bold text-muted-foreground uppercase px-2 py-1">
                          Выберите таблицу для перебора:
                        </span>
                        {#each availableModels as m}
                          <button
                            type="button"
                            onclick={() => insertTemplateLoop(m.key, m.verbose_name)}
                            class="w-full text-left px-2.5 py-1.5 rounded-lg text-xs hover:bg-muted text-foreground flex items-center justify-between transition-colors cursor-pointer"
                          >
                            <span class="font-bold text-primary font-mono">{m.key}</span>
                            <span class="text-2xs text-muted-foreground font-sans">{m.verbose_name || m.key}</span>
                          </button>
                        {/each}
                      </div>
                    {/if}
                  </div>

                  <!-- Быстрый шаблон -->
                  {#if !currentNode.template}
                    <button
                      type="button"
                      onclick={insertStarterTemplate}
                      class="px-2 py-1 rounded-lg text-2xs font-medium text-muted-foreground hover:text-foreground border border-border bg-background transition-colors cursor-pointer"
                      title="Вставить начальный шаблон"
                    >
                      📋 Каркас
                    </button>
                  {/if}
                </div>
              </div>

              <!-- Текстовое поле Jinja2 с подсветкой синтаксиса -->
              <div class="flex flex-col gap-1.5">
                <div class="flex items-center justify-between text-2xs text-muted-foreground px-1 pb-1">
                  <div class="flex items-center gap-2">
                    <span class="inline-flex items-center gap-1 font-mono font-semibold px-2 py-0.5 rounded bg-muted/60 text-foreground border border-border">
                      <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                      Jinja2 / HTML
                    </span>
                    <span class="text-muted-foreground">
                      {(currentNode.template || "").split("\n").length} стр. • {(currentNode.template || "").length} симв.
                    </span>
                  </div>
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      onclick={() => editorMode = editorMode === "highlight" ? "plain" : "highlight"}
                      class="px-2 py-0.5 rounded border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                      title="Переключить режим редактора"
                    >
                      {editorMode === "highlight" ? "📝 Обычный текст" : "🎨 Подсветка кода"}
                    </button>
                    {#if templateValid && currentNode.template}
                      <span class="text-emerald-500 font-semibold flex items-center gap-1">
                        <span>✓</span>
                        <span>Синтаксис корректен</span>
                      </span>
                    {:else if templateError}
                      <span class="text-destructive font-semibold flex items-center gap-1">
                        <span>⚠️</span>
                        <span>Ошибка синтаксиса</span>
                      </span>
                    {/if}
                  </div>
                </div>

                {#if editorMode === "highlight"}
                  <div class="jinja-editor-wrapper relative rounded-lg border {templateError ? 'border-destructive ring-1 ring-destructive' : 'border-border'} bg-[#fdfbf7] dark:bg-[#231812] shadow-inner overflow-hidden transition-all focus-within:ring-2 focus-within:ring-primary/30">
                    <pre
                      bind:this={preElement}
                      aria-hidden="true"
                      class="jinja-code-pre absolute inset-0 w-full h-full m-0 p-3.5 font-mono text-xs leading-relaxed overflow-hidden select-none pointer-events-none"
                    >{@html highlightedTemplate || '<span class="opacity-40">&lt;!-- Пустой шаблон. Нажмите сюда или используйте кнопку &quot;📋 Каркас&quot; выше --&gt;</span>'}</pre>
                    <textarea
                      bind:this={textareaElement}
                      bind:value={currentNode.template}
                      onscroll={syncScroll}
                      onkeydown={handleEditorKeydown}
                      onfocus={() => activeField = "template"}
                      oninput={() => { triggerTemplateValidationDebounced(); triggerPreviewDebounced(); syncScroll(); }}
                      spellcheck="false"
                      autocomplete="off"
                      autocorrect="off"
                      autocapitalize="off"
                      placeholder={`<h1>{{ title }}</h1>\n<p>{{ description }}</p>\n\n<h2>Категории:</h2>\n<ul>\n{% for cat in ForumCategory %}\n  <li><a href="/forum/{{ cat.slug }}">{{ cat.name }}</a></li>\n{% endfor %}\n</ul>`}
                      class="jinja-code-textarea absolute inset-0 w-full h-full p-3.5 font-mono text-xs leading-relaxed bg-transparent text-transparent caret-foreground resize-none border-0 outline-none overflow-auto"
                    ></textarea>
                  </div>
                {:else}
                  <textarea
                    bind:value={currentNode.template}
                    onkeydown={handleEditorKeydown}
                    onfocus={() => activeField = "template"}
                    oninput={() => { triggerTemplateValidationDebounced(); triggerPreviewDebounced(); }}
                    rows={10}
                    placeholder={`<h1>{{ title }}</h1>\n<p>{{ description }}</p>\n\n<h2>Категории:</h2>\n<ul>\n{% for cat in ForumCategory %}\n  <li><a href="/forum/{{ cat.slug }}">{{ cat.name }}</a></li>\n{% endfor %}\n</ul>`}
                    class="w-full p-3 font-mono text-xs rounded-lg border {templateError ? 'border-destructive focus:ring-destructive' : 'border-input'} bg-background text-foreground resize-y leading-relaxed"
                  ></textarea>
                {/if}
                {#if templateError}
                  <div class="p-2.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-2xs leading-relaxed font-mono">
                    {templateError}
                  </div>
                {/if}

                <div class="flex flex-col gap-2 pt-1 border-t border-border/40 text-[11px] text-muted-foreground">
                  <div class="flex items-center justify-between flex-wrap gap-2">
                    <span class="flex items-center gap-2 flex-wrap">
                      <span>💡 <strong>Шпаргалка:</strong></span>
                      {#if currentModelMeta}
                        <span><code class="text-primary font-mono font-bold">record.*</code> — поля текущей записи ({currentModelMeta.verbose_name || currentModelMeta.key});</span>
                      {/if}
                      {#if parentModelMeta}
                        <span><code class="text-primary font-mono font-bold">parent.*</code> — поля раздела-родителя ({parentModelMeta.verbose_name || parentModelMeta.key});</span>
                      {/if}
                      <span><code class="text-primary font-mono font-bold">{"{% for x in Таблица %}"}</code> — перебор любой таблицы.</span>
                    </span>

                    {#if currentNode.template}
                      <button
                        type="button"
                        onclick={() => { currentNode.template = ""; triggerTemplateValidationDebounced(); triggerPreviewDebounced(); }}
                        class="text-2xs text-muted-foreground hover:text-destructive underline cursor-pointer shrink-0"
                      >
                        Сбросить к авто-генерации
                      </button>
                    {/if}
                  </div>
                </div>
              </div>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
              <div>
                <label class="block text-2xs font-semibold text-muted-foreground mb-1">Тип микроразметки Schema.org:</label>
                <select
                  bind:value={currentNode.schema_type}
                  onchange={triggerPreviewDebounced}
                  class="w-full px-2.5 py-1.5 text-xs rounded-lg border border-input bg-background text-foreground"
                >
                  <option value="WebPage">📄 Веб-страница (WebPage)</option>
                  <option value="CollectionPage">📁 Раздел / Каталог (CollectionPage)</option>
                  <option value="Product">🛍️ Карточка товара (Product)</option>
                  <option value="Article">📰 Статья / Новость (Article)</option>
                  <option value="DiscussionForumPosting">💬 Ветка форума (DiscussionForumPosting)</option>
                </select>
              </div>

              <div class="flex items-center gap-4 pt-4">
                <label class="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    bind:checked={currentNode.sitemap_enabled}
                    class="rounded text-primary focus:ring-primary"
                  />
                  <span>Включать в sitemap.xml</span>
                </label>
              </div>
            </div>
          </div>

          <!-- СЕКЦИЯ 2: ЖИВАЯ ПРОВЕРКА В БРАУЗЕРЕ (ГЛАЗАМИ ПОИСКОВИКА) -->
          <div class="p-5 rounded-xl bg-card border border-border shadow-xs flex flex-col gap-4">
            <div class="flex items-center justify-between border-b border-border pb-3">
              <div class="flex flex-col">
                <span class="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <span>🤖</span>
                  <span>Проверка страницы в браузере (глазами поисковика)</span>
                </span>
                <span class="text-2xs text-muted-foreground">
                  Эмуляция реального краулера Яндекс и Google без необходимости настраивать DevTools
                </span>
              </div>
            </div>

            <div class="p-4 rounded-xl bg-muted/40 border border-border flex flex-col gap-3">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex flex-col gap-1">
                  <span class="text-xs font-bold text-foreground flex items-center gap-2">
                    <span>{currentNode.title || "Узел"}</span>
                    <span class="text-2xs font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground">{currentNode.url_pattern}</span>
                  </span>
                  <span class="text-2xs text-muted-foreground">
                    {#if currentNode.url_pattern.includes("{")}
                      Узел параметризован (шаблон). Для проверки перейдите в родительский раздел и откройте реальную карточку или тему.
                    {:else}
                      Статичный URL. Можно сразу открыть в режиме поискового робота.
                    {/if}
                  </span>
                </div>

                <div class="flex items-center gap-2 shrink-0">
                  {#if !currentNode.url_pattern.includes("{")}
                    <a
                      href="{currentNode.url_pattern}?bot=1"
                      target="_blank"
                      rel="noreferrer"
                      class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
                    >
                      <span>👁️</span>
                      <span>Открыть как бот ↗</span>
                    </a>
                  {:else}
                    <a
                      href="/?bot=1"
                      target="_blank"
                      rel="noreferrer"
                      class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
                    >
                      <span>🌐</span>
                      <span>Обойти с Главной ↗</span>
                    </a>
                  {/if}
                </div>
              </div>

              <!-- Пояснение про сессионный режим -->
              <div class="p-3 rounded-lg bg-card border border-border/70 flex items-start gap-2.5 text-2xs text-muted-foreground leading-relaxed">
                <span class="text-sm shrink-0">💡</span>
                <div>
                  <strong class="text-foreground">Как работает режим эмуляции:</strong>
                  При открытии ссылки сервер активирует сессионный режим — вы можете свободно кликать по ссылкам, переходить по разделам и проверять микроразметку Schema.org. Как только вы <strong class="text-foreground">закроете вкладку</strong> (или нажмёте «✕ Выйти» сверху страницы), режим бота автоматически отключится.
                </div>
              </div>
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Модальное окно выбора пресета структуры -->
  {#if showPresetsModal}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div class="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-xl flex flex-col gap-4">
        <div class="flex items-center justify-between border-b border-border pb-3">
          <div class="flex items-center gap-2">
            <span class="text-lg">✨</span>
            <h2 class="text-sm font-bold text-foreground">Выберите готовый шаблон структуры:</h2>
          </div>
          <button
            type="button"
            onclick={() => showPresetsModal = false}
            class="text-muted-foreground hover:text-foreground p-1 text-sm cursor-pointer"
          >
            ✕
          </button>
        </div>

        <p class="text-xs text-muted-foreground">
          Шаблон мгновенно создаст сбалансированную иерархию страниц для поисковых систем. Вы всегда сможете добавить свои разделы и изменить параметры.
        </p>

        <div class="flex flex-col gap-2.5">
          {#each availablePresets as p}
            <div
              class="p-3.5 rounded-xl border border-border bg-card hover:border-primary hover:bg-primary/5 transition-all cursor-pointer flex items-center justify-between gap-3"
              onclick={() => applyPreset(p.key)}
            >
              <div class="flex items-center gap-3">
                <span class="text-2xl">{p.icon}</span>
                <div class="flex flex-col">
                  <span class="text-xs font-bold text-foreground">{p.title}</span>
                  <span class="text-2xs text-muted-foreground">{p.description}</span>
                </div>
              </div>
              <button
                type="button"
                disabled={isApplyingPreset}
                class="px-3 py-1 rounded-lg text-2xs font-semibold bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground transition-all cursor-pointer shrink-0"
              >
                {isApplyingPreset ? "Применение..." : "Выбрать"}
              </button>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .jinja-editor-wrapper {
    min-height: 240px;
    height: 320px;
  }
  .jinja-code-pre {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    padding: 14px;
    box-sizing: border-box;
    overflow: hidden;
    pointer-events: none;
    user-select: none;
    color: #1e293b;
  }
  :global(.dark) .jinja-code-pre {
    color: #f8fafc;
  }
  .jinja-code-textarea {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    padding: 14px;
    box-sizing: border-box;
    overflow: auto;
    resize: none;
    border: none;
    outline: none;
    background: transparent;
    color: transparent;
    -webkit-text-fill-color: transparent;
    caret-color: #0f172a;
  }
  :global(.dark) .jinja-code-textarea {
    caret-color: #f8fafc;
  }
  .jinja-code-pre,
  .jinja-code-textarea {
    box-sizing: border-box;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace !important;
    font-size: 12.5px !important;
    line-height: 1.65 !important;
    letter-spacing: normal !important;
    tab-size: 2 !important;
    white-space: pre !important;
    word-wrap: normal !important;
  }
  .jinja-code-textarea::selection {
    background: rgba(59, 130, 246, 0.25);
    color: transparent;
    -webkit-text-fill-color: transparent;
  }

  /* ========================================================
     СВЕТЛАЯ ТЕМА (Высокая контрастность на светлом фоне)
     ======================================================== */
  :global(.jinja-editor-wrapper .token.comment) {
    color: #64748b;
    font-style: italic;
  }
  :global(.jinja-editor-wrapper .token.delimiter) {
    color: #9a3412; /* Ржаво-оранжевый (чёткий контраст для {% и %}) */
    font-weight: 800;
  }
  :global(.jinja-editor-wrapper .token.tag) {
    color: #1d4ed8; /* Глубокий синий для HTML-тегов <h2>, <a>, <ul> */
    font-weight: 700;
  }
  :global(.jinja-editor-wrapper .token.attr-name) {
    color: #7c3aed; /* Насыщенный фиолетовый для href, class */
    font-weight: 600;
  }
  :global(.jinja-editor-wrapper .token.attr-value),
  :global(.jinja-editor-wrapper .token.string) {
    color: #15803d; /* Насыщенный зелёный для строк "/forum/..." */
    font-weight: 600;
  }
  :global(.jinja-editor-wrapper .token.punctuation) {
    color: #475569; /* Тёмный нейтральный для скобок и точек */
  }
  :global(.jinja-editor-wrapper .token.keyword) {
    color: #b91c1c; /* Глубокий рубиновый/красный для for, in, if, endif */
    font-weight: 800;
  }
  :global(.jinja-editor-wrapper .token.variable) {
    color: #0f766e; /* Насыщенный тёмно-бирюзовый/тиловый для названий моделей и переменных */
    font-weight: 600;
  }
  :global(.jinja-editor-wrapper .token.function) {
    color: #4338ca; /* ЯРКИЙ ИНДИГО-УЛЬТРАМАРИН ДЛЯ .where(...) — МАКСИМАЛЬНО ЧЁТКО ВИДЕН! */
    font-weight: 800;
  }
  :global(.jinja-editor-wrapper .token.operator) {
    color: #b45309; /* Янтарный для = и операций */
    font-weight: 700;
  }
  :global(.jinja-editor-wrapper .token.number) {
    color: #c2410c; /* Тёмно-оранжевый для чисел */
    font-weight: 600;
  }
  :global(.jinja-editor-wrapper .token.boolean) {
    color: #be185d; /* Бордово-малиновый для None, True, False */
    font-weight: 800;
  }

  /* ========================================================
     ТЁМНАЯ ТЕМА (.dark)
     ======================================================== */
  :global(.dark .jinja-editor-wrapper .token.comment) {
    color: #94a3b8;
    font-style: italic;
  }
  :global(.dark .jinja-editor-wrapper .token.delimiter) {
    color: #fb923c;
    font-weight: 800;
  }
  :global(.dark .jinja-editor-wrapper .token.tag) {
    color: #60a5fa;
    font-weight: 700;
  }
  :global(.dark .jinja-editor-wrapper .token.attr-name) {
    color: #c084fc;
    font-weight: 600;
  }
  :global(.dark .jinja-editor-wrapper .token.attr-value),
  :global(.dark .jinja-editor-wrapper .token.string) {
    color: #4ade80;
    font-weight: 600;
  }
  :global(.dark .jinja-editor-wrapper .token.punctuation) {
    color: #94a3b8;
  }
  :global(.dark .jinja-editor-wrapper .token.keyword) {
    color: #fb7185;
    font-weight: 800;
  }
  :global(.dark .jinja-editor-wrapper .token.variable) {
    color: #2dd4bf;
    font-weight: 600;
  }
  :global(.dark .jinja-editor-wrapper .token.function) {
    color: #a78bfa; /* Яркий лавандовый для .where в тёмной теме */
    font-weight: 800;
  }
  :global(.dark .jinja-editor-wrapper .token.operator) {
    color: #fbbf24;
    font-weight: 700;
  }
  :global(.dark .jinja-editor-wrapper .token.number) {
    color: #f97316;
    font-weight: 600;
  }
  :global(.dark .jinja-editor-wrapper .token.boolean) {
    color: #f472b6;
    font-weight: 800;
  }
</style>