# -*- coding: utf-8 -*-
"""
Реэкспорт для обратной совместимости pyferro.plugins.smart_cache.engine -> pyferro.smart_cache.engine.
"""

from pyferro.smart_cache.engine import (
    CacheTagVersion,
    VersionRegistry,
    version_registry,
    invalidates,
    invalidate_tags,
    patch_tag,
)

__all__ = [
    "CacheTagVersion",
    "VersionRegistry",
    "version_registry",
    "invalidates",
    "invalidate_tags",
    "patch_tag",
]
