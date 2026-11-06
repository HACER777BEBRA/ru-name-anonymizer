import random
import re
import threading
import warnings
from collections import abc
from functools import lru_cache
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
)

from ru_name_anonymizer import english
from ru_name_anonymizer.dictionary import CASES, Entry, declension, is_common, load, lookup

LANGUAGES = ("ru", "en")
# Что можно заменять: имена (словарь), отчества и фамилии (суффиксы, английский список), инициалы
KINDS = {"first": "first", "patronymic": "patr", "surname": "surn", "initials": "init"}
# Из чего состоит aggressive: любой регистр, фамилии без имени рядом, имена-омонимы
AGGRESSIVE = ("any_case", "lone_surnames", "ambiguous")
# Ключи параметра pools
POOL_KEYS = ("first_m", "first_f", "patronymic", "surname")
STATE_VERSION = 1

Languages = Union[str, Iterable[str]]
Kinds = Union[str, Iterable[str]]
Aggressive = Union[bool, str, Iterable[str]]
Pools = Mapping[str, Union[str, Iterable[str]]]

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
        r"(?<![А-ЯЁа-яё])[А-ЯЁ]\.(?:[  ]?[А-ЯЁ]\.)?",
        r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*",
        r"[А-ЯЁа-яё]{2,}(?:-[А-ЯЁа-яё]{2,})*",
    ),
    "en": (
        r"(?<![A-Za-z])[A-Z]\.(?:[  ]?[A-Z]\.)?",
        r"[A-Z][a-z]+(?:-[A-Z][a-z]+)*",
        r"[A-Za-z]{2,}(?:-[A-Za-z]{2,})*",
    ),
}
_PATR_M_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))ич(а|у|ем|е)?$")
_PATR_F_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))(на|ны|не|ну|ной)$")
_SURN_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ов|ев|ёв|ин|ын))(а|у|ым|е|ой)?$")
_SK_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ск|цк))(ий|ого|ому|им|ом|ая|ой|ую)$")
_RUN_GAP = re.compile(r"^[  ]+$")
_RU_NAME_RE = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*$")
_EN_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z]+)*$")


class _Options(NamedTuple):
    enabled: FrozenSet[str]  # включённые роли: отключённый источник не используется
    flags: FrozenSet[str]  # включённые части aggressive
    exclude: FrozenSet[str]  # слова, которые не трогаем (casefold)


def _classify(token: str, opts: _Options):
    """Возвращает (роль, данные); у всех ролей data = (лемма или основа, род, падеж)."""
    if token[1:2] == ".":
        return "init", (token, "c", "nomn")
    if "-" in token:
        return _classify_compound(token, opts)
    return _classify_word(token, opts)


def _titled(token: str) -> bool:
    return token[0].isupper() and token[1:].islower()


def _classify_word_en(token: str, opts: _Options):
    titled = _titled(token)
    word = token.capitalize() if "any_case" in opts.flags else token
    if "first" in opts.enabled:
        entry = english.lookup(word, "ambiguous" in opts.flags, titled)
        if entry:
            return "first", entry
    if "surn" in opts.enabled and (titled or token.isupper()) and english.is_surname(word):
        return "surn", (word, "c", "nomn")
    return None, None


def _classify_word(token: str, opts: _Options):
    if token.isascii():
        return _classify_word_en(token, opts)
    word = token.capitalize() if "any_case" in opts.flags else token
    if "first" in opts.enabled:
        ambiguous = "ambiguous" in opts.flags
        entry = lookup(word, ambiguous)
        # «света», «ВЕРА» не с заглавной — скорее обычные слова, если омонимы не включены
        if entry and (ambiguous or _titled(token) or not is_common(entry[0])):
            return "first", entry
    if "patr" in opts.enabled:
        m = _PATR_M_RE.match(word)
        if m:
            return "patr", (m.group(1), "m", _PATR_M[m.group(2) or ""])
        m = _PATR_F_RE.match(word)
        if m:
            return "patr", (m.group(1), "f", _PATR_F[m.group(2)])
    if "surn" in opts.enabled and _titled(token):
        info = _surname_info(token)
        if info:
            return "surn", info
    return None, None


def _classify_compound(token: str, opts: _Options):
    """«Жан-Люк», «Салтыков-Щедрин»: достаточно узнать одну часть, заменяется всё слово."""
    parts = token.split("-")
    infos = [_classify_word(part, opts) for part in parts]
    known = [(role, data) for role, data in infos if role]
    if not known:
        return None, None
    titled = token.isupper() or all(_titled(p) for p in parts)
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


def _as_tuple(value: Union[str, Iterable[str]]) -> Tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


def _normalize_languages(languages: Languages) -> Tuple[str, ...]:
    result = tuple(dict.fromkeys(_as_tuple(languages)))
    unknown = [lang for lang in result if lang not in LANGUAGES]
    if unknown or not result:
        raise ValueError(f"languages: ожидается непустой набор из {LANGUAGES}, получено {result!r}")
    return result


def _normalize_kinds(kinds: Kinds) -> FrozenSet[str]:
    kinds = _as_tuple(kinds)
    unknown = [k for k in kinds if k not in KINDS]
    if unknown or not kinds:
        raise ValueError(f"kinds: ожидается непустой набор из {tuple(KINDS)}, получено {kinds!r}")
    return frozenset(KINDS[k] for k in kinds)


def _normalize_aggressive(aggressive: Aggressive) -> FrozenSet[str]:
    if aggressive is True:
        return frozenset(AGGRESSIVE)
    if aggressive is False or aggressive is None:
        return frozenset()
    flags = _as_tuple(aggressive)
    unknown = [f for f in flags if f not in AGGRESSIVE]
    if unknown:
        raise ValueError(
            f"aggressive: ожидается bool или набор из {AGGRESSIVE}, получено {flags!r}"
        )
    return frozenset(flags)


def _normalize_exclude(exclude: Optional[Iterable[str]]) -> FrozenSet[str]:
    if exclude is None:
        return frozenset()
    words = _as_tuple(exclude)
    bad = [w for w in words if not isinstance(w, str)]
    if bad:
        raise TypeError(f"exclude: ожидаются строки, получено {bad!r}")
    return frozenset(w.casefold() for w in words)


@lru_cache(maxsize=None)
def _pattern(languages: Tuple[str, ...], any_case: bool) -> re.Pattern:
    index = 2 if any_case else 1
    parts = [_PARTS[lang][0] for lang in languages] + [_PARTS[lang][index] for lang in languages]
    return re.compile("|".join(parts))


def preload(languages: Languages = ("ru",), kinds: Kinds = tuple(KINDS)) -> None:
    """Загружает словарь заранее, чтобы первый вызов не тормозил."""
    if "ru" in _normalize_languages(languages) and "first" in _normalize_kinds(kinds):
        load()


_PUBLIC_KIND = {role: kind for kind, role in KINDS.items()}


class NameEntity(NamedTuple):
    """Найденное имя, отчество, фамилия или инициалы.

    start, end — позиции в исходном тексте: text[start:end] == entity.text.
    kind — "first", "patronymic", "surname" или "initials".
    normal_form — начальная форма: «Ивану» → «Иван», «Петровой» → «Петрова»,
    «Достоевского» → «Достоевский»; для инициалов — сам текст.
    gender — "m", "f" или "c" (не удалось определить).
    case — падеж: "nomn", "gent", "datv", "accs", "ablt", "loct"; для инициалов None.
    language — "ru" или "en".
    """

    start: int
    end: int
    text: str
    kind: str
    normal_form: str
    gender: str
    case: Optional[str]
    language: str


class Replacement(NamedTuple):
    """Что на что заменено: entity — найденное в исходном тексте, replacement — подстановка."""

    entity: NameEntity
    replacement: str


class AnonymizeResult(NamedTuple):
    text: str
    replacements: List[Replacement]


Replacer = Callable[[NameEntity], Optional[str]]


class _Token(NamedTuple):
    start: int
    end: int
    text: str


class _Hit(NamedTuple):
    token: _Token
    role: str
    data: Entry
    gender: str  # род и падеж группы слов, к которой относится токен
    case: str


# --- Склонение ---------------------------------------------------------------------------


def _decline_first(name: str, case: str, gender: Optional[str]) -> str:
    table = declension(name, gender if gender in ("m", "f") else None)
    return table.get(case) or name


def _decline_patr(stem: str, gender: str, case: str) -> str:
    return stem + (_PATR_F_SUFFIX if gender == "f" else _PATR_M_SUFFIX)[case]


def _decline_surname(stem: str, gender: str, case: str) -> str:
    female = gender == "f"
    if stem.lower().endswith(("ск", "цк")):
        return stem + (_SK_F_SUFFIX if female else _SK_M_SUFFIX)[case]
    return stem + (_SURN_F_SUFFIX if female else _SURN_M_SUFFIX)[case]


def _parse_patr(name: str) -> Optional[Tuple[str, str]]:
    """(основа, род) отчества в любом падеже."""
    m = _PATR_M_RE.match(name)
    if m:
        return m.group(1), "m"
    m = _PATR_F_RE.match(name)
    if m:
        return m.group(1), "f"
    return None


def inflect(
    name: str,
    case: Optional[str],
    kind: str = "first",
    gender: Optional[str] = None,
) -> str:
    """Ставит имя, отчество или фамилию в нужный падеж.

    Удобно в своей функции replace: inflect("Павел", entity.case) → «Павлу» для "datv".
    kind — "first", "patronymic", "surname" или "initials"; gender — "m", "f" или None
    (род берётся из словаря или из самой формы). Английские имена, инициалы, case=None
    и формы, которые склонять не умеем («Шевченко»), возвращаются как есть.
    """
    if kind not in KINDS:
        raise ValueError(f"kind: ожидается одно из {tuple(KINDS)}, получено {kind!r}")
    if case is not None and case not in CASES:
        raise ValueError(f"case: ожидается одно из {CASES} или None, получено {case!r}")
    if gender not in (None, "m", "f", "c"):
        raise ValueError(f"gender: ожидается 'm', 'f', 'c' или None, получено {gender!r}")
    if case is None or kind == "initials" or not name or name.isascii():
        return name
    if kind == "first":
        return _decline_first(name, case, gender)
    if kind == "patronymic":
        parsed = _parse_patr(name)
        if not parsed:
            return name
        stem, own = parsed
        return _decline_patr(stem, gender if gender in ("m", "f") else own, case)
    info = _surname_info(name)
    if not info:
        return name
    return _decline_surname(info[0], gender if gender in ("m", "f") else info[1], case)


# --- Пулы замен --------------------------------------------------------------------------

_DEFAULT_POOLS: Dict[str, List[str]] = {
    "first:ru:m": _FIRST_POOL["m"],
    "first:ru:f": _FIRST_POOL["f"],
    "first:en:m": english.FIRST["m"],
    "first:en:f": english.FIRST["f"],
    "patr": _PATR_STEMS,
    "surn:ov": _SURNAME_STEMS["ov"],
    "surn:sk": _SURNAME_STEMS["sk"],
    "surn:en": english.SURNAMES,
}


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


@lru_cache(maxsize=None)
def _fallback_pool(category: str) -> Tuple[str, ...]:
    """Запасной пул из словаря на случай, когда основной исчерпан (большие датасеты)."""
    primary = set(_DEFAULT_POOLS[category])
    if category.startswith("first:ru:"):
        gender = category[-1]
        names = (
            n for n, g in load().genders.items()
            if g == gender and "-" not in n and len(declension(n, gender)) == len(CASES)
        )
    elif category in ("patr", "surn:ov"):
        names = iter(_derived_stems())
    elif category == "surn:sk":
        names = (s + "ск" for s in _derived_stems() if (s + "ск").lower() not in _SK_STOP)
    else:  # английские пулы маленькие и запаса не имеют: расширяются через pools
        return ()
    return tuple(sorted(n for n in names if n not in primary))


class _PoolSet:
    """Пулы замен по категориям; пользовательские категории без запасного пула."""

    def __init__(self, pools: Optional[Pools] = None) -> None:
        self.primary: Dict[str, List[str]] = dict(_DEFAULT_POOLS)
        self.custom: Set[str] = set()
        for key, values in (pools or {}).items():
            if key not in POOL_KEYS:
                raise ValueError(f"pools: неизвестный ключ {key!r}, ожидается один из {POOL_KEYS}")
            values = list(dict.fromkeys(_as_tuple(values)))
            if not values or not all(isinstance(v, str) for v in values):
                raise ValueError(f"pools[{key!r}]: ожидается непустой список строк")
            self._add(key, values)

    def _set(self, category: str, values: List[str]) -> None:
        self.primary[category] = values
        self.custom.add(category)

    def _add(self, key: str, values: List[str]) -> None:
        en = [v for v in values if v.isascii()]
        ru = [v for v in values if not v.isascii()]
        bad = [v for v in en if not _EN_NAME_RE.match(v)]
        bad += [v for v in ru if not _RU_NAME_RE.match(v)]
        if bad:
            raise ValueError(f"pools[{key!r}]: ожидаются слова с заглавной буквы: {bad!r}")
        if key in ("first_m", "first_f"):
            gender = key[-1]
            if ru:
                self._set(f"first:ru:{gender}", ru)
            if en:
                self._set(f"first:en:{gender}", en)
        elif key == "patronymic":
            if en:
                raise ValueError(f"pools['patronymic']: только русские отчества, получено {en!r}")
            parsed = [_parse_patr(v) for v in ru]
            if not all(p and _decline_patr(p[0], p[1], "nomn") == v for p, v in zip(parsed, ru)):
                raise ValueError(
                    "pools['patronymic']: ожидаются отчества в именительном падеже "
                    f"на -ович/-евич/-овна/-евна, получено {ru!r}"
                )
            self._set("patr", list(dict.fromkeys(p[0] for p in parsed if p)))
        else:  # surname
            if en:
                self._set("surn:en", en)
            if ru:
                stems = []
                for value in ru:
                    info = _surname_info(value)
                    if not info or info[2] != "nomn":
                        raise ValueError(
                            "pools['surname']: ожидаются фамилии в именительном падеже "
                            f"на -ов/-ев/-ин/-ын/-ский/-цкий, получено {value!r}"
                        )
                    stems.append(info[0])
                stems = list(dict.fromkeys(stems))
                sk = [s for s in stems if s.lower().endswith(("ск", "цк"))]
                self._set("surn:sk", sk)
                self._set("surn:ov", [s for s in stems if s not in sk])

    def fallback(self, category: str) -> Tuple[str, ...]:
        return () if category in self.custom else _fallback_pool(category)


_DEFAULT_POOL_SET = _PoolSet()


def _choose_sparse(candidates: Tuple[str, ...], used: Set[str], rng) -> Optional[str]:
    """Свободный элемент большого пула: несколько случайных попыток, затем полный перебор."""
    if not candidates:
        return None
    for _ in range(32):
        value = rng.choice(candidates)
        if value.lower() not in used:
            return value
    free = [c for c in candidates if c.lower() not in used]
    return rng.choice(free) if free else None


class _Faker:
    """Подбирает замены; в режиме consistent запоминает их в memo."""

    def __init__(self, pools: _PoolSet, used: Set[str], rng, memo: Optional[Dict]) -> None:
        self.pools, self.used, self.rng, self.memo = pools, used, rng, memo

    def fake(self, hit: _Hit) -> str:
        if hit.role == "first":
            return self._first(hit.data, hit.gender)
        if hit.role == "patr":
            original, gender, case = hit.data
            return _decline_patr(self._pick("patr", ("patr", original)), gender, case)
        if hit.role == "surn":
            return self._surname(hit.data, hit.gender, hit.case)
        return self._initials(hit.token.text, hit.gender)

    def _pick(self, category: str, key: tuple) -> str:
        memo, used, rng = self.memo, self.used, self.rng
        if memo is not None and key in memo:
            return memo[key]
        candidates = self.pools.primary[category]
        free = [c for c in candidates if c.lower() not in used]
        if free:
            value = rng.choice(free)
        else:
            value = _choose_sparse(self.pools.fallback(category), used, rng)
            if value is None:
                if memo is not None:
                    warnings.warn(
                        f"Пул замен {category!r} исчерпан: разные имена получат одну замену. "
                        "Расширьте его через pools или вызовите reset().",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                value = rng.choice(candidates)
        if memo is not None:
            memo[key] = value
            used.add(value.lower())
        return value

    def _first(self, data: Entry, run_gender: str) -> str:
        original, gender, case = data
        if gender == "c":
            gender = run_gender if run_gender in ("m", "f") else "m"
        lang = "en" if original.isascii() else "ru"
        name = self._pick(f"first:{lang}:{gender}", ("first", original, gender))
        return name if lang == "en" else _decline_first(name, case, gender)

    def _surname(self, data: Entry, gender: str, case: str) -> str:
        if data[0].isascii():
            return self._pick("surn:en", ("surn", data[0]))
        kind, other = ("sk", "ov") if data[0].lower().endswith(("ск", "цк")) else ("ov", "sk")
        category = f"surn:{kind}" if self.pools.primary[f"surn:{kind}"] else f"surn:{other}"
        return _decline_surname(self._pick(category, ("surn", data[0])), gender, case)

    def _initials(self, original: str, gender: str) -> str:
        gender = gender if gender in ("m", "f") else "m"
        latin = original[0].isascii()  # между буквами может быть неразрывный пробел
        letters = "[A-Z]" if latin else "[А-ЯЁ]"
        pools = (english.FIRST[gender],) * 2 if latin else (_FIRST_POOL[gender], _PATR_STEMS)
        new = []
        for index, letter in enumerate(re.findall(letters, original)):
            key = ("init", index, letter)
            if self.memo is not None and key in self.memo:
                new.append(self.memo[key])
                continue
            value = self.rng.choice(sorted({name[0] for name in pools[index]} - {letter}))
            if self.memo is not None:
                self.memo[key] = value
            new.append(value)
        replacements = iter(new)
        return re.sub(letters, lambda _: next(replacements), original)


# --- Публичный API -----------------------------------------------------------------------


class Anonymizer:
    """Анонимизатор с настройками, заданными один раз.

    Параметры rng, aggressive, languages, kinds, exclude, pools, replace — как у
    anonymize_names.

    consistent=True — одно и то же имя получает одну и ту же замену во всех вызовах этого
    объекта, а не только в пределах одного текста; reset() забывает накопленные замены,
    export_state() / load_state() сохраняют и восстанавливают их (например, в JSON).
    Вызовы одного экземпляра из разных потоков безопасны.
    """

    def __init__(
        self,
        *,
        rng: Optional[random.Random] = None,
        aggressive: Aggressive = False,
        languages: Languages = ("ru",),
        kinds: Kinds = tuple(KINDS),
        consistent: bool = False,
        replace: Optional[Replacer] = None,
        exclude: Optional[Iterable[str]] = None,
        pools: Optional[Pools] = None,
    ) -> None:
        self._languages = _normalize_languages(languages)
        self._opts = _Options(
            _normalize_kinds(kinds), _normalize_aggressive(aggressive), _normalize_exclude(exclude)
        )
        self._pools = _PoolSet(pools) if pools else _DEFAULT_POOL_SET
        self._consistent = bool(consistent)
        self._pattern = _pattern(self._languages, "any_case" in self._opts.flags)
        self._rng = rng
        self._replace = replace
        self._memo: Dict[tuple, str] = {}
        self._used: Set[str] = set()
        self._lock = threading.RLock()

    @property
    def languages(self) -> Tuple[str, ...]:
        return self._languages

    @property
    def kinds(self) -> Tuple[str, ...]:
        return tuple(kind for kind, role in KINDS.items() if role in self._opts.enabled)

    @property
    def aggressive(self) -> Tuple[str, ...]:
        """Включённые части aggressive в порядке AGGRESSIVE; пустой кортеж — режим выключен."""
        return tuple(flag for flag in AGGRESSIVE if flag in self._opts.flags)

    @property
    def consistent(self) -> bool:
        return self._consistent

    def preload(self) -> None:
        """Загружает словарь заранее, если он понадобится при этих настройках."""
        if "ru" in self._languages and "first" in self._opts.enabled:
            load()

    def reset(self) -> None:
        """Забывает замены, накопленные в режиме consistent."""
        with self._lock:
            self._memo.clear()
            self._used.clear()

    def export_state(self) -> Dict[str, Any]:
        """Накопленные в режиме consistent замены в виде, пригодном для json.dumps."""
        with self._lock:
            return {
                "version": STATE_VERSION,
                "mapping": [[list(key), value] for key, value in self._memo.items()],
                "used": sorted(self._used),
            }

    def load_state(self, state: Mapping[str, Any]) -> None:
        """Заменяет накопленные замены сохранёнными через export_state()."""
        if not self._consistent:
            raise ValueError("load_state имеет смысл только для Anonymizer(consistent=True)")
        if not isinstance(state, abc.Mapping) or state.get("version") != STATE_VERSION:
            raise ValueError(
                f"load_state: ожидается результат export_state() версии {STATE_VERSION}"
            )
        try:
            memo = {tuple(key): value for key, value in state["mapping"]}
            used = set(state["used"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"load_state: повреждённое состояние ({error})") from None
        if not all(isinstance(v, str) for v in memo.values()) or not all(
            isinstance(u, str) for u in used
        ):
            raise ValueError("load_state: значения замен должны быть строками")
        with self._lock:
            self._memo, self._used = memo, used

    def find(self, text: str) -> List[NameEntity]:
        """Находит имена, ничего не заменяя; результат упорядочен по позиции."""
        hits, _ = _analyze(text, self._pattern, self._opts)
        return [_entity(hit) for hit in hits]

    def anonymize(self, text: str) -> str:
        return self.anonymize_detailed(text).text

    def anonymize_detailed(self, text: str) -> AnonymizeResult:
        """Как anonymize, но вместе с текстом возвращает список сделанных замен."""
        hits, originals = _analyze(text, self._pattern, self._opts)
        if not hits:
            return AnonymizeResult(text, [])
        rng = self._rng or random
        if not self._consistent:
            return self._substitute(text, hits, _Faker(self._pools, originals, rng, None))
        with self._lock:
            self._used.update(originals)
            return self._substitute(text, hits, _Faker(self._pools, self._used, rng, self._memo))

    def _substitute(self, text: str, hits: List[_Hit], faker: _Faker) -> AnonymizeResult:
        parts: List[str] = []
        done: List[Replacement] = []
        pos = 0
        for hit in hits:
            entity = _entity(hit)
            new = self._replace(entity) if self._replace is not None else None
            if new is None:
                new = _match_case(hit.token.text, faker.fake(hit))
            elif not isinstance(new, str):
                raise TypeError(f"replace должна вернуть str или None, получено {type(new)!r}")
            parts.append(text[pos : hit.token.start])
            parts.append(new)
            pos = hit.token.end
            done.append(Replacement(entity, new))
        parts.append(text[pos:])
        return AnonymizeResult("".join(parts), done)


def find_names(
    text: str,
    aggressive: Aggressive = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
    exclude: Optional[Iterable[str]] = None,
) -> List[NameEntity]:
    """Находит имена, отчества, фамилии и инициалы с позициями, ничего не заменяя.

    Находится ровно то, что заменила бы anonymize_names с теми же параметрами.
    """
    return Anonymizer(
        aggressive=aggressive, languages=languages, kinds=kinds, exclude=exclude
    ).find(text)


def anonymize_names(
    text: str,
    rng: Optional[random.Random] = None,
    aggressive: Aggressive = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
    replace: Optional[Replacer] = None,
    exclude: Optional[Iterable[str]] = None,
    pools: Optional[Pools] = None,
) -> str:
    """Заменяет имена, отчества и фамилии на случайные, сохраняя род и падеж.

    aggressive — True включает всё сразу, или набор частей из AGGRESSIVE:
    "any_case" (имена в нижнем регистре и КАПСЕ), "lone_surnames" (фамилии без имени
    рядом), "ambiguous" (имена, совпадающие с обычными словами: «Вера», «Роман»).

    languages — какие словари использовать: "ru", "en" или оба, например ("ru", "en").
    Имя заменяется именем того же языка.

    kinds — что заменять: "first" (имена по словарю), "patronymic" (отчества по суффиксам),
    "surname" (фамилии по суффиксам и английскому списку), "initials". По умолчанию всё.
    Отключённые виды не ищутся: без "first" русский словарь не загружается, а фамилии
    заменяются и без имени рядом.

    replace — своя функция замены: NameEntity -> строка или None (стандартная замена).
    exclude — слова, которые не трогать («Ростов»); сравниваются без учёта регистра
    с самим словом и его начальной формой.
    pools — свои списки замен: {"first_m": [...], "first_f": [...], "patronymic": [...],
    "surname": [...]}; имена в именительном падеже, склоняются автоматически.
    """
    return Anonymizer(
        rng=rng, aggressive=aggressive, languages=languages, kinds=kinds, replace=replace,
        exclude=exclude, pools=pools,
    ).anonymize(text)


def anonymize_names_consistent(
    text: str,
    rng: Optional[random.Random] = None,
    aggressive: Aggressive = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
    replace: Optional[Replacer] = None,
    exclude: Optional[Iterable[str]] = None,
    pools: Optional[Pools] = None,
) -> str:
    """Как anonymize_names, но одно и то же имя заменяется одной и той же заменой.

    Согласованность действует в пределах одного вызова; чтобы она сохранялась между
    вызовами, используйте Anonymizer(consistent=True).
    """
    return Anonymizer(
        rng=rng,
        aggressive=aggressive,
        languages=languages,
        kinds=kinds,
        consistent=True,
        replace=replace,
        exclude=exclude,
        pools=pools,
    ).anonymize(text)


# --- Разбор текста -----------------------------------------------------------------------


def _analyze(text: str, pattern: re.Pattern, opts: _Options) -> Tuple[List[_Hit], Set[str]]:
    """Токены, которые нужно заменить, и множество исходных имён текста (в нижнем регистре)."""
    if not text or not pattern.search(text):
        return [], set()

    enabled = opts.enabled
    plans = []
    used: Set[str] = set()
    all_roles = [[r for m in run for r in _token_roles(m, opts)] for run in _runs(text, pattern)]
    # «Света не было», «Нате, держите»: одиночное имя-омоним в начале фразы считаем обычным
    # словом, если в тексте оно ни разу не встретилось как имя в другом месте
    doubtful = set() if "ambiguous" in opts.flags else _doubtful_common(text, all_roles)
    for roles in all_roles:
        if id(roles) in doubtful:
            continue
        anchors = [r for r in roles if r[1] in ("first", "patr")]
        if not anchors:
            has_init = any(r[1] == "init" for r in roles)
            if "lone_surnames" in opts.flags or "first" not in enabled or has_init:
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

    hits = [
        _Hit(tok, role, data, gender, case)
        for roles, gender, case in plans
        for tok, role, data in roles
        if role and (role != "init" or "init" in enabled)
    ]
    return hits, used


def _entity(hit: _Hit) -> NameEntity:
    tok, role, data = hit.token, hit.role, hit.data
    case: Optional[str]
    if role == "first":
        gender = hit.gender if data[1] == "c" else data[1]
        normal, case = data[0], data[2]
    elif role == "patr":
        gender, case = data[1], data[2]
        normal = data[0] + ("ич" if gender == "m" else "на")
    elif role == "surn":
        gender, case = hit.gender, hit.case
        normal = _surname_normal(data[0], gender)
    else:
        gender, case, normal = hit.gender, None, tok.text
    language = "en" if tok.text.isascii() else "ru"
    return NameEntity(tok.start, tok.end, tok.text, _PUBLIC_KIND[role], normal, gender, case,
                      language)


def _surname_normal(stem: str, gender: str) -> str:
    female = gender == "f"
    if stem.isascii():
        return stem
    if stem.lower().endswith(("ск", "цк")):
        return stem + ("ая" if female else "ий")
    return stem + ("а" if female else "")


def _excluded(text: str, role: str, data: Entry, exclude: FrozenSet[str]) -> bool:
    """Слово или его начальная форма в exclude; фамилия — в обоих родах."""
    forms = [text]
    if role == "first":
        forms.append(data[0])
    elif role == "patr":
        forms += [data[0] + "ич", data[0] + "на"]
    elif role == "surn":
        forms += [_surname_normal(data[0], "m"), _surname_normal(data[0], "f")]
    return any(form.casefold() in exclude for form in forms)


def _token_roles(m: re.Match, opts: _Options):
    """[(токен, роль, данные)]; нераспознанное составное слово разбирается по частям."""
    role, data = _classify(m.group(), opts)
    if role or "-" not in m.group():
        tokens = [(_Token(m.start(), m.end(), m.group()), role, data)]
    else:
        # «Мария-то», «Ивану-ка»: целиком не имя, но часть может быть именем
        tokens, start = [], m.start()
        for part in m.group().split("-"):
            tokens.append((_Token(start, start + len(part), part), *_classify_word(part, opts)))
            start += len(part) + 1
    if not opts.exclude:
        return tokens
    return [
        (tok, None, None) if role and _excluded(tok.text, role, data, opts.exclude)
        else (tok, role, data)
        for tok, role, data in tokens
    ]


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
    before = text[:start].rstrip("  \t\r\n«\"„(—–-")
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
