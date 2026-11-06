"""Интерфейс локали: всё, что зависит от языка, живёт в её подклассе.

Ядро (anonymizer.py) находит слова, группирует их, подбирает замены и следит за
согласованностью; локаль отвечает на вопросы «что это за слово», «как его склонять»
и «на что заменять». Роли слов: "first" (имя), "patr" (отчество), "surn" (фамилия),
"init" (инициалы — обрабатываются ядром).
"""

import re
from functools import cached_property
from typing import AbstractSet, Dict, FrozenSet, List, NamedTuple, Optional, Sequence, Tuple

CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")

Entry = Tuple[str, str, str]  # (лемма или основа, род "m"/"f"/"c", падеж из CASES)
Classified = Tuple[Optional[str], Optional[Entry]]  # (роль, данные) или (None, None)

# Ключ параметра pools → роль
POOL_ROLES = {"first_m": "first", "first_f": "first", "patronymic": "patr", "surname": "surn"}


class Options(NamedTuple):
    enabled: FrozenSet[str]  # включённые роли: отключённый источник не используется
    flags: FrozenSet[str]  # части aggressive и "ambiguous_titled" (из chat)
    exclude: FrozenSet[str]  # слова, которые не трогаем (casefold)


def titled(token: str) -> bool:
    """«Иван», но не «иван», «ИВАН» или «ИваН»."""
    return token[0].isupper() and token[1:].islower()


class Locale:
    """Базовая локаль. Обязательны code, upper, lower, classify_word и default_pools.

    upper, lower — содержимое классов символов регулярного выражения для заглавных и
    строчных букв алфавита, например "А-ЯЁ" и "а-яё". Из них ядро строит регулярки для
    поиска слов и инициалов, поэтому дефис, точку и «]» сюда включать нельзя.

    Категории пулов замен — произвольные строки внутри локали; соглашения ядра:
    "first:m" и "first:f" — имена, остальные называет сама локаль (surname_categories,
    patronymic_category).
    """

    code: str = ""
    name: str = ""  # человекочитаемое название для сообщений
    upper: str = ""
    lower: str = ""

    # --- Алфавит -------------------------------------------------------------------------

    @cached_property
    def letter_re(self) -> "re.Pattern[str]":
        """Одна заглавная буква: по ней ядро заменяет буквы в инициалах."""
        return re.compile(f"[{self.upper}]")

    @cached_property
    def _token_re(self) -> "re.Pattern[str]":
        return re.compile(f"[{self.upper}{self.lower}.\\-  ]+")

    @cached_property
    def _name_re(self) -> "re.Pattern[str]":
        word = f"[{self.upper}][{self.lower}]+"
        return re.compile(f"{word}(?:-{word})*")

    def owns(self, token: str) -> bool:
        """Токен целиком записан алфавитом локали."""
        return self._token_re.fullmatch(token) is not None

    def is_name_shaped(self, value: str) -> bool:
        """«Анна», «Анна-Мария»: слово с заглавной буквы этого алфавита."""
        return self._name_re.fullmatch(value) is not None

    # --- Распознавание -------------------------------------------------------------------

    def preload(self, roles: AbstractSet[str]) -> None:
        """Загрузить словари, которые понадобятся для этих ролей."""

    def classify_word(self, token: str, opts: Options) -> Classified:
        """Роль и данные одиночного слова без дефиса (как записано в тексте).

        Учитывать opts.enabled (выключенные роли не распознавать) и opts.flags:
        "any_case" — слово может быть в любом регистре, "ambiguous" — распознавать
        имена-омонимы, "ambiguous_titled" — омонимы, но только с заглавной буквы.
        Для фамилии род и падеж можно вернуть "c" и "nomn": ядро возьмёт их у имени
        или отчества рядом.
        """
        raise NotImplementedError

    def is_common_name(self, lemma: str) -> bool:
        """Имя-омоним («Света»): одиночное в начале фразы считается обычным словом."""
        return False

    def is_common_word(self, stem: str) -> bool:
        """Фамилия-омоним («White»): без имени или инициалов рядом не заменяется."""
        return False

    # --- Формы ---------------------------------------------------------------------------

    def decline(self, role: str, stem: str, gender: str, case: str) -> str:
        """Форма замены: лемма имени или основа отчества/фамилии в нужном роде и падеже."""
        return stem

    def normal_form(self, role: str, data: Entry, gender: str) -> str:
        """Начальная форма найденного слова (для NameEntity и exclude)."""
        return data[0]

    def inflect(self, name: str, case: str, role: str, gender: Optional[str]) -> str:
        """Публичный inflect: name — слово в любой форме; не умеем — вернуть как есть."""
        return name

    # --- Замены --------------------------------------------------------------------------

    def default_pools(self) -> Dict[str, List[str]]:
        """Категория → список замен (леммы имён, основы отчеств и фамилий)."""
        raise NotImplementedError

    def fallback_pool(self, category: str) -> Tuple[str, ...]:
        """Запасной пул, когда основной исчерпан в режиме consistent; () — запаса нет."""
        return ()

    def patronymic_category(self) -> str:
        return "patr"

    def surname_categories(self, stem: str) -> Sequence[str]:
        """Категории для замены фамилии по порядку предпочтения (берётся первая непустая)."""
        return ("surn",)

    def custom_pools(self, key: str, values: List[str]) -> Dict[str, List[str]]:
        """Пользовательские pools[key] (слова этого алфавита) → категории этой локали.

        key — один из POOL_ROLES. Неподходящие значения — ValueError с понятным текстом.
        """
        role = POOL_ROLES[key]
        if role == "first":
            return {f"first:{key[-1]}": values}
        if role == "surn":
            return {self.surname_categories("")[0]: values}
        raise ValueError(
            f"pools[{key!r}]: язык {self.code!r} не поддерживает этот вид, получено {values!r}"
        )

    def initial_letters(self, gender: str, index: int) -> AbstractSet[str]:
        """Буквы для замены index-го инициала (0 — имя, 1 — отчество или второе имя)."""
        return {name[0] for name in self.default_pools()[f"first:{gender}"]}
