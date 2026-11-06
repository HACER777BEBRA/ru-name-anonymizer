"""Анонимизация имён, отчеств, фамилий и ников в тексте; языки и ники подключаются как локали."""

from ru_name_anonymizer.anonymizer import (
    Anonymizer,
    AnonymizeResult,
    NameEntity,
    Replacement,
    Replacer,
    anonymize_names,
    anonymize_names_consistent,
    find_names,
    inflect,
    preload,
)
from ru_name_anonymizer.dynamic import (
    DynamicLocale,
    available_dynamic,
    register_dynamic_locale,
)
from ru_name_anonymizer.locales import Locale, available_languages, register_locale

__all__ = [
    "Anonymizer",
    "DynamicLocale",
    "available_dynamic",
    "register_dynamic_locale",
    "AnonymizeResult",
    "NameEntity",
    "Replacement",
    "Replacer",
    "anonymize_names",
    "anonymize_names_consistent",
    "find_names",
    "Locale",
    "available_languages",
    "inflect",
    "preload",
    "register_locale",
]
__version__ = "1.0.1"
