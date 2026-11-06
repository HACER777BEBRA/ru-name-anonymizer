import random

import pytest

from ru_name_anonymizer import anonymize_names, anonymize_names_consistent
from ru_name_anonymizer.locales.ru.dictionary import declension
from ru_name_anonymizer.locales.ru.pools import FIRST as _FIRST_POOL
from ru_name_anonymizer.locales.ru.pools import PATR_STEMS as _PATR_STEMS
from ru_name_anonymizer.locales.ru.pools import SURNAME_STEMS as _SURNAME_STEMS


@pytest.mark.parametrize(
    "text, original",
    [
        ("Никита написал Свете", "Свете"),
        ("Позвони Вере", "Вере"),
        ("Это письмо для Светы", "Светы"),
        ("Надя и Люба пришли", "Надя"),
    ],
)
def test_common_word_names_in_default_mode(text, original):
    for seed in range(10):
        assert original not in anonymize_names(text, random.Random(seed))


def test_lowercase_common_words_kept():
    text = "в свете новых фактов, вера в победу"
    assert anonymize_names(text, random.Random(0)) == text


def test_initials_after_and_before_surname():
    for seed in range(20):
        rng = random.Random(seed)
        after = anonymize_names("Иванов И.И. подписал", rng)
        assert "Иванов" not in after and "И.И." not in after
        assert after.endswith(" подписал")
        before = anonymize_names("Подписал И. И. Иванов", rng)
        assert "Иванов" not in before
        assert before.split()[1].endswith(".") and before.split()[2].endswith(".")


def test_initials_without_surname_kept():
    text = "пункт Б. Затем идём дальше"
    assert anonymize_names(text, random.Random(0)) == text


def test_initials_consistent_mode():
    result = anonymize_names_consistent("Иванов И.И. и Петров И.И.", random.Random(3))
    words = result.split()
    assert words[1] == words[4] and words[1] != "И.И."


@pytest.mark.parametrize(
    "text, original, ending",
    [
        ("Позвони Фёдору Достоевскому", "Достоевскому", "ому"),
        ("Фёдор Достоевский", "Достоевский", "ий"),
        ("Мария говорила с Анной Достоевской", "Достоевской", "ой"),
    ],
)
def test_sk_surnames(text, original, ending):
    result = anonymize_names(text, random.Random(1))
    assert original not in result
    assert result.endswith(ending)


def test_sk_surname_alone_in_aggressive():
    result = anonymize_names("Достоевскому", random.Random(0), aggressive=True)
    assert result != "Достоевскому" and result.endswith("ому")


def test_adjectives_not_surnames_in_aggressive():
    assert anonymize_names("Русский язык", random.Random(0), aggressive=True) == "Русский язык"


def test_hyphenated_names_replaced_whole():
    for seed in range(10):
        result = anonymize_names("Жан-Люк Пикар вошёл", random.Random(seed))
        assert "-" not in result and "Люк" not in result and "Жан" not in result
    result = anonymize_names("Салтыков-Щедрин и Мария", random.Random(0), aggressive=True)
    assert "-" not in result and "Щедрин" not in result


def test_hyphenated_ordinary_words_kept():
    text = "Иван-чай и кто-то"
    assert anonymize_names(text, random.Random(0), aggressive=True).count("-") >= 1


def test_pools_have_at_least_30_and_decline():
    assert len(_FIRST_POOL["m"]) >= 30 and len(_FIRST_POOL["f"]) >= 30
    assert len(_PATR_STEMS) >= 30 and len(_SURNAME_STEMS["ov"]) >= 30
    for pool in _FIRST_POOL.values():
        assert len(set(pool)) == len(pool)
        for lemma in pool:
            assert len(declension(lemma)) == 6, lemma


def test_thirty_distinct_surnames_without_repeats():
    letters = "бвгдклмнпрстфхцчшщ"
    surnames = " ".join(f"Иван {c}авов" for c in letters)
    result = anonymize_names_consistent(surnames, random.Random(0))
    assert len(set(result.split()[1::2])) == len(letters)
