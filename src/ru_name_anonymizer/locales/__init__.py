"""Реестр локалей.

Встроенная локаль — подпакет locales/<код>/ с объектом LOCALE (экземпляр Locale);
она находится автоматически. Локаль из своего кода подключается register_locale().
"""

import importlib
import pkgutil
import re
import threading
from typing import Dict, Tuple

from ru_name_anonymizer.locales.base import CASES, Entry, Locale, Options, titled

__all__ = [
    "CASES",
    "Entry",
    "Locale",
    "Options",
    "available_languages",
    "get_locale",
    "register_locale",
    "titled",
]

_PRIORITY = ("ru", "en")  # при совпадении алфавитов (pools, inflect) выигрывает более ранняя
_CODE_RE = re.compile(r"[a-z][a-z0-9_]*")
_registry: Dict[str, Locale] = {}
_lock = threading.Lock()


def _builtin_codes() -> Tuple[str, ...]:
    found = {m.name for m in pkgutil.iter_modules(__path__) if m.ispkg}
    return tuple(c for c in _PRIORITY if c in found) + tuple(sorted(found - set(_PRIORITY)))


def register_locale(locale: Locale, replace: bool = False) -> None:
    """Подключает локаль; после этого её код можно передавать в languages."""
    if not isinstance(locale, Locale):
        raise TypeError(f"register_locale: ожидается экземпляр Locale, получено {locale!r}")
    if not _CODE_RE.fullmatch(locale.code or ""):
        raise ValueError(f"register_locale: недопустимый код языка {locale.code!r}")
    if not locale.upper or not locale.lower:
        raise ValueError(f"register_locale: у локали {locale.code!r} не заданы upper и lower")
    try:
        re.compile(f"[{locale.upper}{locale.lower}]")
    except re.error as error:
        raise ValueError(f"register_locale: неверные upper/lower ({error})") from None
    with _lock:
        if locale.code in _registry and _registry[locale.code] is not locale and not replace:
            raise ValueError(
                f"register_locale: язык {locale.code!r} уже подключён (replace=True заменит)"
            )
        _registry[locale.code] = locale


def get_locale(code: str) -> Locale:
    """Локаль по коду; встроенная загружается при первом обращении."""
    locale = _registry.get(code)
    if locale is not None:
        return locale
    if not isinstance(code, str) or code not in _builtin_codes():
        raise KeyError(code)
    module = importlib.import_module(f"{__name__}.{code}")
    with _lock:
        return _registry.setdefault(code, module.LOCALE)


def available_languages() -> Tuple[str, ...]:
    """Коды всех доступных языков: встроенные и подключённые через register_locale."""
    builtin = _builtin_codes()
    return builtin + tuple(c for c in _registry if c not in builtin)
