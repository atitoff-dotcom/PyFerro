import asyncio
import inspect
from typing import Callable, List
from .logger import logger

# Реестр колбэков запуска приложения
STARTUP_CALLBACKS: List[Callable] = []

def on_startup(func: Callable) -> Callable:
    """
    Декоратор для регистрации функций инициализации на старте приложения.
    Предотвращает дублирование при повторном импорте как __main__ и как имя модуля.
    """
    def is_dup(c):
        return (c is func) or (
            c.__name__ == func.__name__
            and getattr(c, "__qualname__", "") == getattr(func, "__qualname__", "")
            and getattr(c, "__module__", "") == getattr(func, "__module__", "")
        )

    if not any(is_dup(c) for c in STARTUP_CALLBACKS):
        STARTUP_CALLBACKS.append(func)
    return func

async def run_startup_callbacks() -> None:
    """
    Запускает все зарегистрированные функции инициализации (поддерживает sync/async).
    Автоматически активирует системный обход RLS-фильтров (system_bypass_ctx)
    на время выполнения системных startup-задач.
    """
    from pyferro.db.session import system_bypass

    with system_bypass():
        for callback in STARTUP_CALLBACKS:
            logger.info(f"[Lifecycle] Выполнение {callback.__name__}...")
            if inspect.iscoroutinefunction(callback):
                await callback()
            else:
                callback()
        logger.info("[Lifecycle] Все startup-колбэки выполнены.")


# Реестр колбэков завершения работы приложения
SHUTDOWN_CALLBACKS: List[Callable] = []


def on_shutdown(func: Callable) -> Callable:
    """
    Декоратор для регистрации функций завершения работы приложения (on_shutdown).
    """
    def is_dup(c):
        return (c is func) or (
            c.__name__ == func.__name__
            and getattr(c, "__qualname__", "") == getattr(func, "__qualname__", "")
            and getattr(c, "__module__", "") == getattr(func, "__module__", "")
        )

    if not any(is_dup(c) for c in SHUTDOWN_CALLBACKS):
        SHUTDOWN_CALLBACKS.append(func)
    return func


async def run_shutdown_callbacks() -> None:
    """
    Запускает все зарегистрированные функции завершения приложения (sync/async).
    """
    logger.info(f"[Lifecycle] Запуск {len(SHUTDOWN_CALLBACKS)} shutdown-колбэков: {[c.__name__ for c in SHUTDOWN_CALLBACKS]}")
    for callback in SHUTDOWN_CALLBACKS:
        logger.info(f"[Lifecycle] Выполнение {callback.__name__}...")
        try:
            if inspect.iscoroutinefunction(callback):
                await callback()
            else:
                callback()
        except Exception as e:
            logger.error(f"[Lifecycle] Ошибка выполнения shutdown-колбэка {callback.__name__}: {e}", exc_info=True)
    logger.info("[Lifecycle] Все shutdown-колбэки выполнены.")

