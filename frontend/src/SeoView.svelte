<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import {
    Button,
    Input,
    Card,
    Badge,
    Checkbox,
    Modal,
  } from "./ui/index.js";
  import {
    Plus,
    Trash2,
    Save,
    Settings,
    Zap,
    ExternalLink,
    Search,
    ChevronRight,
    ChevronDown,
    CheckCircle2,
    AlertCircle,
    Code,
  } from "@lucide/svelte";

  let { onnotify = () => {} } = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let isPinging = $state(false);
  let showSettingsModal = $state(false);

  // Глобальные настройки SEO (pf_seo_config)
  let siteName = $state("PyFerro 2.0 Application");
  let siteUrl = $state("http://localhost:8080");
  let defaultTitle = $state("PyFerro 2.0 Application");
  let defaultDescription = $state("");
  let defaultOgImage = $state("");
  let indexnowKey = $state("");
  let sitemapTtl = $state(3600);

  // Справочники с бэкенда
  let availableModels = $state([]);
  let botRoutes = $state([]);

  // Дерево сайта
  let siteTree = $state({
    id: "root",
    title: "Главная страница",
    url_pattern: "/",
    node_type: "static",
    template: "",
    meta_title: "{site_name}",
    meta_description: "",
    og_image: "",
    schema_type: "WebSite",
    sitemap_enabled: true,
    sitemap_priority: 1.0,
    sitemap_changefreq: "daily",
    children: [],
  });

  let selectedNodeId = $state("root");
  let activeField = $state("template"); // "template" | "meta_title" | "meta_description" | "url_pattern" | "title"

  // Валидация шаблона Jinja2
  let templateValid = $state(true);
  let templateError = $state(null);
  let validateTimer = null;

  // DOM ref редактора
  let textareaEl = $state(null);

  // Шпаргалка моделей
  let modelSearch = $state("");
  let expandedModels = $state({}); // { [key]: boolean }

  function findNodeAndParents(node, targetId, parents = []) {
    if (!node) return null;
    if (node.id === targetId) {
      return { node, parents };
    }
    for (const child of node.children || []) {
      const found = findNodeAndParents(child, targetId, [...parents, node]);
      if (found) return found;
    }
    return null;
  }

  let currentSelection = $derived(findNodeAndParents(siteTree, selectedNodeId));
  let currentNode = $derived(currentSelection ? currentSelection.node : siteTree);
  let currentParents = $derived(currentSelection ? currentSelection.parents : []);

  // Показываем ТОЛЬКО те модели, к которым у роли guest есть доступ на чтение
  let allowedModels = $derived(availableModels.filter((m) => m.seo_allowed));

  let filteredModels = $derived(
    allowedModels.filter((m) => {
      const q = modelSearch.trim().toLowerCase();
      if (!q) return true;
      const matchKey = (m.key || "").toLowerCase().includes(q);
      const matchVerbose = (m.verbose_name || "").toLowerCase().includes(q);
      const matchField = (m.fields || []).some((f) => (f.name || "").toLowerCase().includes(q));
      return matchKey || matchVerbose || matchField;
    })
  );

  onMount(async () => {
    await loadSeoData();
  });

  async function loadSeoData() {
    isLoading = true;
    try {
      const data = await rpc.call("seo.get_tree");
      if (data.tree && data.tree.id) {
        siteTree = data.tree;
      }
      siteUrl = data.site_url || "http://localhost:8080";
      siteName = data.site_name || "PyFerro 2.0 Application";
      defaultTitle = data.default_title || "";
      defaultDescription = data.default_description || "";
      defaultOgImage = data.default_og_image || "";
      indexnowKey = data.indexnow_key || "";
      sitemapTtl = data.sitemap_ttl || 3600;
      availableModels = data.available_models || [];
      botRoutes = data.bot_routes || [];
      triggerValidateDebounced();
    } catch (e) {
      onnotify(e.message, "error");
    } finally {
      isLoading = false;
    }
  }

  async function saveSeoData() {
    isSaving = true;
    try {
      await rpc.call("seo.save_tree", {
        tree: siteTree,
        site_url: siteUrl,
        site_name: siteName,
        default_title: defaultTitle,
        default_description: defaultDescription,
        default_og_image: defaultOgImage,
        indexnow_key: indexnowKey,
        sitemap_ttl: sitemapTtl,
      });
      onnotify("Дерево сайта и SEO настройки успешно сохранены!", "info");
    } catch (e) {
      onnotify(e.message, "error");
    } finally {
      isSaving = false;
    }
  }

  async function pingIndexNow() {
    isPinging = true;
    try {
      const res = await rpc.call("seo.ping_indexnow");
      if (res.status === 200 || res.status === 202) {
        onnotify(
          `IndexNow успешно отправлен (${res.url_count || res.pushed_urls?.length || 1} URL передано)`,
          "info"
        );
      } else {
        onnotify(`Ответ IndexNow: ${res.message || res.status}`, "info");
      }
    } catch (e) {
      onnotify(e.message, "error");
    } finally {
      isPinging = false;
    }
  }

  function toggleModelAccordion(modelKey) {
    expandedModels[modelKey] = !expandedModels[modelKey];
  }

  function selectNode(id) {
    selectedNodeId = id;
    triggerValidateDebounced();
  }

  function addChildNode(parentNode) {
    if (!parentNode) return;
    if (!parentNode.children) parentNode.children = [];
    const newId = `node_${Date.now()}`;
    const basePattern = (parentNode.url_pattern || "/").replace(/\/$/, "");
    const newNode = {
      id: newId,
      title: "Новая страница",
      url_pattern: `${basePattern}/page-${parentNode.children.length + 1}`,
      node_type: "static",
      template: "<h1>{{ title }}</h1>\n<p>{{ description }}</p>\n",
      meta_title: "{title} | {site_name}",
      meta_description: "",
      og_image: "",
      schema_type: "WebPage",
      sitemap_enabled: true,
      sitemap_priority: 0.8,
      sitemap_changefreq: "daily",
      children: [],
    };
    parentNode.children.push(newNode);
    selectedNodeId = newId;
    triggerValidateDebounced();
  }

  function removeNodeById(node, targetId) {
    if (!node.children) return false;
    const idx = node.children.findIndex((c) => c.id === targetId);
    if (idx !== -1) {
      node.children.splice(idx, 1);
      return true;
    }
    for (const c of node.children) {
      if (removeNodeById(c, targetId)) return true;
    }
    return false;
  }

  function deleteSelectedNode() {
    if (selectedNodeId === "root") return;
    const parentId =
      currentParents.length > 0
        ? currentParents[currentParents.length - 1].id
        : "root";
    if (removeNodeById(siteTree, selectedNodeId)) {
      selectedNodeId = parentId;
      triggerValidateDebounced();
    }
  }

  // Вставка текста в позицию курсора редактора шаблона
  function insertIntoTemplate(text) {
    if (!currentNode) return;
    const currentTpl = currentNode.template || "";
    if (!textareaEl) {
      currentNode.template = currentTpl + text;
      triggerValidateDebounced();
      return;
    }

    const start = textareaEl.selectionStart ?? currentTpl.length;
    const end = textareaEl.selectionEnd ?? currentTpl.length;
    currentNode.template =
      currentTpl.substring(0, start) + text + currentTpl.substring(end);
    triggerValidateDebounced();

    setTimeout(() => {
      textareaEl.focus();
      const newPos = start + text.length;
      textareaEl.setSelectionRange(newPos, newPos);
    }, 0);
  }

  // Вставка цикла перебора по модели
  function insertModelLoop(modelKey) {
    const loopSnippet = `\n<ul>\n  {% for item in ${modelKey}.order_by("-id")[:20] %}\n    <li><a href="/${modelKey.toLowerCase()}/{{ item.id }}">{{ item.title or item.name or item.id }}</a></li>\n  {% endfor %}\n</ul>\n`;
    insertIntoTemplate(loopSnippet);
  }

  // Вставка поля в активный инпут или в Jinja2-шаблон
  function insertFieldToken(fieldName, prefix = "item") {
    if (!currentNode) return;

    if (activeField === "template") {
      insertIntoTemplate(`{{ ${prefix}.${fieldName} }}`);
      return;
    }

    const token = `{${fieldName}}`;
    if (activeField === "meta_title") {
      currentNode.meta_title = (currentNode.meta_title || "") + (currentNode.meta_title ? " " : "") + token;
    } else if (activeField === "meta_description") {
      currentNode.meta_description = (currentNode.meta_description || "") + (currentNode.meta_description ? " " : "") + token;
    } else if (activeField === "url_pattern") {
      const base = (currentNode.url_pattern || "/").replace(/\/$/, "");
      currentNode.url_pattern = `${base}/${token}`;
    } else if (activeField === "title") {
      currentNode.title = (currentNode.title || "") + " " + token;
    }
  }

  // Вставка глобальных токенов
  function insertGlobalToken(tokenName) {
    if (activeField === "template") {
      insertIntoTemplate(`{{ ${tokenName} }}`);
    } else if (activeField === "meta_title") {
      currentNode.meta_title = (currentNode.meta_title || "") + (currentNode.meta_title ? " " : "") + `{${tokenName}}`;
    } else if (activeField === "meta_description") {
      currentNode.meta_description = (currentNode.meta_description || "") + (currentNode.meta_description ? " " : "") + `{${tokenName}}`;
    }
  }

  // Обработка клавиш в редакторе (Tab = 2 пробела, Ctrl+S = Сохранить)
  function handleTextareaKeyDown(e) {
    if (e.key === "Tab") {
      e.preventDefault();
      const start = e.currentTarget.selectionStart;
      const end = e.currentTarget.selectionEnd;
      const val = currentNode.template || "";
      currentNode.template = val.substring(0, start) + "  " + val.substring(end);
      triggerValidateDebounced();
      setTimeout(() => {
        e.currentTarget.setSelectionRange(start + 2, start + 2);
      }, 0);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      saveSeoData();
    }
  }

  function handleGlobalKeyDown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      saveSeoData();
    }
  }

  function triggerValidateDebounced() {
    clearTimeout(validateTimer);
    validateTimer = setTimeout(async () => {
      if (!currentNode || !currentNode.template) {
        templateValid = true;
        templateError = null;
        return;
      }
      try {
        const res = await rpc.call("seo.validate_template", {
          template: currentNode.template,
        });
        templateValid = res.valid;
        templateError = res.error;
      } catch (e) {
        templateValid = false;
        templateError = e.message;
      }
    }, 250);
  }
</script>

<svelte:window onkeydown={handleGlobalKeyDown} />

<!-- ВЕРХНЯЯ ПАНЕЛЬ ДЕЙСТВИЙ -->
<div class="flex items-center justify-between mb-4 flex-wrap gap-3">
  <div>
    <h2 class="m-0 text-lg font-bold text-text-bright flex items-center gap-2">
      <span>🌲 SEO & Дерево сайта</span>
      <Badge variant="accent" class="text-xs font-mono">Jinja2 Sandbox</Badge>
    </h2>
    <small class="text-muted block mt-0.5">
      Структура URL, метатеги и прямой серверный рендеринг страниц для поисковых ботов
    </small>
  </div>
  <div class="flex gap-2 flex-wrap items-center">
    <Button
      variant="outline"
      size="sm"
      onclick={() => (showSettingsModal = true)}
      title="Глобальные параметры сайта, IndexNow и домен"
    >
      <Settings size={14} class="mr-1.5" />
      Настройки сайта
    </Button>

    <a
      class="inline-flex items-center justify-center min-h-8 h-8 px-3 rounded text-xs font-medium border border-border text-text hover:bg-panel-alt hover:text-text-bright no-underline transition-all"
      href="/sitemap.xml"
      target="_blank"
      rel="noreferrer"
      title="Открыть живой XML файл карты сайта"
    >
      🗺️ /sitemap.xml ↗
    </a>

    <a
      class="inline-flex items-center justify-center min-h-8 h-8 px-3 rounded text-xs font-semibold border border-success/40 text-success bg-success/5 hover:bg-success/15 no-underline transition-all shadow-xs"
      href="{currentNode?.url_pattern ? (currentNode.url_pattern.includes('{') ? '/' : currentNode.url_pattern) : '/'}?bot=1"
      target="_blank"
      rel="noreferrer"
      title="Открыть страницу в браузере с флагом бота (?bot=1) для проверки готового HTML"
    >
      <ExternalLink size={13} class="mr-1.5" />
      Открыть как бот (?bot=1) ↗
    </a>

    <Button
      variant="outline"
      size="sm"
      disabled={isPinging}
      onclick={pingIndexNow}
      title="Отправить мгновенный push в поисковики Яндекс и Bing"
    >
      <Zap size={14} class="mr-1.5 text-accent" />
      {isPinging ? "Отправка..." : "IndexNow"}
    </Button>

    <Button
      variant="primary"
      size="sm"
      disabled={isSaving}
      onclick={saveSeoData}
      title="Сохранить всё дерево и шаблоны в БД (Ctrl+S)"
    >
      <Save size={14} class="mr-1.5" />
      {isSaving ? "Сохранение..." : "Сохранить в БД"}
    </Button>
  </div>
</div>

{#if isLoading}
  <Card class="text-muted p-8 text-center text-sm">
    Загрузка структуры дерева сайта и конфигурации SEO из базы данных...
  </Card>
{:else}
  <!-- ОСНОВНОЙ РАБОЧИЙ ЛЕЙАУТ (Две колонки) -->
  <div class="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4 items-start">
    
    <!-- ЛЕВАЯ КОЛОНКА: Дерево сайта + Шпаргалка моделей для Jinja2 -->
    <div class="flex flex-col gap-4">
      
      <!-- 1. Дерево страниц сайта -->
      <Card class="p-3.5">
        <div class="flex items-center justify-between pb-2.5 mb-2.5 border-b border-border-subtle">
          <span class="font-bold text-xs uppercase tracking-wide text-text-bright">Дерево страниц</span>
          <Button
            variant="outline"
            size="sm"
            class="h-7 text-xs px-2"
            onclick={() => addChildNode(currentNode)}
            title="Добавить дочерний подраздел к выбранному"
          >
            <Plus size={13} class="mr-1" />
            Подраздел
          </Button>
        </div>

        <div class="max-h-[360px] overflow-y-auto pr-1">
          {#snippet treeItem(node, depth)}
            <button
              type="button"
              class="w-full text-left mb-1 p-2 rounded cursor-pointer flex items-center justify-between border transition-all text-xs {selectedNodeId === node.id ? 'border-accent bg-accent-subtle/80 text-text-bright shadow-xs font-semibold' : 'border-border-subtle bg-bg hover:bg-panel-alt text-text'}"
              style="margin-left: {depth * 14}px;"
              onclick={() => selectNode(node.id)}
            >
              <div class="overflow-hidden text-ellipsis whitespace-nowrap mr-2">
                <span class="mr-1.5 opacity-80">
                  {node.children && node.children.length > 0 ? "📁" : "📄"}
                </span>
                <span>{node.title}</span>
                <div class="text-[0.7rem] text-muted font-mono truncate">
                  {node.url_pattern}
                </div>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                {#if node.sitemap_enabled}
                  <span class="text-[0.65rem] text-muted" title="Включен в sitemap">🗺️</span>
                {/if}
              </div>
            </button>
            {#each node.children || [] as child}
              {@render treeItem(child, depth + 1)}
            {/each}
          {/snippet}

          {@render treeItem(siteTree, 0)}
        </div>
      </Card>

      <!-- 2. Интерактивная шпаргалка открытых моделей (Jinja2 Cheat Sheet) -->
      <Card class="p-3.5">
        <div class="flex items-center justify-between pb-2 mb-2 border-b border-border-subtle">
          <div>
            <span class="font-bold text-xs uppercase tracking-wide text-text-bright">Модели для Jinja2</span>
            <small class="text-muted block text-[0.7rem]">Открытые для ботов таблицы</small>
          </div>
          <Badge variant="accent" class="text-xs font-mono">{allowedModels.length}</Badge>
        </div>

        <!-- Поиск моделей и полей -->
        <div class="relative mb-2.5">
          <Input
            class="w-full text-xs h-7 min-h-7 pl-7"
            placeholder="Поиск по таблицам и колонкам..."
            bind:value={modelSearch}
          />
          <Search size={12} class="absolute left-2.5 top-2 text-muted pointer-events-none" />
        </div>

        <!-- Список доступных моделей -->
        <div class="max-h-[460px] overflow-y-auto pr-1 flex flex-col gap-2">
          {#if filteredModels.length === 0}
            <div class="text-xs text-muted text-center py-4">
              {#if allowedModels.length === 0}
                Нет таблиц с доступом guest.read
              {:else}
                Таблицы по запросу не найдены
              {/if}
            </div>
          {:else}
            {#each filteredModels as m}
              <div class="border border-border-subtle rounded bg-bg overflow-hidden text-xs">
                <!-- Заголовок модели -->
                <div class="p-2 flex items-center justify-between gap-1.5 bg-panel-alt/50 border-b border-border-subtle">
                  <button
                    type="button"
                    class="flex items-center gap-1 font-semibold text-text-bright hover:text-accent cursor-pointer truncate text-left"
                    onclick={() => toggleModelAccordion(m.key)}
                    title="Раскрыть список полей"
                  >
                    {#if expandedModels[m.key]}
                      <ChevronDown size={14} class="shrink-0 text-muted" />
                    {:else}
                      <ChevronRight size={14} class="shrink-0 text-muted" />
                    {/if}
                    <span class="font-mono">{m.key}</span>
                    {#if m.verbose_name && m.verbose_name !== m.key}
                      <small class="text-muted font-normal truncate">({m.verbose_name})</small>
                    {/if}
                  </button>

                  <!-- Кнопка быстрой вставки цикла for -->
                  <Button
                    variant="outline"
                    size="sm"
                    class="h-6 text-[0.7rem] px-2 py-0"
                    onclick={() => insertModelLoop(m.key)}
                    title="Вставить цикл: &#123;% for item in {m.key}.order_by('-id')[:20] %&#125;"
                  >
                    + цикл
                  </Button>
                </div>

                <!-- Раскрывающийся список колонок и связей -->
                {#if expandedModels[m.key]}
                  <div class="p-2 bg-bg flex flex-col gap-1.5 animate-in fade-in duration-100">
                    <div class="text-[0.68rem] text-muted uppercase font-semibold">Поля модели:</div>
                    <div class="flex flex-wrap gap-1">
                      {#each m.fields || [] as f}
                        <button
                          type="button"
                          class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[0.7rem] font-mono border border-border bg-panel hover:bg-accent-subtle hover:border-accent hover:text-text-bright transition-colors cursor-pointer"
                          onclick={() => insertFieldToken(f.name, "item")}
                          title="Клик: вставить в редактор &#123;&#123; item.{f.name} &#125;&#125;"
                        >
                          <span>{f.name}</span>
                          <span class="text-[0.62rem] text-muted">({f.type || "str"})</span>
                        </button>
                      {/each}
                    </div>

                    {#if m.relations && m.relations.length > 0}
                      <div class="text-[0.68rem] text-muted uppercase font-semibold mt-1">Связи (FK):</div>
                      <div class="flex flex-wrap gap-1">
                        {#each m.relations as rel}
                          {#each rel.fields || [] as rf}
                            <button
                              type="button"
                              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[0.7rem] font-mono border border-accent/40 bg-accent-subtle/40 hover:bg-accent-subtle hover:border-accent hover:text-text-bright transition-colors cursor-pointer text-accent"
                              onclick={() => insertFieldToken(rf.chip || `${rel.relation_name}.${rf.name}`, "item")}
                              title="Клик: вставить &#123;&#123; item.{rf.chip || `${rel.relation_name}.${rf.name}`} &#125;&#125;"
                            >
                              <span>{rf.chip || `${rel.relation_name}.${rf.name}`}</span>
                            </button>
                          {/each}
                        {/each}
                      </div>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          {/if}
        </div>
      </Card>

      <!-- 3. Кодовые маршруты @bot_page (если есть) -->
      {#if botRoutes.length > 0}
        <Card class="p-3">
          <div class="flex items-center justify-between pb-1.5 mb-1.5 border-b border-border-subtle text-xs font-semibold text-text-bright">
            <span>Кодовые маршруты (@bot_page)</span>
            <Badge variant="default" class="text-xs">{botRoutes.length}</Badge>
          </div>
          <div class="flex flex-wrap gap-1">
            {#each botRoutes as br}
              <code class="text-[0.7rem] font-mono px-1.5 py-0.5 rounded bg-panel-alt text-accent border border-border-subtle">
                {br}
              </code>
            {/each}
          </div>
        </Card>
      {/if}
    </div>

    <!-- ПРАВАЯ КОЛОНКА: Настройки узла + Центральный редактор шаблона Jinja2 -->
    {#if currentNode}
      <div class="flex flex-col gap-4">
        
        <!-- Карточка 1: Основные параметры страницы (Лаконично и компактно) -->
        <Card class="p-4">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-border-subtle flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <span class="font-bold text-sm text-text-bright">
                Страница: <b>{currentNode.title}</b>
              </span>
              <code class="text-xs font-mono bg-bg px-2 py-0.5 rounded border border-border-subtle text-accent">
                {currentNode.url_pattern}
              </code>
            </div>

            {#if selectedNodeId !== "root"}
              <Button
                variant="danger"
                size="sm"
                onclick={deleteSelectedNode}
                title="Удалить данный узел и его подразделы"
              >
                <Trash2 size={13} class="mr-1" />
                Удалить узел
              </Button>
            {/if}
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div>
              <div class="text-xs text-muted block mb-1">Название страницы (хлебные крошки)</div>
              <Input
                class="w-full text-xs"
                bind:value={currentNode.title}
                onfocus={() => (activeField = "title")}
              />
            </div>

            <div>
              <div class="text-xs text-muted block mb-1">Шаблон URL (например: /forum, /forum/&#123;id&#125;)</div>
              <Input
                class="w-full font-mono text-xs"
                bind:value={currentNode.url_pattern}
                disabled={selectedNodeId === "root"}
                onfocus={() => (activeField = "url_pattern")}
              />
            </div>
          </div>

          <div class="mb-3">
            <div class="text-xs text-muted block mb-1">SEO Title (meta_title, og:title)</div>
            <Input
              class="w-full text-xs"
              placeholder="&#123;title&#125; — &#123;site_name&#125;"
              bind:value={currentNode.meta_title}
              onfocus={() => (activeField = "meta_title")}
            />
          </div>

          <div class="mb-3">
            <div class="text-xs text-muted block mb-1">Мета-описание (meta description / og:description)</div>
            <textarea
              class="w-full min-h-[54px] px-3 py-1.5 rounded bg-bg text-text border border-border text-xs outline-none focus:border-accent focus:ring-1 focus:ring-accent resize-y"
              rows="2"
              placeholder="Краткое описание страницы для сниппетов поисковиков..."
              bind:value={currentNode.meta_description}
              onfocus={() => (activeField = "meta_description")}
            ></textarea>
          </div>

          <!-- Единственный переключатель Sitemap: Включить / Выключить -->
          <div class="pt-3 border-t border-border-subtle text-xs bg-panel-alt/30 -mx-4 -mb-4 px-4 py-2.5 rounded-b flex items-center justify-between">
            <Checkbox
              bind:checked={currentNode.sitemap_enabled}
              label="Включить страницу в /sitemap.xml"
            />
            <small class="text-muted text-[0.7rem]">
              URL будет автоматически включен в карту сайта для поисковиков
            </small>
          </div>
        </Card>

        <!-- Карточка 2: Центральный редактор шаблона Jinja2 -->
        <Card class="p-4 flex flex-col flex-1">
          <div class="flex items-center justify-between pb-3 mb-2 border-b border-border-subtle flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <Code size={16} class="text-accent" />
              <span class="font-bold text-sm text-text-bright">Тело страницы (HTML / Jinja2 Sandbox)</span>
            </div>

            <div class="flex items-center gap-3">
              <!-- Индикатор валидации Jinja2 в реальном времени -->
              {#if templateValid}
                <span class="inline-flex items-center gap-1 text-xs text-success font-medium">
                  <CheckCircle2 size={13} />
                  Синтаксис корректен
                </span>
              {:else}
                <span class="inline-flex items-center gap-1 text-xs text-danger font-medium animate-pulse" title={templateError}>
                  <AlertCircle size={13} />
                  Ошибка синтаксиса
                </span>
              {/if}

              <span class="text-[0.7rem] text-muted hidden sm:inline">
                [Tab] 2 пробела • [Ctrl+S] сохранить
              </span>
            </div>
          </div>

          <!-- Панель быстрых глобальных токенов -->
          <div class="flex items-center justify-between flex-wrap gap-2 mb-2 pb-2 border-b border-border-subtle text-xs">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-muted text-[0.72rem]">Быстрая вставка:</span>
              <button
                type="button"
                class="px-2 py-0.5 rounded text-[0.7rem] font-mono border border-border bg-bg hover:bg-panel-alt hover:border-accent cursor-pointer transition-colors"
                onclick={() => insertGlobalToken("site_name")}
              >
                + &#123;&#123; site_name &#125;&#125;
              </button>
              <button
                type="button"
                class="px-2 py-0.5 rounded text-[0.7rem] font-mono border border-border bg-bg hover:bg-panel-alt hover:border-accent cursor-pointer transition-colors"
                onclick={() => insertIntoTemplate("{{ title }}")}
              >
                + &#123;&#123; title &#125;&#125;
              </button>
              <button
                type="button"
                class="px-2 py-0.5 rounded text-[0.7rem] font-mono border border-border bg-bg hover:bg-panel-alt hover:border-accent cursor-pointer transition-colors"
                onclick={() => insertIntoTemplate("{{ description }}")}
              >
                + &#123;&#123; description &#125;&#125;
              </button>
              <button
                type="button"
                class="px-2 py-0.5 rounded text-[0.7rem] font-mono border border-border bg-bg hover:bg-panel-alt hover:border-accent cursor-pointer transition-colors"
                onclick={() => insertIntoTemplate("{{ request.path }}")}
              >
                + &#123;&#123; request.path &#125;&#125;
              </button>
              <button
                type="button"
                class="px-2 py-0.5 rounded text-[0.7rem] font-mono border border-border bg-bg hover:bg-panel-alt hover:border-accent cursor-pointer transition-colors"
                onclick={() => insertIntoTemplate("{{ request.query }}")}
              >
                + &#123;&#123; request.query &#125;&#125;
              </button>
            </div>
          </div>

          <!-- Текстовое поле шаблона -->
          <div class="relative flex-1 flex flex-col">
            <textarea
              bind:this={textareaEl}
              class="w-full min-h-[380px] p-3 rounded bg-bg text-text border border-border text-xs font-mono outline-none focus:border-accent focus:ring-1 focus:ring-accent resize-y leading-relaxed"
              placeholder="<h1>&#123;&#123; title &#125;&#125;</h1>&#10;<p>&#123;&#123; description &#125;&#125;</p>&#10;&#10;<ul>&#10;  &#123;% for item in ModelName.order_by('-id')[:20] %&#125;&#10;    <li><a href='/model/&#123;&#123; item.id &#125;&#125;'>&#123;&#123; item.title &#125;&#125;</a></li>&#10;  &#123;% endfor %&#125;&#10;</ul>"
              bind:value={currentNode.template}
              onfocus={() => (activeField = "template")}
              onkeydown={handleTextareaKeyDown}
              oninput={triggerValidateDebounced}
            ></textarea>

            {#if !templateValid && templateError}
              <div class="mt-2 p-2.5 rounded bg-danger-subtle/50 border border-danger/40 text-danger text-xs font-mono">
                <b>⚠️ Ошибка компиляции Jinja2:</b> {templateError}
              </div>
            {/if}
          </div>
        </Card>
      </div>
    {/if}
  </div>
{/if}

<!-- МОДАЛЬНОЕ ОКНО: ГЛОБАЛЬНЫЕ НАСТРОЙКИ САЙТА И INDEXNOW -->
<Modal
  open={showSettingsModal}
  title="⚙️ Глобальные параметры сайта и поисковой оптимизации"
  maxWidth="max-w-xl"
  onclose={() => (showSettingsModal = false)}
>
  <div class="flex flex-col gap-3 text-xs p-1">
    <div>
      <div class="text-muted block mb-1">Название проекта / сайта (og:site_name, &#123;site_name&#125;)</div>
      <Input class="w-full text-xs" bind:value={siteName} />
    </div>

    <div>
      <div class="text-muted block mb-1">Базовый доменный URL (для канонических ссылок и sitemap.xml)</div>
      <Input class="w-full font-mono text-xs" bind:value={siteUrl} />
    </div>

    <div>
      <div class="text-muted block mb-1">Ключ протокола IndexNow (раздается на /&lt;key&gt;.txt)</div>
      <Input
        class="w-full font-mono text-xs"
        placeholder="Например: a1b2c3d4e5f6..."
        bind:value={indexnowKey}
      />
      <small class="text-muted block mt-0.5">
        Используется для мгновенной отправки новых URL в Яндекс и Bing по кнопке IndexNow.
      </small>
    </div>

    <div>
      <div class="text-muted block mb-1">Изображение для соцсетей по умолчанию (og:image)</div>
      <Input
        class="w-full text-xs"
        placeholder="https://example.com/assets/og-image.png"
        bind:value={defaultOgImage}
      />
    </div>

    <div>
      <div class="text-muted block mb-1">TTL кэширования карты сайта sitemap.xml (секунд)</div>
      <Input
        type="number"
        class="w-full text-xs"
        bind:value={sitemapTtl}
      />
    </div>
  </div>

  {#snippet footer()}
    <div class="flex items-center justify-between w-full">
      <small class="text-muted text-[0.7rem]">
        Изменения сохраняются в БД по кнопке «Сохранить в БД»
      </small>
      <Button
        variant="primary"
        size="sm"
        onclick={() => (showSettingsModal = false)}
      >
        Готово
      </Button>
    </div>
  {/snippet}
</Modal>
