import pytest

from ru_name_anonymizer import preload
from ru_name_anonymizer.dictionary import declension, load, lookup


@pytest.mark.parametrize(
    "token, lemma, case",
    [
        ("Дмитрий", "Дмитрий", "nomn"),
        ("Дмитрию", "Дмитрий", "datv"),
        ("Диме", "Дима", "datv"),
        ("Марии", "Мария", "gent"),
        ("Анной", "Анна", "ablt"),
        ("Игорем", "Игорь", "ablt"),
        ("Павла", "Павел", "gent"),
    ],
)
def test_lookup(token, lemma, case):
    found = lookup(token)
    assert found is not None and found[0] == lemma and found[2] == case


@pytest.mark.parametrize("token", ["Москва", "Привет", "Мир", "Март", "Вера"])
def test_common_words_are_not_names(token):
    assert lookup(token) is None


def test_declension_regular_and_exception():
    assert declension("Анна")["datv"] == "Анне"
    assert declension("Ольга")["gent"] == "Ольги"
    assert declension("Павел")["gent"] == "Павла"


def test_preload_fills_cache():
    load.cache_clear()
    preload()
    assert load.cache_info().currsize == 1
