"""Небольшой словарь самых популярных английских имён и фамилий (не склоняются)."""

from typing import Dict, List, Optional

from ru_name_anonymizer.dictionary import Entry

_MALE = """
James John Robert Michael William David Richard Joseph Thomas Charles Christopher Daniel
Matthew Anthony Paul Andrew Joshua Kevin Brian George Edward Peter Henry Oliver Jacob
Ethan Benjamin Samuel Alexander Patrick Nicholas Jack Harry Oscar Liam Noah Lucas
""".split()

_FEMALE = """
Mary Patricia Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen Nancy Lisa Emily
Margaret Sandra Ashley Michelle Amanda Melissa Rachel Laura Emma Olivia Sophia Anna Helen
Catherine Victoria Charlotte Alice Julia Chloe Lily Hannah Natalie Isabella
""".split()

# Могут быть и мужскими, и женскими: род берётся из окружения, иначе мужской
_UNISEX = "Alex Sam Taylor Jordan Morgan Casey".split()

# Совпадают с обычными словами: заменяются только в aggressive и только с заглавной буквы
_AMBIGUOUS = {
    "m": "Will Bill Mark Frank",
    "f": "Hope Faith Joy May June April Rose Grace",
}

_SURNAMES = """
Smith Johnson Williams Brown Jones Miller Davis Wilson Anderson Moore Jackson Martin Lee
Thompson White Harris Clark Lewis Robinson Walker Young Allen King Wright Scott Hill Green
Adams Nelson Baker Hall Campbell Mitchell Carter Roberts Phillips Evans Turner Parker
Edwards Collins Stewart Morris Murphy Cook Rogers Cooper Reed Bailey Bell Kelly Howard
""".split()

# Фамилии, совпадающие с обычными словами («The White House», «Young people»)
_COMMON_WORD_SURNAMES = frozenset(
    "White Young Green King Hill Bell Cook Hall Brown Baker Turner Reed Walker Cooper Carter "
    "Parker Moore Lee Scott Wright".split()
)

FIRST: Dict[str, List[str]] = {"m": sorted(set(_MALE)), "f": sorted(set(_FEMALE))}
SURNAMES: List[str] = sorted(set(_SURNAMES))

_GENDERS: Dict[str, str] = {name: "m" for name in _MALE}
_GENDERS.update({name: "f" for name in _FEMALE})
_GENDERS.update({name: "c" for name in _UNISEX})
_AMBIGUOUS_GENDERS: Dict[str, str] = {
    name: gender for gender, names in _AMBIGUOUS.items() for name in names.split()
}
_SURNAME_SET = frozenset(_SURNAMES) - _GENDERS.keys() - _AMBIGUOUS_GENDERS.keys()


def lookup(word: str, ambiguous: bool, titled: bool) -> Optional[Entry]:
    """Имя из словаря как (имя, род, nomn); titled — слово в исходном тексте с заглавной."""
    if len(word) < 3:
        return None
    gender = _GENDERS.get(word)
    if gender is None and ambiguous and titled:
        gender = _AMBIGUOUS_GENDERS.get(word)
    return (word, gender, "nomn") if gender else None


def is_surname(word: str) -> bool:
    return word in _SURNAME_SET


def is_common_word(word: str) -> bool:
    """Фамилия, совпадающая с обычным словом: без имени или инициалов рядом не заменяется."""
    return word in _COMMON_WORD_SURNAMES
