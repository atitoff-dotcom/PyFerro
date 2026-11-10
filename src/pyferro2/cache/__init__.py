"""
Подсистема интеллектуального кеширования, авто-инвалидации и Offline-First в PyFerro 2.0 (`pyferro2.cache`).
"""

from pyferro2.cache.manager import (
    CacheManager,
    cache_manager,
    compute_etag,
    load_cache_from_db,
    purge_all_cache,
    record_read_table,
    save_cache_to_db,
    start_table_tracking,
    stop_table_tracking,
)
from pyferro2.cache.models import (
    CacheConfig,
    CacheConfigRecord,
    CacheRule,
    CacheRuleRecord,
)
from pyferro2.cache.rpc import infer_method_cache_scope, register_cache_rpc

__all__ = [
    "CacheManager",
    "cache_manager",
    "compute_etag",
    "load_cache_from_db",
    "save_cache_to_db",
    "purge_all_cache",
    "start_table_tracking",
    "stop_table_tracking",
    "record_read_table",
    "CacheConfig",
    "CacheConfigRecord",
    "CacheRule",
    "CacheRuleRecord",
    "infer_method_cache_scope",
    "register_cache_rpc",
]
