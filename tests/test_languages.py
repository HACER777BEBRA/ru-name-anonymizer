import random

import pytest

from ru_name_anonymizer import anonymize_names, anonymize_names_consistent, preload


def rng():
    return random.Random(1)


def test_default_is_russian_only():
    assert anonymize_names("John Smith", rng()) == "John Smith"
    assert anonymize_names("Иван Петров", rng()) != "Иван Петров"


def test_english_only_ignores_russian():
    text = "Иван Петров и John Smith"
    out = anonymize_names(text, rng(), languages="en")
    assert out.startswith("Иван Петров и ")
    assert "John" not in out and "Smith" not in out


def test_both_languages():
    out = anonymize_names("Иван Петров и John Smith", rng(), languages=("ru", "en"))
    for original in ("Иван", "Петров", "John", "Smith"):
        assert original not in out


def test_replacement_keeps_language():
    out = anonymize_names("John Smith", rng(), languages=("ru", "en"))
    assert out.isascii()


def test_english_gender_kept():
    from ru_name_anonymizer.locales.en import names as english

    for seed in range(20):
        out = anonymize_names("Mary Smith", random.Random(seed), languages="en")
        assert out.split()[0] in english.FIRST["f"]


def test_english_possessive_and_initials():
    out = anonymize_names("John's book by J. K. Smith", rng(), languages="en")
    assert "'s book by " in out and "John" not in out and "Smith" not in out


def test_english_surname_alone_needs_aggressive():
    assert anonymize_names("Smith said", rng(), languages="en") == "Smith said"
    assert anonymize_names("Smith said", rng(), aggressive=True, languages="en") != "Smith said"


def test_english_ambiguous_only_aggressive_and_capitalized():
    assert anonymize_names("Will you go", rng(), languages="en") == "Will you go"
    out = anonymize_names("will you go, Will", rng(), aggressive=True, languages="en")
    assert out.startswith("will you go, ") and not out.endswith("Will")


def test_english_case_preserved_in_aggressive():
    out = anonymize_names("john JOHN", rng(), aggressive=True, languages="en")
    first, second = out.split()
    assert first.islower() and second.isupper()


def test_english_consistent():
    out = anonymize_names_consistent("John met John and Mary", rng(), languages="en").split()
    assert out[0] == out[2] and out[0] != out[-1]


def test_invalid_languages():
    with pytest.raises(ValueError):
        anonymize_names("x", languages="de")
    with pytest.raises(ValueError):
        anonymize_names("x", languages=())


def test_preload_accepts_languages():
    preload("en")
    preload(("ru", "en"))


def test_kinds_only_first():
    out = anonymize_names("Иван Петрович Сидоров", rng(), kinds="first").split()
    assert out[0] != "Иван" and out[1:] == ["Петрович", "Сидоров"]


def test_kinds_only_patronymic_does_not_load_dictionary():
    from ru_name_anonymizer.locales.ru import dictionary

    dictionary.load.cache_clear()
    out = anonymize_names("Иван Петрович Сидоров", rng(), kinds="patronymic").split()
    assert out[0] == "Иван" and out[1] != "Петрович" and out[2] == "Сидоров"
    assert dictionary.load.cache_info().currsize == 0


def test_kinds_only_surname_without_name_nearby():
    out = anonymize_names("сказал Иванов", rng(), kinds="surname")
    assert out.startswith("сказал ") and "Иванов" not in out
    assert anonymize_names("Иван Иванов", rng(), kinds="surname").startswith("Иван ")


def test_kinds_only_initials():
    out = anonymize_names("И.И. Иванов", rng(), kinds="initials")
    assert out.endswith(" Иванов") and out != "И.И. Иванов"


def test_kinds_combination_and_english():
    out = anonymize_names(
        "Иван Петрович Сидоров и John Smith", rng(), languages=("ru", "en"),
        kinds=("first", "surname"),
    ).split()
    assert out[0] != "Иван" and out[1] == "Петрович" and out[2] != "Сидоров"
    assert out[-2] != "John" and out[-1] != "Smith"


def test_invalid_kinds():
    with pytest.raises(ValueError):
        anonymize_names("x", kinds="nickname")
    with pytest.raises(ValueError):
        anonymize_names("x", kinds=[])
