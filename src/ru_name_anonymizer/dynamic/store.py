"""Словарь терминов одного Anonymizer: группы «термин + алиасы» и поиск их в тексте."""

import re
from collections import abc
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from ru_name_anonymizer.dynamic.base import DynamicLocale

Key = Tuple[str, str]  # (код локали, термин в casefold)
TermSpec = Union[str, Iterable[str], Mapping[str, Union[None, str, Mapping[str, object]]]]


class Group:
    """Один человек: основной термин, его алиасы и, если задана, своя замена."""

    __slots__ = ("locale", "term", "aliases", "replacement")

    def __init__(self, locale: DynamicLocale, term: str) -> None:
        self.locale = locale
        self.term = term
        self.aliases: List[str] = []
        self.replacement: Optional[str] = None

    @property
    def key(self) -> Key:
        return (self.locale.code, self.term.casefold())

    def copy(self) -> "Group":
        group = Group(self.locale, self.term)
        group.aliases = list(self.aliases)
        group.replacement = self.replacement
        return group


def _strings(value, what: str) -> Tuple[str, ...]:
    values = (value,) if isinstance(value, str) else tuple(value)
    bad = [v for v in values if not isinstance(v, str)]
    if bad:
        raise TypeError(f"{what}: ожидаются строки, получено {bad!r}")
    return values


class TermStore:
    """Термины всех динамических локалей; каждая строка (без учёта регистра) — один человек."""

    def __init__(self) -> None:
        self.groups: Dict[Key, Group] = {}
        self.index: Dict[str, Key] = {}  # casefold термина или алиаса → группа
        self.version = 0
        self._cache: Optional[Tuple[int, bool, Optional["re.Pattern[str]"]]] = None

    def __bool__(self) -> bool:
        return bool(self.groups)

    def copy(self) -> "TermStore":
        store = TermStore()
        store.groups = {key: group.copy() for key, group in self.groups.items()}
        store.index = dict(self.index)
        return store

    # --- Изменение -----------------------------------------------------------------------

    def add(
        self,
        locale: DynamicLocale,
        terms: TermSpec,
        aliases: Union[str, Iterable[str]] = (),
        replacement: Optional[str] = None,
    ) -> None:
        aliases = _strings(aliases, "aliases")
        if isinstance(terms, str):
            entries = [(terms, aliases, replacement)]
        elif isinstance(terms, abc.Mapping):
            if aliases or replacement is not None:
                raise ValueError("aliases и replacement задаются либо аргументами, либо в словаре")
            entries = [(term, *self._spec(term, spec)) for term, spec in terms.items()]
        else:
            if aliases or replacement is not None:
                raise ValueError("aliases и replacement можно задать только для одного термина")
            entries = [(term, (), None) for term in _strings(terms, "terms")]
        if len(entries) == 1:
            self._add_one(locale, *entries[0])
            return
        draft = self.copy()  # несколько терминов добавляются целиком или никак
        for entry in entries:
            draft._add_one(locale, *entry)
        self.groups, self.index = draft.groups, draft.index
        self.version += 1

    @staticmethod
    def _spec(term, spec) -> Tuple[Tuple[str, ...], Optional[str]]:
        if spec is None or isinstance(spec, str):
            return (), spec
        if isinstance(spec, abc.Mapping):
            unknown = set(spec) - {"aliases", "replacement"}
            if unknown:
                raise ValueError(
                    f"{term!r}: неизвестные ключи {sorted(unknown)}, "
                    "ожидаются aliases и replacement"
                )
            return _strings(spec.get("aliases", ()), "aliases"), spec.get("replacement")
        raise TypeError(
            f"{term!r}: ожидается замена (str), None или словарь с aliases и replacement"
        )

    def _add_one(
        self,
        locale: DynamicLocale,
        term: str,
        aliases: Sequence[str],
        replacement: Optional[str],
    ) -> None:
        if not isinstance(term, str):
            raise TypeError(f"{locale.code}: термин должен быть строкой, получено {term!r}")
        term = locale.prepare(term)
        if not locale.validate(term):
            raise ValueError(f"{locale.code}: недопустимый термин {term!r}")
        if replacement is not None and (not isinstance(replacement, str) or not replacement):
            raise ValueError(f"{term!r}: замена должна быть непустой строкой")
        key = (locale.code, term.casefold())
        new_aliases = []
        for alias in aliases:
            alias = alias.strip()
            if not locale.validate_alias(alias):
                raise ValueError(f"{locale.code}: недопустимый алиас {alias!r}")
            new_aliases.append(alias)
        for value in (term, *new_aliases):
            owner = self.index.get(value.casefold())
            if owner is not None and owner != key:
                raise ValueError(
                    f"{value!r} уже относится к термину {self.groups[owner].term!r} "
                    f"({owner[0]}); одна строка — один человек"
                )
        # проверки пройдены — меняем
        group = self.groups.get(key)
        if group is None:
            group = self.groups[key] = Group(locale, term)
            self.index[key[1]] = key
        known = {a.casefold() for a in group.aliases} | {key[1]}
        for alias in new_aliases:
            if alias.casefold() not in known:
                group.aliases.append(alias)
                known.add(alias.casefold())
                self.index[alias.casefold()] = key
        if replacement is not None:
            group.replacement = replacement
        self.version += 1

    def remove(self, locale: DynamicLocale, terms: Union[str, Iterable[str]]) -> None:
        """Термин удаляет всю группу, алиас — только себя; незнакомые строки пропускаются."""
        for value in _strings(terms, "terms"):
            folded = locale.prepare(value).casefold()
            key = self.index.get(folded)
            if key is None or key[0] != locale.code:
                continue
            group = self.groups[key]
            if folded == key[1]:
                for alias in group.aliases:
                    self.index.pop(alias.casefold(), None)
                del self.index[folded], self.groups[key]
            else:
                group.aliases = [a for a in group.aliases if a.casefold() != folded]
                del self.index[folded]
            self.version += 1

    def detect(self, text: str, locales: Sequence[DynamicLocale]) -> None:
        """Автопоиск: добавляет термины, найденные шаблонами detect, если их ещё нет."""
        for locale in locales:
            pattern = locale.detect_re
            if pattern is None:
                continue
            for match in pattern.finditer(text):
                raw = match.group("term") if "term" in pattern.groupindex else match.group()
                term = locale.prepare(raw)
                if term.casefold() in self.index or not locale.validate(term):
                    continue
                self._add_one(locale, term, (), None)

    # --- Поиск ---------------------------------------------------------------------------

    def pattern(self, any_case: bool) -> Optional["re.Pattern[str]"]:
        cache = self._cache
        if cache is not None and cache[0] == self.version and cache[1] == any_case:
            return cache[2]
        alternatives: List[Tuple[int, str]] = []
        for group in self.groups.values():
            chars = group.locale.word_chars

            def add(value: str, ignore_case: bool) -> None:
                body = re.escape(value)
                if ignore_case:
                    body = f"(?i:{body})"
                alternatives.append((len(value), f"(?<![{chars}]){body}(?![{chars}])"))

            # username и другие термины — без учёта регистра
            add(group.term, True)
            for alias in group.aliases:
                if any_case:
                    add(alias, True)
                    continue
                # алиас — как записан, с заглавной и КАПСОМ, но не строчными («Zik», не «zik»)
                for form in dict.fromkeys((alias, alias[:1].upper() + alias[1:], alias.upper())):
                    add(form, False)
        alternatives.sort(key=lambda item: -item[0])
        compiled = re.compile("|".join(a for _, a in alternatives)) if alternatives else None
        self._cache = (self.version, any_case, compiled)
        return compiled

    def find(self, text: str, any_case: bool) -> List[Tuple[int, int, Group]]:
        pattern = self.pattern(any_case)
        if pattern is None or not text:
            return []
        found = []
        for match in pattern.finditer(text):
            key = self.index.get(match.group().casefold())
            if key is not None:
                found.append((match.start(), match.end(), self.groups[key]))
        return found

    # --- Представление -------------------------------------------------------------------

    def view(self) -> Dict[str, Dict[str, List[str]]]:
        result: Dict[str, Dict[str, List[str]]] = {}
        for (code, _), group in self.groups.items():
            result.setdefault(code, {})[group.term] = list(group.aliases)
        return result

    def export(self) -> List[Dict[str, object]]:
        return [
            {
                "locale": group.locale.code,
                "term": group.term,
                "aliases": list(group.aliases),
                "replacement": group.replacement,
            }
            for group in self.groups.values()
        ]
