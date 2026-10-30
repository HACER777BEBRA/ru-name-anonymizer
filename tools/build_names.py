"""Собирает src/ru_name_anonymizer/names.tsv.gz из словаря pymorphy2 (OpenCorpora).

Запуск: python tools/build_names.py  (нужен pymorphy2==0.9.1, pymorphy2-dicts-ru, setuptools<81)
"""

import gzip
import inspect
import sys
from pathlib import Path

# pymorphy2 0.9.1 вызывает удалённый inspect.getargspec
inspect.getargspec = lambda f: inspect.getfullargspec(f)[:4]

import pymorphy2  # noqa: E402

MIN_NAME_WEIGHT = 0.5
CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
OUT = Path(__file__).resolve().parent.parent / "src" / "ru_name_anonymizer" / "names.tsv.gz"


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

    rows = []
    for lemma, gender in sorted(lemmas.items()):
        if name_weight(morph, lemma) < MIN_NAME_WEIGHT:
            continue
        parse = next(p for p in morph.parse(lemma) if p.normal_form == lemma)
        for case in CASES:
            inflected = parse.inflect({"sing", case})
            if not inflected:
                continue
            form = inflected.word
            if name_weight(morph, form) < MIN_NAME_WEIGHT:
                continue
            rows.append((lemma.capitalize(), gender, case, form.capitalize()))

    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as fh:
        for row in rows:
            fh.write("\t".join(row) + "\n")
    print(f"lemmas={len({r[0] for r in rows})} forms={len(rows)} -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
