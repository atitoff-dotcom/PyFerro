<script lang="ts">
  import logoLight from "./logo-light.png";
  import logoDark from "./logo-dark.png";

  interface Props {
    size?: number | string;
    class?: string;
    color?: string;
    theme?: "auto" | "light" | "dark";
    alt?: string;
  }

  let {
    size = 32,
    class: className = "",
    color = "",
    theme = "auto",
    alt = "PyFerro Logo"
  }: Props = $props();

  const pxSize = $derived(typeof size === "number" ? `${size}px` : size);
</script>

{#if theme === "light"}
  <img
    src={logoLight}
    {alt}
    width={size}
    height={size}
    style:width={pxSize}
    style:height={pxSize}
    class="shrink-0 select-none object-contain {className}"
  />
{:else if theme === "dark"}
  <img
    src={logoDark}
    {alt}
    width={size}
    height={size}
    style:width={pxSize}
    style:height={pxSize}
    class="shrink-0 select-none object-contain {className}"
  />
{:else}
  <!-- Светлая тема по умолчанию / тёмная при наличии .dark -->
  <img
    src={logoLight}
    {alt}
    width={size}
    height={size}
    style:width={pxSize}
    style:height={pxSize}
    class="block dark:hidden shrink-0 select-none object-contain {className}"
  />
  <img
    src={logoDark}
    {alt}
    width={size}
    height={size}
    style:width={pxSize}
    style:height={pxSize}
    class="hidden dark:block shrink-0 select-none object-contain {className}"
  />
{/if}
