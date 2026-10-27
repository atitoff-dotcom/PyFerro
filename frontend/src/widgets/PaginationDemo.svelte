<script>
  import Pagination from '../Pagination.svelte';

  let props = $props();

  let totalCount = $state(Number(props.total) || 250);
  let limit = $state(Number(props.pageSize) || 10);
  let page = $state(Number(props.currentPage) || 1);

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

<div class="demo-card">
  <div class="demo-card-header">
    <div class="demo-title">
      <span class="live-dot"></span>
      <strong>Живой компонент Svelte:</strong> <code>Pagination.svelte</code>
    </div>
    <div class="demo-controls">
      <label class="demo-ctrl-label">
        Всего записей:
        <input
          type="number"
          class="demo-input"
          min="0"
          max="10000"
          step="50"
          bind:value={totalCount}
        />
      </label>
    </div>
  </div>

  <div class="demo-card-body">
    <div class="mock-table-preview">
      <div class="mock-row header-row">
        <span># ID</span>
        <span>Тестовая строка данных</span>
        <span>Статус</span>
      </div>
      {#each Array(Math.min(limit, Math.max(0, totalCount - (page - 1) * limit))).slice(0, 3) as _, idx}
        <div class="mock-row">
          <span>{(page - 1) * limit + idx + 1}</span>
          <span>Пример записи в таблице на странице {page}</span>
          <span class="mock-status">active</span>
        </div>
      {/each}
      {#if Math.min(limit, Math.max(0, totalCount - (page - 1) * limit)) > 3}
        <div class="mock-row more-row">
          <span>… еще {Math.min(limit, Math.max(0, totalCount - (page - 1) * limit)) - 3} строк на текущей странице …</span>
        </div>
      {/if}
      {#if totalCount === 0}
        <div class="mock-row empty-row">Нет записей для отображения</div>
      {/if}
    </div>

    <div class="demo-pagination-mount">
      <Pagination paginator={mockPaginator} showLimitSelect={true} showTotal={true} />
    </div>
  </div>
</div>

<style>
  .demo-card {
    margin: 1.5rem 0;
    border: 1px solid var(--border);
    border-radius: 0.65rem;
    background: #0f172a;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
    overflow: hidden;
  }
  .demo-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: #1e293b;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
    gap: 0.75rem;
  }
  .demo-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    color: #f1f5f9;
  }
  .demo-title code {
    background: #090d16;
    padding: 0.2rem 0.4rem;
    border-radius: 0.3rem;
    color: #38bdf8;
    font-size: 0.85rem;
  }
  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 8px #22c55e;
    display: inline-block;
  }
  .demo-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .demo-ctrl-label {
    font-size: 0.8rem;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .demo-input {
    background: #090d16;
    border: 1px solid var(--border);
    color: #f8fafc;
    border-radius: 0.35rem;
    padding: 0.25rem 0.4rem;
    width: 80px;
    font-size: 0.85rem;
  }
  .demo-card-body {
    padding: 1rem;
  }
  .mock-table-preview {
    border: 1px solid #334155;
    border-radius: 0.45rem;
    overflow: hidden;
    margin-bottom: 1rem;
    background: #141e33;
  }
  .mock-row {
    display: grid;
    grid-template-columns: 80px 1fr 100px;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #1e293b;
    font-size: 0.82rem;
    color: #cbd5e1;
    align-items: center;
  }
  .mock-row:last-child {
    border-bottom: none;
  }
  .header-row {
    background: #1e293b;
    font-weight: 600;
    color: #94a3b8;
  }
  .more-row, .empty-row {
    display: block;
    text-align: center;
    color: #64748b;
    font-style: italic;
    padding: 0.4rem;
  }
  .mock-status {
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.12);
    padding: 0.15rem 0.4rem;
    border-radius: 0.25rem;
    text-align: center;
    font-size: 0.75rem;
  }
  .demo-pagination-mount {
    background: #1e293b;
    padding: 0.5rem 0.75rem;
    border-radius: 0.45rem;
    border: 1px solid #334155;
  }
</style>
