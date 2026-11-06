import random

import pytest

from ru_name_anonymizer import (
    Anonymizer,
    Locale,
    anonymize_names,
    available_languages,
    find_names,
    inflect,
    register_locale,
)
from ru_name_anonymizer.locales import _registry, get_locale, titled


class ToyLocale(Locale):
    """Белорусскоподобный алфавит: кириллица с «і» и «ў», крошечный словарь."""

    code = "xx"
    upper = "А-ЯЁІЎ"
    lower = "а-яёіў'"
    NAMES = {"Алесь": "m", "Васіль": "m", "Алеся": "f", "Янка": "m"}

    def classify_word(self, token, opts):
        word = token.capitalize() if "any_case" in opts.flags else token
        if "first" in opts.enabled and word in self.NAMES:
            return "first", (word, self.NAMES[word], "nomn")
        if "surn" in opts.enabled and titled(token) and token.endswith(("ук", "ёў")):
            return "surn", (token, "c", "nomn")
        return None, None

    def default_pools(self):
        return {"first:m": ["Міхась", "Сымон"], "first:f": ["Ганна", "Ядвіся"], "surn": ["Ткачук"]}


@pytest.fixture
def toy():
    locale = ToyLocale()
    register_locale(locale)
    yield locale
    _registry.pop("xx", None)


def test_builtin_locales_discovered():
    assert available_languages()[:2] == ("ru", "en")
    assert get_locale("ru").code == "ru"


def test_registered_locale_is_used(toy):
    assert "xx" in available_languages()
    out = anonymize_names("Васіль Ковалёў прыйшоў", random.Random(1), languages="xx")
    first, surname, rest = out.split()
    assert first in ("Міхась", "Сымон") and surname == "Ткачук" and rest == "прыйшоў"


def test_union_alphabet_keeps_word_whole(toy):
    # слово с «і» не режется русской регуляркой на «Вас» + «іль»
    entities = find_names("Васіль і Иван Петров", languages=("ru", "xx"))
    assert [(e.text, e.language) for e in entities] == [
        ("Васіль", "xx"), ("Иван", "ru"), ("Петров", "ru"),
    ]


def test_language_order_decides_shared_words(toy):
    # «Алеся» записана общими буквами: узнаёт первый язык, который её знает
    assert find_names("Алеся пришла", languages=("xx", "ru"))[0].language == "xx"


def test_prefixed_pool_key(toy):
    anon = Anonymizer(rng=random.Random(0), languages="xx", pools={"xx:first_m": ["Алег"]})
    assert anon.anonymize("Янка") == "Алег"
    with pytest.raises(ValueError):
        Anonymizer(pools={"zz:first_m": ["Алег"]})


def test_inflect_language(toy):
    assert inflect("Павел", "datv") == "Павлу"
    assert inflect("Павел", "datv", language="ru") == "Павлу"
    assert inflect("Алесь", "datv", language="xx") == "Алесь"  # локаль без склонения
    with pytest.raises(ValueError):
        inflect("Павел", "datv", language="zz")


def test_register_validation(toy):
    with pytest.raises(ValueError):
        register_locale(ToyLocale())  # код уже занят
    register_locale(toy, replace=False)  # тот же объект — не ошибка
    bad = ToyLocale()
    bad.code = "Bad Code"
    with pytest.raises(ValueError):
        register_locale(bad)
    with pytest.raises(TypeError):
        register_locale(object())
