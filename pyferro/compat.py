# -*- coding: utf-8 -*-
"""
pyferro.compat: Transparent backward-compatibility bridge.

Allows legacy code and existing projects using flat imports
(`import core...`, `import plugins...`) to continue working smoothly
without changes, mapping them to `pyferro.core...` and `pyferro.plugins...`.
"""
import sys
import importlib
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec


class _AliasLoader(Loader):
    """
    Transparent loader that returns the already imported canonical module
    without re-executing its bytecode, preventing duplicate class/table definitions.
    """
    def __init__(self, target_module):
        self.target_module = target_module

    def create_module(self, spec):
        return self.target_module

    def exec_module(self, module):
        pass


class _LegacyAliasFinder(MetaPathFinder):
    """
    Transparent meta path finder redirecting legacy root imports:
    - `core` -> `pyferro.core`
    - `core.<submodule>` -> `pyferro.core.<submodule>`
    - `plugins` -> `pyferro.plugins`
    - `plugins.<submodule>` -> `pyferro.plugins.<submodule>`
    """

    MAPPING = {
        "core": "pyferro.core",
        "plugins": "pyferro.plugins",
    }

    def find_spec(self, fullname, path, target=None):
        if fullname in self.MAPPING:
            target_name = self.MAPPING[fullname]
        elif fullname.startswith("core."):
            target_name = "pyferro.core." + fullname[5:]
        elif fullname.startswith("plugins."):
            target_name = "pyferro.plugins." + fullname[8:]
        else:
            return None

        # 1. Если модуль уже загружен под целевым или исходным именем
        mod = sys.modules.get(target_name) or sys.modules.get(fullname)
        if mod is not None:
            sys.modules[fullname] = mod
            loader = _AliasLoader(mod)
            spec = ModuleSpec(fullname, loader, origin=getattr(mod, "__file__", None))
            spec.submodule_search_locations = getattr(mod, "__path__", None)
            return spec

        # 2. Иначе импортируем целевой канонический модуль, если он существует в pyferro
        try:
            mod = importlib.import_module(target_name)
            sys.modules[fullname] = mod
            loader = _AliasLoader(mod)
            spec = ModuleSpec(fullname, loader, origin=getattr(mod, "__file__", None))
            spec.submodule_search_locations = getattr(mod, "__path__", None)
            return spec
        except (ImportError, ModuleNotFoundError):
            # Если в pyferro такого модуля нет, возвращаем None,
            # чтобы стандартные finders Python могли найти локальный модуль пользователя
            return None
        except Exception:
            return None


def sync_legacy_aliases():
    """Синхронизирует все существующие подмодули pyferro.* в core.* и plugins.*."""
    for name, mod in list(sys.modules.items()):
        if name.startswith("pyferro.core"):
            alias = "core" + name[len("pyferro.core"):]
            sys.modules.setdefault(alias, mod)
        elif name.startswith("pyferro.plugins"):
            alias = "plugins" + name[len("pyferro.plugins"):]
            sys.modules.setdefault(alias, mod)


def install_compat():
    """
    Installs the backward-compatibility hook into sys.meta_path
    and sets up base aliases in sys.modules.
    """
    for finder in sys.meta_path:
        if isinstance(finder, _LegacyAliasFinder):
            return
    sys.meta_path.insert(0, _LegacyAliasFinder())

    try:
        import pyferro.core
        sys.modules.setdefault("core", pyferro.core)
    except Exception:
        pass

    try:
        import pyferro.plugins
        sys.modules.setdefault("plugins", pyferro.plugins)
    except Exception:
        pass

    sync_legacy_aliases()
