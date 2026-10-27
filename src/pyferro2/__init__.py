"""
PyFerro 2.0 — высокопроизводительный веб-фреймворк с минимальным потреблением CPU и zero-boilerplate.
"""

from pyferro2.db.pagination import decode_cursor, encode_cursor, paginate_tabular
from pyferro2.seo import (
    HtmlBuilder,
    SeoConfig,
    SeoPageData,
    bot_page,
    configure_seo,
    get_seo_config,
    is_bot,
    notify_indexnow,
    register_sitemap_provider,
)

__version__ = "2.1.0"

__all__ = [
    "__version__",
    "paginate_tabular",
    "encode_cursor",
    "decode_cursor",
    "SeoConfig",
    "SeoPageData",
    "HtmlBuilder",
    "configure_seo",
    "get_seo_config",
    "is_bot",
    "bot_page",
    "register_sitemap_provider",
    "notify_indexnow",
]
