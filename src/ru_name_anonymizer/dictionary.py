from functools import lru_cache
from importlib import resources
from typing import Dict, NamedTuple, Optional, Tuple

CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
_STEM_ENDINGS = ("", "а", "я", "й", "ь")
_MAX_CUT = 3

Entry = Tuple[str, str, str]  # (лемма, род, падеж)

# Имена, совпадающие с обычными словами; распознаются только в режиме aggressive
_AMBIGUOUS = {
    "Вера": ("f", "Веры Вере Веру Верой Вере"),
    "Надежда": ("f", "Надежды Надежде Надежду Надеждой Надежде"),
    "Любовь": ("f", "Любови Любови Любовь Любовью Любови"),
    "Роман": ("m", "Романа Роману Романа Романом Романе"),
}
_AMBIGUOUS_GENDERS = {lemma: gender for lemma, (gender, _) in _AMBIGUOUS.items()}
_AMBIGUOUS_FORMS: Dict[str, Tuple[str, str]] = {}
for _lemma, (_, _forms) in _AMBIGUOUS.items():
    _AMBIGUOUS_FORMS.setdefault(_lemma, (_lemma, "nomn"))
    for _case, _form in zip(CASES[1:], _forms.split()):
        _AMBIGUOUS_FORMS.setdefault(_form, (_lemma, _case))


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
    text = resources.files("ru_name_anonymizer").joinpath("names.txt").read_text("utf-8")
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


def declension(lemma: str) -> Dict[str, str]:
    """Падеж -> словоформа для леммы из словаря или с регулярным окончанием."""
    d = load()
    forms = d.exceptions.get(lemma)
    if forms is None:
        forms = regular_forms(lemma, d.genders.get(lemma, "m")) or ()
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
