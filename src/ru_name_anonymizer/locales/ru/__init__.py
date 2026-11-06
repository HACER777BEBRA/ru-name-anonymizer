"""Русский язык: словарь имён, отчества и фамилии по суффиксам, склонение по падежам."""

from functools import lru_cache
from typing import AbstractSet, Dict, List, Optional, Sequence, Tuple

from ru_name_anonymizer.locales.base import CASES, Classified, Entry, Locale, Options, titled
from ru_name_anonymizer.locales.ru import morphology as morph
from ru_name_anonymizer.locales.ru import pools
from ru_name_anonymizer.locales.ru.dictionary import declension, is_common, load, lookup


def _decline_first(name: str, case: str, gender: Optional[str]) -> str:
    table = declension(name, gender if gender in ("m", "f") else None)
    return table.get(case) or name


@lru_cache(maxsize=1)
def _derived_stems() -> Tuple[str, ...]:
    """Основы вида «Иванов», «Сергеев», «Юрьев» из мужских имён словаря."""
    stems = set()
    for name, gender in load().genders.items():
        if gender != "m" or len(name) < 3 or "-" in name:
            continue
        if name[-1] in "бвгдзклмнпрстфх":
            stems.add(name + "ов")
        elif name.endswith("ий"):
            stems.add(name[:-2] + "ьев")
        elif name.endswith(("ей", "ай", "уй", "ой")) or name[-1] == "ь":
            stems.add(name[:-1] + "ев")
    return tuple(sorted(stems))


class RussianLocale(Locale):
    code = "ru"
    name = "русский"
    upper = "А-ЯЁ"
    lower = "а-яё"

    def preload(self, roles: AbstractSet[str]) -> None:
        if "first" in roles:
            load()

    def classify_word(self, token: str, opts: Options) -> Classified:
        word = token.capitalize() if "any_case" in opts.flags else token
        if "first" in opts.enabled:
            ambiguous = "ambiguous" in opts.flags
            entry = lookup(word, ambiguous)
            # «света», «ВЕРА» не с заглавной — скорее обычные слова, если омонимы не включены
            if entry and (ambiguous or titled(token) or not is_common(entry[0])):
                return "first", entry
        if "patr" in opts.enabled:
            info = morph.patronymic_info(word)
            if info:
                return "patr", info
        if "surn" in opts.enabled and titled(token):
            info = morph.surname_info(token)
            if info:
                return "surn", info
        return None, None

    def is_common_name(self, lemma: str) -> bool:
        return is_common(lemma)

    def decline(self, role: str, stem: str, gender: str, case: str) -> str:
        if role == "first":
            return _decline_first(stem, case, gender)
        if role == "patr":
            return morph.decline_patronymic(stem, gender, case)
        return morph.decline_surname(stem, gender, case)

    def normal_form(self, role: str, data: Entry, gender: str) -> str:
        stem, female = data[0], gender == "f"
        if role == "patr":
            return stem + ("на" if female else "ич")
        if role == "surn":
            if morph.is_sk(stem):
                return stem + ("ая" if female else "ий")
            return stem + ("а" if female else "")
        return stem

    def inflect(self, name: str, case: str, role: str, gender: Optional[str]) -> str:
        if role == "first":
            return _decline_first(name, case, gender)
        info = morph.patronymic_info(name) if role == "patr" else morph.surname_info(name)
        if not info:
            return name
        return self.decline(role, info[0], gender if gender in ("m", "f") else info[1], case)

    def default_pools(self) -> Dict[str, List[str]]:
        return {
            "first:m": pools.FIRST["m"],
            "first:f": pools.FIRST["f"],
            "patr": pools.PATR_STEMS,
            "surn:ov": pools.SURNAME_STEMS["ov"],
            "surn:sk": pools.SURNAME_STEMS["sk"],
        }

    @lru_cache(maxsize=None)
    def fallback_pool(self, category: str) -> Tuple[str, ...]:
        """Имена и производные основы из словаря — для больших датасетов."""
        primary = set(self.default_pools()[category])
        if category.startswith("first:"):
            gender = category[-1]
            names = (
                n for n, g in load().genders.items()
                if g == gender and "-" not in n and len(declension(n, gender)) == len(CASES)
            )
        elif category in ("patr", "surn:ov"):
            names = iter(_derived_stems())
        else:  # surn:sk
            names = (s + "ск" for s in _derived_stems() if (s + "ск").lower() not in morph.SK_STOP)
        return tuple(sorted(n for n in names if n not in primary))

    def surname_categories(self, stem: str) -> Sequence[str]:
        return ("surn:sk", "surn:ov") if morph.is_sk(stem) else ("surn:ov", "surn:sk")

    def custom_pools(self, key: str, values: List[str]) -> Dict[str, List[str]]:
        if key in ("first_m", "first_f"):
            return {f"first:{key[-1]}": values}
        if key == "patronymic":
            parsed = [morph.parse_patronymic(v) for v in values]
            if not all(
                p and morph.decline_patronymic(p[0], p[1], "nomn") == v
                for p, v in zip(parsed, values)
            ):
                raise ValueError(
                    "pools['patronymic']: ожидаются отчества в именительном падеже "
                    f"на -ович/-евич/-овна/-евна, получено {values!r}"
                )
            return {"patr": list(dict.fromkeys(p[0] for p in parsed if p))}
        stems = []
        for value in values:
            info = morph.surname_info(value)
            if not info or info[2] != "nomn":
                raise ValueError(
                    "pools['surname']: ожидаются фамилии в именительном падеже "
                    f"на -ов/-ев/-ин/-ын/-ский/-цкий, получено {value!r}"
                )
            stems.append(info[0])
        stems = list(dict.fromkeys(stems))
        sk = [s for s in stems if morph.is_sk(s)]
        return {"surn:sk": sk, "surn:ov": [s for s in stems if s not in sk]}

    def initial_letters(self, gender: str, index: int) -> AbstractSet[str]:
        source = pools.FIRST[gender] if index == 0 else pools.PATR_STEMS
        return {name[0] for name in source}


LOCALE = RussianLocale()
