"""Children's reading levels from published reports, and the test passages they are measured on.

research/difficulty/reading_levels.csv holds one row per published figure: the per cent of
children meeting a reading standard on a Grade 2 text (UNICEF MICS6 Foundational Learning Skills,
or a citizen-led assessment: Uwezo, ASER, the PAL Network; for South Africa, which has none, PIRLS
2021's Grade 4 passages), with the report, page and table it comes from. research/difficulty/yardsticks.csv lists each test passage and its scores; the
passages themselves are kept out of git, in build/difficulty/yardsticks/<id>.txt.

A figure is for books in the language children were tested in, whatever language lessons are
taught in (Lee, 2026-10-20), and in any language, not only English (Lee, 2026-10-27). It is usable
when all children were tested in its one language; when it pools several languages (any-language:
reading in any of them, a ceiling on reading in each); or when it is the pass rate among the
children given the story in its language (english-tested / language-tested: MICS microdata,
scripts/mics_reading.py, Lee 2026-10-21; PIRLS). Figures are chosen per country and book
language. MICS, a national probability sample, leads where there are several.
"""
from __future__ import annotations

import csv
from pathlib import Path

from tgs.difficulty.measures import score_text, word_tokens

READING_COLUMNS = ["iso3", "source", "year", "grade", "age", "share", "language",
                   "english_instruction", "all_tested_in_language", "yardstick", "report", "page",
                   "table", "note"]
# optional: a short caveat the page prints beside the figure ("rural children only"); the
# figure's scope: "all-english" (every child tested in English), "any-language" (reading in
# English or a local language: a looser ceiling), "english-tested" (MICS microdata: the share
# passing among the children given the English story; for PIRLS, the share of children tested
# in English reaching the Low benchmark; "language-tested" the same for another language), or
# "english-panel", "subnational" or "superseded" (not used); and n_tested, the children a
# "-tested" share is taken over; se, the share's standard error in points where the report gives
# one; secondary, "yes" for a figure that makes only a secondary line (an EGRA from a purposive or
# programme sample, or whose passage is a stand-in). english_instruction is recorded, not required.
YARDSTICK_COLUMNS = ["id", "source", "grade", "language", "citation", "words", "outside_1000",
                     "outside_2000", "fk", "spache", "sentence_words"]
# PIRLS: South Africa (Lee, 2026-10-27). EGRA last: used only where no survey above has a
# figure (the EGRA rule, Lee 2026-11-01; research/difficulty/EGRA_SOURCES.md)
SOURCES = ("MICS6", "Uwezo", "ASER", "PAL", "PIRLS", "EGRA")
TARGET_GRADE = 3       # the grade whose figure stands for a country (closest to it)
MIN_TESTED = 50        # children given the story a "-tested" share needs
NOT_USED = ("english-panel", "subnational", "superseded")
TESTED = ("english-tested", "language-tested")
# language names as reading_levels.csv and yardsticks.csv write them -> wordfreq's codes
LANGUAGE_CODES = {
    "english": "en", "bangla": "bn", "bengali": "bn", "kiswahili": "sw", "swahili": "sw",
    "hindi": "hi", "marathi": "mr", "urdu": "ur", "nepali": "ne", "arabic": "ar", "tamil": "ta",
    "sinhala": "si", "telugu": "te", "kannada": "kn", "gujarati": "gu", "punjabi": "pa",
    "sindhi": "sd", "odia": "or", "assamese": "as", "malayalam": "ml", "french": "fr",
    "portuguese": "pt", "spanish": "es", "hausa": "ha", "igbo": "ig", "yoruba": "yo",
    "amharic": "am", "oromo": "om", "chichewa": "ny", "sesotho": "st", "shona": "sn",
    "ndebele": "nd", "kiribati": "gil", "khmer": "km", "kinyarwanda": "rw", "luganda": "lg",
}


LANGUAGE_NAMES = {"en": "English", "bn": "Bangla", "sw": "Kiswahili", "hi": "Hindi", "ur": "Urdu",
                  "ar": "Arabic", "ta": "Tamil", "fr": "French", "pt": "Portuguese",
                  "es": "Spanish"}


def languages(row: dict) -> tuple[str, ...]:
    """The codes of the languages a figure or passage was in, in order ("English, Hausa, Igbo or
    Yoruba" -> en, ha, ig, yo). A name not in LANGUAGE_CODES is kept, lower-cased: no book has
    it, so no book is set against it."""
    import re

    names = [n.strip().lower() for n in re.split(r",|\bor\b|\band\b|/|\(|\)", row["language"])]
    out = []
    for n in names:
        if n and n not in ("first additional language",):
            code = LANGUAGE_CODES.get(n, n)
            if code not in out:
                out.append(code)
    return tuple(out)


def yardstick_language(row: dict) -> str:
    """A passage's language code (its first language)."""
    return languages(row)[0]


def _int(value: str) -> int | None:
    return int(value) if value.strip() else None


def _grade(row: dict) -> float | None:
    """The grade attended, or for an age band the grade it corresponds to (age 6 is Grade 1)."""
    if row["grade"] is not None:
        return row["grade"]
    if row["age"]:
        ages = [int(a) for a in row["age"].split("-")]
        return sum(ages) / len(ages) - 6
    return None


def load_reading(path: Path) -> list[dict]:
    """The reading figures, typed. A ValueError names the file and the row (the header is row 1)
    for a missing column, an unknown source or a share outside 0-100."""
    path = Path(path)
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in READING_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: no column {', '.join(missing)}")
        out = []
        for n, r in enumerate(reader, start=2):
            where = f"{path}, row {n}"
            if r["source"] not in SOURCES:
                raise ValueError(f"{where}: source {r['source']!r} (use one of {', '.join(SOURCES)})")
            try:
                share = float(r["share"])
                year, grade = int(r["year"]), _int(r["grade"])
            except ValueError as e:
                raise ValueError(f"{where}: {e}") from e
            if not 0 <= share <= 100:
                raise ValueError(f"{where}: share {share} is not a per cent")
            out.append({**r, "iso3": r["iso3"].strip().upper(), "year": year, "grade": grade,
                        "share": share})
    return out


def usable(row: dict) -> bool:
    """Every child tested in the figure's one language, in any language (Lee, 2026-10-27). Whether
    it is also the language of instruction (`english_instruction`) is recorded but not required:
    Kenyan children read English textbooks from Grade 1 and are taught in English only from
    Grade 4 (Lee, 2026-10-20)."""
    scope = (row.get("scope") or "").strip().lower()
    if scope in NOT_USED:
        return False
    langs = languages(row)
    if scope in TESTED:
        # MICS microdata (scripts/mics_reading.py): the pass rate among children given the
        # story in this language, a ceiling if those not given it (mostly taught in another
        # language) read it no better (Lee, 2026-10-21); over at least MIN_TESTED children
        n = (row.get("n_tested") or "").strip()
        return len(langs) == 1 and n.isdigit() and int(n) >= MIN_TESTED
    if len(langs) == 1 and row["all_tested_in_language"].strip().lower() == "yes":
        return True
    # Reading in any of several languages (school language first, home language on failure) is
    # at least reading in each, so the share is still a ceiling for books in each of them
    # (2026-10-21). Not a one-language panel that counts children never given that story as
    # failing (Zimbabwe), which understates reading, nor one province (MICS Punjab).
    return len(langs) > 1 and scope == "any-language"


def _best(rows: list[dict]) -> dict:
    """Among one source's rows: the grade nearest TARGET_GRADE, then the latest year."""
    def key(r):
        g = _grade(r)
        return (abs(g - TARGET_GRADE) if g is not None else 99, -r["year"])
    return min(rows, key=key)


def choose(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """Per country and book language, among usable rows: {"main": row, "by_grade": {grade: row},
    "other": row | None}. A figure pooling several languages counts for each; where a country
    has a figure in that language alone too, the pooled one is left out. MICS6 is the main figure
    where there is one; otherwise the first source in SOURCES order. "by_grade" holds the main
    source's figures from the main row's year, one per grade (an age-band row has no grade and
    is only "main"). "other" is the best row of another source, if any."""
    candidates: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if usable(r):
            for lang in languages(r):
                candidates.setdefault((r["iso3"], lang), []).append(r)
    by: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for key, rs in candidates.items():
        alone = [r for r in rs if len(languages(r)) == 1]
        for r in alone or rs:
            by.setdefault(key, {}).setdefault(r["source"], []).append(r)
    out = {}
    for key, sources in by.items():
        ranked = [s for s in SOURCES if s in sources]
        main = _best(sources[ranked[0]])
        by_grade = {r["grade"]: r for r in sorted(sources[ranked[0]], key=lambda r: r["year"])
                    if r["year"] == main["year"] and r["grade"] is not None}
        out[key] = {"main": main, "by_grade": by_grade,
                     "other": _best(sources[ranked[1]]) if len(ranked) > 1 else None}
    return out


def load_yardsticks(path: Path) -> list[dict]:
    """The test passages and their scores (numbers as numbers; blank when not scored yet)."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("words",):
            r[k] = int(r[k]) if r[k] else None
        for k in ("outside_1000", "outside_2000", "fk", "spache", "sentence_words"):
            r[k] = float(r[k]) if r.get(k) else None
    return rows


def score_yardsticks(folder: Path, path: Path) -> None:
    """Score each passage in `folder` (<id>.txt) as one passage and write its measures into
    `path`. A passage whose file is missing keeps blank scores."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        f = Path(folder) / f"{r['id']}.txt"
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        s = score_text(text, whole=True, lang=yardstick_language(r))
        lang = yardstick_language(r)
        r.update(words=len(word_tokens(text, lang)), outside_1000=round(s["outside_1000"], 2),
                 outside_2000=round(s["outside_2000"], 2),
                 fk="" if s["fk"] is None else round(s["fk"], 2),
                 spache="" if s["spache"] is None else round(s["spache"], 2),
                 sentence_words="" if s["sentence_words"] is None else round(float(s["sentence_words"]), 1))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=YARDSTICK_COLUMNS)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in YARDSTICK_COLUMNS} for r in rows)
