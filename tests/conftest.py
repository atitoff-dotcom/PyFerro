# -*- coding: utf-8 -*-
import pytest


@pytest.fixture(autouse=True)
def _reset_seo_cache():
    try:
        from pyferro.plugins.seo.page_cache import clear_seo_cache
        clear_seo_cache()
    except ImportError:
        pass
    yield
    try:
        from pyferro.plugins.seo.page_cache import clear_seo_cache
        clear_seo_cache()
    except ImportError:
        pass
