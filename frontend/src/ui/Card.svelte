<script>
  let {
    title = "",
    headerExtra,
    children,
    class: customClass = "",
    ...restProps
  } = $props();
</script>

<div
  class="bg-panel-alt border border-border-subtle rounded p-4 shadow-sm {customClass}"
  {...restProps}
>
  {#if title || headerExtra}
    <div class="flex items-center justify-between pb-3 mb-3 border-b border-border-subtle">
      {#if title}
        <h3 class="font-bold text-sm text-text-bright m-0">{title}</h3>
      {/if}
      {#if headerExtra}
        <div>{@render headerExtra()}</div>
      {/if}
    </div>
  {/if}
  {@render children?.()}
</div>
