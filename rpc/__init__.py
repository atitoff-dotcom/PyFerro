"""
Подсистема JSON-RPC 2.0: роутер, декоратор `@rpc_method`, O(1) проверка доступа и исключения (`pyferro2/rpc/`).
"""

from pyferro2.rpc.errors import (
    ForbiddenError,
    InvalidParamsError,
    MethodNotFoundError,
    RpcError,
    UnauthorizedError,
)
from pyferro2.rpc.router import (
    RpcMethodSpec,
    RpcRouter,
    check_rpc_access,
    default_router,
    rpc_method,
)

__all__ = [
    "RpcRouter",
    "RpcMethodSpec",
    "default_router",
    "rpc_method",
    "check_rpc_access",
    "RpcError",
    "UnauthorizedError",
    "ForbiddenError",
    "MethodNotFoundError",
    "InvalidParamsError",
]
