"""Настройка под приложение: части aggressive, exclude, pools, inflect, состояние consistent."""

import json
import random
import threading
import warnings

import pytest

from ru_name_anonymizer import (
    Anonymizer,
    anonymize_names,
    anonymize_names_consistent,
    find_names,
    inflect,
)
from ru_name_anonymizer.anonymizer import AGGRESSIVE
from ru_name_anonymizer.locales.ru.dictionary import declension, load


def rng(seed=0):
    return random.Random(seed)


# --- aggressive по частям ---------------------------------------------------------------

TEXT = "дима и Иванов, Роман и Любовь"


def test_any_case_only():
    result = anonymize_names(TEXT, rng(), aggressive="any_case")
    assert not result.startswith("дима")
    assert result.endswith("Иванов, Роман и Любовь")


def test_lone_surnames_only():
    result = anonymize_names(TEXT, rng(), aggressive="lone_surnames")
    assert result.startswith("дима и ") and "Иванов" not in result
    assert result.endswith("Роман и Любовь")


def test_ambiguous_only():
    result = anonymize_names(TEXT, rng(), aggressive="ambiguous")
    assert result.startswith("дима и Иванов, ")
    assert "Роман" not in result and "Любовь" not in result


def test_ambiguous_also_disables_sentence_start_doubt():
    assert anonymize_names("Света не было.", rng()) == "Света не было."
    assert anonymize_names("Света не было.", rng(), aggressive="ambiguous") != "Света не было."


def test_any_case_without_ambiguous_keeps_lowercase_homonyms():
    text = "много света, ВЕРА"
    assert anonymize_names(text, rng(), aggressive="any_case") == text
    assert anonymize_names(text, rng(), aggressive=("any_case", "ambiguous")) != text


def test_true_means_all_parts():
    for seed in range(5):
        assert anonymize_names(TEXT, rng(seed), aggressive=True) == anonymize_names(
            TEXT, rng(seed), aggressive=AGGRESSIVE
        )


def test_aggressive_validation_and_property():
    assert Anonymizer(aggressive=True).aggressive == AGGRESSIVE
    assert Anonymizer().aggressive == ()
    assert Anonymizer(aggressive=["ambiguous", "any_case"]).aggressive == ("any_case", "ambiguous")
    with pytest.raises(ValueError):
        Anonymizer(aggressive="everything")


def test_english_ambiguous_part():
    text = "Will said"
    assert anonymize_names(text, rng(), languages="en") == text
    assert anonymize_names(text, rng(), languages="en", aggressive="ambiguous") != text


# --- exclude -----------------------------------------------------------------------------


def test_exclude_word_in_any_case_form():
    text = "Иван Ростов приехал в Ростове"
    result = anonymize_names(text, rng(), aggressive=True, exclude=["ростов"])
    assert "Ростов приехал в Ростове" in result and not result.startswith("Иван")


def test_exclude_surname_covers_both_genders():
    text = "Иван Петров и Ольга Петровой"
    found = [e.text for e in find_names(text, exclude="Петров")]
    assert found == ["Иван", "Ольга"]


def test_exclude_first_name_and_patronymic():
    text = "Иван Сергеевич и Мария"
    assert [e.text for e in find_names(text, exclude=["Сергеевна", "Мария"])] == ["Иван"]


def test_excluded_word_is_not_an_anchor():
    # без имени рядом фамилия не заменяется, а исключённое имя опорой не служит
    assert anonymize_names("Роман Петров", rng(), aggressive="ambiguous", exclude=["Роман"]) == (
        "Роман Петров"
    )


def test_exclude_validation():
    with pytest.raises(TypeError):
        Anonymizer(exclude=[1])


# --- inflect -----------------------------------------------------------------------------


def test_inflect_first_names():
    assert inflect("Павел", "datv") == "Павлу"
    assert inflect("Анна", "ablt") == "Анной"
    assert inflect("Нинель", "gent", gender="f") == "Нинели"
    assert inflect("Мэри", "datv") == "Мэри"


def test_inflect_patronymics_and_surnames():
    assert inflect("Петрович", "datv", kind="patronymic") == "Петровичу"
    assert inflect("Петрович", "ablt", kind="patronymic", gender="f") == "Петровной"
    assert inflect("Петрова", "ablt", kind="surname") == "Петровой"
    assert inflect("Петров", "datv", kind="surname", gender="f") == "Петровой"
    assert inflect("Достоевский", "gent", kind="surname", gender="f") == "Достоевской"
    assert inflect("Шевченко", "gent", kind="surname") == "Шевченко"


def test_inflect_passthrough_and_validation():
    assert inflect("И. И.", None, kind="initials") == "И. И."
    assert inflect("John", "datv") == "John"
    with pytest.raises(ValueError):
        inflect("Павел", "dative")
    with pytest.raises(ValueError):
        inflect("Павел", "datv", kind="nickname")
    with pytest.raises(ValueError):
        inflect("Павел", "datv", gender="x")


def test_inflect_in_custom_replace():
    fakes = {"Иван": "Павел", "Мария": "Нинель"}
    result = anonymize_names(
        "Позвони Ивану и Марии",
        kinds="first",
        replace=lambda e: inflect(fakes[e.normal_form], e.case, gender=e.gender),
    )
    assert result == "Позвони Павлу и Нинели"


def test_declension_respects_gender():
    assert declension("Нинель", "f")["gent"] == "Нинели"


# --- pools -------------------------------------------------------------------------------

POOLS = {
    "first_m": ["Акакий", "Jack"],
    "first_f": ["Нинель"],
    "patronymic": ["Тихонович"],
    "surname": ["Пушкин", "Вяземская"],
}


def test_pools_are_used_and_declined():
    text = "Позвони Ивану Сергеевичу Петрову и Марии Ивановне Достоевской"
    result = anonymize_names(text, rng(), pools=POOLS)
    assert result == "Позвони Акакию Тихоновичу Пушкину и Нинели Тихоновне Вяземской"


def test_pools_split_by_language():
    result = anonymize_names("John и Иван", rng(), languages=("ru", "en"), pools=POOLS)
    assert result == "Jack и Акакий"
    # английских женских имён в pools нет — остаётся стандартный пул
    assert anonymize_names("Mary", rng(), languages="en", pools=POOLS) != "Mary"


def test_pool_of_one_surname_type_serves_both():
    result = anonymize_names("Иван Достоевский", rng(), pools={"surname": ["Пушкин"]})
    assert result.endswith(" Пушкин")


@pytest.mark.parametrize(
    "pools",
    [
        {"nickname": ["Акакий"]},
        {"first_m": []},
        {"first_m": ["акакий"]},
        {"patronymic": ["Тихоновичу"]},
        {"patronymic": ["Tikhonovich"]},
        {"surname": ["Шевченко"]},
        {"surname": ["Пушкину"]},
    ],
)
def test_pools_validation(pools):
    with pytest.raises(ValueError):
        Anonymizer(pools=pools)


def test_custom_pool_exhaustion_warns_in_consistent_mode():
    with pytest.warns(RuntimeWarning):
        anonymize_names_consistent("Иван, Пётр и Олег", rng(), pools={"first_m": ["Акакий"]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        anonymize_names("Иван, Пётр и Олег", rng(), pools={"first_m": ["Акакий"]})


# --- коллизии в consistent ---------------------------------------------------------------


def test_consistent_many_names_stay_distinct():
    names = [n for n, g in load().genders.items() if g == "m"][:300]
    anon = Anonymizer(rng=rng(), consistent=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fakes = [anon.anonymize_detailed(f"{n} Сергеевич Петров").replacements for n in names]
    first = [r[0].replacement for r in fakes]
    assert len(set(first)) == len(names)
    assert all(fake != name for fake, name in zip(first, names))


def test_consistent_many_surnames_and_patronymics_stay_distinct():
    stems = ["Абрам", "Богдан", "Вадим", "Глеб", "Давид", "Ефим", "Захар", "Игнат", "Карп",
             "Лукьян", "Марат", "Назар", "Остап", "Платон", "Родион", "Савват", "Тарас",
             "Устин", "Фрол", "Харитон", "Эмиль", "Ян", "Арсен", "Булат", "Гордей", "Демид",
             "Елисей", "Жан", "Зиновий", "Илларион", "Касьян", "Лавр", "Мирон", "Нестор"]
    anon = Anonymizer(rng=rng(), consistent=True)
    texts = [f"Иван {s}ович {s}ов" for s in stems]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        results = [anon.anonymize(t).split() for t in texts]
    assert len({r[1] for r in results}) == len(stems)
    assert len({r[2] for r in results}) == len(stems)


# --- состояние consistent ----------------------------------------------------------------


def test_export_and_load_state_through_json():
    anon = Anonymizer(rng=rng(), consistent=True)
    before = anon.anonymize("Иван Сергеевич Петров и А. С. Пушкин")
    state = json.loads(json.dumps(anon.export_state(), ensure_ascii=False))

    restored = Anonymizer(rng=rng(42), consistent=True)
    restored.load_state(state)
    assert restored.anonymize("Иван Сергеевич Петров и А. С. Пушкин") == before
    assert restored.export_state() == anon.export_state()


def test_load_state_validation():
    with pytest.raises(ValueError):
        Anonymizer().load_state(Anonymizer(consistent=True).export_state())
    anon = Anonymizer(consistent=True)
    for bad in ({}, {"version": 99}, {"version": 1, "mapping": 5, "used": []},
                {"version": 1, "mapping": [[["first", "Иван", "m"], 1]], "used": []}):
        with pytest.raises(ValueError):
            anon.load_state(bad)


def test_consistent_is_thread_safe():
    anon = Anonymizer(consistent=True)
    names = ["Иван", "Пётр", "Олег", "Мария", "Анна", "Ольга"] * 50
    results = {}

    def work(index, name):
        results[index] = (name, anon.anonymize(name))

    threads = [threading.Thread(target=work, args=item) for item in enumerate(names)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    mapping = {}
    for name, fake in results.values():
        assert mapping.setdefault(name, fake) == fake
    assert len(set(mapping.values())) == len(mapping)
