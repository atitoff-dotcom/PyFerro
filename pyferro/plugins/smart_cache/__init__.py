# -*- coding: utf-8 -*-
"""
Официальный плагин умного реактивного кэширования PyFerro (pyferro.plugins.smart_cache).
Для обратной совместимости реэкспортирует подсистему ядра pyferro.smart_cache.
"""

from pyferro.smart_cache import (
    CacheTagVersion,
    VersionRegistry,
    version_registry,
    invalidates,
    invalidate_tags,
    patch_tag,
)
from pyferro.smart_cache import handlers

__all__ = [
    "CacheTagVersion",
    "VersionRegistry",
    "version_registry",
    "invalidates",
    "invalidate_tags",
    "patch_tag",
]
