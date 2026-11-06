"""Публичный API для встраивания: find_names, replace, Anonymizer."""

import random

import pytest

from ru_name_anonymizer import (
    Anonymizer,
    NameEntity,
    anonymize_names,
    anonymize_names_consistent,
    find_names,
)

TEXT = "Позвони Александру Сергеевичу Петрову и Анне Ивановне Достоевской."


def rng(seed=0):
    return random.Random(seed)


def test_find_names_positions_and_metadata():
    entities = find_names(TEXT)
    assert [e.text for e in entities] == [
        "Александру", "Сергеевичу", "Петрову", "Анне", "Ивановне", "Достоевской",
    ]
    for e in entities:
        assert TEXT[e.start : e.end] == e.text
    first, patr, surn = entities[:3]
    assert first == NameEntity(8, 18, "Александру", "first", "Александр", "m", "datv", "ru")
    assert (patr.kind, patr.normal_form, patr.case) == ("patronymic", "Сергеевич", "datv")
    assert (surn.kind, surn.normal_form, surn.gender) == ("surname", "Петров", "m")
    assert entities[5].normal_form == "Достоевская"
    assert entities[5].gender == "f"


def test_find_names_matches_what_anonymize_replaces():
    text = "Пушкин написал. А.С. Пушкин написал. Света не было. John Smith и White House."
    for kwargs in ({}, {"aggressive": True}, {"languages": ("ru", "en")}, {"kinds": "surname"}):
        found = find_names(text, **kwargs)
        result = Anonymizer(rng=rng(), **kwargs).anonymize_detailed(text)
        assert [r.entity for r in result.replacements] == found


def test_find_names_empty_and_without_names():
    assert find_names("") == []
    assert find_names("обычный текст без имён") == []


def test_find_names_respects_kinds():
    assert {e.kind for e in find_names(TEXT, kinds="patronymic")} == {"patronymic"}


def test_find_names_initials_and_english():
    entities = find_names("И. И. Иванов и J. K. Smith", languages=("ru", "en"))
    kinds = [(e.text, e.kind, e.language) for e in entities]
    assert ("И. И.", "initials", "ru") in kinds
    assert ("Smith", "surname", "en") in kinds
    assert all(e.case is None for e in entities if e.kind == "initials")


def test_replace_placeholder():
    result = anonymize_names(TEXT, replace=lambda e: f"[{e.kind}]")
    assert result == (
        "Позвони [first] [patronymic] [surname] и [first] [patronymic] [surname]."
    )


def test_replace_none_falls_back_to_default():
    result = anonymize_names(
        TEXT, rng(), replace=lambda e: "[ФАМИЛИЯ]" if e.kind == "surname" else None
    )
    assert result.count("[ФАМИЛИЯ]") == 2
    assert "Александру" not in result and "Анне" not in result


def test_replace_result_is_not_case_adjusted():
    assert anonymize_names("дима пришёл", aggressive=True, replace=lambda e: "[X]") == "[X] пришёл"


def test_replace_bad_return_type():
    with pytest.raises(TypeError):
        anonymize_names(TEXT, replace=lambda e: 42)


def test_consistent_function_accepts_replace():
    result = anonymize_names_consistent(TEXT, replace=lambda e: e.normal_form.upper())
    assert "АЛЕКСАНДР" in result


def test_anonymizer_consistent_across_calls():
    anon = Anonymizer(rng=rng(), consistent=True)
    first = anon.anonymize("Иван пришёл.")
    second = anon.anonymize("Иван ушёл.")
    assert first.split()[0] == second.split()[0] != "Иван"
    # падеж свой, а человек тот же
    third = anon.anonymize("Ивана нет.")
    assert third.split()[0].startswith(first.split()[0])


def test_anonymizer_reset_forgets_mapping():
    picks = set()
    anon = Anonymizer(rng=rng(3), consistent=True)
    for _ in range(10):
        picks.add(anon.anonymize("Иван").strip())
        anon.reset()
    assert len(picks) > 1


def test_anonymizer_not_consistent_by_default():
    anon = Anonymizer(rng=rng())
    picks = {anon.anonymize("Иван") for _ in range(20)}
    assert len(picks) > 1


def test_anonymize_detailed_mapping():
    result = Anonymizer(rng=rng()).anonymize_detailed("Встретил Ольгу Петрову")
    assert [r.entity.text for r in result.replacements] == ["Ольгу", "Петрову"]
    rebuilt = "Встретил " + " ".join(r.replacement for r in result.replacements)
    assert rebuilt == result.text


def test_anonymize_detailed_without_names():
    result = Anonymizer().anonymize_detailed("нет имён")
    assert result.text == "нет имён" and result.replacements == []


def test_anonymizer_same_as_function_for_same_seed():
    text = "Позвони Ивану Петровичу Сидорову, а потом Марии."
    assert Anonymizer(rng=rng(5)).anonymize(text) == anonymize_names(text, rng(5))


def test_anonymizer_settings_are_validated_and_exposed():
    anon = Anonymizer(languages="en", kinds=("surname", "first"), aggressive=True)
    assert anon.languages == ("en",)
    assert anon.kinds == ("first", "surname")
    assert anon.aggressive and not anon.consistent
    with pytest.raises(ValueError):
        Anonymizer(languages="de")
    with pytest.raises(ValueError):
        Anonymizer(kinds="nickname")
