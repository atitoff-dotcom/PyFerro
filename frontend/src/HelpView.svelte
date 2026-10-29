<script>
  import { onMount, tick } from 'svelte';
  import { rpc } from './rpc.js';
  import { WIDGETS } from './widgets/registry.js';
  import { Badge } from './ui/index.js';
  import { BookOpen, Search, AlertCircle, ChevronRight } from '@lucide/svelte';

  let { currentSlug = '', onNavigate = null } = $props();

  let articles = $state([]);
  let searchIndex = $state([]);
  let selectedSlug = $state('');
  let activeArticle = $state(null);
  let loading = $state(true);
  let articleLoading = $state(false);
  let errorMsg = $state('');
  let filterQuery = $state('');

  function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function createSnippet(text, query) {
    if (!text || !query) return '';
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return '';

    const start = Math.max(0, idx - 25);
    const end = Math.min(text.length, idx + query.length + 45);
    let snippet = text.slice(start, end);
    if (start > 0) snippet = '…' + snippet;
    if (end < text.length) snippet = snippet + '…';

    const safeSnippet = escapeHtml(snippet);
    const safeQuery = escapeHtml(query);
    const re = new RegExp(escapeRegex(safeQuery), 'gi');
    return safeSnippet.replace(re, '<mark>$&</mark>');
  }

  // Встроенный поиск по статьям, подразделам, тексту и коду
  let searchResults = $derived.by(() => {
    const q = filterQuery.trim();
    if (!q) return [];
    const qLower = q.toLowerCase();

    const results = [];

    if (searchIndex && searchIndex.length > 0) {
      for (const sec of searchIndex) {
        let matchType = null;
        let snippetHtml = '';

        if (sec.code && sec.code.toLowerCase().includes(qLower)) {
          matchType = 'code';
          snippetHtml = createSnippet(sec.code, q);
        } else if (sec.section_title && sec.section_title.toLowerCase().includes(qLower)) {
          matchType = 'section';
          snippetHtml = escapeHtml(sec.section_title).replace(
            new RegExp(escapeRegex(escapeHtml(q)), 'gi'),
            '<mark>$&</mark>'
          );
        } else if (sec.article_title && sec.article_title.toLowerCase().includes(qLower)) {
          matchType = 'article';
          snippetHtml = escapeHtml(sec.article_title).replace(
            new RegExp(escapeRegex(escapeHtml(q)), 'gi'),
            '<mark>$&</mark>'
          );
        } else if (sec.text && sec.text.toLowerCase().includes(qLower)) {
          matchType = 'text';
          snippetHtml = createSnippet(sec.text, q);
        }

        if (matchType) {
          results.push({
            slug: sec.slug,
            article_title: sec.article_title,
            section_title: sec.section_title,
            section_id: sec.section_id,
            matchType,
            snippetHtml,
          });
        }
      }
    } else {
      // Фолбэк по дереву статей, если индекс еще не загружен
      for (const art of articles) {
        if (
          art.title.toLowerCase().includes(qLower) ||
          art.slug.toLowerCase().includes(qLower)
        ) {
          results.push({
            slug: art.slug,
            article_title: art.title,
            section_title: art.title,
            section_id: '',
            matchType: 'article',
            snippetHtml: escapeHtml(art.title).replace(
              new RegExp(escapeRegex(escapeHtml(q)), 'gi'),
              '<mark>$&</mark>'
            ),
          });
        }
      }
    }

    return results;
  });

  onMount(async () => {
    await loadTree();
    await loadSearchIndex();
  });

  $effect(() => {
    if (currentSlug && currentSlug !== selectedSlug) {
      selectedSlug = currentSlug;
      loadArticle(currentSlug);
    }
  });

  async function loadTree() {
    loading = true;
    errorMsg = '';
    try {
      let resp;
      try {
        resp = await rpc.call('help.get_tree');
      } catch {
        resp = await rpc.call('help.tree');
      }
      articles = Array.isArray(resp) ? resp : (resp?.articles || []);
      if (!selectedSlug && articles.length > 0) {
        selectedSlug = currentSlug || articles[0].slug;
      }
      if (selectedSlug) {
        await loadArticle(selectedSlug);
      }
    } catch (e) {
      errorMsg = 'Ошибка загрузки статей: ' + (e.message || String(e));
    } finally {
      loading = false;
    }
  }

  async function loadSearchIndex() {
    try {
      let resp;
      try {
        resp = await rpc.call('help.get_search_index');
      } catch {
        resp = await rpc.call('help.search_index');
      }
      searchIndex = resp?.index || [];
    } catch {
      // Поиск фолбэчится на заголовки статей
    }
  }

  async function selectArticle(slug, sectionId = '') {
    selectedSlug = slug;
    filterQuery = '';
    if (onNavigate) {
      onNavigate(slug);
    }
    await loadArticle(slug, sectionId);
  }

  async function loadArticle(slug, targetAnchor = '') {
    if (!slug) return;
    articleLoading = true;
    errorMsg = '';
    try {
      let data;
      try {
        data = await rpc.call('help.get_article', { slug });
      } catch {
        data = await rpc.call('help.article', { slug });
      }
      activeArticle = data;

      if (targetAnchor) {
        await tick();
        const el = document.getElementById(targetAnchor);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    } catch (e) {
      errorMsg = 'Ошибка загрузки статьи: ' + (e.message || String(e));
      activeArticle = null;
    } finally {
      articleLoading = false;
    }
  }
</script>

<div class="help-layout">
  <!-- Боковое меню статей и встроенного поиска -->
  <aside class="help-sidebar">
    <div class="help-sidebar-header">
      <div class="flex items-center gap-2">
        <BookOpen size={17} class="text-accent" />
        <span class="help-title">Справочник</span>
      </div>
      <Badge variant="default">{articles.length}</Badge>
    </div>

    <div class="help-search-box">
      <div class="relative flex items-center">
        <Search size={14} class="absolute left-2.5 text-muted pointer-events-none" />
        <input
          type="text"
          placeholder="Поиск по статьям и коду…"
          class="help-search-input pl-8"
          bind:value={filterQuery}
        />
        {#if filterQuery}
          <button
            class="help-search-clear"
            onclick={() => (filterQuery = '')}
            title="Очистить поиск"
          >
            ✕
          </button>
        {/if}
      </div>
    </div>

    <nav class="help-nav">
      {#if loading}
        <div class="help-loading-state">Загрузка оглавления…</div>
      {:else if filterQuery.trim()}
        <!-- Результаты встроенного поиска -->
        {#if searchResults.length === 0}
          <div class="help-empty-state">По запросу ничего не найдено</div>
        {:else}
          <div class="help-search-count">Найдено совпадений: {searchResults.length}</div>
          {#each searchResults as res}
            <button
              class="help-search-result-item {selectedSlug === res.slug ? 'active' : ''}"
              onclick={() => selectArticle(res.slug, res.section_id)}
            >
              <div class="help-search-meta">
                <span class="help-search-art-name">{res.article_title}</span>
                {#if res.matchType === 'code'}
                  <span class="badge-code">код</span>
                {:else if res.matchType === 'section'}
                  <span class="badge-section">раздел</span>
                {/if}
              </div>
              <div class="help-search-sec-name">
                <ChevronRight size={11} class="shrink-0 opacity-70" />
                <span>{res.section_title}</span>
              </div>
              {#if res.snippetHtml}
                <div class="help-search-snippet {res.matchType === 'code' ? 'is-code' : ''}">
                  {@html res.snippetHtml}
                </div>
              {/if}
            </button>
          {/each}
        {/if}
      {:else}
        <!-- Обычный список статей оглавления -->
        {#each articles as art}
          <button
            class="help-nav-item {selectedSlug === art.slug ? 'active' : ''}"
            onclick={() => selectArticle(art.slug)}
          >
            <span class="help-nav-order">{art.order}</span>
            <span class="help-nav-label">{art.title}</span>
          </button>
        {/each}
      {/if}
    </nav>
  </aside>

  <!-- Основная область статьи -->
  <main class="help-main">
    {#if errorMsg}
      <div class="help-alert alert-error">
        <AlertCircle size={18} />
        <div>{errorMsg}</div>
      </div>
    {/if}

    {#if articleLoading}
      <div class="help-loading-indicator">Загрузка статьи…</div>
    {:else if activeArticle}
      <!-- Навигация / TOC (если есть h2/h3) -->
      {#if activeArticle.toc && activeArticle.toc.length > 1}
        <div class="help-toc-bar">
          <span class="help-toc-label">Содержание:</span>
          <div class="help-toc-links">
            {#each activeArticle.toc as item}
              {#if item.level > 1}
                <a href="#{item.id}" class="help-toc-link level-{item.level}">
                  {item.text}
                </a>
              {/if}
            {/each}
          </div>
        </div>
      {/if}

      <article class="help-article-content">
        {#each activeArticle.blocks as block, i}
          {#if block.type === 'html'}
            <div class="markdown-body">
              {@html block.html}
            </div>
          {:else if block.type === 'widget'}
            <div class="embedded-widget-wrapper">
              {#if WIDGETS[block.widget]}
                {@const WidgetComp = WIDGETS[block.widget]}
                <WidgetComp {...block.props} />
              {:else}
                <div class="widget-fallback">
                  <AlertCircle size={16} />
                  <div>Виджет <code>{block.widget}</code> еще не зарегистрирован в фронтенде</div>
                </div>
              {/if}
            </div>
          {/if}
        {/each}
      </article>
    {:else}
      <div class="help-empty-placeholder">
        Выберите статью из оглавления слева для просмотра.
      </div>
    {/if}
  </main>
</div>

<style>
  .help-layout {
    display: flex;
    height: calc(100vh - 3rem);
    max-height: calc(100vh - 3rem);
    background: var(--bg);
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--border);
  }

  /* Боковой список статей */
  .help-sidebar {
    width: 300px;
    background: var(--panel);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .help-sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid var(--border);
  }
  .help-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text-bright);
    letter-spacing: -0.01em;
  }
  .help-search-box {
    padding: 0.65rem 0.85rem;
    border-bottom: 1px solid var(--border-subtle);
  }
  .help-search-input {
    width: 100%;
    padding: 0.45rem 1.8rem 0.45rem 2rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-size: 0.82rem;
    outline: none;
    box-sizing: border-box;
    transition: all 0.15s ease;
  }
  .help-search-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-subtle);
  }
  .help-search-clear {
    position: absolute;
    right: 0.5rem;
    background: none;
    border: none;
    color: var(--muted);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0.2rem;
    line-height: 1;
  }
  .help-search-clear:hover {
    color: var(--text);
  }

  .help-nav {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .help-nav-item {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.52rem 0.75rem;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius);
    color: var(--muted);
    text-align: left;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.15s ease;
  }
  .help-nav-item:hover {
    background: var(--panel-hover);
    color: var(--text-bright);
  }
  .help-nav-item.active {
    background: var(--accent-subtle);
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
  }
  .help-nav-order {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.35rem;
    height: 1.35rem;
    background: var(--panel-alt);
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--text);
  }
  .help-nav-item.active .help-nav-order {
    background: var(--accent);
    color: var(--accent-fg);
  }
  .help-nav-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Элементы результатов поиска */
  .help-search-count {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.25rem 0.5rem;
  }
  .help-search-result-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.55rem 0.75rem;
    background: var(--bg);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    text-align: left;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .help-search-result-item:hover {
    border-color: var(--accent);
    background: var(--panel-hover);
  }
  .help-search-result-item.active {
    border-color: var(--accent);
    background: var(--accent-subtle);
  }
  .help-search-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .help-search-art-name {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--text-bright);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .help-search-sec-name {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--accent);
    font-weight: 500;
  }
  .help-search-snippet {
    font-size: 0.72rem;
    color: var(--muted);
    line-height: 1.35;
    background: var(--panel-alt);
    padding: 0.25rem 0.45rem;
    border-radius: var(--radius-sm);
    overflow: hidden;
    word-break: break-all;
  }
  .help-search-snippet.is-code {
    font-family: monospace;
    font-size: 0.7rem;
    color: var(--text);
  }
  :global(.help-search-snippet mark) {
    background: var(--accent);
    color: var(--accent-fg);
    border-radius: 2px;
    padding: 0 2px;
    font-weight: 700;
  }

  .badge-code {
    background: var(--accent-subtle);
    color: var(--accent);
    border: 1px solid var(--accent);
    font-size: 0.65rem;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-weight: 600;
  }
  .badge-section {
    background: var(--panel-alt);
    color: var(--text-bright);
    border: 1px solid var(--border-subtle);
    font-size: 0.65rem;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-weight: 600;
  }

  .help-loading-state, .help-empty-state {
    padding: 1.5rem 1rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.85rem;
  }

  /* Основная область статьи */
  .help-main {
    flex: 1;
    overflow-y: auto;
    padding: 2rem 2.5rem;
    max-width: 960px;
    box-sizing: border-box;
  }
  .help-loading-indicator {
    padding: 3rem;
    text-align: center;
    color: var(--muted);
  }
  .help-empty-placeholder {
    padding: 4rem 2rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.95rem;
  }

  /* Верхний TOC бар статьи */
  .help-toc-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 0.75rem;
    padding: 0.65rem 0.9rem;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 1.5rem;
    font-size: 0.8rem;
  }
  .help-toc-label {
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
  }
  .help-toc-links {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 0.75rem;
  }
  .help-toc-link {
    color: var(--accent);
    text-decoration: none;
    transition: opacity 0.15s ease;
  }
  .help-toc-link:hover {
    text-decoration: underline;
  }
  .help-toc-link.level-3 {
    opacity: 0.8;
  }

  /* Стилизация тела статьи Markdown и блоков кода */
  :global(.markdown-body pre) {
    background: var(--panel-alt);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    overflow-x: auto;
    font-size: 0.85rem;
    margin: 1.25rem 0;
    line-height: 1.5;
  }
  :global(.markdown-body pre code) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }

  /* Подсветка синтаксиса Pygments */
  :global(.markdown-body .k) { color: #f43f5e; font-weight: 600; }
  :global(.markdown-body .kn) { color: #f43f5e; font-weight: 600; }
  :global(.markdown-body .nn) { color: var(--accent); }
  :global(.markdown-body .n) { color: var(--text); }
  :global(.markdown-body .nf) { color: #a855f7; font-weight: 600; }
  :global(.markdown-body .nc) { color: #fbbf24; font-weight: 600; }
  :global(.markdown-body .nd) { color: var(--accent); font-weight: 600; }
  :global(.markdown-body .s), :global(.markdown-body .s1), :global(.markdown-body .s2), :global(.markdown-body .sd) { color: #34d399; }
  :global(.markdown-body .mi), :global(.markdown-body .mf) { color: #f59e0b; }
  :global(.markdown-body .c), :global(.markdown-body .c1) { color: var(--muted); font-style: italic; }
  :global(.markdown-body .o) { color: #ec4899; }
  :global(.markdown-body .nb) { color: var(--accent); }
  :global(.markdown-body .bp) { color: var(--accent); }
  :global(.markdown-body p code), :global(.markdown-body li code) {
    background: var(--panel-alt);
    color: var(--accent);
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    border: 1px solid var(--border-subtle);
    font-size: 0.85em;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }
  :global(.markdown-body h1) {
    font-size: 1.6rem;
    margin-top: 0;
    margin-bottom: 1rem;
    color: var(--text-bright);
    font-weight: 800;
    letter-spacing: -0.02em;
  }
  :global(.markdown-body h2) {
    font-size: 1.25rem;
    margin-top: 2rem;
    margin-bottom: 0.75rem;
    color: var(--text-bright);
    font-weight: 700;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 0.4rem;
  }
  :global(.markdown-body h3) {
    font-size: 1.05rem;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
    color: var(--text-bright);
    font-weight: 600;
  }
  :global(.markdown-body p) {
    line-height: 1.65;
    color: var(--text);
    margin: 0.85rem 0;
  }
  :global(.markdown-body ul), :global(.markdown-body ol) {
    padding-left: 1.5rem;
    margin: 0.85rem 0;
    color: var(--text);
    line-height: 1.65;
  }
  :global(.markdown-body li) {
    margin: 0.35rem 0;
  }

  /* Обертка встроенных интерактивных виджетов */
  .embedded-widget-wrapper {
    margin: 1.5rem 0;
  }
  .widget-fallback {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: var(--panel);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    color: var(--muted);
    font-size: 0.85rem;
  }

  .help-alert {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.75rem 1rem;
    border-radius: var(--radius);
    margin-bottom: 1rem;
    font-size: 0.85rem;
  }
  .alert-error {
    background: var(--danger-subtle);
    border: 1px solid var(--danger);
    color: var(--danger);
  }
</style>
