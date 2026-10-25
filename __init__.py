"""
PyFerro 2.0 — высокопроизводительный веб-фреймворк с минимальным потреблением CPU и zero-boilerplate.
"""

from pyferro2.db.pagination import decode_cursor, encode_cursor, paginate_tabular

__version__ = "2.0.1"

__all__ = [
    "__version__",
    "paginate_tabular",
    "encode_cursor",
    "decode_cursor",
]
