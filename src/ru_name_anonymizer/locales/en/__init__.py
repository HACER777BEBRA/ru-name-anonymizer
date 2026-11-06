"""Английский язык: небольшой словарь имён и фамилий, без склонения."""

from typing import Dict, List

from ru_name_anonymizer.locales.base import Classified, Locale, Options, titled
from ru_name_anonymizer.locales.en import names


class EnglishLocale(Locale):
    code = "en"
    name = "английский"
    upper = "A-Z"
    lower = "a-z"

    def classify_word(self, token: str, opts: Options) -> Classified:
        is_titled = titled(token)
        word = token.capitalize() if "any_case" in opts.flags else token
        if "first" in opts.enabled:
            entry = names.lookup(word, "ambiguous" in opts.flags, is_titled)
            if entry:
                return "first", entry
        if "surn" in opts.enabled and (is_titled or token.isupper()) and names.is_surname(word):
            return "surn", (word, "c", "nomn")
        return None, None

    def is_common_word(self, stem: str) -> bool:
        return names.is_common_word(stem)

    def default_pools(self) -> Dict[str, List[str]]:
        return {"first:m": names.FIRST["m"], "first:f": names.FIRST["f"], "surn": names.SURNAMES}


LOCALE = EnglishLocale()
