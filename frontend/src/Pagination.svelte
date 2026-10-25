<script>
  /**
   * Готовый визуальный компонент пагинации для PyFerro 2.0.
   * Принимает контроллер createPaginator и автоматически отображает:
   * - Стрелки «Назад» и «Вперед» с блокировкой
   * - Номера страниц с умными многоточиями
   * - Индикатор общего количества строк
   * - Переключатель лимита строк (20, 50, 100)
   */

  let { paginator, showLimitSelect = true, showTotal = true } = $props();

  function fromRow() {
    if (!paginator.total || paginator.total === 0) return 0;
    return (paginator.page - 1) * paginator.limit + 1;
  }

  function toRow() {
    if (!paginator.total || paginator.total === 0) return 0;
    return Math.min(paginator.page * paginator.limit, paginator.total);
  }
</script>

<div class="pf-pagination">
  {#if showTotal}
    <div class="pf-pagination-info">
      {#if paginator.total > 0}
        Показано <strong>{fromRow()}–{toRow()}</strong> из <strong>{paginator.total}</strong>
      {:else}
        Нет записей
      {/if}
    </div>
  {/if}

  <div class="pf-pagination-controls">
    <button
      class="pf-btn pf-btn-nav"
      disabled={!paginator.hasPrev || paginator.loading}
      onclick={() => paginator.prev()}
      title="Предыдущая страница"
    >
      ← Назад
    </button>

    <div class="pf-page-numbers">
      {#each paginator.pageNumbers as p}
        {#if p === '...'}
          <span class="pf-ellipsis">…</span>
        {:else}
          <button
            class="pf-btn pf-page-num"
            class:active={p === paginator.page}
            disabled={paginator.loading}
            onclick={() => paginator.goTo(p)}
          >
            {p}
          </button>
        {/if}
      {/each}
    </div>

    <button
      class="pf-btn pf-btn-nav"
      disabled={!paginator.hasNext || paginator.loading}
      onclick={() => paginator.next()}
      title="Следующая страница"
    >
      Вперед →
    </button>
  </div>

  {#if showLimitSelect}
    <div class="pf-limit-select">
      <span>На стр:</span>
      <select
        value={paginator.limit}
        disabled={paginator.loading}
        onchange={(e) => paginator.setLimit(e.target.value)}
      >
        <option value={10}>10</option>
        <option value={20}>20</option>
        <option value={50}>50</option>
        <option value={100}>100</option>
      </select>
    </div>
  {/if}
</div>

<style>
  .pf-pagination {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 0.5rem;
    color: var(--muted, #94a3b8);
    font-size: 0.875rem;
    flex-wrap: wrap;
  }

  .pf-pagination-info {
    font-size: 0.85rem;
  }

  .pf-pagination-info strong {
    color: var(--text, #f8fafc);
  }

  .pf-pagination-controls {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .pf-page-numbers {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .pf-btn {
    background: var(--panel, #1e293b);
    border: 1px solid var(--border, #334155);
    color: var(--text, #f8fafc);
    padding: 0.35rem 0.65rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
    transition: background 0.15s, border-color 0.15s;
    user-select: none;
  }

  .pf-btn:hover:not(:disabled) {
    background: var(--panel-alt, #263349);
    border-color: var(--accent, #38bdf8);
  }

  .pf-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .pf-page-num.active {
    background: var(--accent, #38bdf8);
    color: #0f172a;
    font-weight: 600;
    border-color: var(--accent, #38bdf8);
  }

  .pf-ellipsis {
    padding: 0 0.35rem;
    color: var(--muted, #94a3b8);
  }

  .pf-limit-select {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
  }

  .pf-limit-select select {
    background: var(--panel, #1e293b);
    border: 1px solid var(--border, #334155);
    color: var(--text, #f8fafc);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.85rem;
    outline: none;
    cursor: pointer;
  }
</style>
