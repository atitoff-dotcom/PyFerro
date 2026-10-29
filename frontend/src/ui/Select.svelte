<script>
  let {
    value = $bindable(),
    disabled = false,
    options = [],
    error = false,
    children,
    class: customClass = "",
    ...restProps
  } = $props();
</script>

<select
  {disabled}
  bind:value
  class="inline-flex items-center min-h-8 h-8 px-2.5 rounded bg-bg text-text border text-sm transition-all duration-150 box-border outline-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-panel-alt {error ? 'border-danger focus:border-danger focus:ring-2 focus:ring-danger-subtle' : 'border-border focus:border-accent focus:ring-2 focus:ring-accent-subtle'} {customClass}"
  {...restProps}
>
  {#if children}
    {@render children()}
  {:else}
    {#each options as opt}
      {#if typeof opt === "object" && opt !== null}
        <option value={opt.value}>{opt.label ?? opt.value}</option>
      {:else}
        <option value={opt}>{opt}</option>
      {/if}
    {/each}
  {/if}
</select>
