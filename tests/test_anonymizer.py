import random

import pytest

from ru_name_anonymizer import anonymize_names


@pytest.fixture
def rng():
    return random.Random(0)


def test_empty_and_plain_text_unchanged(rng):
    assert anonymize_names("", rng) == ""
    text = "Привет! Москва большая, Мир прекрасен."
    assert anonymize_names(text, rng) == text


@pytest.mark.parametrize(
    "text, originals",
    [
        ("Меня зовут Дмитрий", ["Дмитрий"]),
        ("Позвони Диме вечером", ["Диме"]),
        ("Это письмо для Анны", ["Анны"]),
        ("Я видел Сергея", ["Сергея"]),
        ("Мария Ивановна Кузнецова", ["Мария", "Ивановна", "Кузнецова"]),
        ("Позвони Александру Сергеевичу", ["Александру", "Сергеевичу"]),
    ],
)
def test_names_are_replaced(text, originals, rng):
    result = anonymize_names(text, rng)
    for original in originals:
        assert original not in result


def test_case_and_gender_are_kept(rng):
    result = anonymize_names("Позвони Александру Сергеевичу Петрову", rng).split()
    assert result[1].endswith("у") and result[2].endswith("ичу") and result[3].endswith("у")
    result = anonymize_names("Письмо Марии Ивановне Кузнецовой", rng).split()
    assert result[2].endswith("не") and result[3].endswith("ой")


def test_surname_alone_is_kept(rng):
    assert anonymize_names("Это сказал Иванов", rng) == "Это сказал Иванов"


def test_original_values_are_not_reused():
    for seed in range(50):
        result = anonymize_names("Иван Иванович Иванов", random.Random(seed))
        assert (
            "Иван " not in result + " "
            and "Иванович" not in result
            and "Иванов" not in result.split()[-1:]
        )


def test_other_text_is_preserved(rng):
    result = anonymize_names("Привет, Дмитрий! Как дела?", rng)
    assert result.startswith("Привет, ") and result.endswith("! Как дела?")
