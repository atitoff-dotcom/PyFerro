<script>
  /**
   * Готовый визуальный компонент пагинации для PyFerro 2.0.
   * Принимает контроллер createPaginator и автоматически отображает:
   * - Стрелки «Назад» и «Вперед» с блокировкой
   * - Номера страниц с умными многоточиями
   * - Индикатор общего количества строк
   * - Переключатель лимита строк (10, 20, 50, 100)
   */
  import Button from "./ui/Button.svelte";
  import Select from "./ui/Select.svelte";

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

<div class="flex items-center justify-between gap-4 py-2 px-1 text-muted text-sm flex-wrap">
  {#if showTotal}
    <div class="text-xs">
      {#if paginator.total > 0}
        Показано <strong class="text-text-bright font-semibold">{fromRow()}–{toRow()}</strong> из <strong class="text-text-bright font-semibold">{paginator.total}</strong>
      {:else}
        Нет записей
      {/if}
    </div>
  {/if}

  <div class="flex items-center gap-1.5">
    <Button
      variant="outline"
      size="sm"
      disabled={!paginator.hasPrev || paginator.loading}
      onclick={() => paginator.prev()}
      title="Предыдущая страница"
    >
      ← Назад
    </Button>

    <div class="flex items-center gap-1">
      {#each paginator.pageNumbers as p, idx}
        {#if p === '...'}
          <Button
            variant="ghost"
            size="sm"
            disabled={paginator.loading}
            onclick={() => {
              const maxP = paginator.totalPages || paginator.pages || Math.ceil((paginator.total || 0) / (paginator.limit || 10)) || 1;
              if (idx < paginator.pageNumbers.length / 2) {
                paginator.goTo(Math.max(1, paginator.page - 5));
              } else {
                paginator.goTo(Math.min(maxP, paginator.page + 5));
              }
            }}
            title="Перейти на 5 страниц {idx < paginator.pageNumbers.length / 2 ? 'назад' : 'вперед'}"
          >
            …
          </Button>
        {:else}
          <Button
            variant={p === paginator.page ? "primary" : "outline"}
            size="sm"
            disabled={paginator.loading}
            onclick={() => paginator.goTo(p)}
          >
            {p}
          </Button>
        {/if}
      {/each}
    </div>

    <Button
      variant="outline"
      size="sm"
      disabled={!paginator.hasNext || paginator.loading}
      onclick={() => paginator.next()}
      title="Следующая страница"
    >
      Вперед →
    </Button>
  </div>

  {#if showLimitSelect}
    <div class="flex items-center gap-2 text-xs text-muted">
      <span>На стр:</span>
      <Select
        value={paginator.limit}
        disabled={paginator.loading}
        onchange={(e) => paginator.setLimit(e.target.value)}
        class="h-8 min-h-8 text-xs py-0"
        options={[10, 20, 50, 100]}
      />
    </div>
  {/if}
</div>
