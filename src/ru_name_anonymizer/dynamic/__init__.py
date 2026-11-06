"""Реестр динамических локалей: ники и другие идентификаторы, известные во время работы.

Встроенные: "tg" (Telegram) и "nick" (любые строки). Свою локаль подключает
register_dynamic_locale().
"""

import re
import threading
from typing import Dict, Tuple

from ru_name_anonymizer.dynamic.base import DynamicLocale, NickLocale, TelegramLocale

__all__ = [
    "DynamicLocale",
    "NickLocale",
    "TelegramLocale",
    "available_dynamic",
    "get_dynamic_locale",
    "register_dynamic_locale",
]

_CODE_RE = re.compile(r"[a-z][a-z0-9_]*")
_registry: Dict[str, DynamicLocale] = {"tg": TelegramLocale(), "nick": NickLocale()}
_lock = threading.Lock()


def register_dynamic_locale(locale: DynamicLocale, replace: bool = False) -> None:
    """Подключает динамическую локаль; после этого её код можно передавать в dynamic=."""
    if not isinstance(locale, DynamicLocale):
        raise TypeError(
            f"register_dynamic_locale: ожидается экземпляр DynamicLocale, получено {locale!r}"
        )
    if not _CODE_RE.fullmatch(locale.code or ""):
        raise ValueError(f"register_dynamic_locale: недопустимый код {locale.code!r}")
    try:
        re.compile(f"[{locale.word_chars}]")
        if locale.detect:
            re.compile(locale.detect)
    except re.error as error:
        raise ValueError(
            f"register_dynamic_locale: неверное регулярное выражение ({error})"
        ) from None
    with _lock:
        if locale.code in _registry and _registry[locale.code] is not locale and not replace:
            raise ValueError(
                f"register_dynamic_locale: код {locale.code!r} уже занят (replace=True заменит)"
            )
        _registry[locale.code] = locale


def get_dynamic_locale(code: str) -> DynamicLocale:
    """Динамическая локаль по коду; неизвестный код — ValueError."""
    locale = _registry.get(code) if isinstance(code, str) else None
    if locale is None:
        raise ValueError(
            f"неизвестная динамическая локаль {code!r}, доступны {available_dynamic()}"
        )
    return locale


def available_dynamic() -> Tuple[str, ...]:
    """Коды всех динамических локалей: встроенных и подключённых."""
    return tuple(_registry)
