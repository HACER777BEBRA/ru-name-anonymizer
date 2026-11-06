"""Интерфейс динамической локали.

Статическая локаль (locales/) знает язык: словарь имён, суффиксы, склонение. Динамическая
знает только правила для идентификаторов, которые приложение передаёт во время работы:
ники, username, подписи. Сами термины хранит Anonymizer (add_terms), а локаль отвечает на
вопросы «как привести термин к виду для поиска», «годится ли он», «где кончается ник»
и «на что его заменить». Библиотека не пытается найти такие идентификаторы сама, кроме
необязательного шаблона detect (автопоиск, например @упоминаний в Telegram).
"""

import re
from functools import cached_property
from typing import AbstractSet, Optional, Sequence

from ru_name_anonymizer.dynamic import pools

_CYRILLIC = re.compile("[А-Яа-яЁё]")


class DynamicLocale:
    """Базовая динамическая локаль; переопределите в подклассе то, что нужно.

    code — код локали, его передают в dynamic= и add_terms().
    word_chars — содержимое класса символов регулярного выражения: символы, которые
    считаются продолжением термина. Термин совпадает, только если до и после него стоит
    что-то другое: «Zik» не найдётся внутри «Zikov», но найдётся в «Zik's» и «@Zik».
    detect — регулярное выражение для автопоиска новых терминов (Anonymizer(auto_detect=…));
    термин — группа «term», а без неё всё совпадение. None — автопоиска нет.
    """

    code: str = ""
    name: str = ""  # человекочитаемое название для сообщений
    word_chars: str = r"\w"
    detect: Optional[str] = None

    @cached_property
    def detect_re(self) -> Optional["re.Pattern[str]"]:
        return re.compile(self.detect) if self.detect else None

    # --- Термины -------------------------------------------------------------------------

    def prepare(self, term: str) -> str:
        """Термин в том виде, в котором его ищем: убрать пробелы, префиксы и т. п."""
        return term.strip()

    def validate(self, term: str) -> bool:
        """Годится ли подготовленный термин (основная строка группы)."""
        return len(term) >= 2 and "\n" not in term and term == term.strip()

    def validate_alias(self, alias: str) -> bool:
        """Годится ли алиас: другое написание того же человека («Zik» для «Zik_2005»)."""
        return DynamicLocale.validate(self, alias)

    # --- Замены --------------------------------------------------------------------------

    def pool(self, term: str) -> Sequence[str]:
        """Основы замен для термина: кириллические для кириллицы, иначе английские."""
        return pools.RU if _CYRILLIC.search(term) else pools.EN

    def fake(self, term: str, rng, used: AbstractSet[str]) -> str:
        """Новый ник для термина; used — уже выданные замены в нижнем регистре.

        Вызывается один раз на термин: дальше Anonymizer подставляет запомненное значение.
        """
        bases = self.pool(term)
        lower = term == term.lower() and term != term.upper()

        def styled(base: str, year: str, extra: str = "") -> str:
            value = f"{base}{year}{extra}"
            return value.lower() if lower else value

        for _ in range(32):
            value = styled(rng.choice(bases), rng.choice(pools.YEARS))
            if value.lower() not in used:
                return value
        free = [
            styled(base, year)
            for base in bases
            for year in pools.YEARS
            if styled(base, year).lower() not in used
        ]
        if free:
            return rng.choice(free)
        base, year = rng.choice(bases), rng.choice(pools.YEARS)
        extra = 2
        while styled(base, year, f"_{extra}").lower() in used:
            extra += 1
        return styled(base, year, f"_{extra}")


class NickLocale(DynamicLocale):
    """Любые строки: ники из игр, подписи, отображаемые имена."""

    code = "nick"
    name = "ники и произвольные строки"


class TelegramLocale(DynamicLocale):
    """Базовый шаблон для Telegram: username и, по желанию, автопоиск @упоминаний."""

    code = "tg"
    name = "Telegram"
    word_chars = r"\w"
    detect = r"(?<![\w.@])@(?P<term>[A-Za-z][A-Za-z0-9_]{4,31})(?!\w)"

    _USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")

    def prepare(self, term: str) -> str:
        return term.strip().lstrip("@")

    def validate(self, term: str) -> bool:
        return self._USERNAME.fullmatch(term) is not None

    def pool(self, term: str) -> Sequence[str]:
        return pools.EN  # замена — тоже допустимый username
