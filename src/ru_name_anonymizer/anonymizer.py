import random
import re
from typing import Dict, List, Optional, Set, Tuple

from ru_name_anonymizer.dictionary import Entry, declension, load, lookup

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
_TOKEN_ANY = re.compile(r"[А-ЯЁа-яё]{2,}")
_PATR_M_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))ич(а|у|ем|е)?$")
_PATR_F_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))(на|ны|не|ну|ной)$")
_SURN_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ов|ев|ёв|ин|ын))(а|у|ым|е|ой)?$")
_RUN_GAP = re.compile(r"^[  ]+$")


def _classify(token: str, aggressive: bool):
    """Возвращает (роль, данные); у всех ролей data = (лемма или основа, род, падеж)."""
    word = token.capitalize() if aggressive else token
    entry = lookup(word, aggressive)
    if entry:
        return "first", entry
    m = _PATR_M_RE.match(word)
    if m:
        return "patr", (m.group(1), "m", _PATR_M[m.group(2) or ""])
    m = _PATR_F_RE.match(word)
    if m:
        return "patr", (m.group(1), "f", _PATR_F[m.group(2)])
    if token[0].isupper() and token[1:].islower() and _SURN_RE.match(token):
        return "surn", _surname_info(token)
    return None, None


def _surname_info(token: str) -> Entry:
    m = _SURN_RE.match(token)
    stem, ending = m.group(1), m.group(2) or ""
    if ending == "":
        return stem, "m", "nomn"
    if ending == "а":
        return stem, "f", "nomn"
    if ending == "ой":
        return stem, "f", "gent"
    return stem, "m", _SURN_M[ending]


def _runs(text: str, pattern: re.Pattern) -> List[List[re.Match]]:
    runs: List[List[re.Match]] = []
    prev: Optional[re.Match] = None
    for m in pattern.finditer(text):
        if prev is not None and _RUN_GAP.match(text[prev.end() : m.start()]):
            runs[-1].append(m)
        else:
            runs.append([m])
        prev = m
    return runs


def preload() -> None:
    """Загружает словарь заранее, чтобы первый вызов не тормозил."""
    load()


def anonymize_names(
    text: str, rng: Optional[random.Random] = None, aggressive: bool = False
) -> str:
    """Заменяет имена, отчества и фамилии на случайные, сохраняя род и падеж.

    aggressive=True дополнительно ловит имена в нижнем регистре и КАПСЕ,
    одиночные фамилии и имена, совпадающие с обычными словами («Вера», «Роман»).
    """
    return _anonymize(text, rng, aggressive, consistent=False)


def anonymize_names_consistent(
    text: str, rng: Optional[random.Random] = None, aggressive: bool = False
) -> str:
    """Как anonymize_names, но одно и то же имя заменяется одной и той же заменой."""
    return _anonymize(text, rng, aggressive, consistent=True)


def _anonymize(text: str, rng, aggressive: bool, consistent: bool) -> str:
    pattern = _TOKEN_ANY if aggressive else _TOKEN
    if not text or not pattern.search(text):
        return text
    rng = rng or random
    memo: Optional[Dict[tuple, str]] = {} if consistent else None

    plans = []
    used: Set[str] = set()
    for run in _runs(text, pattern):
        roles = [(m, *_classify(m.group(), aggressive)) for m in run]
        anchors = [r for r in roles if r[1] in ("first", "patr")]
        if not anchors and aggressive:
            anchors = [r for r in roles if r[1] == "surn"]
        if not anchors:
            continue
        plans.append((roles, *_context(anchors)))
        used.update(data[0].lower() for _, role, data in roles if role)

    parts: List[str] = []
    pos = 0
    for roles, gender, case in plans:
        for m, role, data in roles:
            if role == "first":
                new = _new_first(data, gender, used, rng, memo)
            elif role == "patr":
                new = _new_patr(data, used, rng, memo)
            elif role == "surn":
                new = _new_surname(data, gender, case, used, rng, memo)
            else:
                continue
            parts.append(text[pos : m.start()])
            parts.append(_match_case(m.group(), new))
            pos = m.end()
    parts.append(text[pos:])
    return "".join(parts)


def _match_case(original: str, new: str) -> str:
    if original.islower():
        return new.lower()
    if original.isupper():
        return new.upper()
    return new


def _context(anchors) -> Tuple[str, str]:
    for _, role, data in anchors:
        if role == "patr":
            return data[1], data[2]
    data = anchors[0][2]
    return data[1], data[2]


def _pick(candidates: List[str], used: Set[str], rng, memo, key) -> str:
    if memo is not None and key in memo:
        return memo[key]
    free = [c for c in candidates if c.lower() not in used]
    value = rng.choice(free or candidates)
    if memo is not None:
        memo[key] = value
        used.add(value.lower())
    return value


def _new_first(data: Entry, run_gender: str, used: Set[str], rng, memo) -> str:
    original, gender, case = data
    if gender == "c":
        gender = run_gender if run_gender in ("m", "f") else "m"
    lemma = _pick(_FIRST_POOL[gender], used, rng, memo, ("first", original, gender))
    table = declension(lemma)
    return table.get(case) or table["nomn"]


def _new_patr(data: Entry, used: Set[str], rng, memo) -> str:
    original, gender, case = data
    stem = _pick(_PATR_STEMS, used, rng, memo, ("patr", original))
    suffix = (_PATR_M_SUFFIX if gender == "m" else _PATR_F_SUFFIX)[case]
    return stem + suffix


def _new_surname(data: Entry, gender: str, case: str, used: Set[str], rng, memo) -> str:
    stem = _pick(_SURNAME_STEMS, used, rng, memo, ("surn", data[0]))
    suffix = (_SURN_M_SUFFIX if gender == "m" else _SURN_F_SUFFIX)[case]
    return stem + suffix
