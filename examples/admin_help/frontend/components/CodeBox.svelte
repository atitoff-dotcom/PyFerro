<script lang="ts">
  import Prism from 'prismjs';
  import 'prismjs/components/prism-python';
  import 'prismjs/components/prism-bash';
  import 'prismjs/components/prism-json';
  import 'prismjs/components/prism-sql';

  let { code = '', language = 'python', title = '' }: { code: string; language?: string; title?: string } = $props();

  let copied = $state(false);

  let highlighted = $derived.by(() => {
    const gram = Prism.languages[language] || Prism.languages.python;
    return Prism.highlight(code.trim(), gram, language);
  });

  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(code.trim());
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch (e) {
      console.error(e);
    }
  }
</script>

<div class="my-4 rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden text-sm">
  {#if title}
    <div class="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2 font-mono text-xs text-slate-600 font-medium">
      <div class="flex items-center space-x-2">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-slate-300"></span>
        <span>{title}</span>
      </div>
      <button
        onclick={copyToClipboard}
        class="flex items-center space-x-1 rounded px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-200 transition-colors"
        title="Копировать код"
      >
        {#if copied}
          <span class="text-emerald-600 font-medium">✓ Скопировано</span>
        {:else}
          <span>📋 Копировать</span>
        {/if}
      </button>
    </div>
  {/if}

  <div class="relative overflow-x-auto p-4 bg-slate-50/50">
    {#if !title}
      <button
        onclick={copyToClipboard}
        class="absolute right-3 top-3 rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 shadow-sm hover:bg-slate-50 transition-colors"
      >
        {copied ? '✓ Скопировано' : '📋 Копировать'}
      </button>
    {/if}
    <pre class="!m-0 !p-0 !bg-transparent font-mono text-[13px] leading-relaxed text-slate-800"><code>{@html highlighted}</code></pre>
  </div>
</div>