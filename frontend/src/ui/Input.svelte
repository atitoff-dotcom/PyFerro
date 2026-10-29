<script>
  let {
    value = $bindable(),
    type = "text",
    disabled = false,
    error = false,
    class: customClass = "",
    ...restProps
  } = $props();
</script>

<input
  {type}
  {disabled}
  bind:value
  class="inline-flex items-center min-h-8 h-8 px-3 rounded bg-bg text-text border text-sm transition-all duration-150 box-border outline-none placeholder:text-muted disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-panel-alt {error ? 'border-danger focus:border-danger focus:ring-2 focus:ring-danger-subtle' : 'border-border focus:border-accent focus:ring-2 focus:ring-accent-subtle'} {customClass}"
  {...restProps}
/>
