"""
Официальная подсистема SEO, Dynamic Rendering, «Живого дерева сайта» (Site Tree),
генерации `sitemap.xml` и интеграции с протоколом IndexNow для PyFerro 2.0 (`pyferro2/seo/`).
"""

from pyferro2.seo.detector import (
    BOT_USER_AGENT_PATTERN,
    BROWSER_ENGINE_PATTERN,
    CLI_SCRAPERS_PATTERN,
    extract_cookies,
    extract_header,
    extract_query_params,
    is_bot,
)
from pyferro2.seo.indexnow import (
    INDEXNOW_ENDPOINTS,
    enqueue_indexnow_urls,
    flush_indexnow_queue,
    notify_indexnow,
)
from pyferro2.seo.jinja_engine import (
    ModelQueryWrapper,
    RecordWrapper,
    build_template_context,
    is_model_allowed_for_seo,
    render_jinja_template,
    serialize_safe_record,
    validate_jinja_template,
)
from pyferro2.seo.models import (
    SeoConfig,
    SeoConfigRecord,
    SeoPageData,
    configure_seo,
    get_seo_config,
)
from pyferro2.seo.page_cache import (
    TTLCache,
    clear_seo_cache,
    get_cached,
    set_cached,
)
from pyferro2.seo.renderer import (
    HtmlBuilder,
    render_404_html,
    render_seo_page,
)
from pyferro2.seo.router import (
    BOT_ROUTES,
    BotRoute,
    bot_page,
    handle_bot_http,
)
from pyferro2.seo.rpc import register_seo_rpc
from pyferro2.seo.site_tree import (
    STRUCTURE_PRESETS,
    collect_site_tree_sitemap_urls,
    compile_pattern_to_regex,
    flatten_tree_nodes,
    get_cached_site_tree,
    get_model_schema_for_seo,
    load_seo_from_db,
    match_and_render_site_tree,
    resolve_template,
    save_seo_to_db,
    set_cached_site_tree,
)
from pyferro2.seo.sitemap import (
    SITEMAP_PROVIDERS,
    build_sitemap_xml,
    collect_all_sitemap_urls,
    handle_sitemap_http,
    invalidate_sitemap_cache,
    register_sitemap_provider,
)

__all__ = [
    # Модели и конфигурация
    "SeoConfig",
    "SeoConfigRecord",
    "SeoPageData",
    "configure_seo",
    "get_seo_config",
    # Детектор ботов и заголовки
    "BOT_USER_AGENT_PATTERN",
    "CLI_SCRAPERS_PATTERN",
    "BROWSER_ENGINE_PATTERN",
    "is_bot",
    "extract_header",
    "extract_query_params",
    "extract_cookies",
    # Рендерер
    "HtmlBuilder",
    "render_seo_page",
    "render_404_html",
    # Роутер ботов
    "BotRoute",
    "BOT_ROUTES",
    "bot_page",
    "handle_bot_http",
    # Дерево сайта (Site Tree)
    "STRUCTURE_PRESETS",
    "get_cached_site_tree",
    "set_cached_site_tree",
    "load_seo_from_db",
    "save_seo_to_db",
    "flatten_tree_nodes",
    "match_and_render_site_tree",
    "collect_site_tree_sitemap_urls",
    "get_model_schema_for_seo",
    "resolve_template",
    "compile_pattern_to_regex",
    # Jinja2 песочница
    "RecordWrapper",
    "ModelQueryWrapper",
    "is_model_allowed_for_seo",
    "serialize_safe_record",
    "validate_jinja_template",
    "build_template_context",
    "render_jinja_template",
    # Sitemap
    "SITEMAP_PROVIDERS",
    "register_sitemap_provider",
    "invalidate_sitemap_cache",
    "collect_all_sitemap_urls",
    "build_sitemap_xml",
    "handle_sitemap_http",
    # IndexNow
    "INDEXNOW_ENDPOINTS",
    "enqueue_indexnow_urls",
    "flush_indexnow_queue",
    "notify_indexnow",
    # Кэш страниц
    "TTLCache",
    "get_cached",
    "set_cached",
    "clear_seo_cache",
    # RPC админки
    "register_seo_rpc",
]
