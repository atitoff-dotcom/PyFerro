<script>
  import { getToasts, removeToast } from "./toast.svelte.js";
  import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from "@lucide/svelte";

  const toasts = getToasts();

  const icons = {
    success: CheckCircle2,
    danger: AlertCircle,
    warning: AlertTriangle,
    info: Info,
  };

  const borderClasses = {
    success: "border-success/40 text-success",
    danger: "border-danger/40 text-danger",
    warning: "border-warning/40 text-warning",
    info: "border-accent/40 text-accent",
  };
</script>

<div class="fixed top-4 right-4 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none p-2 sm:p-0">
  {#each toasts as t (t.id)}
    {@const IconComponent = icons[t.type] || CheckCircle2}
    <div
      class="pointer-events-auto flex items-start justify-between gap-3 p-3.5 rounded-lg bg-panel-alt/95 backdrop-blur shadow-lg border text-sm text-text transition-all duration-200 {borderClasses[t.type] || borderClasses.success}"
      role="status"
    >
      <div class="flex items-start gap-2.5 min-w-0">
        <IconComponent size={18} class="flex-shrink-0 mt-0.5" />
        <span class="break-words font-medium leading-snug text-text">
          {t.message}
        </span>
      </div>

      <button
        type="button"
        onclick={() => removeToast(t.id)}
        class="text-muted hover:text-text-bright p-0.5 rounded cursor-pointer transition-colors flex-shrink-0 -mr-1 -mt-1"
        aria-label="Закрыть уведомление"
      >
        <X size={15} />
      </button>
    </div>
  {/each}
</div>
