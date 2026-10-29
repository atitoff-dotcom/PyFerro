<script>
  let {
    variant = "primary",
    size = "md",
    type = "button",
    disabled = false,
    children,
    class: customClass = "",
    ...restProps
  } = $props();

  const variantClasses = {
    primary: "bg-accent text-accent-fg hover:bg-accent-hover",
    outline: "bg-transparent text-text border border-border hover:bg-panel-alt hover:text-text-bright",
    danger: "bg-danger-subtle text-danger border border-danger hover:bg-danger hover:text-accent-fg",
    ghost: "bg-transparent text-text hover:bg-panel-alt hover:text-text-bright",
  };

  const sizeClasses = {
    sm: "min-h-8 px-2.5 py-1 text-xs leading-normal",
    md: "min-h-8 px-3.5 py-1.5 text-sm leading-normal",
    lg: "min-h-10 px-4 py-2 text-base leading-normal",
    icon: "min-h-8 min-w-8 h-8 w-8 p-0",
  };
</script>

<button
  {type}
  {disabled}
  class="inline-flex items-center justify-center gap-1.5 rounded font-medium whitespace-nowrap cursor-pointer transition-all duration-150 select-none box-border active:scale-[0.99] active:opacity-90 disabled:opacity-50 disabled:pointer-events-none disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent {variantClasses[variant] || variantClasses.primary} {sizeClasses[size] || sizeClasses.md} {customClass}"
  {...restProps}
>
  {@render children?.()}
</button>
