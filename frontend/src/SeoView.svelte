<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";

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
      const res = await rpc.call("seo.save_tree", {
        tree: siteTree,
        site_url: siteUrl,
        site_name: siteName,
        default_title: defaultTitle,
        default_description: defaultDescription,
        default_og_image: defaultOgImage,
        indexnow_key: indexnowKey,
        sitemap_ttl: Number(sitemapTtl) || 3600,
      });
      if (res.tree) {
        siteTree = res.tree;
      }
      onnotify(res.message || "Настройки SEO и дерево сайта сохранены", "success");
      await refreshPreview();
    } catch (e) {
      onnotify(e.message, "error");
    } finally {
      isSaving = false;
    }
  }

  async function applyPreset(presetKey) {
    try {
      const res = await rpc.call("seo.apply_preset", { preset_key: presetKey });
      if (res.tree) {
        siteTree = res.tree;
        selectedNodeId = "root";
      }
      showPresetsModal = false;
      onnotify(res.message || "Шаблон применен", "success");
      await refreshPreview();
    } catch (e) {
      onnotify(e.message, "error");
    }
  }

  async function toggleGuestRead(modelKey, checked) {
    try {
      const res = await rpc.call("seo.toggle_guest_read", {
        model_key: modelKey,
        allowed: checked,
      });
      availableModels = availableModels.map((m) =>
        m.key === modelKey ? { ...m, seo_allowed: res.seo_allowed } : m
      );
      onnotify(
        checked
          ? `Таблица ${modelKey} открыта для гостей и поисковых роботов (${modelKey}.read)`
          : `Публичный доступ к ${modelKey} закрыт`,
        "success"
      );
      await refreshPreview();
    } catch (e) {
      onnotify(e.message, "error");
    }
  }

  async function pingIndexNow() {
    isPinging = true;
    try {
      const res = await rpc.call("seo.ping_indexnow");
      onnotify(res.message || "IndexNow уведомлен", "success");
    } catch (e) {
      onnotify(e.message, "error");
    } finally {
      isPinging = false;
    }
  }

  function selectNode(id) {
    selectedNodeId = id;
    triggerPreviewDebounced();
  }

  function addChildNode(parentNode = currentNode) {
    if (!parentNode) return;
    if (!parentNode.children) {
      parentNode.children = [];
    }
    const newId = "node_" + Math.random().toString(36).slice(2, 8);
    const parentUrl =
      parentNode.url_pattern === "/" ? "" : parentNode.url_pattern || "";
    const newNode = {
      id: newId,
      title: "Новый раздел",
      url_pattern: `${parentUrl}/new-section`,
      node_type: "static",
      template: "",
      meta_title: "Новый раздел — {site_name}",
      meta_description: "Описание нового раздела",
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
    const snippet = `\n<h2>${modelKey}:</h2>\n<ul>\n{% for item in ${modelKey} %}\n  <li><a href="/${modelKey.toLowerCase()}s/{{ item.id }}">{{ item.title or item.name or item.id }}</a></li>\n{% endfor %}\n</ul>\n`;
    currentNode.template = (currentNode.template || "") + snippet;
    triggerValidateDebounced();
    triggerPreviewDebounced();
  }

  function triggerValidateDebounced() {
    clearTimeout(validateTimer);
    validateTimer = setTimeout(async () => {
      if (!currentNode) return;
      try {
        const res = await rpc.call("seo.validate_template", {
          template: currentNode.template || "",
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

<div class="row-between">
  <div>
    <h2 style="margin:0;">🌲 SEO, Дерево сайта и Dynamic Rendering</h2>
    <small style="color: var(--muted);">
      Единое дерево URL, метатеги OpenGraph / JSON-LD, песочница Jinja2 и карта
      сайта <code>/sitemap.xml</code>
    </small>
  </div>
  <div style="display:flex; gap: 0.5rem; flex-wrap:wrap; align-items:center;">
    <button class="btn btn-outline" onclick={() => (showPresetsModal = true)}>
      📐 Шаблоны структуры
    </button>
    <a
      class="btn btn-outline"
      style="text-decoration:none;"
      href="/sitemap.xml"
      target="_blank"
      rel="noreferrer"
    >
      🗺️ /sitemap.xml ↗
    </a>
    <a
      class="btn btn-outline"
      style="text-decoration:none; border-color: var(--success); color: var(--success);"
      href="{currentNode?.url_pattern && !currentNode.url_pattern.includes('{')
        ? currentNode.url_pattern
        : '/'}?bot=1"
      target="_blank"
      rel="noreferrer"
    >
      🤖 Открыть как бот (?bot=1) ↗
    </a>
    <button
      class="btn btn-outline"
      disabled={isPinging}
      onclick={pingIndexNow}
    >
      ⚡ {isPinging ? "Отправка..." : "IndexNow Ping"}
    </button>
    <button class="btn" disabled={isSaving} onclick={saveSeoData}>
      💾 {isSaving ? "Сохранение..." : "Сохранить в БД"}
    </button>
  </div>
</div>

{#if showPresetsModal}
  <div class="card" style="margin-bottom: 1.25rem; border-color: var(--accent);">
    <div class="card-header">
      <span>Выберите готовый шаблон структуры дерева сайта</span>
      <button
        class="btn btn-outline"
        style="padding: 0.25rem 0.6rem;"
        onclick={() => (showPresetsModal = false)}
      >
        ✕ Закрыть
      </button>
    </div>
    <div class="card-grid">
      {#each availablePresets as p}
        <div class="card" style="background: var(--bg);">
          <div style="font-weight:700; margin-bottom: 0.35rem;">
            {p.icon} {p.title}
          </div>
          <p style="font-size: 0.84rem; color: var(--muted); margin-top:0;">
            {p.description}
          </p>
          <button
            class="btn btn-outline"
            onclick={() => applyPreset(p.key)}
          >
            Применить шаблон
          </button>
        </div>
      {/each}
    </div>
  </div>
{/if}

{#if isLoading}
  <div class="card">Загрузка дерева сайта и конфигурации SEO из БД...</div>
{:else}
  <div
    style="display:grid; grid-template-columns: 360px 1fr; gap: 1.25rem; align-items:start;"
  >
    <!-- ЛЕВАЯ КОЛОНКА: Дерево сайта, глобальные настройки и доступ гостей к таблицам -->
    <div style="display:flex; flex-direction:column; gap: 1rem;">
      <!-- 1. Живое дерево сайта -->
      <div class="card">
        <div class="card-header">
          <span>Дерево страниц сайта</span>
          <button
            class="btn btn-outline"
            style="padding: 0.25rem 0.6rem; font-size: 0.8rem;"
            onclick={() => addChildNode(currentNode)}
          >
            + Подраздел
          </button>
        </div>

        {#snippet treeItem(node, depth)}
          <div
            style="margin-left: {depth * 14}px; margin-bottom: 0.35rem; padding: 0.45rem 0.6rem; border-radius: 0.45rem; cursor: pointer; display:flex; align-items:center; justify-content:space-between; border: 1px solid {selectedNodeId === node.id ? 'var(--accent)' : 'var(--border)'}; background: {selectedNodeId === node.id ? 'rgba(56, 189, 248, 0.14)' : 'var(--bg)'};"
            onclick={() => selectNode(node.id)}
          >
            <div style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
              <span style="margin-right:0.35rem;">
                {#if node.node_type === "collection"}📁{:else if node.node_type === "detail"}🏷️{:else}📄{/if}
              </span>
              <b style="font-size:0.86rem;">{node.title}</b>
              <div style="font-size:0.74rem; color: var(--muted); font-family:monospace;">
                {node.url_pattern}
              </div>
            </div>
            {#if node.model_key}
              <span class="badge badge-sys">{node.model_key}</span>
            {/if}
          </div>
          {#each node.children || [] as child}
            {@render treeItem(child, depth + 1)}
          {/each}
        {/snippet}

        {@render treeItem(siteTree, 0)}
      </div>

      <!-- 2. Публичный доступ таблиц (guest -> Model.read) -->
      <div class="card">
        <div class="card-header">
          <span>Доступ таблиц для ботов (guest)</span>
          <span class="badge">Model.read</span>
        </div>
        <small style="color: var(--muted); display:block; margin-bottom: 0.65rem;">
          Поисковые роботы индексируют только те таблицы, для которых у роли
          <code>guest</code> включено право <code>.read</code>:
        </small>
        {#if availableModels.length === 0}
          <div style="font-size: 0.85rem; color: var(--muted);">
            Нет зарегистрированных прикладных таблиц
          </div>
        {:else}
          <div style="display:flex; flex-direction:column; gap: 0.45rem;">
            {#each availableModels as m}
              <label
                style="display:flex; align-items:center; justify-content:space-between; padding: 0.35rem 0.5rem; border-radius: 0.4rem; background: var(--bg); border: 1px solid var(--border); font-size: 0.85rem;"
              >
                <span>
                  <b>{m.key}</b>
                  <small style="color: var(--muted);">({m.verbose_name})</small>
                </span>
                <input
                  type="checkbox"
                  checked={m.seo_allowed}
                  onchange={(e) =>
                    toggleGuestRead(m.key, e.currentTarget.checked)}
                />
              </label>
            {/each}
          </div>
        {/if}
      </div>

      <!-- 3. Глобальные настройки домена и IndexNow -->
      <div class="card">
        <div class="card-header">
          <span>Глобальные параметры сайта</span>
        </div>
        <div style="display:flex; flex-direction:column; gap: 0.6rem;">
          <div>
            <small style="color: var(--muted);">Название сайта (og:site_name)</small>
            <input
              class="input"
              style="width:100%;"
              bind:value={siteName}
            />
          </div>
          <div>
            <small style="color: var(--muted);">Базовый URL (для канонических ссылок и Sitemap)</small>
            <input
              class="input"
              style="width:100%;"
              bind:value={siteUrl}
            />
          </div>
          <div>
            <small style="color: var(--muted);">Ключ IndexNow (раздается на /&lt;key&gt;.txt)</small>
            <input
              class="input"
              style="width:100%;"
              placeholder="Например: my-indexnow-key-123"
              bind:value={indexnowKey}
            />
          </div>
          <div>
            <small style="color: var(--muted);">Картинка соцсетей по умолчанию (og:image)</small>
            <input
              class="input"
              style="width:100%;"
              placeholder="https://example.com/og.png"
              bind:value={defaultOgImage}
            />
          </div>
        </div>
      </div>

      {#if botRoutes.length > 0}
        <div class="card">
          <div class="card-header">
            <span>Кодовые маршруты (@bot_page)</span>
            <span class="badge">{botRoutes.length}</span>
          </div>
          <div style="display:flex; flex-wrap:wrap; gap: 0.35rem;">
            {#each botRoutes as br}
              <code class="badge badge-sys">{br}</code>
            {/each}
          </div>
        </div>
      {/if}
    </div>

    <!-- ПРАВАЯ КОЛОНКА: Редактор выбранного узла + Чипсы + Живой симулятор (Google / Telegram / Бот) -->
    {#if currentNode}
      <div style="display:flex; flex-direction:column; gap: 1rem;">
        <div class="card">
          <div class="card-header">
            <span>
              Редактирование узла: <b>{currentNode.title}</b>
              <code style="margin-left: 0.5rem; font-size:0.85rem;">{currentNode.url_pattern}</code>
            </span>
            {#if selectedNodeId !== "root"}
              <button
                class="btn btn-danger"
                style="padding: 0.25rem 0.65rem; font-size: 0.8rem;"
                onclick={deleteSelectedNode}
              >
                Удалить узел
              </button>
            {/if}
          </div>

          <div
            style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; margin-bottom: 0.85rem;"
          >
            <div>
              <small style="color: var(--muted);">Название в хлебных крошках</small>
              <input
                class="input"
                style="width:100%;"
                bind:value={currentNode.title}
                oninput={triggerPreviewDebounced}
              />
            </div>

            <div>
              <small style="color: var(--muted);">Шаблон URL (например /books/&#123;id&#125;)</small>
              <input
                class="input"
                style="width:100%; font-family:monospace;"
                bind:value={currentNode.url_pattern}
                disabled={selectedNodeId === "root"}
                onfocus={() => (activeField = "url_pattern")}
                oninput={triggerPreviewDebounced}
              />
            </div>

            <div>
              <small style="color: var(--muted);">Тип узла</small>
              <select
                class="input"
                style="width:100%;"
                bind:value={currentNode.node_type}
                onchange={triggerPreviewDebounced}
              >
                <option value="static">📄 Статическая страница (static)</option>
                <option value="collection">📁 Раздел / список записей (collection)</option>
                <option value="detail">🏷️ Детальная карточка из БД (detail)</option>
              </select>
            </div>

            <div>
              <small style="color: var(--muted);">Привязка к таблице БД (CRUD)</small>
              <select
                class="input"
                style="width:100%;"
                bind:value={currentNode.model_key}
                onchange={triggerPreviewDebounced}
              >
                <option value={null}>— Без привязки к таблице —</option>
                {#each availableModels as m}
                  <option value={m.key}>
                    {m.key} ({m.verbose_name}) {m.seo_allowed ? "✓" : "🔒"}
                  </option>
                {/each}
              </select>
            </div>
          </div>

          <!-- Панель быстрых чипсов для подстановки полей БД и циклов -->
          <div
            style="background: var(--bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.6rem 0.75rem; margin-bottom: 0.85rem;"
          >
            <div
              style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap: 0.5rem;"
            >
              <small style="color: var(--muted);">
                Быстрая вставка в поле <code>{activeField}</code>:
              </small>
              <div style="display:flex; flex-wrap:wrap; gap: 0.35rem;">
                <button
                  type="button"
                  class="badge badge-sys"
                  style="cursor:pointer;"
                  onclick={() => insertChip("site_name")}
                >
                  + &#123;site_name&#125;
                </button>
                {#if selectedModelSchema}
                  {#each selectedModelSchema.fields as f}
                    <button
                      type="button"
                      class="badge"
                      style="cursor:pointer; color: var(--text);"
                      onclick={() => insertChip(f.name)}
                    >
                      + &#123;{f.name}&#125;
                    </button>
                  {/each}
                  {#each selectedModelSchema.relations || [] as rel}
                    {#each rel.fields as rf}
                      <button
                        type="button"
                        class="badge badge-sys"
                        style="cursor:pointer;"
                        onclick={() => insertChip(rf.chip)}
                      >
                        + &#123;{rf.chip}&#125;
                      </button>
                    {/each}
                  {/each}
                {/if}
              </div>
            </div>
          </div>

          <div
            style="display:grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.85rem;"
          >
            <div>
              <small style="color: var(--muted);">SEO Заголовок (Title / og:title)</small>
              <input
                class="input"
                style="width:100%;"
                bind:value={currentNode.meta_title}
                onfocus={() => (activeField = "meta_title")}
                oninput={triggerPreviewDebounced}
              />
            </div>

            <div>
              <small style="color: var(--muted);">Тип микроразметки Schema.org (@type)</small>
              <select
                class="input"
                style="width:100%;"
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
              </select>
            </div>
          </div>

          <div style="margin-bottom: 0.85rem;">
            <small style="color: var(--muted);">Мета-описание (meta description / og:description)</small>
            <textarea
              class="input"
              rows="2"
              style="width:100%; resize:vertical;"
              bind:value={currentNode.meta_description}
              onfocus={() => (activeField = "meta_description")}
              oninput={triggerPreviewDebounced}
            ></textarea>
          </div>

          {#if currentNode.node_type === "collection"}
            <div
              style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.75rem; margin-bottom: 0.85rem; padding: 0.65rem; border-radius: 0.5rem; background: var(--bg); border: 1px solid var(--border);"
            >
              <div>
                <small style="color: var(--muted);">Шаблон ссылки элемента</small>
                <input
                  class="input"
                  style="width:100%; font-family:monospace;"
                  placeholder="/books/&#123;id&#125;"
                  bind:value={currentNode.item_link_pattern}
                  oninput={triggerPreviewDebounced}
                />
              </div>
              <div>
                <small style="color: var(--muted);">Заголовок элемента</small>
                <input
                  class="input"
                  style="width:100%;"
                  placeholder="&#123;title&#125;"
                  bind:value={currentNode.item_title_pattern}
                  oninput={triggerPreviewDebounced}
                />
              </div>
              <div>
                <small style="color: var(--muted);">Описание элемента</small>
                <input
                  class="input"
                  style="width:100%;"
                  placeholder="&#123;author&#125;"
                  bind:value={currentNode.item_desc_pattern}
                  oninput={triggerPreviewDebounced}
                />
              </div>
            </div>
          {/if}

          <!-- Кастомный шаблон Jinja2 (опционально) -->
          <div style="margin-bottom: 0.85rem;">
            <div class="row-between" style="margin-bottom: 0.35rem;">
              <small style="color: var(--muted);">
                Кастомный HTML-шаблон Jinja2 для бота (оставьте пустым для авто-генерации):
              </small>
              <div style="display:flex; gap: 0.35rem; flex-wrap:wrap;">
                {#each availableModels as m}
                  <button
                    type="button"
                    class="badge badge-sys"
                    style="cursor:pointer;"
                    onclick={() => insertModelLoop(m.key)}
                  >
                    + Цикл &#123;% for item in {m.key} %&#125;
                  </button>
                {/each}
              </div>
            </div>
            <textarea
              class="input"
              rows="6"
              style="width:100%; font-family:monospace; font-size: 0.84rem;"
              placeholder="<h1>&#123;&#123; title &#125;&#125;</h1>&#10;<p>&#123;&#123; description &#125;&#125;</p>"
              bind:value={currentNode.template}
              onfocus={() => (activeField = "template")}
              oninput={() => {
                triggerValidateDebounced();
                triggerPreviewDebounced();
              }}
            ></textarea>
            {#if !templateValid && templateError}
              <div style="color: var(--danger); font-size: 0.8rem; margin-top: 0.25rem;">
                ⚠️ {templateError}
              </div>
            {/if}
          </div>

          <!-- Параметры Sitemap для узла -->
          <div
            style="display:flex; align-items:center; gap: 1.25rem; flex-wrap:wrap; padding-top: 0.5rem; border-top: 1px solid var(--border);"
          >
            <label style="display:inline-flex; align-items:center; gap: 0.4rem; font-size: 0.86rem;">
              <input
                type="checkbox"
                bind:checked={currentNode.sitemap_enabled}
              />
              <span>Включить в /sitemap.xml</span>
            </label>
            <label style="display:inline-flex; align-items:center; gap: 0.4rem; font-size: 0.86rem;">
              <span style="color: var(--muted);">Приоритет:</span>
              <input
                class="input"
                type="number"
                step="0.1"
                min="0.1"
                max="1.0"
                style="width: 75px; padding: 0.25rem 0.4rem;"
                bind:value={currentNode.sitemap_priority}
              />
            </label>
            <label style="display:inline-flex; align-items:center; gap: 0.4rem; font-size: 0.86rem;">
              <span style="color: var(--muted);">Частота:</span>
              <select
                class="input"
                style="padding: 0.25rem 0.5rem;"
                bind:value={currentNode.sitemap_changefreq}
              >
                <option value="always">always</option>
                <option value="hourly">hourly</option>
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
                <option value="monthly">monthly</option>
              </select>
            </label>
          </div>
        </div>

        <!-- ЖИВОЙ СИМУЛЯТОР ПРЕВЬЮ (Google / Telegram / Семантический HTML робота) -->
        <div class="card">
          <div class="card-header">
            <span>
              👁️ Живой симулятор: как страницу видит поисковик и мессенджер
              {#if isPreviewLoading}
                <small style="color: var(--muted); font-weight:normal;">(обновление...)</small>
              {/if}
            </span>
            <div style="display:flex; gap: 0.35rem;">
              <button
                class="btn {previewTab === 'google' ? '' : 'btn-outline'}"
                style="padding: 0.25rem 0.65rem; font-size: 0.8rem;"
                onclick={() => (previewTab = "google")}
              >
                🔍 Google / Яндекс
              </button>
              <button
                class="btn {previewTab === 'telegram' ? '' : 'btn-outline'}"
                style="padding: 0.25rem 0.65rem; font-size: 0.8rem;"
                onclick={() => (previewTab = "telegram")}
              >
                💬 Telegram / Соцсети
              </button>
              <button
                class="btn {previewTab === 'robot' ? '' : 'btn-outline'}"
                style="padding: 0.25rem 0.65rem; font-size: 0.8rem;"
                onclick={() => (previewTab = "robot")}
              >
                🤖 Семантический HTML бота
              </button>
            </div>
          </div>

          {#if previewData}
            {#if previewTab === "google"}
              <div
                style="background: #ffffff; color: #202124; padding: 1.1rem 1.35rem; border-radius: 0.55rem; max-width: 650px;"
              >
                <div style="font-size: 0.78rem; color: #4d5156; margin-bottom: 0.2rem;">
                  {siteUrl.replace(/\/$/, "")}{previewData.url || "/"}
                </div>
                <div
                  style="font-size: 1.15rem; color: #1a0dab; font-weight: 500; margin-bottom: 0.25rem;"
                >
                  {previewData.title || "Без заголовка"}
                </div>
                <div style="font-size: 0.86rem; color: #4d5156; line-height: 1.4;">
                  {previewData.description || "Описание не указано"}
                </div>
                {#if previewData.breadcrumbs && previewData.breadcrumbs.length > 0}
                  <div
                    style="margin-top: 0.55rem; font-size: 0.76rem; color: #5f6368;"
                  >
                    Хлебные крошки Schema.org:
                    {previewData.breadcrumbs.map((b) => b.title).join(" › ")}
                  </div>
                {/if}
              </div>
            {:else if previewTab === "telegram"}
              <div
                style="background: #182533; border-left: 4px solid #38bdf8; padding: 0.85rem 1rem; border-radius: 0.45rem; max-width: 520px;"
              >
                <div
                  style="font-size: 0.78rem; color: #38bdf8; font-weight: 700; margin-bottom: 0.2rem;"
                >
                  {siteName}
                </div>
                <div style="font-weight: 700; color: #f8fafc; margin-bottom: 0.25rem;">
                  {previewData.title || "Без заголовка"}
                </div>
                <div style="font-size: 0.85rem; color: #cbd5e1;">
                  {previewData.description || ""}
                </div>
              </div>
            {:else}
              <div
                style="background: var(--bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.85rem; font-family: monospace; font-size: 0.82rem; white-space: pre-wrap; max-height: 320px; overflow-y: auto;"
              >
                {previewData.body_html || ""}
              </div>
            {/if}
          {/if}
        </div>
      </div>
    {/if}
  </div>
{/if}
