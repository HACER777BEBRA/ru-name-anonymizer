import random

from ru_name_anonymizer import anonymize_names, anonymize_names_consistent


def test_consistent_same_name_same_replacement():
    for seed in range(20):
        result = anonymize_names_consistent(
            "Мария позвонила Анне. Потом Мария написала Анне", random.Random(seed)
        )
        first, second = result.split(". ")
        assert first.split()[0] == second.split()[1]
        assert first.split()[-1] == second.split()[-1]
        assert first.split()[0] != first.split()[-1]


def test_consistent_keeps_case_forms():
    result = anonymize_names_consistent("Дмитрий и Дмитрию", random.Random(1))
    nom, dat = result.split(" и ")
    assert dat.endswith(("ю", "и"))
    assert nom[:3] == dat[:3]


def test_default_mode_ignores_lowercase_and_standalone():
    text = "дима и Иванов, Вера и Роман"
    assert anonymize_names(text, random.Random(0)) == text


def test_aggressive_lowercase_caps_standalone_and_ambiguous():
    result = anonymize_names("дима, ДИМА, Иванов, Вера и Роман", random.Random(2), aggressive=True)
    for original in ["дима", "ДИМА", "Иванов", "Вера", "Роман"]:
        assert original not in result
    words = result.replace(",", "").split()
    assert words[0].islower() and words[1].isupper()


def test_aggressive_keeps_ordinary_lowercase_words():
    text = "привет, это сын и дом"
    assert anonymize_names(text, random.Random(0), aggressive=True) == text


def test_no_cyrillic_returns_same_object():
    text = "hello world 123"
    assert anonymize_names(text) is text
    assert anonymize_names(text, aggressive=True) is text
