"""
Подсистема стартовых приложений и примеров PyFerro 2.0 (`pyferro2/starters/`).
"""

from pyferro2.starters.catalog import DEFAULT_CATALOG, StarterManifest
from pyferro2.starters.manager import StartersManager
from pyferro2.starters.models import TstMessage, TstMeta, TstTopic
from pyferro2.starters.rpc import register_starters_rpc

__all__ = [
    "DEFAULT_CATALOG",
    "StarterManifest",
    "StartersManager",
    "TstMeta",
    "TstTopic",
    "TstMessage",
    "register_starters_rpc",
]
