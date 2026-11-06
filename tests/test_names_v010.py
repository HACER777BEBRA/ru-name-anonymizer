import pytest

from ru_name_anonymizer import find_names


def _found(text, **kw):
    return [(e.text, e.normal_form, e.case) for e in find_names(text, **kw)]


@pytest.mark.parametrize("text, word", [
    ("Слава пришёл", "Слава"),
    ("Варвара пришла", "Варвара"),
    ("Позвони Славе", "Славе"),
    ("Передай Варваре", "Варваре"),
])
def test_slava_varvara_in_chat(text, word):
    assert word in [e.text for e in find_names(text, chat=True)]


@pytest.mark.parametrize("text", ["слава богу", "дикие варвара не пощадят", "много славы"])
def test_slava_varvara_lowercase_kept_in_chat(text):
    assert find_names(text, chat=True) == []


@pytest.mark.parametrize("text, lemma", [
    ("Позвони Анне", "Анна"),
    ("Скажи Алине", "Алина"),
    ("Подари Карине", "Карина"),
    ("Напиши Кристине", "Кристина"),
])
def test_dative_not_indeclinable_lemma(text, lemma):
    (_, normal, case), = _found(text)
    assert normal == lemma and case == "datv"


@pytest.mark.parametrize("word, lemma", [
    ("Майя", "Майя"), ("Аде", "Ада"), ("Ян", "Ян"), ("Яну", "Ян"), ("Милане", "Милана"),
    ("Лейсан", "Лейсан"), ("Ксюха", "Ксюха"), ("Ксюхе", "Ксюха"), ("Жека", "Жека"),
    ("Санёк", "Санёк"), ("Ия", "Ия"), ("Колян", "Колян"), ("Ленке", "Ленка"),
])
def test_short_rare_and_colloquial_names(word, lemma):
    assert [f[1] for f in _found(f"Позвони {word} сейчас")] == [lemma]


@pytest.mark.parametrize("text", ["цивилизация майя", "из ада", "плюшевый мишка"])
def test_colloquial_homonyms_lowercase_kept(text):
    assert find_names(text, chat=True) == []


@pytest.mark.parametrize("text", [
    "Живу в Иванове", "Приехал из Петрова", "улица Ленина", "на улице Пушкина",
    "Был в Милане", "Аллея Славы", "ул. Гагарина",
])
def test_place_after_preposition_or_street(text):
    assert find_names(text, chat=True) == []
    assert find_names(text, aggressive=True) == []


@pytest.mark.parametrize("text, word", [
    ("Влюбилась в Машу", "Машу"),
    ("Иван Петров живёт в Иванове", "Петров"),
    ("Видел в Иване Петрове друга", "Петрове"),
])
def test_names_near_place_markers_still_found(text, word):
    assert word in [e.text for e in find_names(text, chat=True)]
