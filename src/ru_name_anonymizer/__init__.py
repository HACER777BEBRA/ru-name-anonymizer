"""Анонимизация русских имён, отчеств и фамилий в тексте."""

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

__all__ = [
    "Anonymizer",
    "AnonymizeResult",
    "NameEntity",
    "Replacement",
    "Replacer",
    "anonymize_names",
    "anonymize_names_consistent",
    "find_names",
    "inflect",
    "preload",
]
__version__ = "0.6.0"
