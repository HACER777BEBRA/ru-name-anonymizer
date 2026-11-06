"""Словарь русских имён (names.txt) и правила их склонения."""

from functools import lru_cache
from importlib import resources
from typing import Dict, NamedTuple, Optional, Tuple

from ru_name_anonymizer.locales.base import CASES, Entry

_STEM_ENDINGS = ("", "а", "я", "й", "ь")
_MAX_CUT = 3

# Имена, совпадающие с обычными словами. _COMMON распознаются всегда (если слово с заглавной),
# _AMBIGUOUS только в режиме aggressive
_COMMON = {
    "Света": ("f", "Светы Свете Свету Светой Свете"),
    "Вера": ("f", "Веры Вере Веру Верой Вере"),
    "Ната": ("f", "Наты Нате Нату Натой Нате"),
}
_AMBIGUOUS = {
    "Надежда": ("f", "Надежды Надежде Надежду Надеждой Надежде"),
    "Любовь": ("f", "Любови Любови Любовь Любовью Любови"),
    "Роман": ("m", "Романа Роману Романа Романом Романе"),
}
_AMBIGUOUS_GENDERS = {
    lemma: gender for lemma, (gender, _) in {**_COMMON, **_AMBIGUOUS}.items()
}


def _index_forms(table) -> Dict[str, Tuple[str, str]]:
    index: Dict[str, Tuple[str, str]] = {}
    for lemma, (_, forms) in table.items():
        index.setdefault(lemma, (lemma, "nomn"))
        for case, form in zip(CASES[1:], forms.split()):
            index.setdefault(form, (lemma, case))
    return index


_COMMON_FORMS = _index_forms(_COMMON)
_AMBIGUOUS_FORMS = _index_forms(_AMBIGUOUS)


class Dictionary(NamedTuple):
    genders: Dict[str, str]
    exceptions: Dict[str, Tuple[Optional[str], ...]]
    exception_forms: Dict[str, Tuple[str, str]]


def regular_forms(lemma: str, gender: str) -> Optional[Tuple[str, ...]]:
    """Падежи gent..loct по правилам; None, если для окончания правила нет."""
    last, stem = lemma[-1], lemma[:-1]
    if last == "а":
        gent = stem + ("и" if stem[-1:] in "гкхжчшщ" else "ы")
        ablt = stem + ("ей" if stem[-1:] in "жчшщц" else "ой")
        return gent, stem + "е", stem + "у", ablt, stem + "е"
    if last == "я":
        if stem[-1:] == "и":
            return stem + "и", stem + "и", stem + "ю", stem + "ей", stem + "и"
        return stem + "и", stem + "е", stem + "ю", stem + "ей", stem + "е"
    if last == "й":
        loct = stem + ("и" if stem[-1:] == "и" else "е")
        return stem + "я", stem + "ю", stem + "я", stem + "ем", loct
    if last == "ь":
        if gender == "f":
            return None
        return stem + "я", stem + "ю", stem + "я", stem + "ем", stem + "е"
    if last in "бвгджзклмнпрстфхцчшщ":
        ablt = lemma + ("ем" if last in "жчшщц" else "ом")
        return lemma + "а", lemma + "у", lemma + "а", ablt, lemma + "е"
    return None


@lru_cache(maxsize=1)
def load() -> Dictionary:
    genders: Dict[str, str] = {}
    exceptions: Dict[str, Tuple[Optional[str], ...]] = {}
    exception_forms: Dict[str, Tuple[str, str]] = {}
    text = resources.files(__package__).joinpath("names.txt").read_text("utf-8")
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        lemma, gender, *forms = line.split(" ")
        genders[lemma] = gender
        if forms:
            values = tuple(None if f == "-" else f for f in forms)
            exceptions[lemma] = values
            for case, form in zip(CASES[1:], values):
                if form:
                    exception_forms.setdefault(form, (lemma, case))
    return Dictionary(genders, exceptions, exception_forms)


def is_common(lemma: str) -> bool:
    """Имя из _COMMON: совпадает с обычным словом, но распознаётся и без aggressive."""
    return lemma in _COMMON


def declension(lemma: str, gender: Optional[str] = None) -> Dict[str, str]:
    """Падеж -> словоформа для леммы из словаря или с регулярным окончанием.

    gender нужен для имён не из словаря: «Нинель» склоняется по-разному в разных родах.
    """
    d = load()
    gender = gender or d.genders.get(lemma, "m")
    regular = regular_forms(lemma, gender) or ()
    forms = d.exceptions.get(lemma)
    if forms is None:
        forms = regular
    else:  # пропуски в исключениях добираем по правилам, чтобы падеж не терялся при замене
        forms = tuple(f or (regular[i] if i < len(regular) else None) for i, f in enumerate(forms))
    table = {"nomn": lemma}
    table.update({case: f for case, f in zip(CASES[1:], forms) if f})
    return table


@lru_cache(maxsize=8192)
def lookup(token: str, ambiguous: bool = False) -> Optional[Entry]:
    """Самая ранняя по алфавиту лемма, чья словоформа совпала с токеном."""
    d = load()
    if token in d.genders:
        return token, d.genders[token], "nomn"
    found = []
    if token in d.exception_forms:
        found.append(d.exception_forms[token])
    if token in _COMMON_FORMS:
        found.append(_COMMON_FORMS[token])
    if ambiguous and token in _AMBIGUOUS_FORMS:
        found.append(_AMBIGUOUS_FORMS[token])
    for cut in range(1, _MAX_CUT + 1):
        stem = token[: len(token) - cut]
        if len(stem) < 2:
            break
        for ending in _STEM_ENDINGS:
            lemma = stem + ending
            gender = d.genders.get(lemma)
            if gender is None or lemma in d.exceptions:
                continue
            forms = regular_forms(lemma, gender)
            if forms and token in forms:
                found.append((lemma, CASES[1 + forms.index(token)]))
    if not found:
        return None
    lemma, case = min(found, key=lambda f: (f[0], CASES.index(f[1])))
    return lemma, d.genders.get(lemma) or _AMBIGUOUS_GENDERS[lemma], case
