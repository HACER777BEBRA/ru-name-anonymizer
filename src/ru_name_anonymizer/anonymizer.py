"""Ядро: поиск слов, группировка, подбор замен. Всё языковое — в locales/<код>/,
динамические термины (ники, username) — в dynamic/."""

import bisect
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

from ru_name_anonymizer.dynamic import DynamicLocale, available_dynamic, get_dynamic_locale
from ru_name_anonymizer.dynamic.store import Group, TermSpec, TermStore
from ru_name_anonymizer.locales import available_languages, get_locale
from ru_name_anonymizer.locales.base import CASES, POOL_ROLES, Entry, Locale, Options

# Что можно заменять: имена (словарь), отчества и фамилии (суффиксы, списки), инициалы,
# ники и другие термины динамических локалей
KINDS = {
    "first": "first",
    "patronymic": "patr",
    "surname": "surn",
    "initials": "init",
    "nickname": "nick",
}
# Из чего состоит aggressive: любой регистр, фамилии без имени рядом, имена-омонимы
AGGRESSIVE = ("any_case", "lone_surnames", "ambiguous")
# Что включает chat: любой регистр, фамилии без имени рядом и имена-омонимы, но только
# с заглавной буквы — «Роман пишет» заменяется, «читаю роман» нет
CHAT_FLAGS = frozenset({"any_case", "lone_surnames", "ambiguous_titled"})
# Ключи параметра pools; с префиксом языка («be:first_m») — только для этого языка
POOL_KEYS = tuple(POOL_ROLES)
STATE_VERSION = 2  # 2: добавлены термины динамических локалей и их замены

Languages = Union[str, Iterable[str]]
Kinds = Union[str, Iterable[str]]
Aggressive = Union[bool, str, Iterable[str]]
Pools = Mapping[str, Union[str, Iterable[str]]]
Dynamic = Mapping[str, TermSpec]
AutoDetect = Union[bool, str, Iterable[str]]

_RUN_GAP = re.compile(r"^[  ]+$")


def __getattr__(name: str) -> Any:
    if name == "LANGUAGES":  # список меняется при register_locale
        return available_languages()
    raise AttributeError(name)


def _classify(token: str, opts: Options, locales: Tuple[Locale, ...]):
    """(роль, данные, локаль); у всех ролей data = (лемма или основа, род, падеж).

    Токен разбирает первая из локалей с подходящим алфавитом, которая его узнала.
    """
    for loc in locales:
        if not loc.owns(token):
            continue
        if token[1:2] == ".":
            return "init", (token, "c", "nomn"), loc
        if "-" in token:
            role, data = _classify_compound(token, opts, loc)
        else:
            role, data = loc.classify_word(token, opts)
        if role:
            return role, data, loc
    return None, None, None


def _titled(token: str) -> bool:
    return token[0].isupper() and token[1:].islower()


def _classify_compound(token: str, opts: Options, loc: Locale):
    """«Жан-Люк», «Салтыков-Щедрин»: достаточно узнать одну часть, заменяется всё слово."""
    parts = token.split("-")
    infos = [loc.classify_word(part, opts) for part in parts]
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
    known = available_languages()
    unknown = [lang for lang in result if lang not in known]
    if unknown or not result:
        raise ValueError(f"languages: ожидается непустой набор из {known}, получено {result!r}")
    return result


def _locales(languages: Tuple[str, ...]) -> Tuple[Locale, ...]:
    return tuple(get_locale(code) for code in languages)


def _all_locales() -> Tuple[Locale, ...]:
    return _locales(available_languages())


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


def _flags(aggressive: Aggressive, chat: bool) -> FrozenSet[str]:
    flags = _normalize_aggressive(aggressive)
    return flags | CHAT_FLAGS if chat else flags


def _normalize_exclude(exclude: Optional[Iterable[str]]) -> FrozenSet[str]:
    if exclude is None:
        return frozenset()
    words = _as_tuple(exclude)
    bad = [w for w in words if not isinstance(w, str)]
    if bad:
        raise TypeError(f"exclude: ожидаются строки, получено {bad!r}")
    return frozenset(w.casefold() for w in words)


def _normalize_auto_detect(auto_detect: AutoDetect) -> Tuple[DynamicLocale, ...]:
    """True — все динамические локали с шаблоном detect, иначе перечисленные коды."""
    if auto_detect is False or auto_detect is None:
        return ()
    if auto_detect is True:
        locales = tuple(get_dynamic_locale(code) for code in available_dynamic())
        return tuple(loc for loc in locales if loc.detect)
    locales = tuple(get_dynamic_locale(code) for code in dict.fromkeys(_as_tuple(auto_detect)))
    without = [loc.code for loc in locales if not loc.detect]
    if without:
        raise ValueError(f"auto_detect: у локалей {without} нет шаблона автопоиска (detect)")
    return locales


def _overlaps(starts: List[int], ends: List[int], start: int, end: int) -> bool:
    """Пересекается ли [start, end) с одним из непересекающихся упорядоченных отрезков."""
    i = bisect.bisect_right(ends, start)  # первый отрезок, который кончается после start
    return i < len(starts) and starts[i] < end


@lru_cache(maxsize=None)
def _pattern(locales: Tuple[Locale, ...], any_case: bool) -> re.Pattern:
    """Инициалы или слово в объединённом алфавите; чей это токен, решает _classify."""
    up = "".join(loc.upper for loc in locales)
    low = "".join(loc.lower for loc in locales)
    initials = f"(?<![{up}{low}])[{up}]\\.(?:[  ]?[{up}]\\.)?"
    if any_case:
        word = f"[{up}{low}]{{2,}}(?:-[{up}{low}]{{2,}})*"
    else:
        word = f"[{up}][{low}]+(?:-[{up}][{low}]+)*"
    return re.compile(f"{initials}|{word}")


def preload(languages: Languages = ("ru",), kinds: Kinds = tuple(KINDS)) -> None:
    """Загружает словари заранее, чтобы первый вызов не тормозил."""
    roles = _normalize_kinds(kinds)
    for loc in _locales(_normalize_languages(languages)):
        loc.preload(roles)


_PUBLIC_KIND = {role: kind for kind, role in KINDS.items()}


class NameEntity(NamedTuple):
    """Найденное имя, отчество, фамилия, инициалы или ник.

    start, end — позиции в исходном тексте: text[start:end] == entity.text.
    kind — "first", "patronymic", "surname", "initials" или "nickname".
    normal_form — начальная форма: «Ивану» → «Иван», «Петровой» → «Петрова»,
    «Достоевского» → «Достоевский»; для инициалов — сам текст; для ника — основной термин
    группы, даже если найден алиас («Zik» → «Zik_2005»).
    gender — "m", "f" или "c" (не удалось определить; у ников всегда "c").
    case — падеж: "nomn", "gent", "datv", "accs", "ablt", "loct"; для инициалов и ников None.
    language — код языка, например "ru" или "en"; для ника — код динамической локали ("tg").
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
    loc: Optional[Locale]  # локаль, узнавшая слово; None — не узнано


class _Hit(NamedTuple):
    token: _Token
    role: str
    data: Entry
    gender: str  # род и падеж группы слов, к которой относится токен
    case: str


class _Item(NamedTuple):
    """Что заменить: находка статической локали (hit) или термин динамической (group)."""

    entity: NameEntity
    hit: Optional[_Hit]
    group: Optional[Group]


def inflect(
    name: str,
    case: Optional[str],
    kind: str = "first",
    gender: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """Ставит имя, отчество или фамилию в нужный падеж.

    Удобно в своей функции replace: inflect("Павел", entity.case) → «Павлу» для "datv".
    kind — "first", "patronymic", "surname" или "initials"; gender — "m", "f" или None
    (род берётся из словаря или из самой формы). language — код языка (entity.language);
    по умолчанию — первый язык, алфавитом которого записано слово. Несклоняемые языки,
    инициалы, ники, case=None и формы, которые склонять не умеем («Шевченко»), возвращаются
    как есть.
    """
    if kind not in KINDS:
        raise ValueError(f"kind: ожидается одно из {tuple(KINDS)}, получено {kind!r}")
    if case is not None and case not in CASES:
        raise ValueError(f"case: ожидается одно из {CASES} или None, получено {case!r}")
    if gender not in (None, "m", "f", "c"):
        raise ValueError(f"gender: ожидается 'm', 'f', 'c' или None, получено {gender!r}")
    if kind == "nickname":
        return name
    loc = _locales(_normalize_languages(language))[0] if language is not None else None
    if case is None or kind == "initials" or not name:
        return name
    if loc is None:
        loc = next((candidate for candidate in _all_locales() if candidate.owns(name)), None)
        if loc is None:
            return name
    return loc.inflect(name, case, KINDS[kind], gender)


# --- Пулы замен --------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _defaults(loc: Locale) -> Dict[str, List[str]]:
    return loc.default_pools()


class _PoolSet:
    """Пулы замен: стандартные из локалей и пользовательские (без запасного пула)."""

    def __init__(self, pools: Optional[Pools] = None, locales: Tuple[Locale, ...] = ()) -> None:
        self.custom: Dict[Tuple[str, str], List[str]] = {}
        if not pools:
            return
        candidates = locales + tuple(loc for loc in _all_locales() if loc not in locales)
        for key, values in pools.items():
            lang, _, base = key.rpartition(":") if isinstance(key, str) else ("", "", key)
            if base not in POOL_KEYS or (lang and lang not in available_languages()):
                raise ValueError(
                    f"pools: неизвестный ключ {key!r}, ожидается один из {POOL_KEYS}, "
                    "можно с префиксом языка, например 'ru:first_m'"
                )
            values = list(dict.fromkeys(_as_tuple(values)))
            if not values or not all(isinstance(v, str) for v in values):
                raise ValueError(f"pools[{key!r}]: ожидается непустой список строк")
            self._add(base, values, (get_locale(lang),) if lang else candidates)

    def _add(self, key: str, values: List[str], candidates: Tuple[Locale, ...]) -> None:
        groups: Dict[Locale, List[str]] = {}
        bad = []
        for value in values:
            loc = next((c for c in candidates if c.is_name_shaped(value)), None)
            if loc is None:
                bad.append(value)
            else:
                groups.setdefault(loc, []).append(value)
        if bad:
            raise ValueError(f"pools[{key!r}]: ожидаются слова с заглавной буквы: {bad!r}")
        for loc, group in groups.items():
            for category, pool in loc.custom_pools(key, group).items():
                self.custom[(loc.code, category)] = list(pool)

    def get(self, loc: Locale, category: str) -> List[str]:
        custom = self.custom.get((loc.code, category))
        return custom if custom is not None else _defaults(loc)[category]

    def fallback(self, loc: Locale, category: str) -> Tuple[str, ...]:
        if (loc.code, category) in self.custom:
            return ()
        return loc.fallback_pool(category)


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
        loc = hit.token.loc
        if hit.role == "first":
            return self._first(loc, hit.data, hit.gender)
        if hit.role == "patr":
            original, gender, case = hit.data
            stem = self._pick(loc, loc.patronymic_category(), ("patr", original))
            return loc.decline("patr", stem, gender, case)
        if hit.role == "surn":
            categories = loc.surname_categories(hit.data[0])
            category = next((c for c in categories if self.pools.get(loc, c)), categories[0])
            stem = self._pick(loc, category, ("surn", hit.data[0]))
            return loc.decline("surn", stem, hit.gender, hit.case)
        return self._initials(loc, hit.token.text, hit.gender)

    def _pick(self, loc: Locale, category: str, key: tuple) -> str:
        memo, used, rng = self.memo, self.used, self.rng
        if memo is not None and key in memo:
            return memo[key]
        candidates = self.pools.get(loc, category)
        free = [c for c in candidates if c.lower() not in used]
        if free:
            value = rng.choice(free)
        else:
            value = _choose_sparse(self.pools.fallback(loc, category), used, rng)
            if value is None:
                if memo is not None:
                    warnings.warn(
                        f"Пул замен {loc.code}:{category} исчерпан: разные имена получат одну "
                        "замену. Расширьте его через pools или вызовите reset().",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                value = rng.choice(candidates)
        if memo is not None:
            memo[key] = value
            used.add(value.lower())
        return value

    def _first(self, loc: Locale, data: Entry, run_gender: str) -> str:
        original, gender, case = data
        if gender == "c":
            gender = run_gender if run_gender in ("m", "f") else "m"
        name = self._pick(loc, f"first:{gender}", ("first", original, gender))
        return loc.decline("first", name, gender, case)

    def _initials(self, loc: Locale, original: str, gender: str) -> str:
        gender = gender if gender in ("m", "f") else "m"
        letters = loc.letter_re  # между буквами может быть неразрывный пробел
        new = []
        for index, letter in enumerate(letters.findall(original)):
            key = ("init", index, letter)
            if self.memo is not None and key in self.memo:
                new.append(self.memo[key])
                continue
            value = self.rng.choice(sorted(set(loc.initial_letters(gender, index)) - {letter}))
            if self.memo is not None:
                self.memo[key] = value
            new.append(value)
        replacements = iter(new)
        return letters.sub(lambda _: next(replacements), original)


# --- Публичный API -----------------------------------------------------------------------


class Anonymizer:
    """Анонимизатор с настройками, заданными один раз.

    Параметры rng, aggressive, chat, languages, kinds, exclude, pools, replace — как у
    anonymize_names.

    consistent=True — одно и то же имя получает одну и ту же замену во всех вызовах этого
    объекта, а не только в пределах одного текста; reset() забывает накопленные замены,
    export_state() / load_state() сохраняют и восстанавливают их (например, в JSON).

    dynamic — термины динамических локалей (ники, username), известные заранее:
    {"tg": ["HACER777BEBRA"], "nick": {"Бебрыч": "кабачок2008"}}; дополнять во время работы —
    add_terms(). Термин всегда получает одну и ту же замену, даже без consistent.
    auto_detect — True или коды локалей: перед заменой искать новые термины шаблоном detect
    локали (в "tg" — @упоминания) и добавлять их в словарь.

    Вызовы одного экземпляра из разных потоков безопасны.
    """

    def __init__(
        self,
        *,
        rng: Optional[random.Random] = None,
        aggressive: Aggressive = False,
        chat: bool = False,
        languages: Languages = ("ru",),
        kinds: Kinds = tuple(KINDS),
        consistent: bool = False,
        replace: Optional[Replacer] = None,
        exclude: Optional[Iterable[str]] = None,
        pools: Optional[Pools] = None,
        dynamic: Optional[Dynamic] = None,
        auto_detect: AutoDetect = False,
    ) -> None:
        self._languages = _normalize_languages(languages)
        self._locales = _locales(self._languages)
        self._opts = Options(
            _normalize_kinds(kinds), _flags(aggressive, chat), _normalize_exclude(exclude)
        )
        self._chat = bool(chat)
        self._aggressive = tuple(f for f in AGGRESSIVE if f in _normalize_aggressive(aggressive))
        self._static = bool(self._opts.enabled - {"nick"})
        self._pools = _PoolSet(pools, self._locales) if pools else _DEFAULT_POOL_SET
        self._consistent = bool(consistent)
        self._pattern = _pattern(self._locales, "any_case" in self._opts.flags)
        self._rng = rng
        self._replace = replace
        self._memo: Dict[tuple, str] = {}
        self._used: Set[str] = set()
        self._terms = TermStore()
        self._auto = _normalize_auto_detect(auto_detect)
        self._nick_memo: Dict[Tuple[str, str], str] = {}
        self._nick_used: Set[str] = set()
        self._lock = threading.RLock()
        if dynamic is not None:
            if not isinstance(dynamic, abc.Mapping):
                raise TypeError("dynamic: ожидается словарь {код локали: термины}")
            for code, terms in dynamic.items():
                self._terms.add(get_dynamic_locale(code), terms)

    @property
    def languages(self) -> Tuple[str, ...]:
        return self._languages

    @property
    def kinds(self) -> Tuple[str, ...]:
        return tuple(kind for kind, role in KINDS.items() if role in self._opts.enabled)

    @property
    def aggressive(self) -> Tuple[str, ...]:
        """Части aggressive в порядке AGGRESSIVE (без учёта chat); пустой кортеж — выключен."""
        return self._aggressive

    @property
    def chat(self) -> bool:
        return self._chat

    @property
    def consistent(self) -> bool:
        return self._consistent

    @property
    def auto_detect(self) -> Tuple[str, ...]:
        """Коды динамических локалей с включённым автопоиском."""
        return tuple(loc.code for loc in self._auto)

    def preload(self) -> None:
        """Загружает словари заранее, если они понадобятся при этих настройках."""
        for loc in self._locales:
            loc.preload(self._opts.enabled)

    # --- Динамические термины ------------------------------------------------------------

    def add_terms(
        self,
        locale: str,
        terms: TermSpec,
        *,
        aliases: Union[str, Iterable[str]] = (),
        replacement: Optional[str] = None,
    ) -> None:
        """Добавляет термины динамической локали: ники, username, подписи.

        terms — строка, список строк или словарь {термин: замена | None |
        {"aliases": [...], "replacement": ...}}. aliases — другие написания того же человека
        («Zik» для «Zik_2005»): вся группа получает одну замену. replacement — своя замена
        вместо ника из пула. Повторное добавление термина не ошибка: новые алиасы
        дописываются. Строка, уже принадлежащая другому термину, — ValueError.
        """
        loc = get_dynamic_locale(locale)
        with self._lock:
            self._terms.add(loc, terms, aliases, replacement)

    def remove_terms(self, locale: str, terms: Union[str, Iterable[str]]) -> None:
        """Удаляет термины (вместе с алиасами) или отдельные алиасы; незнакомые пропускает."""
        loc = get_dynamic_locale(locale)
        with self._lock:
            self._terms.remove(loc, terms)

    def terms(self) -> Dict[str, Dict[str, List[str]]]:
        """Текущий словарь: {код локали: {термин: [алиасы]}}."""
        with self._lock:
            return self._terms.view()

    # --- Состояние -----------------------------------------------------------------------

    def reset(self) -> None:
        """Забывает накопленные замены (в том числе замены ников); словарь терминов остаётся."""
        with self._lock:
            self._memo.clear()
            self._used.clear()
            self._nick_memo.clear()
            self._nick_used.clear()

    def export_state(self) -> Dict[str, Any]:
        """Накопленные замены и словарь терминов в виде, пригодном для json.dumps."""
        with self._lock:
            return {
                "version": STATE_VERSION,
                "mapping": [[list(key), value] for key, value in self._memo.items()],
                "used": sorted(self._used),
                "terms": self._terms.export(),
                "nicknames": [[code, key, value] for (code, key), value in self._nick_memo.items()],
                "nickname_used": sorted(self._nick_used),
            }

    def load_state(self, state: Mapping[str, Any]) -> None:
        """Заменяет накопленные замены и словарь терминов сохранёнными через export_state().

        Состояния версии 1 (без терминов) тоже принимаются. Замены обычных имён имеют смысл
        только для consistent=True; без него такое состояние — ValueError.
        """
        if not isinstance(state, abc.Mapping) or state.get("version") not in (1, STATE_VERSION):
            raise ValueError(
                f"load_state: ожидается результат export_state() версии {STATE_VERSION}"
            )
        try:
            memo = {tuple(key): value for key, value in state["mapping"]}
            used = set(state["used"])
            nick_memo = {(code, key): value for code, key, value in state.get("nicknames", [])}
            nick_used = set(state.get("nickname_used", []))
            terms = TermStore()
            for entry in state.get("terms", []):
                terms.add(
                    get_dynamic_locale(entry["locale"]),
                    entry["term"],
                    entry.get("aliases", ()),
                    entry.get("replacement"),
                )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"load_state: повреждённое состояние ({error})") from None
        values = [*memo.values(), *used, *nick_memo.values(), *nick_used]
        if not all(isinstance(v, str) for v in values):
            raise ValueError("load_state: значения замен должны быть строками")
        if memo and not self._consistent:
            raise ValueError(
                "load_state: замены имён имеют смысл только для Anonymizer(consistent=True)"
            )
        with self._lock:
            self._memo, self._used = memo, used
            self._nick_memo, self._nick_used = nick_memo, nick_used
            self._terms = terms

    # --- Поиск и замена ------------------------------------------------------------------

    def _dynamic_on(self) -> bool:
        return "nick" in self._opts.enabled and (bool(self._terms) or bool(self._auto))

    def find(self, text: str) -> List[NameEntity]:
        """Находит имена и термины, ничего не заменяя; результат упорядочен по позиции.

        Автопоиск здесь не меняет словарь: найденное учитывается только в этом вызове.
        """
        if not self._dynamic_on():
            items, _ = self._collect(text, None)
        else:
            with self._lock:
                store = self._terms
                if self._auto:
                    store = store.copy()
                    store.detect(text, self._auto)
                items, _ = self._collect(text, store)
        return [item.entity for item in items]

    def anonymize(self, text: str) -> str:
        return self.anonymize_detailed(text).text

    def anonymize_detailed(self, text: str) -> AnonymizeResult:
        """Как anonymize, но вместе с текстом возвращает список сделанных замен."""
        rng = self._rng or random
        dynamic = self._dynamic_on()
        if not dynamic and not self._consistent:
            items, originals = self._collect(text, None)
            if not items:
                return AnonymizeResult(text, [])
            return self._substitute(text, items, _Faker(self._pools, originals, rng, None))
        with self._lock:
            if dynamic and self._auto:
                self._terms.detect(text, self._auto)
            items, originals = self._collect(text, self._terms if dynamic else None)
            if not items:
                return AnonymizeResult(text, [])
            if self._consistent:
                self._used.update(originals)
                faker = _Faker(self._pools, self._used, rng, self._memo)
            else:
                faker = _Faker(self._pools, originals, rng, None)
            return self._substitute(text, items, faker)

    def _collect(self, text: str, store: Optional[TermStore]) -> Tuple[List[_Item], Set[str]]:
        """Что заменить: сначала термины словаря, затем статические находки вне их."""
        items: List[_Item] = []
        starts: List[int] = []
        ends: List[int] = []
        if store:
            exclude = self._opts.exclude
            for start, end, group in store.find(text, "any_case" in self._opts.flags):
                matched = text[start:end]
                if exclude and (
                    matched.casefold() in exclude or group.term.casefold() in exclude
                ):
                    continue
                starts.append(start)
                ends.append(end)
                entity = NameEntity(
                    start, end, matched, "nickname", group.term, "c", None, group.locale.code
                )
                items.append(_Item(entity, None, group))
        originals: Set[str] = set()
        if self._static:
            hits, originals = _analyze(text, self._pattern, self._opts, self._locales)
            static = [
                _Item(_entity(hit), hit, None)
                for hit in hits
                if not starts or not _overlaps(starts, ends, hit.token.start, hit.token.end)
            ]
            if items:
                items = sorted(items + static, key=lambda item: item.entity.start)
            else:
                items = static
        return items, originals

    def _nickname(self, group: Group, rng) -> str:
        if group.replacement is not None:
            return group.replacement
        key = group.key
        value = self._nick_memo.get(key)
        if value is None:
            value = group.locale.fake(group.term, rng, self._nick_used)
            if not isinstance(value, str) or not value:
                raise TypeError(
                    f"{type(group.locale).__name__}.fake должна вернуть непустую строку, "
                    f"получено {value!r}"
                )
            self._nick_memo[key] = value
            self._nick_used.add(value.lower())
        return value

    def _substitute(self, text: str, items: List[_Item], faker: _Faker) -> AnonymizeResult:
        parts: List[str] = []
        done: List[Replacement] = []
        pos = 0
        for item in items:
            entity = item.entity
            new = self._replace(entity) if self._replace is not None else None
            if new is None:
                if item.hit is not None:
                    new = _match_case(item.hit.token.text, faker.fake(item.hit))
                else:
                    new = self._nickname(item.group, faker.rng)
            elif not isinstance(new, str):
                raise TypeError(f"replace должна вернуть str или None, получено {type(new)!r}")
            parts.append(text[pos : entity.start])
            parts.append(new)
            pos = entity.end
            done.append(Replacement(entity, new))
        parts.append(text[pos:])
        return AnonymizeResult("".join(parts), done)


def find_names(
    text: str,
    aggressive: Aggressive = False,
    chat: bool = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
    exclude: Optional[Iterable[str]] = None,
    dynamic: Optional[Dynamic] = None,
    auto_detect: AutoDetect = False,
) -> List[NameEntity]:
    """Находит имена, отчества, фамилии, инициалы и термины dynamic, ничего не заменяя.

    Находится ровно то, что заменила бы anonymize_names с теми же параметрами.
    """
    return Anonymizer(
        aggressive=aggressive, chat=chat, languages=languages, kinds=kinds, exclude=exclude,
        dynamic=dynamic, auto_detect=auto_detect,
    ).find(text)


def anonymize_names(
    text: str,
    rng: Optional[random.Random] = None,
    aggressive: Aggressive = False,
    chat: bool = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
    replace: Optional[Replacer] = None,
    exclude: Optional[Iterable[str]] = None,
    pools: Optional[Pools] = None,
    dynamic: Optional[Dynamic] = None,
    auto_detect: AutoDetect = False,
) -> str:
    """Заменяет имена, отчества и фамилии на случайные, сохраняя род и падеж.

    aggressive — True включает всё сразу, или набор частей из AGGRESSIVE:
    "any_case" (имена в нижнем регистре и КАПСЕ), "lone_surnames" (фамилии без имени
    рядом), "ambiguous" (имена, совпадающие с обычными словами: «Вера», «Роман»).

    chat — режим переписки, без aggressive: имена в любом регистре («дима», «ДИМА»),
    фамилии без имени рядом и омонимы с заглавной буквы («Роман», «Надежда», «Света» и
    в начале фразы). Омонимы строчными («читаю роман», «много света») не трогаются.

    languages — какие языки использовать: "ru", "en" или несколько, например ("ru", "en");
    список доступных — available_languages(). Имя заменяется именем того же языка.

    kinds — что заменять: "first" (имена по словарю), "patronymic" (отчества по суффиксам),
    "surname" (фамилии по суффиксам и спискам), "initials", "nickname" (термины dynamic).
    По умолчанию всё. Отключённые виды не ищутся: без "first" словарь имён не загружается,
    а фамилии заменяются и без имени рядом.

    replace — своя функция замены: NameEntity -> строка или None (стандартная замена).
    exclude — слова, которые не трогать («Ростов»); сравниваются без учёта регистра
    с самим словом и его начальной формой.
    pools — свои списки замен: {"first_m": [...], "first_f": [...], "patronymic": [...],
    "surname": [...]}; имена в именительном падеже, склоняются автоматически. Язык значения
    определяется по алфавиту; ключ вида "ru:first_m" задаёт его явно.
    dynamic — термины динамических локалей: {"tg": ["HACER777BEBRA"]}; см. Anonymizer.
    auto_detect — искать новые термины шаблонами локалей (в "tg" — @упоминания).
    """
    return Anonymizer(
        rng=rng, aggressive=aggressive, chat=chat, languages=languages, kinds=kinds,
        replace=replace,
        exclude=exclude, pools=pools, dynamic=dynamic, auto_detect=auto_detect,
    ).anonymize(text)


def anonymize_names_consistent(
    text: str,
    rng: Optional[random.Random] = None,
    aggressive: Aggressive = False,
    chat: bool = False,
    languages: Languages = ("ru",),
    kinds: Kinds = tuple(KINDS),
    replace: Optional[Replacer] = None,
    exclude: Optional[Iterable[str]] = None,
    pools: Optional[Pools] = None,
    dynamic: Optional[Dynamic] = None,
    auto_detect: AutoDetect = False,
) -> str:
    """Как anonymize_names, но одно и то же имя заменяется одной и той же заменой.

    Согласованность действует в пределах одного вызова; чтобы она сохранялась между
    вызовами, используйте Anonymizer(consistent=True).
    """
    return Anonymizer(
        rng=rng,
        aggressive=aggressive,
        chat=chat,
        languages=languages,
        kinds=kinds,
        consistent=True,
        replace=replace,
        exclude=exclude,
        pools=pools,
        dynamic=dynamic,
        auto_detect=auto_detect,
    ).anonymize(text)


# --- Разбор текста -----------------------------------------------------------------------


def _analyze(
    text: str, pattern: re.Pattern, opts: Options, locales: Tuple[Locale, ...]
) -> Tuple[List[_Hit], Set[str]]:
    """Токены, которые нужно заменить, и множество исходных имён текста (в нижнем регистре)."""
    if not text or not pattern.search(text):
        return [], set()

    enabled = opts.enabled
    plans = []
    used: Set[str] = set()
    all_roles = [
        [r for m in run for r in _token_roles(m, opts, locales)] for run in _runs(text, pattern)
    ]
    # «Света не было», «Нате, держите»: одиночное имя-омоним в начале фразы считаем обычным
    # словом, если в тексте оно ни разу не встретилось как имя в другом месте
    homonyms = opts.flags & {"ambiguous", "ambiguous_titled"}
    doubtful = set() if homonyms else _doubtful_common(text, all_roles)
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
                    if r[1] == "surn" and (has_init or not r[0].loc.is_common_word(r[2][0]))
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
        gender, case = (hit.gender if data[1] == "c" else data[1]), data[2]
    elif role == "patr":
        gender, case = data[1], data[2]
    elif role == "surn":
        gender, case = hit.gender, hit.case
    else:
        return NameEntity(tok.start, tok.end, tok.text, "initials", tok.text, hit.gender, None,
                          tok.loc.code)
    normal = tok.loc.normal_form(role, data, gender)
    return NameEntity(tok.start, tok.end, tok.text, _PUBLIC_KIND[role], normal, gender, case,
                      tok.loc.code)


def _excluded(tok: _Token, role: str, data: Entry, exclude: FrozenSet[str]) -> bool:
    """Слово или его начальная форма в exclude; отчество и фамилия — в обоих родах."""
    forms = [tok.text]
    if role == "first":
        forms.append(tok.loc.normal_form(role, data, data[1]))
    elif role in ("patr", "surn"):
        forms += [tok.loc.normal_form(role, data, "m"), tok.loc.normal_form(role, data, "f")]
    return any(form.casefold() in exclude for form in forms)


def _token_roles(m: re.Match, opts: Options, locales: Tuple[Locale, ...]):
    """[(токен, роль, данные)]; нераспознанное составное слово разбирается по частям."""
    role, data, loc = _classify(m.group(), opts, locales)
    if role or "-" not in m.group():
        tokens = [(_Token(m.start(), m.end(), m.group(), loc), role, data)]
    else:
        # «Мария-то», «Ивану-ка»: целиком не имя, но часть может быть именем
        tokens, start = [], m.start()
        for part in m.group().split("-"):
            role, data, loc = _classify(part, opts, locales)
            tokens.append((_Token(start, start + len(part), part, loc), role, data))
            start += len(part) + 1
    if not opts.exclude:
        return tokens
    return [
        (tok, None, None) if role and _excluded(tok, role, data, opts.exclude)
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
            if role != "first" or not tok.loc.is_common_name(data[0]):
                continue
            if len(known) == 1 and _at_sentence_start(text, tok.start):
                doubtful[id(roles)] = data[0]
            else:
                confirmed.add(data[0])
    return {key for key, lemma in doubtful.items() if lemma not in confirmed}


def _at_sentence_start(text: str, start: int) -> bool:
    before = text[:start].rstrip("  \t\r\n«\"„(—–-")
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
