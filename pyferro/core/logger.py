import logging
import os
from logging.handlers import RotatingFileHandler

# ANSI escape-коды для раскрашивания терминала
COLOR_RESET = "\033[0m"
COLOR_DEBUG = "\033[36m"      # Голубой (Cyan)
COLOR_INFO = "\033[32m"       # Зеленый (Green)
COLOR_WARNING = "\033[33m"    # Желтый (Yellow)
COLOR_ERROR = "\033[31m"      # Красный (Red)
COLOR_CRITICAL = "\033[41;37m" # Белый текст на красном фоне

def get_current_session_safe():
    """
    Безопасно извлекает текущую транспортную сессию из контекста.
    """
    try:
        from .session import current_transport_ctx
        return current_transport_ctx.get()
    except (ImportError, LookupError):
        return None

def _extract_username_safe(session) -> str:
    if not session or not getattr(session, "data", None):
        return "guest"
    data = session.data
    if isinstance(data, dict):
        return str(data.get("user_name") or data.get("username") or data.get("sub") or "guest")
    for attr in ("user_name", "username", "sub", "login", "name"):
        val = getattr(data, attr, None)
        if val:
            return str(val)
    return "guest"

class ContextColoredFormatter(logging.Formatter):
    """
    Форматтер для цветного вывода в консоль с автоматическим
    извлечением контекста текущей WebSocket-сессии.
    """
    def format(self, record: logging.LogRecord) -> str:
        session = get_current_session_safe()
        if session:
            user_str = _extract_username_safe(session)
            record.ctx = f"[{session.ip} | {user_str}]"
        else:
            record.ctx = "[SYSTEM]"

        # Получаем относительный путь файла для логов
        try:
            rel_path = os.path.relpath(record.pathname)
            if rel_path.startswith(".."):
                rel_path = record.filename
            elif rel_path.startswith("app/"):
                rel_path = rel_path[4:]
        except Exception:
            rel_path = record.filename

        record.err_loc = f" [{rel_path}:{record.lineno}]"

        # Выбираем цвет в зависимости от уровня лога
        level_color = COLOR_RESET
        if record.levelno == logging.DEBUG:
            level_color = COLOR_DEBUG
        elif record.levelno == logging.INFO:
            level_color = COLOR_INFO
        elif record.levelno == logging.WARNING:
            level_color = COLOR_WARNING
        elif record.levelno == logging.ERROR:
            level_color = COLOR_ERROR
        elif record.levelno == logging.CRITICAL:
            level_color = COLOR_CRITICAL

        # Формируем итоговую строку лога
        fmt = f"%(asctime)s [{level_color}%(levelname)s{COLOR_RESET}] %(ctx)s%(err_loc)s %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

class ContextFileFormatter(logging.Formatter):
    """
    Форматтер для записи в файл (без ANSI-кодов цветов)
    с автоматическим извлечением контекста сессии.
    """
    def format(self, record: logging.LogRecord) -> str:
        session = get_current_session_safe()
        if session:
            user_str = _extract_username_safe(session)
            record.ctx = f"[{session.ip} | {user_str}]"
        else:
            record.ctx = "[SYSTEM]"

        # Получаем относительный путь файла для логов
        try:
            rel_path = os.path.relpath(record.pathname)
            if rel_path.startswith(".."):
                rel_path = record.filename
            elif rel_path.startswith("app/"):
                rel_path = rel_path[4:]
        except Exception:
            rel_path = record.filename

        record.err_loc = f" [{rel_path}:{record.lineno}]"

        fmt = "%(asctime)s [%(levelname)s] %(ctx)s%(err_loc)s %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

def setup_logging(level: int = logging.INFO) -> None:
    """
    Настраивает корневой логгер для вывода в консоль и файл.
    """
    os.makedirs("logs", exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Очищаем старые обработчики (если они были)
    root_logger.handlers.clear()

    # 1. Настройка вывода в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ContextColoredFormatter())
    root_logger.addHandler(console_handler)

    # 2. Настройка вывода в файл с ротацией (макс 5 МБ, храним до 5 файлов)
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(ContextFileFormatter())
    root_logger.addHandler(file_handler)

    # 3. Настройка буфера оперативной памяти для Mission Control Cockpit
    if _memory_log_handler not in root_logger.handlers:
        root_logger.addHandler(_memory_log_handler)

from collections import deque
import time

_LOG_BUFFER = deque(maxlen=300)

class MemoryLogHandler(logging.Handler):
    """
    Кольцевой буфер логов в оперативной памяти для панели управления /admin/system.
    """
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg_str = record.getMessage()
            # Защита от дубликатов при мульти-логгерах или повторной эмиссии
            if _LOG_BUFFER:
                last = _LOG_BUFFER[-1]
                if (
                    last.get("timestamp") == record.created
                    and last.get("message") == msg_str
                    and last.get("logger") == record.name
                ):
                    return

            session = get_current_session_safe()
            user_str = _extract_username_safe(session) if session else "SYSTEM"
            ctx_str = f"[{session.ip} | {user_str}]" if session else "[SYSTEM]"
            entry = {
                "timestamp": record.created,
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "ctx": ctx_str,
                "message": msg_str,
            }
            _LOG_BUFFER.append(entry)
        except Exception:
            pass

_memory_log_handler = MemoryLogHandler()
_memory_log_handler.setLevel(logging.DEBUG)

# Добавляем обработчик памяти строго один раз в корневой логгер
_root = logging.getLogger()
if _memory_log_handler not in _root.handlers:
    _root.addHandler(_memory_log_handler)

# Экспортируем готовый логгер по умолчанию (все логи транслируются через root_logger)
logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

def get_recent_logs(limit: int = 150) -> list:
    """Возвращает последние записи логов из кольцевого буфера памяти."""
    items = list(_LOG_BUFFER)
    return items[-limit:]


def get_runtime_log_level() -> str:
    """Возвращает текущий строковый уровень логирования."""
    return logging.getLevelName(logger.level)


def set_runtime_log_level(level_name: str) -> str:
    """Динамически переключает уровень логирования в рантайме."""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    norm = str(level_name).upper().strip()
    if norm not in levels:
        raise ValueError(f"Неизвестный уровень логирования: '{level_name}'. Допустимые: {list(levels.keys())}")
    val = levels[norm]
    logging.getLogger().setLevel(val)
    logger.setLevel(val)
    return norm


