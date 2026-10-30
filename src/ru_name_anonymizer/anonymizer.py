import gzip
import random
import re
from functools import lru_cache
from importlib import resources
from typing import Dict, List, Optional, Set, Tuple

CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")

_FIRST_POOL = {
    "m": [
        "Александр",
        "Дмитрий",
        "Сергей",
        "Андрей",
        "Максим",
        "Иван",
        "Никита",
        "Артём",
        "Владимир",
        "Кирилл",
        "Михаил",
        "Алексей",
        "Николай",
        "Павел",
    ],
    "f": [
        "Мария",
        "Анна",
        "Елена",
        "Ольга",
        "Наталья",
        "Екатерина",
        "Светлана",
        "Юлия",
        "Дарья",
        "Ирина",
        "Татьяна",
        "Алина",
        "Марина",
        "Полина",
    ],
}
_PATR_STEMS = [
    "Александров",
    "Дмитриев",
    "Сергеев",
    "Андреев",
    "Иванов",
    "Николаев",
    "Петров",
    "Михайлов",
    "Владимиров",
    "Алексеев",
]
_SURNAME_STEMS = [
    "Иванов",
    "Смирнов",
    "Кузнецов",
    "Попов",
    "Соколов",
    "Лебедев",
    "Козлов",
    "Новиков",
    "Морозов",
    "Волков",
    "Петров",
    "Васильев",
    "Зайцев",
    "Павлов",
    "Орлов",
    "Макаров",
    "Андреев",
    "Фёдоров",
]

_PATR_M = {"": "nomn", "а": "gent", "у": "datv", "ем": "ablt", "е": "loct"}
_PATR_F = {"на": "nomn", "ны": "gent", "не": "datv", "ну": "accs", "ной": "ablt"}
_SURN_M = {"": "nomn", "а": "gent", "у": "datv", "ым": "ablt", "е": "loct"}
_SURN_F = {"а": "nomn", "ой": "gent", "у": "accs", "ым": "ablt"}
_PATR_M_SUFFIX = {
    "nomn": "ич",
    "gent": "ича",
    "datv": "ичу",
    "accs": "ича",
    "ablt": "ичем",
    "loct": "иче",
}
_PATR_F_SUFFIX = {
    "nomn": "на",
    "gent": "ны",
    "datv": "не",
    "accs": "ну",
    "ablt": "ной",
    "loct": "не",
}
_SURN_M_SUFFIX = {"nomn": "", "gent": "а", "datv": "у", "accs": "а", "ablt": "ым", "loct": "е"}
_SURN_F_SUFFIX = {"nomn": "а", "gent": "ой", "datv": "ой", "accs": "у", "ablt": "ой", "loct": "ой"}

_TOKEN = re.compile(r"[А-ЯЁ][а-яё]+")
_PATR_M_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))ич(а|у|ем|е)?$")
_PATR_F_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))(на|ны|не|ну|ной)$")
_SURN_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ов|ев|ёв|ин|ын))(а|у|ым|е|ой)?$")
_RUN_GAP = re.compile(r"^[  ]+$")

_Form = Tuple[str, str, str]  # (лемма, род, падеж)


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[str, List[_Form]], Dict[str, Dict[str, str]]]:
    forms: Dict[str, List[_Form]] = {}
    lemmas: Dict[str, Dict[str, str]] = {}
    data = resources.files("ru_name_anonymizer").joinpath("names.tsv.gz").read_bytes()
    for line in gzip.decompress(data).decode("utf-8").splitlines():
        lemma, gender, case, form = line.split("\t")
        forms.setdefault(form, []).append((lemma, gender, case))
        lemmas.setdefault(lemma, {})[case] = form
    return forms, lemmas


def _classify(token: str):
    """Возвращает (роль, данные) для слова с заглавной буквы."""
    forms, _ = _load()
    if token in forms:
        return "first", forms[token][0]
    m = _PATR_M_RE.match(token)
    if m:
        return "patr", (m.group(1), "m", _PATR_M[m.group(2) or ""])
    m = _PATR_F_RE.match(token)
    if m:
        return "patr", (m.group(1), "f", _PATR_F[m.group(2)])
    if _SURN_RE.match(token):
        return "surn", token
    return None, None


def _runs(text: str) -> List[List[re.Match]]:
    runs: List[List[re.Match]] = []
    prev: Optional[re.Match] = None
    for m in _TOKEN.finditer(text):
        if prev is not None and _RUN_GAP.match(text[prev.end() : m.start()]):
            runs[-1].append(m)
        else:
            runs.append([m])
        prev = m
    return runs


def _surname_form(token: str, gender: str, case: str) -> Tuple[str, str]:
    m = _SURN_RE.match(token)
    ending = m.group(2) or ""
    if gender == "f":
        return m.group(1), _SURN_F.get(ending, "nomn")
    return m.group(1), _SURN_M.get(ending, "nomn")


def anonymize_names(text: str, rng: Optional[random.Random] = None) -> str:
    """Заменяет имена, отчества и фамилии на случайные, сохраняя род и падеж."""
    if not text:
        return text
    rng = rng or random
    forms, lemmas = _load()

    replacements: List[Tuple[int, int, str]] = []
    used: Set[str] = set()
    plans = []
    for run in _runs(text):
        roles = [(m, *_classify(m.group())) for m in run]
        anchors = [r for r in roles if r[1] in ("first", "patr")]
        if not anchors:
            continue
        gender, case = _context(anchors)
        plans.append((roles, gender, case))
        for m, role, data in roles:
            if role == "first":
                used.add(data[0].lower())
            elif role == "patr":
                used.add(data[0].lower())
            elif role == "surn":
                used.add(_SURN_RE.match(m.group()).group(1).lower())

    for roles, gender, case in plans:
        for m, role, data in roles:
            if role == "first":
                new = _new_first(data, gender, case, lemmas, used, rng)
            elif role == "patr":
                new = _new_patr(data, used, rng)
            elif role == "surn":
                new = _new_surname(m.group(), gender, case, used, rng)
            else:
                continue
            replacements.append((m.start(), m.end(), new))

    for start, end, new in sorted(replacements, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def _context(anchors) -> Tuple[str, str]:
    for _, role, data in anchors:
        if role == "patr":
            return data[1], data[2]
    _, _, (_, gender, case) = anchors[0]
    return gender, case


def _pick(candidates: List[str], used: Set[str], rng) -> str:
    free = [c for c in candidates if c.lower() not in used]
    return rng.choice(free or candidates)


def _new_first(data: _Form, run_gender, run_case, lemmas, used, rng) -> str:
    _, gender, case = data
    if gender == "c":
        gender = run_gender if run_gender in ("m", "f") else "m"
    lemma = _pick(_FIRST_POOL[gender], used, rng)
    table = lemmas.get(lemma, {})
    return table.get(case) or table.get("nomn", lemma)


def _new_patr(data, used, rng) -> str:
    _, gender, case = data
    stem = _pick(_PATR_STEMS, used, rng)
    suffix = (_PATR_M_SUFFIX if gender == "m" else _PATR_F_SUFFIX)[case]
    return stem + suffix


def _new_surname(token: str, gender: str, case: str, used, rng) -> str:
    stem = _pick(_SURNAME_STEMS, used, rng)
    suffix = (_SURN_M_SUFFIX if gender == "m" else _SURN_F_SUFFIX)[case]
    return stem + suffix
