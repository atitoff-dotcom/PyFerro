"""
Декларативный CRUD-движок и матрица прав PyFerro 2.0 (`pyferro2/crud/`).
"""

from pyferro2.crud.engine import CrudEngine
from pyferro2.crud.rpc import register_crud_rpc
from pyferro2.crud.spec import FieldSpec, ModelSpec, compile_model_spec

__all__ = [
    "FieldSpec",
    "ModelSpec",
    "compile_model_spec",
    "CrudEngine",
    "register_crud_rpc",
]
