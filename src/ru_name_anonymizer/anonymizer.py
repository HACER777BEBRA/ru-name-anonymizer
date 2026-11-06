import random
import re
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Set, Tuple, Union

from ru_name_anonymizer import english
from ru_name_anonymizer.dictionary import Entry, declension, is_common, load, lookup

LANGUAGES = ("ru", "en")
# Что можно заменять: имена (словарь), отчества и фамилии (суффиксы, английский список), инициалы
KINDS = {"first": "first", "patronymic": "patr", "surname": "surn", "initials": "init"}
Languages = Union[str, Iterable[str]]
Kinds = Union[str, Iterable[str]]

_FIRST_POOL = {
    "m": [
        "Александр", "Дмитрий", "Сергей", "Андрей", "Максим", "Иван", "Никита", "Артём",
        "Владимир", "Кирилл", "Михаил", "Алексей", "Николай", "Павел", "Егор", "Денис",
        "Антон", "Виктор", "Олег", "Игорь", "Станислав", "Евгений", "Василий", "Григорий",
        "Тимофей", "Борис", "Константин", "Юрий", "Леонид", "Ярослав",
    ],
    "f": [
        "Мария", "Анна", "Елена", "Ольга", "Наталья", "Екатерина", "Светлана", "Юлия",
        "Дарья", "Ирина", "Татьяна", "Алина", "Марина", "Полина", "Валентина", "Галина",
        "Ксения", "Вероника", "Евгения", "Лариса", "Оксана", "Людмила", "Виктория", "Инна",
        "Анастасия", "Кристина", "Диана", "Елизавета", "Алла", "Нина",
    ],
}
_PATR_STEMS = [
    "Александров", "Дмитриев", "Сергеев", "Андреев", "Иванов", "Николаев", "Петров",
    "Михайлов", "Владимиров", "Алексеев", "Павлов", "Борисов", "Григорьев", "Романов",
    "Егоров", "Денисов", "Викторов", "Олегов", "Антонов", "Константинов", "Евгеньев",
    "Юрьев", "Станиславов", "Тимофеев", "Леонидов", "Максимов", "Кириллов", "Игорев",
    "Васильев", "Геннадьев",
]
_SURNAME_STEMS = {
    "ov": [
        "Иванов", "Смирнов", "Кузнецов", "Попов", "Соколов", "Лебедев", "Козлов", "Новиков",
        "Морозов", "Волков", "Петров", "Васильев", "Зайцев", "Павлов", "Орлов", "Макаров",
        "Андреев", "Фёдоров", "Михайлов", "Беляев", "Тарасов", "Белов", "Комаров", "Захаров",
        "Борисов", "Яковлев", "Григорьев", "Романов", "Сергеев", "Фролов", "Жуков", "Крылов",
    ],
    "sk": [
        "Достоевск", "Чайковск", "Маяковск", "Тарковск", "Станиславск", "Вяземск", "Белинск",
        "Бродск", "Мусоргск", "Пржевальск", "Заболоцк", "Ковалевск", "Гребенск", "Ходынск",
        "Тухачевск",
    ],
}

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
_SK_M = {"ий": "nomn", "ого": "gent", "ому": "datv", "им": "ablt", "ом": "loct"}
_SK_F = {"ая": "nomn", "ой": "gent", "ую": "accs"}
_SK_M_SUFFIX = {
    "nomn": "ий",
    "gent": "ого",
    "datv": "ому",
    "accs": "ого",
    "ablt": "им",
    "loct": "ом",
}
_SK_F_SUFFIX = {"nomn": "ая", "gent": "ой", "datv": "ой", "accs": "ую", "ablt": "ой", "loct": "ой"}
# основы прилагательных на -ский, которые не фамилии
_SK_STOP = {
    "русск", "польск", "английск", "французск", "немецк", "украинск", "московск", "китайск",
    "японск", "испанск", "итальянск", "еврейск", "детск", "городск", "морск", "сельск",
    "российск", "всероссийск", "советск", "европейск", "американск", "азиатск", "петербургск",
    "белорусск", "казахск", "грузинск", "армянск", "турецк", "шведск", "финск", "датск",
    "норвежск", "канадск", "индийск", "корейск", "арабск", "минск", "мужск", "женск",
}

_PARTS = {  # инициалы, слово с заглавной, слово в любом регистре
    "ru": (
        r"(?<![А-ЯЁа-яё])[А-ЯЁ]\.(?:[  ]?[А-ЯЁ]\.)?",
        r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*",
        r"[А-ЯЁа-яё]{2,}(?:-[А-ЯЁа-яё]{2,})*",
    ),
    "en": (
        r"(?<![A-Za-z])[A-Z]\.(?:[  ]?[A-Z]\.)?",
        r"[A-Z][a-z]+(?:-[A-Z][a-z]+)*",
        r"[A-Za-z]{2,}(?:-[A-Za-z]{2,})*",
    ),
}
_PATR_M_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))ич(а|у|ем|е)?$")
_PATR_F_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))(на|ны|не|ну|ной)$")
_SURN_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ов|ев|ёв|ин|ын))(а|у|ым|е|ой)?$")
_SK_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ск|цк))(ий|ого|ому|им|ом|ая|ой|ую)$")
_RUN_GAP = re.compile(r"^[  ]+$")


def _classify(token: str, aggressive: bool, enabled: FrozenSet[str]):
    """Возвращает (роль, данные); у всех ролей data = (лемма или основа, род, падеж).

    enabled — включённые роли: отключённый источник (словарь, суффиксы) не используется.
    """
    if token[1:2] == ".":
        return "init", (token, "c", "nomn")
    if "-" in token:
        return _classify_compound(token, aggressive, enabled)
    return _classify_word(token, aggressive, enabled)


def _classify_word_en(token: str, aggressive: bool, enabled: FrozenSet[str]):
    titled = token[0].isupper() and token[1:].islower()
    word = token.capitalize() if aggressive else token
    if "first" in enabled:
        entry = english.lookup(word, aggressive, titled)
        if entry:
            return "first", entry
    if "surn" in enabled and (titled or token.isupper()) and english.is_surname(word):
        return "surn", (word, "c", "nomn")
    return None, None


def _classify_word(token: str, aggressive: bool, enabled: FrozenSet[str]):
    if token.isascii():
        return _classify_word_en(token, aggressive, enabled)
    word = token.capitalize() if aggressive else token
    if "first" in enabled:
        entry = lookup(word, aggressive)
        if entry:
            return "first", entry
    if "patr" in enabled:
        m = _PATR_M_RE.match(word)
        if m:
            return "patr", (m.group(1), "m", _PATR_M[m.group(2) or ""])
        m = _PATR_F_RE.match(word)
        if m:
            return "patr", (m.group(1), "f", _PATR_F[m.group(2)])
    if "surn" in enabled and token[0].isupper() and token[1:].islower():
        info = _surname_info(token)
        if info:
            return "surn", info
    return None, None


def _classify_compound(token: str, aggressive: bool, enabled: FrozenSet[str]):
    """«Жан-Люк», «Салтыков-Щедрин»: достаточно узнать одну часть, заменяется всё слово."""
    parts = token.split("-")
    infos = [_classify_word(part, aggressive, enabled) for part in parts]
    known = [(role, data) for role, data in infos if role]
    if not known:
        return None, None
    titled = token.isupper() or all(p[0].isupper() and p[1:].islower() for p in parts)
    if not titled and len(known) != len(parts):
        return None, None
    for role in ("first", "patr", "surn"):
        found = [data for r, data in known if r == role]
        if found:
            return role, found[-1]
    return None, None


def _surname_info(token: str) -> Optional[Entry]:
    m = _SK_RE.match(token)
    if m:
        stem, ending = m.group(1), m.group(2)
        # «-ческий» почти всегда прилагательное: «Технический», «Исторический»
        if stem.lower() in _SK_STOP or stem.endswith("ческ"):
            return None
        if ending in _SK_F:
            return stem, "f", _SK_F[ending]
        return stem, "m", _SK_M[ending]
    m = _SURN_RE.match(token)
    if not m:
        return None
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
        gap = text[prev.end() : m.start()] if prev is not None else None
        # «А.С.Пушкин»: после инициалов слово может идти без пробела
        if gap is not None and (_RUN_GAP.match(gap) or (not gap and prev.group().endswith("."))):
            runs[-1].append(m)
        else:
            runs.append([m])
        prev = m
    return runs


def _normalize_languages(languages: Languages) -> Tuple[str, ...]:
    if isinstance(languages, str):
        languages = (languages,)
    result = tuple(dict.fromkeys(languages))
    unknown = [lang for lang in result if lang not in LANGUAGES]
    if unknown or not result:
        raise ValueError(f"languages: ожидается непустой набор из {LANGUAGES}, получено {result!r}")
    return result


def _normalize_kinds(kinds: Kinds) -> FrozenSet[str]:
    if isinstance(kinds, str):
        kinds = (kinds,)
    kinds = tuple(kinds)
    unknown = [k for k in kinds if k not in KINDS]
    if unknown or not kinds:
        raise ValueError(f"kinds: ожидается непустой набор из {tuple(KINDS)}, получено {kinds!r}")
    return frozenset(KINDS[k] for k in kinds)


@lru_cache(maxsize=None)
def _pattern(languages: Tuple[str, ...], aggressive: bool) -> re.Pattern:
    index = 2 if aggressive else 1
    parts = [_PARTS[lang][0] for lang in languages] + [_PARTS[lang][index] for lang in languages]
    return re.compile("|".join(parts))


def preload(languages: Languages = ("ru",), kinds: Kinds = tuple(KINDS)) -> None:
    """Загружает словарь заранее, чтобы первый вызов не тормозил."""
    if "ru" in _normalize_languages(languages) and "first" in _normalize_kinds(kinds):
        load()


def anonymize_names(
    text: str,
    rng: Optional[random.Random] = None,
    aggressive: bool = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
) -> str:
    """Заменяет имена, отчества и фамилии на случайные, сохраняя род и падеж.

    aggressive=True дополнительно ловит имена в нижнем регистре и КАПСЕ,
    одиночные фамилии и имена, совпадающие с обычными словами («Вера», «Роман»).

    languages — какие словари использовать: "ru", "en" или оба, например ("ru", "en").
    Имя заменяется именем того же языка.

    kinds — что заменять: "first" (имена по словарю), "patronymic" (отчества по суффиксам),
    "surname" (фамилии по суффиксам и английскому списку), "initials". По умолчанию всё.
    Отключённые виды не ищутся: без "first" русский словарь не загружается, а фамилии
    заменяются и без имени рядом.
    """
    return _anonymize(text, rng, aggressive, False, languages, kinds)


def anonymize_names_consistent(
    text: str,
    rng: Optional[random.Random] = None,
    aggressive: bool = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
) -> str:
    """Как anonymize_names, но одно и то же имя заменяется одной и той же заменой."""
    return _anonymize(text, rng, aggressive, True, languages, kinds)


def _anonymize(
    text: str, rng, aggressive: bool, consistent: bool, languages: Languages, kinds: Kinds
) -> str:
    enabled = _normalize_kinds(kinds)
    pattern = _pattern(_normalize_languages(languages), aggressive)
    if not text or not pattern.search(text):
        return text
    rng = rng or random
    memo: Optional[Dict[tuple, str]] = {} if consistent else None

    plans = []
    used: Set[str] = set()
    all_roles = [
        [r for m in run for r in _token_roles(m, aggressive, enabled)]
        for run in _runs(text, pattern)
    ]
    # «Света не было», «Нате, держите»: одиночное имя-омоним в начале фразы считаем обычным
    # словом, если в тексте оно ни разу не встретилось как имя в другом месте
    doubtful = {} if aggressive else _doubtful_common(text, all_roles)
    for roles in all_roles:
        if id(roles) in doubtful:
            continue
        anchors = [r for r in roles if r[1] in ("first", "patr")]
        if not anchors:
            has_init = any(r[1] == "init" for r in roles)
            if aggressive or "first" not in enabled or has_init:
                # «White», «Young» без имени или инициалов рядом — скорее обычные слова
                anchors = [
                    r for r in roles
                    if r[1] == "surn" and (has_init or not english.is_common_word(r[2][0]))
                ]
            if not anchors and "init" in enabled:
                # инициалы без фамилии рядом: только двухбуквенные, «пункт Б.» не трогаем
                anchors = [r for r in roles if r[1] == "init" and _initial_count(r[0].text) > 1]
        if not anchors:
            continue
        plans.append((roles, *_context(anchors)))
        used.update(data[0].lower() for _, role, data in roles if role and role != "init")

    parts: List[str] = []
    pos = 0
    for roles, gender, case in plans:
        for tok, role, data in roles:
            if role == "first":
                new = _new_first(data, gender, used, rng, memo)
            elif role == "patr":
                new = _new_patr(data, used, rng, memo)
            elif role == "init" and "init" in enabled:
                new = _new_initials(tok.text, gender, rng, memo)
            elif role == "surn":
                new = _new_surname(data, gender, case, used, rng, memo)
            else:
                continue
            parts.append(text[pos : tok.start])
            parts.append(_match_case(tok.text, new))
            pos = tok.end
    parts.append(text[pos:])
    return "".join(parts)


class _Token(NamedTuple):
    start: int
    end: int
    text: str


def _token_roles(m: re.Match, aggressive: bool, enabled: FrozenSet[str]):
    """[(токен, роль, данные)]; нераспознанное составное слово разбирается по частям."""
    role, data = _classify(m.group(), aggressive, enabled)
    if role or "-" not in m.group():
        return [(_Token(m.start(), m.end(), m.group()), role, data)]
    # «Мария-то», «Ивану-ка»: целиком не имя, но часть может быть именем
    result, start = [], m.start()
    for part in m.group().split("-"):
        token = _Token(start, start + len(part), part)
        result.append((token, *_classify_word(part, aggressive, enabled)))
        start += len(part) + 1
    return result


def _doubtful_common(text: str, all_roles) -> Set[int]:
    """id групп, где единственное распознанное слово — имя-омоним в начале фразы."""
    doubtful: Dict[int, str] = {}
    confirmed: Set[str] = set()
    for roles in all_roles:
        known = [r for r in roles if r[1]]
        for tok, role, data in known:
            if role != "first" or not is_common(data[0]):
                continue
            if len(known) == 1 and _at_sentence_start(text, tok.start):
                doubtful[id(roles)] = data[0]
            else:
                confirmed.add(data[0])
    return {key for key, lemma in doubtful.items() if lemma not in confirmed}


def _at_sentence_start(text: str, start: int) -> bool:
    before = text[:start].rstrip(" \u00a0\t\r\n«\"„(—–-")
    return not before or before[-1] in ".!?…"


def _initial_count(token: str) -> int:
    return sum(ch.isupper() for ch in token)


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
    if original.isascii():
        return _pick(english.FIRST[gender], used, rng, memo, ("first", original, gender))
    lemma = _pick(_FIRST_POOL[gender], used, rng, memo, ("first", original, gender))
    table = declension(lemma)
    return table.get(case) or table["nomn"]


def _new_patr(data: Entry, used: Set[str], rng, memo) -> str:
    original, gender, case = data
    stem = _pick(_PATR_STEMS, used, rng, memo, ("patr", original))
    suffix = (_PATR_M_SUFFIX if gender == "m" else _PATR_F_SUFFIX)[case]
    return stem + suffix


def _new_surname(data: Entry, gender: str, case: str, used: Set[str], rng, memo) -> str:
    if data[0].isascii():
        return _pick(english.SURNAMES, used, rng, memo, ("surn", data[0]))
    kind = "sk" if data[0].lower().endswith(("ск", "цк")) else "ov"
    stem = _pick(_SURNAME_STEMS[kind], used, rng, memo, ("surn", data[0]))
    if kind == "sk":
        return stem + (_SK_F_SUFFIX if gender == "f" else _SK_M_SUFFIX)[case]
    return stem + (_SURN_F_SUFFIX if gender == "f" else _SURN_M_SUFFIX)[case]


def _new_initials(original: str, gender: str, rng, memo) -> str:
    gender = gender if gender in ("m", "f") else "m"
    latin = original[0].isascii()  # между буквами может быть неразрывный пробел
    letters = "[A-Z]" if latin else "[А-ЯЁ]"
    pools = (english.FIRST[gender],) * 2 if latin else (_FIRST_POOL[gender], _PATR_STEMS)
    new = [
        _pick(sorted({name[0] for name in pools[index]} - {letter}), set(), rng, memo,
              ("init", index, letter))
        for index, letter in enumerate(re.findall(letters, original))
    ]
    replacements = iter(new)
    return re.sub(letters, lambda _: next(replacements), original)
