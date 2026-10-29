<script>
  let {
    checked = false,
    disabled = false,
    onchange = () => {},
    label = "",
    id = undefined,
    class: customClass = "",
    ...restProps
  } = $props();

  function handleClick() {
    if (disabled) return;
    onchange(!checked);
  }

  function handleKeyDown(e) {
    if (disabled) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onchange(!checked);
    }
  }
</script>

<button
  type="button"
  role="switch"
  aria-checked={checked}
  {id}
  {disabled}
  onclick={handleClick}
  onkeydown={handleKeyDown}
  class="relative inline-flex items-center min-w-11 w-11 h-6 rounded-full cursor-pointer transition-colors duration-200 select-none box-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none {checked ? 'bg-accent' : 'bg-step-4'} {customClass}"
  {...restProps}
>
  <span
    class="inline-block w-4 h-4 rounded-full bg-text-bright shadow-sm transform transition-transform duration-200 ease-in-out pointer-events-none {checked ? 'translate-x-6' : 'translate-x-1'}"
  ></span>
  {#if label}
    <span class="sr-only">{label}</span>
  {/if}
</button>
