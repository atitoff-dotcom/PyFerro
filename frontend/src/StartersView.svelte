<script>
  import { onMount } from "svelte";
  import { rpc } from "./rpc.js";
  import { Button, Card, Badge, Modal, toast } from "./ui/index.js";
  import {
    Boxes,
    Download,
    Trash2,
    Eye,
    RefreshCw,
    AlertTriangle,
    CheckCircle2,
    Database,
    Tag,
  } from "@lucide/svelte";

  let { onnotify = () => {} } = $props();

  let isLoading = $state(true);
  let isActionRunning = $state(false);
  let starters = $state([]);

  // Модальные окна
  let showConflictModal = $state(false);
  let showDeleteModal = $state(false);
  let showSeoModal = $state(false);

  let targetStarter = $state(null);
  let seoPreviewData = $state(null);
  let conflictMessage = $state("");

  async function loadStarters() {
    isLoading = true;
    try {
      starters = await rpc.call("starters.list");
    } catch (err) {
      toast.error(err.message || "Ошибка загрузки списка стартеров");
      onnotify({ type: "error", message: err.message });
    } finally {
      isLoading = false;
    }
  }

  async function handleInstall(starter, overwrite = false) {
    isActionRunning = true;
    try {
      const res = await rpc.call("starters.install", {
        starter_id: starter.id,
        overwrite,
      });
      toast.success(res.message || "Стартер успешно установлен");
      onnotify({ type: "success", message: res.message });
      showConflictModal = false;
      await loadStarters();
    } catch (err) {
      if (err.code === 409) {
        targetStarter = starter;
        conflictMessage = err.message;
        showConflictModal = true;
      } else {
        toast.error(err.message || "Ошибка установки стартера");
        onnotify({ type: "error", message: err.message });
      }
    } finally {
      isActionRunning = false;
    }
  }

  async function handleUninstall() {
    if (!targetStarter) return;
    isActionRunning = true;
    try {
      const res = await rpc.call("starters.uninstall", {
        starter_id: targetStarter.id,
      });
      toast.success(res.message || "Стартер успешно удален");
      onnotify({ type: "success", message: res.message });
      showDeleteModal = false;
      targetStarter = null;
      await loadStarters();
    } catch (err) {
      toast.error(err.message || "Ошибка удаления стартера");
      onnotify({ type: "error", message: err.message });
    } finally {
      isActionRunning = false;
    }
  }

  async function handleOpenSeoPreview(starter) {
    isActionRunning = true;
    try {
      seoPreviewData = await rpc.call("starters.seo_preview", {
        starter_id: starter.id,
      });
      targetStarter = starter;
      showSeoModal = true;
    } catch (err) {
      toast.error(err.message || "Ошибка загрузки SEO предпросмотра");
      onnotify({ type: "error", message: err.message });
    } finally {
      isActionRunning = false;
    }
  }

  onMount(() => {
    loadStarters();
  });
</script>

<div class="space-y-6">
  <!-- Заголовок страницы -->
  <div class="flex items-center justify-between flex-wrap gap-4">
    <div>
      <h1 class="text-xl font-bold flex items-center gap-2 text-text-bright">
        <Boxes class="text-primary" size={24} />
        <span>Каталог стартовых примеров (Starter Apps)</span>
      </h1>
      <p class="text-xs text-muted mt-1">
        Готовые эталонные приложения, скачиваемые из GitHub Релизов в 1 клик. Все таблицы изолированы префиксом <code class="text-primary font-mono">tst_*</code>.
      </p>
    </div>
    <Button variant="outline" size="sm" onclick={loadStarters} disabled={isLoading}>
      <RefreshCw size={14} class={isLoading ? "animate-spin" : ""} />
      <span>Обновить каталог</span>
    </Button>
  </div>

  {#if isLoading}
    <div class="p-12 text-center text-sm text-muted">Загрузка каталога стартеров...</div>
  {:else if starters.length === 0}
    <div class="p-12 text-center text-sm text-muted">Доступных стартеров не найдено.</div>
  {:else}
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      {#each starters as starter}
        <Card class="flex flex-col justify-between h-full border border-border hover:border-primary/50 transition-colors">
          <div class="space-y-4">
            <!-- Шапка карточки -->
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-bold text-base text-text-bright flex items-center gap-2">
                  <span>{starter.name}</span>
                </h3>
                <div class="text-xs text-muted font-mono mt-0.5">
                  ID: {starter.id} • GitHub: {starter.repo} ({starter.compatible_tag})
                </div>
              </div>

              {#if starter.installed}
                {#if starter.version_mismatch}
                  <Badge variant="warning" class="shrink-0 flex items-center gap-1">
                    <AlertTriangle size={12} />
                    <span>Требуется обновить</span>
                  </Badge>
                {:else}
                  <Badge variant="success" class="shrink-0 flex items-center gap-1">
                    <CheckCircle2 size={12} />
                    <span>Установлен (v{starter.installed_version})</span>
                  </Badge>
                {/if}
              {:else}
                <Badge variant="outline" class="shrink-0">Не установлен</Badge>
              {/if}
            </div>

            <!-- Описание -->
            <p class="text-xs text-text leading-relaxed">
              {starter.description}
            </p>

            <!-- Теги -->
            <div class="flex flex-wrap gap-1.5 pt-1">
              {#each starter.tags as tag}
                <span class="inline-flex items-center gap-1 text-[0.7rem] bg-surface-raised px-2 py-0.5 rounded text-muted border border-border-subtle">
                  <Tag size={10} />
                  <span>{tag}</span>
                </span>
              {/each}
            </div>

            <!-- Таблицы базы данных -->
            <div class="pt-2 border-t border-border-subtle">
              <div class="text-[0.7rem] text-muted uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <Database size={11} />
                <span>Таблицы стартера ({starter.tables.length}):</span>
              </div>
              <div class="flex flex-wrap gap-1">
                {#each starter.tables as tbl}
                  <code class="text-[0.75rem] px-1.5 py-0.5 rounded {starter.existing_tables.includes(tbl) ? 'bg-primary/10 text-primary font-semibold' : 'bg-surface-raised text-muted'}">
                    {tbl}
                  </code>
                {/each}
              </div>
            </div>
          </div>

          <!-- Нижняя панель действий -->
          <div class="pt-4 mt-4 border-t border-border flex items-center justify-between gap-2">
            {#if starter.installed}
              <div class="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onclick={() => handleOpenSeoPreview(starter)}
                  disabled={isActionRunning}
                >
                  <Eye size={14} />
                  <span>Проверить SEO</span>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onclick={() => handleInstall(starter, true)}
                  disabled={isActionRunning}
                  title="Сбросить и переустановить демо-данные"
                >
                  <RefreshCw size={14} />
                  <span>Переустановить</span>
                </Button>
              </div>

              <Button
                variant="danger"
                size="sm"
                onclick={() => {
                  targetStarter = starter;
                  showDeleteModal = true;
                }}
                disabled={isActionRunning}
              >
                <Trash2 size={14} />
                <span>Удалить</span>
              </Button>
            {:else}
              <Button
                variant="primary"
                size="sm"
                class="w-full justify-center"
                onclick={() => handleInstall(starter, false)}
                disabled={isActionRunning}
              >
                <Download size={14} />
                <span>Скачать и установить в 1 клик</span>
              </Button>
            {/if}
          </div>
        </Card>
      {/each}
    </div>
  {/if}
</div>

<!-- Модальное окно разрешения конфликта таблиц -->
<Modal
  open={showConflictModal}
  onclose={() => (showConflictModal = false)}
  title="Конфликт существующих таблиц в БД"
  maxWidth="max-w-lg"
>
  <div class="space-y-3 text-sm text-text">
    <div class="p-3 bg-danger/10 border border-danger/30 rounded text-xs text-danger flex items-start gap-2">
      <AlertTriangle size={16} class="shrink-0 mt-0.5" />
      <span>{conflictMessage}</span>
    </div>
    <p>
      В вашей базе данных уже обнаружены таблицы стартера с префиксом <code>tst_*</code>.
    </p>
    <p class="text-xs text-muted">
      Вы можете принудительно очистить старые таблицы и накатить свежие демонстрационные данные.
    </p>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (showConflictModal = false)}>
      Отмена
    </Button>
    <Button
      variant="danger"
      onclick={() => handleInstall(targetStarter, true)}
      disabled={isActionRunning}
    >
      Перезаписать таблицы (overwrite)
    </Button>
  {/snippet}
</Modal>

<!-- Модальное окно удаления стартера -->
<Modal
  open={showDeleteModal}
  onclose={() => (showDeleteModal = false)}
  title="Удаление тестового стартера"
  maxWidth="max-w-md"
>
  <div class="space-y-3 text-sm text-text">
    <p>
      Вы действительно хотите удалить стартер <strong>{targetStarter?.name}</strong>?
    </p>
    <p class="text-xs text-muted">
      Будут выполнены команды безопасного удаления:
      <code>DROP TABLE IF EXISTS {targetStarter?.tables?.join(", ")};</code>
      и удалены локальные файлы примера.
    </p>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (showDeleteModal = false)}>
      Отмена
    </Button>
    <Button
      variant="danger"
      onclick={handleUninstall}
      disabled={isActionRunning}
    >
      Удалить и очистить базу
    </Button>
  {/snippet}
</Modal>

<!-- Модальное окно предпросмотра SEO -->
<Modal
  open={showSeoModal}
  onclose={() => (showSeoModal = false)}
  title="Предпросмотр SEO: Schema.org и Sitemap"
  maxWidth="max-w-3xl"
>
  {#if seoPreviewData}
    <div class="space-y-4 text-xs">
      <div>
        <div class="font-bold text-sm text-text-bright mb-1">
          {seoPreviewData.topic.title}
        </div>
        <div class="text-muted">
          ЧПУ Slug: <code>/forum/{seoPreviewData.topic.slug}</code>
        </div>
      </div>

      <!-- Хлебные крошки JSON-LD -->
      <div>
        <div class="font-bold uppercase tracking-wider text-muted mb-1 flex items-center justify-between">
          <span>1. Schema.org BreadcrumbList (JSON-LD):</span>
          <Badge variant="outline">Хлебные крошки</Badge>
        </div>
        <pre class="bg-surface-raised p-3 rounded overflow-x-auto text-[0.75rem] border border-border-subtle max-h-48 font-mono">
{JSON.stringify(seoPreviewData.breadcrumbs_json_ld, null, 2)}
        </pre>
      </div>

      <!-- Форумная разметка JSON-LD -->
      <div>
        <div class="font-bold uppercase tracking-wider text-muted mb-1 flex items-center justify-between">
          <span>2. Schema.org DiscussionForumPosting (JSON-LD):</span>
          <Badge variant="outline">Форумный сниппет</Badge>
        </div>
        <pre class="bg-surface-raised p-3 rounded overflow-x-auto text-[0.75rem] border border-border-subtle max-h-48 font-mono">
{JSON.stringify(seoPreviewData.discussion_json_ld, null, 2)}
        </pre>
      </div>

      <!-- Карта сайта sitemap.xml -->
      <div>
        <div class="font-bold uppercase tracking-wider text-muted mb-1 flex items-center justify-between">
          <span>3. Динамический sitemap.xml (всего {seoPreviewData.total_sitemap_urls} URL):</span>
          <Badge variant="outline">Sitemap sample</Badge>
        </div>
        <div class="space-y-1 bg-surface-raised p-2 rounded border border-border-subtle font-mono text-[0.75rem]">
          {#each seoPreviewData.sitemap_sample as url}
            <div class="flex items-center justify-between p-1 hover:bg-surface rounded">
              <span class="text-primary">{url.loc}</span>
              <span class="text-muted">lastmod: {url.lastmod}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="outline" onclick={() => (showSeoModal = false)}>
      Закрыть
    </Button>
  {/snippet}
</Modal>
