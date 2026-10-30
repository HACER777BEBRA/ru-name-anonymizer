"""Собирает src/ru_name_anonymizer/names.txt из словаря pymorphy2 (OpenCorpora).

Запуск: python tools/build_names.py  (нужен pymorphy2==0.9.1, pymorphy2-dicts-ru, setuptools<81)
"""

import inspect
import sys
from pathlib import Path

# pymorphy2 0.9.1 вызывает удалённый inspect.getargspec
inspect.getargspec = lambda f: inspect.getfullargspec(f)[:4]

import pymorphy2  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
from ru_name_anonymizer import dictionary  # noqa: E402

MIN_NAME_WEIGHT = 0.5
CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
OUT = SRC / "ru_name_anonymizer" / "names.txt"
HEADER = (
    "# Имена из OpenCorpora (CC BY-SA 3.0), собрано tools/build_names.py.\n"
    "# лемма род [родительный дательный винительный творительный предложный]\n"
    "# Падежи указаны только там, где они не выводятся правилами из dictionary.py; - = формы нет.\n"
)


def name_weight(morph, word):
    return sum(p.score for p in morph.parse(word) if "Name" in p.tag)


def main() -> None:
    morph = pymorphy2.MorphAnalyzer()
    lemmas = {}
    for word, tag, norm, _, _ in morph.dictionary.iter_known_words():
        if word == norm and "Name" in tag and "NOUN" in tag and "sing" in tag:
            gender = "c" if "ms-f" in tag else "m" if "masc" in tag else "f" if "femn" in tag else None
            if gender and len(word) >= 3 and word.isalpha():
                lemmas[word] = gender

    entries = {}
    for lemma, gender in sorted(lemmas.items()):
        if name_weight(morph, lemma) < MIN_NAME_WEIGHT:
            continue
        parse = next(p for p in morph.parse(lemma) if p.normal_form == lemma)
        forms = []
        for case in CASES[1:]:
            inflected = parse.inflect({"sing", case})
            form = inflected.word.capitalize() if inflected else None
            if form and name_weight(morph, form) < MIN_NAME_WEIGHT:
                form = None
            forms.append(form)
        entries[lemma.capitalize()] = (gender, tuple(forms))

    lines = [HEADER.rstrip("\n")]
    for lemma, (gender, forms) in entries.items():
        if dictionary.regular_forms(lemma, gender) == forms:
            lines.append(f"{lemma} {gender}")
        else:
            lines.append(f"{lemma} {gender} " + " ".join(f or "-" for f in forms))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    dictionary.load.cache_clear()
    for lemma, (_, forms) in entries.items():
        table = dictionary.declension(lemma)
        assert tuple(table.get(c) for c in CASES[1:]) == forms, lemma
    exceptions = sum(1 for line in lines[3:] if len(line.split(" ")) > 2)
    print(f"lemmas={len(entries)} exceptions={exceptions} -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
