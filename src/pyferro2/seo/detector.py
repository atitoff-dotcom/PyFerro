"""
Высокопроизводительное распознавание поисковых, социальных и ИИ-роботов
по User-Agent (двухслойный гибридный анализ) и утилиты извлечения HTTP-заголовков RSGI.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
import re
from typing import Any
from urllib.parse import parse_qs

from pyferro2.seo.models import get_seo_config

# Фаза 1: Скомпилированный регистронезависимый паттерн для явных ботов
# 1. Поисковые системы: Google, Yandex, Bing, Baidu, DuckDuckGo, Yahoo, Mail.ru, Ecosia, Seznam, Sogou
# 2. Соцсети и мессенджеры: Telegram, VK, Twitter, Facebook, WhatsApp, Discord, Slack, LinkedIn, Pinterest, Skype, Viber
# 3. ИИ-краулеры и LLM-индексаторы: OpenAI/ChatGPT, Perplexity, Claude/Anthropic, Applebot, ByteSpider, CommonCrawl, Cohere, Diffbot, Amazonbot
BOT_USER_AGENT_PATTERN = re.compile(
    r"("
    r"googlebot|yandex(?:bot|images|video|media|blogs|favicons)?|bingbot|baiduspider|"
    r"duckduckbot|yahoo!\s+slurp|mail\.ru_bot|ecosia|seznambot|sogou|"
    r"telegrambot|vkshare|twitterbot|facebookexternalhit|whatsapp|discordbot|"
    r"slackbot|linkedinbot|pinterest(?:bot)?|skypeuripreview|viber|"
    r"oai-searchbot|chatgpt-user|gptbot|perplexitybot|claudebot|anthropic-ai|"
    r"applebot-extended|applebot|bytespider|ccbot|cohere-ai|diffbot|amazonbot"
    r")",
    re.IGNORECASE,
)

# Фаза 1.5: Известные консольные утилиты и скриптовые библиотеки (не браузеры)
CLI_SCRAPERS_PATTERN = re.compile(
    r"^(?:curl|wget|python|aiohttp|httpx|requests|urllib|go-http-client|node-fetch|axios|postman|scrapy|java|httpie)",
    re.IGNORECASE,
)

# Фаза 2: Валидные браузерные движки и идентификаторы реальных браузеров
BROWSER_ENGINE_PATTERN = re.compile(
    r"(?:AppleWebKit|WebKit|Gecko|Trident|Blink|Chrome|Safari|Firefox|Opera|Edge|Edg)",
    re.IGNORECASE,
)


def extract_header(scope: Any, header_name: str, default: str = "") -> str:
    """Безопасно извлекает значение HTTP-заголовка из RSGI scope или словаря."""
    target = header_name.lower()
    headers = getattr(scope, "headers", None)
    if headers is None and isinstance(scope, dict):
        headers = scope.get("headers")

    if headers is None:
        return default

    if hasattr(headers, "get"):
        val = headers.get(target) or headers.get(header_name)
        return str(val) if val is not None else default

    if isinstance(headers, (list, tuple)):
        for k, v in headers:
            k_str = k.decode("latin-1").lower() if isinstance(k, bytes) else str(k).lower()
            if k_str == target:
                return v.decode("latin-1") if isinstance(v, bytes) else str(v)

    return default


def extract_query_params(scope: Any) -> dict[str, str]:
    """Извлекает плоский словарь query-параметров (`?bot=1`) из RSGI scope."""
    qs = getattr(scope, "query_string", None)
    if qs is None and isinstance(scope, dict):
        qs = scope.get("query_string")
    if not qs:
        return {}
    if isinstance(qs, bytes):
        qs = qs.decode("latin-1")
    parsed = parse_qs(str(qs), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


def extract_cookies(scope: Any) -> dict[str, str]:
    """Извлекает словарь cookies из заголовка `cookie` RSGI scope."""
    raw_cookie = extract_header(scope, "cookie", default="")
    if not raw_cookie:
        return {}
    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
        return {k: morsel.value for k, morsel in cookie.items()}
    except Exception:
        out: dict[str, str] = {}
        for part in raw_cookie.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out


def is_bot(scope_or_ua: str | Any | None) -> bool:
    """
    Определяет, является ли клиент поисковым краулером, ботом соцсети,
    ИИ-ботом или текстовым клиентом (двухслойный гибридный анализ).
    Принимает либо строку User-Agent, либо RSGI scope (или словарь запроса).
    """
    if scope_or_ua is None:
        return False

    if isinstance(scope_or_ua, str):
        ua = scope_or_ua.strip()
    else:
        ua = extract_header(scope_or_ua, "user-agent", default="").strip()

    if not ua:
        return False

    cfg = get_seo_config()

    # 0. Пользовательский детектор разработчика (если задан)
    if cfg.custom_detector is not None:
        verdict = cfg.custom_detector(scope_or_ua)
        if verdict is not None:
            return bool(verdict)

    # 0.1. Пользовательские дополнительные паттерны
    if cfg.extra_bot_patterns:
        for pattern in cfg.extra_bot_patterns:
            if re.search(pattern, ua, re.IGNORECASE):
                return True

    # 1. Фаза 1: Проверка по явному черному списку ботов/краулеров
    if BOT_USER_AGENT_PATTERN.search(ua):
        return True

    # 2. Фаза 1.5: CLI-утилиты и HTTP библиотеки
    if CLI_SCRAPERS_PATTERN.search(ua):
        return True

    # 3. Фаза 2: Инвертированный вайтлист браузерных движков
    if not BROWSER_ENGINE_PATTERN.search(ua):
        return True

    return False
