<script>
  import Pagination from '../Pagination.svelte';
  import { Input, Badge } from '../ui/index.js';

  let { total = 250, pageSize = 10, currentPage = 1 } = $props();

  let totalCount = $state(250);
  let limit = $state(10);
  let page = $state(1);

  $effect.pre(() => {
    if (total !== undefined) totalCount = Number(total) || 250;
    if (pageSize !== undefined) limit = Number(pageSize) || 10;
    if (currentPage !== undefined) page = Number(currentPage) || 1;
  });

  let totalPages = $derived(Math.max(1, Math.ceil(totalCount / limit)));
  let hasPrev = $derived(page > 1);
  let hasNext = $derived(page < totalPages);

  let pageNumbers = $derived.by(() => {
    const pages = [];
    const maxVisible = 7;
    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push('...');
      const start = Math.max(2, page - 1);
      const end = Math.min(totalPages - 1, page + 1);
      for (let i = start; i <= end; i++) pages.push(i);
      if (page < totalPages - 2) pages.push('...');
      pages.push(totalPages);
    }
    return pages;
  });

  const mockPaginator = {
    get total() { return totalCount; },
    get page() { return page; },
    get limit() { return limit; },
    get totalPages() { return totalPages; },
    get hasPrev() { return hasPrev; },
    get hasNext() { return hasNext; },
    get pageNumbers() { return pageNumbers; },
    get loading() { return false; },
    prev() { if (page > 1) page--; },
    next() { if (page < totalPages) page++; },
    goTo(p) { page = Math.max(1, Math.min(totalPages, Number(p))); },
    goToPage(p) { page = Math.max(1, Math.min(totalPages, Number(p))); },
    setLimit(l) { limit = Number(l); page = 1; }
  };
</script>

<div class="my-6 border border-border-subtle rounded-lg bg-panel shadow-sm overflow-hidden">
  <div class="flex items-center justify-between px-4 py-3 bg-panel-alt border-b border-border-subtle flex-wrap gap-3">
    <div class="flex items-center gap-2 text-sm text-text-bright">
      <span class="w-2 h-2 rounded-full bg-success inline-block shadow-sm"></span>
      <span class="font-semibold">Живой компонент Svelte:</span>
      <code class="bg-bg px-1.5 py-0.5 rounded text-accent text-xs">Pagination.svelte</code>
    </div>
    <div class="flex items-center gap-2">
      <label class="text-xs text-muted flex items-center gap-2">
        Всего записей:
        <Input
          type="number"
          min="0"
          max="10000"
          step="50"
          bind:value={totalCount}
          class="w-24 h-7 min-h-7 text-xs py-0"
        />
      </label>
    </div>
  </div>

  <div class="p-4 space-y-4">
    <div class="border border-border-subtle rounded bg-bg overflow-hidden text-xs">
      <div class="grid grid-cols-[80px_1fr_100px] px-3 py-2 bg-panel-alt border-b border-border-subtle font-semibold text-muted">
        <span># ID</span>
        <span>Тестовая строка данных</span>
        <span>Статус</span>
      </div>
      {#each Array(Math.min(limit, Math.max(0, totalCount - (page - 1) * limit))).slice(0, 3) as _, idx}
        <div class="grid grid-cols-[80px_1fr_100px] px-3 py-2 border-b border-border-subtle/50 text-text items-center last:border-b-0 hover:bg-panel-hover transition-colors">
          <span class="font-mono text-muted">{(page - 1) * limit + idx + 1}</span>
          <span>Пример записи в таблице на странице {page}</span>
          <span><Badge variant="accent">active</Badge></span>
        </div>
      {/each}
      {#if Math.min(limit, Math.max(0, totalCount - (page - 1) * limit)) > 3}
        <div class="text-center text-muted italic py-1.5 bg-panel-alt/40 border-t border-border-subtle/30">
          … еще {Math.min(limit, Math.max(0, totalCount - (page - 1) * limit)) - 3} строк на текущей странице …
        </div>
      {/if}
      {#if totalCount === 0}
        <div class="text-center text-muted italic py-3">Нет записей для отображения</div>
      {/if}
    </div>

    <div class="bg-panel-alt px-3 py-2 rounded border border-border-subtle">
      <Pagination paginator={mockPaginator} showLimitSelect={true} showTotal={true} />
    </div>
  </div>
</div>
