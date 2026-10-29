<script>
  let {
    variant = "default",
    children,
    class: customClass = "",
    ...restProps
  } = $props();

  const variantClasses = {
    default: "bg-panel-alt text-muted border-border-subtle",
    accent: "bg-accent-subtle text-accent border-accent",
    success: "bg-success-subtle text-success border-success",
    warning: "bg-warning-subtle text-warning border-warning",
    danger: "bg-danger-subtle text-danger border-danger",
  };
</script>

<span
  class="inline-flex items-center gap-1 min-h-[22px] px-2 py-0.5 rounded text-xs font-semibold border box-border {variantClasses[variant] || variantClasses.default} {customClass}"
  {...restProps}
>
  {@render children?.()}
</span>
