"""Анонимизация русских имён, отчеств и фамилий в тексте."""

from ru_name_anonymizer.anonymizer import anonymize_names, preload

__all__ = ["anonymize_names", "preload"]
__version__ = "0.2.0"
