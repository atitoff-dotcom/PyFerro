<script>
  let {
    checked = $bindable(),
    disabled = false,
    label = "",
    id = "",
    children,
    class: customClass = "",
    ...restProps
  } = $props();

  const fallbackId = `pf-cb-${Math.random().toString(36).substring(2, 9)}`;
  let elementId = $derived(id || fallbackId);
</script>

<label
  for={elementId}
  class="inline-flex items-center gap-2 min-h-8 select-none transition-colors {disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:text-text-bright'} text-text text-sm {customClass}"
>
  <span class="relative flex items-center justify-center">
    <input
      type="checkbox"
      id={elementId}
      {disabled}
      bind:checked
      class="appearance-none w-[18px] h-[18px] border border-border rounded bg-bg cursor-pointer inline-grid place-content-center m-0 transition-all duration-150 hover:border-accent active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none checked:bg-accent checked:border-accent"
      {...restProps}
    />
    {#if checked}
      <svg
        class="absolute pointer-events-none w-3 h-3 text-accent-fg stroke-[2.5]"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
    {/if}
  </span>
  {#if children}
    <span>{@render children()}</span>
  {:else if label}
    <span>{label}</span>
  {/if}
</label>
