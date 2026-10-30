"""Анонимизация русских имён, отчеств и фамилий в тексте."""

from ru_name_anonymizer.anonymizer import anonymize_names, anonymize_names_consistent, preload

__all__ = ["anonymize_names", "anonymize_names_consistent", "preload"]
__version__ = "0.3.0"
