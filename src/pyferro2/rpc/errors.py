"""
Стандартные исключения протокола JSON-RPC 2.0 для PyFerro 2.0.

Каждое исключение хранит числовой код ошибки из `JsonRpcErrorCode`,
понятное сообщение и опциональные дополнительные данные (`data`).
"""

from typing import Any

from pyferro2.core.constants import JsonRpcErrorCode


class RpcError(Exception):
    """Базовое исключение вызова JSON-RPC 2.0."""

    default_code: int = JsonRpcErrorCode.INTERNAL_ERROR
    default_message: str = "Внутренняя ошибка сервера"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: int | None = None,
        data: Any = None,
    ) -> None:
        self.code: int = int(code if code is not None else self.default_code)
        self.message: str = message if message is not None else self.default_message
        self.data: Any = data
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Формирует стандартный объект `error` по спецификации JSON-RPC 2.0."""
        err: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            err["data"] = self.data
        return err


class UnauthorizedError(RpcError):
    """Требуется авторизация (-32001) — вызов от имени неавторизованного гостя."""

    default_code = JsonRpcErrorCode.UNAUTHORIZED
    default_message = "Требуется авторизация"


class ForbiddenError(RpcError):
    """Недостаточно прав (-32003) — у авторизованного пользователя нет нужной роли или права."""

    default_code = JsonRpcErrorCode.FORBIDDEN
    default_message = "Недостаточно прав для вызова метода"


class MethodNotFoundError(RpcError):
    """Метод не зарегистрирован в роутере (-32601)."""

    default_code = JsonRpcErrorCode.METHOD_NOT_FOUND
    default_message = "Метод не найден"


class InvalidParamsError(RpcError):
    """Ошибка валидации входных параметров метода (-32602)."""

    default_code = JsonRpcErrorCode.INVALID_PARAMS
    default_message = "Некорректные параметры вызова"
