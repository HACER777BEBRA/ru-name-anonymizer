"""Регрессии по итогам ревью: утечки имён и ложные замены."""

import random

import pytest

from ru_name_anonymizer import anonymize_names, anonymize_names_consistent


def rng(seed=0):
    return random.Random(seed)


@pytest.mark.parametrize("seed", range(10))
def test_name_with_hyphen_particle_aggressive(seed):
    result = anonymize_names("Мария-то пришла, Ивану-ка скажи", rng(seed), aggressive=True)
    assert "Мария" not in result and "Ивану" not in result
    assert "-то пришла" in result and "-ка скажи" in result


@pytest.mark.parametrize("seed", range(10))
def test_initials_glued_to_surname(seed):
    result = anonymize_names("А.С.Пушкин написал", rng(seed))
    assert "Пушкин" not in result and not result.startswith("А.С.")


@pytest.mark.parametrize("seed", range(10))
def test_latin_initials_with_nbsp(seed):
    result = anonymize_names("J. K. Smith wrote", rng(seed), languages="en")
    assert not result.startswith("J. K.") and " " in result


def test_two_letter_initials_alone_replaced_single_kept():
    assert not anonymize_names("Подписал А. С. сам", rng()).startswith("Подписал А. С.")
    text = "Витамин С. Пункт Б."
    assert anonymize_names(text, rng(), kinds="initials") == text


@pytest.mark.parametrize(
    "text", ["Нате, держите.", "Света не было.", "«Вера в победу» — лозунг"]
)
def test_common_word_at_sentence_start_kept(text):
    assert anonymize_names(text, rng()) == text


def test_common_name_confirmed_elsewhere_replaced_everywhere():
    for seed in range(10):
        result = anonymize_names("Никита написал Свете. Света ответила.", rng(seed))
        assert "Свет" not in result


@pytest.mark.parametrize("text", ["Технический директор", "Российский рынок", "Советский союз"])
def test_adjectives_not_surnames(text):
    assert anonymize_names(text, rng(), kinds="surname") == text
    assert anonymize_names(text, rng(), aggressive=True) == text


def test_english_common_word_surname_alone_kept():
    text = "The White House and Young people"
    assert anonymize_names(text, rng(), languages="en", aggressive=True) == text
    result = anonymize_names("Emma White came", rng(), languages="en")
    assert "White" not in result and "Emma" not in result


def test_initials_consistent_after_refactor():
    result = anonymize_names_consistent("Иванов И.И. и Петров И.И.", rng(3)).split()
    assert result[1] == result[4] != "И.И."
