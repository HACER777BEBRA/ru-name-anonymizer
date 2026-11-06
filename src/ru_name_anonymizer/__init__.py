"""Анонимизация имён, отчеств и фамилий в тексте; языки подключаются как локали."""

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
from ru_name_anonymizer.locales import Locale, available_languages, register_locale

__all__ = [
    "Anonymizer",
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
__version__ = "0.7.0"
