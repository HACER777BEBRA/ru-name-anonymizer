"""Отчества и фамилии: распознавание по суффиксам и склонение."""

import re
from typing import Optional, Tuple

from ru_name_anonymizer.locales.base import Entry

_PATR_M = {"": "nomn", "а": "gent", "у": "datv", "ем": "ablt", "е": "loct"}
_PATR_F = {"на": "nomn", "ны": "gent", "не": "datv", "ну": "accs", "ной": "ablt"}
_SURN_M = {"": "nomn", "а": "gent", "у": "datv", "ым": "ablt", "е": "loct"}
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
SK_STOP = {
    "русск", "польск", "английск", "французск", "немецк", "украинск", "московск", "китайск",
    "японск", "испанск", "итальянск", "еврейск", "детск", "городск", "морск", "сельск",
    "российск", "всероссийск", "советск", "европейск", "американск", "азиатск", "петербургск",
    "белорусск", "казахск", "грузинск", "армянск", "турецк", "шведск", "финск", "датск",
    "норвежск", "канадск", "индийск", "корейск", "арабск", "минск", "мужск", "женск",
}

_PATR_M_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))ич(а|у|ем|е)?$")
_PATR_F_RE = re.compile(r"^([А-ЯЁ][а-яё]*?(?:ов|ев))(на|ны|не|ну|ной)$")
_SURN_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ов|ев|ёв|ин|ын))(а|у|ым|е|ой)?$")
_SK_RE = re.compile(r"^([А-ЯЁ][а-яё]+?(?:ск|цк))(ий|ого|ому|им|ом|ая|ой|ую)$")


def is_sk(stem: str) -> bool:
    """Основа фамилии-прилагательного: «Достоевск», «Заболоцк»."""
    return stem.lower().endswith(("ск", "цк"))


def patronymic_info(word: str) -> Optional[Entry]:
    """(основа, род, падеж) отчества: «Петровичу» → («Петров», "m", "datv")."""
    m = _PATR_M_RE.match(word)
    if m:
        return m.group(1), "m", _PATR_M[m.group(2) or ""]
    m = _PATR_F_RE.match(word)
    if m:
        return m.group(1), "f", _PATR_F[m.group(2)]
    return None


def parse_patronymic(name: str) -> Optional[Tuple[str, str]]:
    """(основа, род) отчества в любом падеже."""
    info = patronymic_info(name)
    return (info[0], info[1]) if info else None


def surname_info(token: str) -> Optional[Entry]:
    """(основа, род, падеж) фамилии на -ов/-ев/-ин/-ын/-ский/-цкий."""
    m = _SK_RE.match(token)
    if m:
        stem, ending = m.group(1), m.group(2)
        # «-ческий» почти всегда прилагательное: «Технический», «Исторический»
        if stem.lower() in SK_STOP or stem.endswith("ческ"):
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


def decline_patronymic(stem: str, gender: str, case: str) -> str:
    return stem + (_PATR_F_SUFFIX if gender == "f" else _PATR_M_SUFFIX)[case]


def decline_surname(stem: str, gender: str, case: str) -> str:
    female = gender == "f"
    if is_sk(stem):
        return stem + (_SK_F_SUFFIX if female else _SK_M_SUFFIX)[case]
    return stem + (_SURN_F_SUFFIX if female else _SURN_M_SUFFIX)[case]
