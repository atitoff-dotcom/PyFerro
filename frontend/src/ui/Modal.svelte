<script>
  import { X } from "@lucide/svelte";

  let {
    open = false,
    onclose = () => {},
    title = "",
    children,
    footer,
    class: customClass = "",
    maxWidth = "max-w-xl",
  } = $props();

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) {
      onclose();
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Escape" && open) {
      onclose();
    }
  }
</script>

<svelte:window onkeydown={handleKeyDown} />

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs transition-opacity duration-150 animate-in fade-in"
    onclick={handleBackdropClick}
    role="presentation"
  >
    <div
      class="bg-panel border border-border rounded-lg shadow-md w-full {maxWidth} max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150 {customClass}"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="flex items-center justify-between px-5 py-3.5 border-b border-border-subtle bg-panel">
        <h3 class="m-0 text-base font-semibold text-text-bright">{title}</h3>
        <button
          type="button"
          class="min-h-8 min-w-8 h-8 w-8 inline-flex items-center justify-center rounded text-muted hover:text-text-bright hover:bg-panel-alt transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          onclick={onclose}
          aria-label="Закрыть окно"
        >
          <X size={18} />
        </button>
      </div>

      <div class="p-5 overflow-y-auto flex-1 text-text">
        {@render children?.()}
      </div>

      {#if footer}
        <div class="flex items-center justify-end gap-2.5 px-5 py-3 border-t border-border-subtle bg-panel-alt">
          {@render footer?.()}
        </div>
      {/if}
    </div>
  </div>
{/if}
