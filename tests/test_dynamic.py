"""Динамические локали: ники и другие термины, известные во время работы."""

import json
import random
import threading

import pytest

from ru_name_anonymizer import (
    Anonymizer,
    DynamicLocale,
    anonymize_names,
    available_dynamic,
    find_names,
    register_dynamic_locale,
)
from ru_name_anonymizer.dynamic import pools


def rng(seed=0):
    return random.Random(seed)


def nicks(result):
    return [r.replacement for r in result.replacements if r.entity.kind == "nickname"]


def test_builtin_locales():
    assert {"tg", "nick"} <= set(available_dynamic())


def test_telegram_nick_replaced_everywhere_with_one_value():
    anon = Anonymizer(rng=rng(), dynamic={"tg": ["HACER777BEBRA"]})
    text = "HACER777BEBRA, ты сегодня прекрасен! Спасибо HACER777BEBRA'у и @hacer777bebra-у."
    result = anon.anonymize_detailed(text)
    values = nicks(result)
    assert len(values) == 3 and len(set(values)) == 1
    fake = values[0]
    assert fake[:-4] in pools.EN and fake[-4:] in pools.YEARS
    assert result.text == (
        f"{fake}, ты сегодня прекрасен! Спасибо {fake}'у и @{fake}-у."
    )
    # между вызовами — та же замена, даже без consistent
    assert anon.anonymize("пиши HACER777BEBRA") == f"пиши {fake}"


def test_boundaries():
    anon = Anonymizer(rng=rng(), kinds="nickname", dynamic={"tg": ["HACER777BEBRA"]})
    for text in ("HACER777BEBRA2 тут", "xHACER777BEBRA", "HACER777BEBRA_x"):
        assert anon.anonymize(text) == text
    assert anon.anonymize("(HACER777BEBRA)") != "(HACER777BEBRA)"


def test_aliases_share_replacement_and_case_rule():
    anon = Anonymizer(rng=rng(), kinds="nickname")
    anon.add_terms("tg", "@Zik_2005", aliases=["Zik"])
    text = "Zik wants more. Zik's request, ZIK, zik, Zikov, @zik_2005"
    result = anon.anonymize_detailed(text)
    found = [r.entity.text for r in result.replacements]
    assert found == ["Zik", "Zik", "ZIK", "zik_2005"]  # «zik» строчными и «Zikov» не трогаем
    assert len(set(nicks(result))) == 1
    assert {r.entity.normal_form for r in result.replacements} == {"Zik_2005"}
    assert anon.terms() == {"tg": {"Zik_2005": ["Zik"]}}


def test_any_case_alias():
    anon = Anonymizer(rng=rng(), kinds="nickname", aggressive="any_case")
    anon.add_terms("tg", "Zik_2005", aliases="Zik")
    assert [e.text for e in anon.find("zik и Zik")] == ["zik", "Zik"]


def test_nick_locale_picks_alphabet_and_style():
    anon = Anonymizer(rng=rng(), kinds="nickname", dynamic={"nick": ["Бебрыч", "xXSniperXx"]})
    ru, en = (r.replacement for r in anon.anonymize_detailed("Бебрыч и xXSniperXx").replacements)
    assert ru[:-4] in pools.RU and en[:-4] in pools.EN
    lower = Anonymizer(rng=rng(), dynamic={"nick": ["lowernick"]}).anonymize("lowernick")
    assert lower == lower.lower()


def test_explicit_replacement_and_mapping_spec():
    anon = Anonymizer(dynamic={
        "nick": {"Бебрыч": "кабачок2008"},
        "tg": {"Zik_2005": {"aliases": ["Zik"], "replacement": "Гость"}},
    })
    assert anon.anonymize("Бебрыч и Zik") == "кабачок2008 и Гость"


def test_static_and_dynamic_together():
    anon = Anonymizer(rng=rng(), dynamic={"nick": ["Дима"]})
    result = anon.anonymize_detailed("Дима и Диме написал Петров")
    kinds = [(r.entity.text, r.entity.kind) for r in result.replacements]
    assert kinds[0] == ("Дима", "nickname")
    assert ("Диме", "first") in kinds  # другие формы ловит статическая локаль
    # только ники
    only = Anonymizer(rng=rng(), kinds="nickname", dynamic={"nick": ["Дима"]})
    assert [e.kind for e in only.find("Дима и Диме написал Петров")] == ["nickname"]


def test_find_matches_anonymize_and_entity_fields():
    text = "Zik wants it, Иван Петров тоже"
    kwargs = {"dynamic": {"tg": {"Zik_2005": {"aliases": ["Zik"]}}}}
    found = find_names(text, **kwargs)
    assert found[0].kind == "nickname"
    assert found[0].language == "tg" and found[0].case is None and found[0].gender == "c"
    result = Anonymizer(rng=rng(), **kwargs).anonymize_detailed(text)
    assert [r.entity for r in result.replacements] == found


def test_auto_detect():
    text = "vasya_pupkin написал, @Vasya_Pupkin ответь. Почта a@gmail.com, @abc"
    assert Anonymizer(kinds="nickname").anonymize(text) == text  # по умолчанию выключен
    anon = Anonymizer(rng=rng(), kinds="nickname", auto_detect=True)
    assert anon.find(text) and anon.terms() == {}  # find не меняет словарь
    out = anon.anonymize(text)
    assert "pupkin" not in out.lower() and "a@gmail.com" in out and "@abc" in out
    assert anon.terms() == {"tg": {"Vasya_Pupkin": []}}
    assert anon.auto_detect == ("tg",)
    with pytest.raises(ValueError):
        Anonymizer(auto_detect="nick")  # у nick нет шаблона


def test_remove_terms():
    anon = Anonymizer(dynamic={"tg": {"Zik_2005": {"aliases": ["Zik", "Зик"]}}})
    anon.remove_terms("tg", "Зик")
    assert anon.terms() == {"tg": {"Zik_2005": ["Zik"]}}
    anon.remove_terms("tg", ["@zik_2005", "unknown_user"])
    assert anon.terms() == {}
    assert anon.anonymize("Zik") == "Zik"


def test_validation():
    anon = Anonymizer()
    with pytest.raises(ValueError):
        anon.add_terms("tg", "abc")  # короче 5 символов
    with pytest.raises(ValueError):
        anon.add_terms("tg", "имя_по_русски")
    with pytest.raises(ValueError):
        anon.add_terms("xx", "something")
    with pytest.raises(ValueError):
        anon.add_terms("tg", ["user_one", "user_two"], aliases=["X"])
    anon.add_terms("tg", "user_one", aliases=["Uno"])
    with pytest.raises(ValueError):  # одна строка — один человек
        anon.add_terms("tg", "user_two", aliases=["uno"])
    with pytest.raises(ValueError):  # пачка добавляется целиком или никак
        anon.add_terms("nick", ["Новый", "x"])
    assert "nick" not in anon.terms()
    anon.add_terms("tg", "USER_ONE", aliases=["Один"])  # повторно — дописывает алиасы
    assert anon.terms() == {"tg": {"user_one": ["Uno", "Один"]}}


def test_exclude_and_replace():
    dyn = {"tg": {"Zik_2005": {"aliases": ["Zik"]}}}
    assert anonymize_names("Zik", dynamic=dyn, exclude=["zik"]) == "Zik"
    out = anonymize_names(
        "Zik и Иван", dynamic=dyn, replace=lambda e: "[USER]" if e.kind == "nickname" else None
    )
    assert out.startswith("[USER] и ") and "Иван" not in out


def test_state_roundtrip_and_reset():
    dyn = {"tg": {"Zik_2005": {"aliases": ["Zik"]}}}
    anon = Anonymizer(rng=rng(), consistent=True, dynamic=dyn)
    before = anon.anonymize("Zik и Иван")
    state = json.loads(json.dumps(anon.export_state(), ensure_ascii=False))
    assert state["version"] == 2

    restored = Anonymizer(rng=rng(9), consistent=True)
    restored.load_state(state)
    assert restored.anonymize("Zik и Иван") == before
    assert restored.export_state() == anon.export_state()

    plain = Anonymizer()  # без consistent словарь терминов тоже загружается
    plain.load_state({**state, "mapping": [], "used": []})
    assert plain.terms() == anon.terms()

    anon.reset()
    assert anon.terms() and anon.export_state()["nicknames"] == []


def test_old_state_version_loads():
    anon = Anonymizer(consistent=True)
    anon.load_state({"version": 1, "mapping": [[["first", "Иван", "m"], "Павел"]], "used": []})
    assert anon.anonymize("Иван").startswith("Павел")


def test_many_nicks_stay_distinct():
    anon = Anonymizer(rng=rng(), kinds="nickname")
    terms = [f"user_{i:04d}" for i in range(400)]  # больше, чем сочетаний основа+год
    anon.add_terms("tg", terms)
    result = anon.anonymize_detailed(" ".join(terms))
    assert len(set(nicks(result))) == len(terms)


def test_custom_dynamic_locale():
    class GameLocale(DynamicLocale):
        code = "game_test"
        detect = r"\[(?P<term>[A-Za-z]{3,})\]"

        def fake(self, term, rng, used):
            return "Player" + str(len(used) + 1)

    register_dynamic_locale(GameLocale(), replace=True)
    anon = Anonymizer(kinds="nickname", auto_detect="game_test")
    out = anon.anonymize("[Steve] убил Steve-а, но не SteveBot")
    assert out == "[Player1] убил Player1-а, но не SteveBot"
    with pytest.raises(ValueError):
        register_dynamic_locale(GameLocale())  # код занят


def test_threads_add_and_anonymize():
    anon = Anonymizer(rng=rng(), kinds="nickname")
    errors = []

    def worker(i):
        try:
            name = f"thread_user_{i}"
            anon.add_terms("tg", name)
            assert name not in anon.anonymize(f"привет {name}")
        except Exception as error:  # pragma: no cover
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(anon.terms()["tg"]) == 20
