<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import { Button, Input, Select, Card, Badge, Checkbox } from "./ui/index.js";

  let { onnotify = () => {} } = $props();

  let isLoading = $state(true);
  let isSaving = $state(false);
  let isPinging = $state(false);
  let isPreviewLoading = $state(false);
  let showPresetsModal = $state(false);

  // Глобальные настройки SEO (хранятся в pf_seo_config)
  let siteName = $state("PyFerro 2.0 Application");
  let siteUrl = $state("http://localhost:8080");
  let defaultTitle = $state("PyFerro 2.0 Application");
  let defaultDescription = $state("");
  let defaultOgImage = $state("");
  let indexnowKey = $state("");
  let sitemapTtl = $state(3600);

  // Справочники с бэкенда
  let availablePresets = $state([]);
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
    schema_type: "WebPage",
    sitemap_enabled: true,
    sitemap_priority: 1.0,
    sitemap_changefreq: "daily",
    children: [],
  });

  let selectedNodeId = $state("root");
  let activeField = $state("meta_title");

  // Валидация шаблона Jinja2 и превью
  let templateValid = $state(true);
  let templateError = $state(null);
  let previewTab = $state("google"); // "google" | "telegram" | "robot"
  let previewData = $state(null);

  let previewTimer = null;
  let validateTimer = null;

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

  let selectedModelSchema = $derived(
    availableModels.find((m) => m.key === currentNode?.model_key) || null
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
      availablePresets = data.presets || [];
      botRoutes = data.bot_routes || [];
      await refreshPreview();
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
      onnotify("Дерево сайта и SEO настройки успешно сохранены в БД!", "info");
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
          `IndexNow успешно отправлен (${res.url_count} URL передано в поисковики)`,
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

  async function toggleGuestRead(modelKey, enabled) {
    try {
      const res = await rpc.call("seo.toggle_model_read", {
        model_key: modelKey,
        enabled,
      });
      const m = availableModels.find((x) => x.key === modelKey);
      if (m) m.seo_allowed = res.seo_allowed;
      onnotify(
        `Право .read для роли guest на модель ${modelKey}: ${res.seo_allowed ? "включено" : "выключено"}`,
        "info"
      );
      triggerPreviewDebounced();
    } catch (e) {
      onnotify(e.message, "error");
    }
  }

  async function applyPreset(presetKey) {
    try {
      const res = await rpc.call("seo.apply_preset", { preset_key: presetKey });
      siteTree = res.tree;
      selectedNodeId = "root";
      showPresetsModal = false;
      onnotify(`Применен готовый шаблон структуры: ${presetKey}`, "info");
      triggerPreviewDebounced();
    } catch (e) {
      onnotify(e.message, "error");
    }
  }

  function selectNode(id) {
    selectedNodeId = id;
    triggerPreviewDebounced();
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
      template: "",
      meta_title: "{site_name}",
      meta_description: "",
      og_image: "",
      schema_type: "WebPage",
      sitemap_enabled: true,
      sitemap_priority: 0.7,
      sitemap_changefreq: "weekly",
      children: [],
    };
    parentNode.children.push(newNode);
    selectedNodeId = newId;
    triggerPreviewDebounced();
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
      triggerPreviewDebounced();
    }
  }

  function insertChip(tokenExpr) {
    if (!currentNode) return;
    if (activeField === "template") {
      currentNode.template =
        (currentNode.template || "") + `{{ ${tokenExpr} }}`;
      triggerValidateDebounced();
    } else if (activeField === "url_pattern") {
      const clean = tokenExpr.replace(/^record\./, "");
      const base = (currentNode.url_pattern || "/").replace(/\/$/, "");
      currentNode.url_pattern = `${base}/{${clean}}`;
    } else if (activeField === "meta_title") {
      const clean = tokenExpr.replace(/^record\./, "");
      currentNode.meta_title =
        (currentNode.meta_title || "") +
        (currentNode.meta_title ? " " : "") +
        `{${clean}}`;
    } else if (activeField === "meta_description") {
      const clean = tokenExpr.replace(/^record\./, "");
      currentNode.meta_description =
        (currentNode.meta_description || "") +
        (currentNode.meta_description ? " " : "") +
        `{${clean}}`;
    }
    triggerPreviewDebounced();
  }

  function insertModelLoop(modelKey) {
    if (!currentNode) return;
    const loopSnippet = `\n<ul>\n{% for item in ${modelKey} %}\n  <li><a href="/${modelKey}/{{ item.id }}">{{ item.title or item.name or item.id }}</a></li>\n{% endfor %}\n</ul>\n`;
    currentNode.template = (currentNode.template || "") + loopSnippet;
    activeField = "template";
    triggerValidateDebounced();
    triggerPreviewDebounced();
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

  function triggerPreviewDebounced() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      refreshPreview();
    }, 300);
  }

  async function refreshPreview() {
    if (!currentNode) return;
    isPreviewLoading = true;
    try {
      previewData = await rpc.call("seo.preview_node", {
        node: currentNode,
        parents: currentParents,
      });
    } catch (e) {
      // Игнорируем промежуточные ошибки при вводе
    } finally {
      isPreviewLoading = false;
    }
  }
</script>

<div class="flex items-center justify-between mb-4 flex-wrap gap-3">
  <div>
    <h2 class="m-0 text-lg font-bold text-text-bright">🌲 SEO, Дерево сайта и Dynamic Rendering</h2>
    <small class="text-muted">
      Единое дерево URL, метатеги OpenGraph / JSON-LD, песочница Jinja2 и карта сайта <code class="text-accent">/sitemap.xml</code>
    </small>
  </div>
  <div class="flex gap-2 flex-wrap items-center">
    <Button variant="outline" onclick={() => (showPresetsModal = true)}>
      📐 Шаблоны структуры
    </Button>
    <a
      class="inline-flex items-center justify-center min-h-8 h-8 px-3.5 rounded text-sm font-medium border border-border text-text hover:bg-panel-alt hover:text-text-bright no-underline transition-all"
      href="/sitemap.xml"
      target="_blank"
      rel="noreferrer"
    >
      🗺️ /sitemap.xml ↗
    </a>
    <a
      class="inline-flex items-center justify-center min-h-8 h-8 px-3.5 rounded text-sm font-medium border border-success text-success hover:bg-success-subtle no-underline transition-all"
      href="{currentNode?.url_pattern && !currentNode.url_pattern.includes('{')
        ? currentNode.url_pattern
        : '/'}?bot=1"
      target="_blank"
      rel="noreferrer"
    >
      🤖 Открыть как бот (?bot=1) ↗
    </a>
    <Button
      variant="outline"
      disabled={isPinging}
      onclick={pingIndexNow}
    >
      ⚡ {isPinging ? "Отправка..." : "IndexNow Ping"}
    </Button>
    <Button variant="primary" disabled={isSaving} onclick={saveSeoData}>
      💾 {isSaving ? "Сохранение..." : "Сохранить в БД"}
    </Button>
  </div>
</div>

{#if showPresetsModal}
  <Card class="mb-5 border-accent">
    <div class="flex items-center justify-between pb-3 mb-3 border-b border-border-subtle font-bold text-sm text-text-bright">
      <span>Выберите готовый шаблон структуры дерева сайта</span>
      <Button
        variant="outline"
        size="sm"
        onclick={() => (showPresetsModal = false)}
      >
        ✕ Закрыть
      </Button>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {#each availablePresets as p}
        <Card class="bg-bg">
          <div class="font-bold text-sm text-text-bright mb-1.5">
            {p.icon} {p.title}
          </div>
          <p class="text-xs text-muted mt-0 mb-3">
            {p.description}
          </p>
          <Button
            variant="outline"
            size="sm"
            onclick={() => applyPreset(p.key)}
          >
            Применить шаблон
          </Button>
        </Card>
      {/each}
    </div>
  </Card>
{/if}

{#if isLoading}
  <Card class="text-muted">Загрузка дерева сайта и конфигурации SEO из БД...</Card>
{:else}
  <div class="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-5 items-start">
    <!-- ЛЕВАЯ КОЛОНКА: Дерево сайта, глобальные настройки и доступ гостей к таблицам -->
    <div class="flex flex-col gap-4">
      <!-- 1. Живое дерево сайта -->
      <Card>
        <div class="flex items-center justify-between pb-3 mb-3 border-b border-border-subtle font-bold text-sm text-text-bright">
          <span>Дерево страниц сайта</span>
          <Button
            variant="outline"
            size="sm"
            onclick={() => addChildNode(currentNode)}
          >
            + Подраздел
          </Button>
        </div>

        {#snippet treeItem(node, depth)}
          <button
            type="button"
            class="w-full text-left mb-1.5 p-2 rounded cursor-pointer flex items-center justify-between border transition-colors {selectedNodeId === node.id ? 'border-accent bg-accent-subtle text-text-bright' : 'border-border-subtle bg-bg hover:bg-panel-hover text-text'}"
            style="margin-left: {depth * 14}px;"
            onclick={() => selectNode(node.id)}
          >
            <div class="overflow-hidden text-ellipsis whitespace-nowrap mr-2">
              <span class="mr-1.5">
                {#if node.node_type === "collection"}📁{:else if node.node_type === "detail"}🏷️{:else}📄{/if}
              </span>
              <b class="text-xs font-semibold">{node.title}</b>
              <div class="text-[0.72rem] text-muted font-mono">
                {node.url_pattern}
              </div>
            </div>
            {#if node.model_key}
              <Badge variant="accent">{node.model_key}</Badge>
            {/if}
          </button>
          {#each node.children || [] as child}
            {@render treeItem(child, depth + 1)}
          {/each}
        {/snippet}

        {@render treeItem(siteTree, 0)}
      </Card>

      <!-- 2. Публичный доступ таблиц (guest -> Model.read) -->
      <Card>
        <div class="flex items-center justify-between pb-2 mb-2 border-b border-border-subtle font-bold text-sm text-text-bright">
          <span>Доступ таблиц для ботов (guest)</span>
          <Badge variant="default">Model.read</Badge>
        </div>
        <small class="text-muted block mb-3 text-xs">
          Поисковые роботы индексируют только те таблицы, для которых у роли
          <code class="text-accent">guest</code> включено право <code class="text-accent">.read</code>:
        </small>
        {#if availableModels.length === 0}
          <div class="text-xs text-muted">
            Нет зарегистрированных прикладных таблиц
          </div>
        {:else}
          <div class="flex flex-col gap-2">
            {#each availableModels as m}
              <div class="flex items-center justify-between p-2 rounded bg-bg border border-border-subtle text-xs">
                <span>
                  <b class="text-text-bright">{m.key}</b>
                  <small class="text-muted">({m.verbose_name})</small>
                </span>
                <Checkbox
                  checked={m.seo_allowed}
                  onchange={(e) =>
                    toggleGuestRead(m.key, e.currentTarget.checked)}
                />
              </div>
            {/each}
          </div>
        {/if}
      </Card>

      <!-- 3. Глобальные настройки домена и IndexNow -->
      <Card>
        <div class="pb-2 mb-3 border-b border-border-subtle font-bold text-sm text-text-bright">
          <span>Глобальные параметры сайта</span>
        </div>
        <div class="flex flex-col gap-3 text-xs">
          <div>
            <div class="text-muted block mb-1">Название сайта (og:site_name)</div>
            <Input class="w-full" bind:value={siteName} />
          </div>
          <div>
            <div class="text-muted block mb-1">Базовый URL (для канонических ссылок и Sitemap)</div>
            <Input class="w-full" bind:value={siteUrl} />
          </div>
          <div>
            <div class="text-muted block mb-1">Ключ IndexNow (раздается на /&lt;key&gt;.txt)</div>
            <Input
              class="w-full"
              placeholder="Например: my-indexnow-key-123"
              bind:value={indexnowKey}
            />
          </div>
          <div>
            <div class="text-muted block mb-1">Картинка соцсетей по умолчанию (og:image)</div>
            <Input
              class="w-full"
              placeholder="https://example.com/og.png"
              bind:value={defaultOgImage}
            />
          </div>
        </div>
      </Card>

      {#if botRoutes.length > 0}
        <Card>
          <div class="flex items-center justify-between pb-2 mb-2 border-b border-border-subtle font-bold text-sm text-text-bright">
            <span>Кодовые маршруты (@bot_page)</span>
            <Badge variant="default">{botRoutes.length}</Badge>
          </div>
          <div class="flex flex-wrap gap-1.5">
            {#each botRoutes as br}
              <Badge variant="accent">{br}</Badge>
            {/each}
          </div>
        </Card>
      {/if}
    </div>

    <!-- ПРАВАЯ КОЛОНКА: Редактор выбранного узла + Чипсы + Живой симулятор (Google / Telegram / Бот) -->
    {#if currentNode}
      <div class="flex flex-col gap-4">
        <Card>
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-border-subtle font-bold text-sm text-text-bright flex-wrap gap-2">
            <span class="flex items-center gap-2">
              <span>Редактирование узла: <b>{currentNode.title}</b></span>
              <code class="text-xs font-mono bg-bg px-1.5 py-0.5 rounded text-accent">{currentNode.url_pattern}</code>
            </span>
            {#if selectedNodeId !== "root"}
              <Button
                variant="danger"
                size="sm"
                onclick={deleteSelectedNode}
              >
                Удалить узел
              </Button>
            {/if}
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div>
              <div class="text-xs text-muted block mb-1">Название в хлебных крошках</div>
              <Input
                class="w-full"
                bind:value={currentNode.title}
                oninput={triggerPreviewDebounced}
              />
            </div>

            <div>
              <div class="text-xs text-muted block mb-1">Шаблон URL (например /books/&#123;id&#125;)</div>
              <Input
                class="w-full font-mono"
                bind:value={currentNode.url_pattern}
                disabled={selectedNodeId === "root"}
                onfocus={() => (activeField = "url_pattern")}
                oninput={triggerPreviewDebounced}
              />
            </div>

            <div>
              <div class="text-xs text-muted block mb-1">Тип узла</div>
              <Select
                class="w-full"
                bind:value={currentNode.node_type}
                onchange={triggerPreviewDebounced}
              >
                <option value="static">📄 Статическая страница (static)</option>
                <option value="collection">📁 Раздел / список записей (collection)</option>
                <option value="detail">🏷️ Детальная карточка из БД (detail)</option>
              </Select>
            </div>

            <div>
              <div class="text-xs text-muted block mb-1">Привязка к таблице БД (CRUD)</div>
              <Select
                class="w-full"
                bind:value={currentNode.model_key}
                onchange={triggerPreviewDebounced}
              >
                <option value={null}>— Без привязки к таблице —</option>
                {#each availableModels as m}
                  <option value={m.key}>
                    {m.key} ({m.verbose_name}) {m.seo_allowed ? "✓" : "🔒"}
                  </option>
                {/each}
              </Select>
            </div>
          </div>

          <!-- Панель быстрых чипсов для подстановки полей БД и циклов -->
          <div class="bg-bg border border-border-subtle rounded-md p-3 mb-3">
            <div class="flex items-center justify-between flex-wrap gap-2">
              <small class="text-xs text-muted">
                Быстрая вставка в поле <code class="text-accent">{activeField}</code>:
              </small>
              <div class="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  class="cursor-pointer"
                  onclick={() => insertChip("site_name")}
                >
                  <Badge variant="accent">+ &#123;site_name&#125;</Badge>
                </button>
                {#if selectedModelSchema}
                  {#each selectedModelSchema.fields as f}
                    <button
                      type="button"
                      class="cursor-pointer"
                      onclick={() => insertChip(f.name)}
                    >
                      <Badge variant="default">+ &#123;{f.name}&#125;</Badge>
                    </button>
                  {/each}
                  {#each selectedModelSchema.relations || [] as rel}
                    {#each rel.fields as rf}
                      <button
                        type="button"
                        class="cursor-pointer"
                        onclick={() => insertChip(rf.chip)}
                      >
                        <Badge variant="accent">+ &#123;{rf.chip}&#125;</Badge>
                      </button>
                    {/each}
                  {/each}
                {/if}
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div>
              <div class="text-xs text-muted block mb-1">SEO Заголовок (Title / og:title)</div>
              <Input
                class="w-full"
                bind:value={currentNode.meta_title}
                onfocus={() => (activeField = "meta_title")}
                oninput={triggerPreviewDebounced}
              />
            </div>

            <div>
              <div class="text-xs text-muted block mb-1">Тип микроразметки Schema.org (@type)</div>
              <Select
                class="w-full"
                bind:value={currentNode.schema_type}
                onchange={triggerPreviewDebounced}
              >
                <option value="WebPage">WebPage</option>
                <option value="WebSite">WebSite</option>
                <option value="CollectionPage">CollectionPage</option>
                <option value="Article">Article (Статья / Новость)</option>
                <option value="Book">Book (Книга)</option>
                <option value="Product">Product (Товар)</option>
                <option value="DiscussionForumPosting">DiscussionForumPosting (Форум)</option>
                <option value="AboutPage">AboutPage</option>
                <option value="ContactPage">ContactPage</option>
              </Select>
            </div>
          </div>

          <div class="mb-3">
            <div class="text-xs text-muted block mb-1">Мета-описание (meta description / og:description)</div>
            <textarea
              class="w-full min-h-[64px] px-3 py-2 rounded bg-bg text-text border border-border text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent-subtle resize-y"
              rows="2"
              bind:value={currentNode.meta_description}
              onfocus={() => (activeField = "meta_description")}
              oninput={triggerPreviewDebounced}
            ></textarea>
          </div>

          {#if currentNode.node_type === "collection"}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3 p-3 rounded-md bg-bg border border-border-subtle">
              <div>
                <div class="text-xs text-muted block mb-1">Шаблон ссылки элемента</div>
                <Input
                  class="w-full font-mono text-xs"
                  placeholder="/books/&#123;id&#125;"
                  bind:value={currentNode.item_link_pattern}
                  oninput={triggerPreviewDebounced}
                />
              </div>
              <div>
                <div class="text-xs text-muted block mb-1">Заголовок элемента</div>
                <Input
                  class="w-full text-xs"
                  placeholder="&#123;title&#125;"
                  bind:value={currentNode.item_title_pattern}
                  oninput={triggerPreviewDebounced}
                />
              </div>
              <div>
                <div class="text-xs text-muted block mb-1">Описание элемента</div>
                <Input
                  class="w-full text-xs"
                  placeholder="&#123;author&#125;"
                  bind:value={currentNode.item_desc_pattern}
                  oninput={triggerPreviewDebounced}
                />
              </div>
            </div>
          {/if}

          <!-- Кастомный шаблон Jinja2 (опционально) -->
          <div class="mb-3">
            <div class="flex items-center justify-between mb-1.5 flex-wrap gap-2">
              <small class="text-xs text-muted">
                Кастомный HTML-шаблон Jinja2 для бота (оставьте пустым для авто-генерации):
              </small>
              <div class="flex gap-1.5 flex-wrap">
                {#each availableModels as m}
                  <button
                    type="button"
                    class="cursor-pointer"
                    onclick={() => insertModelLoop(m.key)}
                  >
                    <Badge variant="accent">+ Цикл &#123;% for item in {m.key} %&#125;</Badge>
                  </button>
                {/each}
              </div>
            </div>
            <textarea
              class="w-full min-h-[120px] px-3 py-2 rounded bg-bg text-text border border-border text-xs font-mono outline-none focus:border-accent focus:ring-2 focus:ring-accent-subtle"
              rows="6"
              placeholder="<h1>&#123;&#123; title &#125;&#125;</h1>&#10;<p>&#123;&#123; description &#125;&#125;</p>"
              bind:value={currentNode.template}
              onfocus={() => (activeField = "template")}
              oninput={() => {
                triggerValidateDebounced();
                triggerPreviewDebounced();
              }}
            ></textarea>
            {#if !templateValid && templateError}
              <div class="text-danger text-xs mt-1">
                ⚠️ {templateError}
              </div>
            {/if}
          </div>

          <!-- Параметры Sitemap для узла -->
          <div class="flex items-center gap-5 flex-wrap pt-3 border-t border-border-subtle text-xs">
            <Checkbox
              bind:checked={currentNode.sitemap_enabled}
              label="Включить в /sitemap.xml"
            />
            <div class="flex items-center gap-2">
              <span class="text-muted">Приоритет:</span>
              <Input
                type="number"
                step="0.1"
                min="0.1"
                max="1.0"
                class="w-20 h-7 min-h-7 text-xs py-0"
                bind:value={currentNode.sitemap_priority}
              />
            </div>
            <div class="flex items-center gap-2">
              <span class="text-muted">Частота:</span>
              <Select
                class="h-7 min-h-7 text-xs py-0"
                bind:value={currentNode.sitemap_changefreq}
                options={["always", "hourly", "daily", "weekly", "monthly"]}
              />
            </div>
          </div>
        </Card>

        <!-- ЖИВОЙ СИМУЛЯТОР ПРЕВЬЮ (Google / Telegram / Семантический HTML робота) -->
        <Card>
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-border-subtle font-bold text-sm text-text-bright flex-wrap gap-2">
            <span>
              👁️ Живой симулятор: как страницу видит поисковик и мессенджер
              {#if isPreviewLoading}
                <small class="text-muted font-normal">(обновление...)</small>
              {/if}
            </span>
            <div class="flex gap-1.5">
              <Button
                variant={previewTab === 'google' ? 'primary' : 'outline'}
                size="sm"
                onclick={() => (previewTab = "google")}
              >
                🔍 Google / Яндекс
              </Button>
              <Button
                variant={previewTab === 'telegram' ? 'primary' : 'outline'}
                size="sm"
                onclick={() => (previewTab = "telegram")}
              >
                💬 Telegram / Соцсети
              </Button>
              <Button
                variant={previewTab === 'robot' ? 'primary' : 'outline'}
                size="sm"
                onclick={() => (previewTab = "robot")}
              >
                🤖 Семантический HTML бота
              </Button>
            </div>
          </div>

          {#if previewData}
            {#if previewTab === "google"}
              <!-- Точный симулятор сниппета выдачи Google -->
              <div class="bg-white text-[#202124] p-4 rounded-lg max-w-2xl border border-gray-200 shadow-sm">
                <div class="text-xs text-[#4d5156] mb-1">
                  {siteUrl.replace(/\/$/, "")}{previewData.url || "/"}
                </div>
                <div class="text-lg text-[#1a0dab] font-medium mb-1 hover:underline cursor-pointer">
                  {previewData.title || "Без заголовка"}
                </div>
                <div class="text-sm text-[#4d5156] leading-relaxed">
                  {previewData.description || "Описание не указано"}
                </div>
                {#if previewData.breadcrumbs && previewData.breadcrumbs.length > 0}
                  <div class="mt-2 text-xs text-[#5f6368]">
                    Хлебные крошки Schema.org:
                    {previewData.breadcrumbs.map((b) => b.title).join(" › ")}
                  </div>
                {/if}
              </div>
            {:else if previewTab === "telegram"}
              <!-- Точный симулятор превью в Telegram -->
              <div class="bg-[#182533] border-l-4 border-[#38bdf8] p-3.5 rounded max-w-lg shadow-sm">
                <div class="text-xs text-[#38bdf8] font-bold mb-1">
                  {siteName}
                </div>
                <div class="font-bold text-[#f8fafc] text-sm mb-1">
                  {previewData.title || "Без заголовка"}
                </div>
                <div class="text-xs text-[#cbd5e1] leading-relaxed">
                  {previewData.description || ""}
                </div>
              </div>
            {:else}
              <div class="bg-bg border border-border-subtle rounded-md p-3 font-mono text-xs text-text whitespace-pre-wrap max-h-80 overflow-y-auto">
                {previewData.body_html || ""}
              </div>
            {/if}
          {/if}
        </Card>
      </div>
    {/if}
  </div>
{/if}
