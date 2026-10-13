# -*- coding: utf-8 -*-
"""
Подсистема умного реактивного кэширования PyFerro (pyferro.smart_cache).
Реализует RFC 0001: Event-Driven Feedback Caching.
"""

from .engine import (
    CacheTagVersion,
    VersionRegistry,
    version_registry,
    invalidates,
    invalidate_tags,
    patch_tag,
)
from . import handlers  # Регистрация WSRPC методов cache.*

__all__ = [
    "CacheTagVersion",
    "VersionRegistry",
    "version_registry",
    "invalidates",
    "invalidate_tags",
    "patch_tag",
]
