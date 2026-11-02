"""Score the national textbooks in scope against each country's reading yardstick.

`measure` writes research/difficulty/books.csv: every national book of Grades 1-6 (all subjects;
Lee, 2026-10-20) in a country with a usable reading figure in the book's language, scored as
passages (tgs.difficulty.measures) and set against that figure's yardstick, the passage its
children are tested on. The site's national books are English; books in another language are
listed in research/difficulty/extra_books.csv, their texts in build/ (Bangladesh's Bangla-medium
books, OCR'd by scripts/ocr_bangla.py; Lee, 2026-10-27). A combined book (chapter files) is its
files' texts joined in order. A line is a country and a language: India's English books and its
Hindi books would be two.
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from tgs.difficulty import measures, reading
from tgs.stereo.books import Texts, national_books

GRADES = range(1, 7)            # Lee, 2026-10-20: Grades 1-6, all subjects
READING = Path("research/difficulty/reading_levels.csv")
YARDSTICKS = Path("research/difficulty/yardsticks.csv")
BOOKS = Path("research/difficulty/books.csv")
EXTRA = Path("research/difficulty/extra_books.csv")
EXTRA_COLUMNS = ["id", "iso3", "country", "grade", "subject_group", "title", "language", "text",
                 "source_url"]
RESULTS = Path("research/difficulty/results.json")
CJ_BOOKS = Path("research/difficulty/cj_books.csv")   # tgs.difficulty.cjrun
MIN_BOOKS = 5          # scored books a country needs for a point (all subjects; Lee, 2026-10-20);
                       # kept as the one minimum-n rule for every chart of these results
MARGIN = 1.0           # points of outside_2000 a book must exceed the story by: the hardest
                       # version of the test, where it has several (Lee, 2026-11-01)
# The ceiling (Lee, 2026-11-01, replacing a 75%-of-books cut-off): the most children who could
# read a book drawn at random from the country's set. A harder book can be read by at most the
# share who pass the test; of a book not harder we know nothing, so all 100%. Its interval draws
# each grade's share of harder books from a Beta posterior (Jeffreys prior) and its pass rate
# from a Beta with the figure's sampling error, where known.
DRAWS = 20000
SEED = 20261101
INTERVAL = (0.05, 0.95)  # a 90% interval
DEFF = 2.0               # design effect for a pass rate's error from the number tested alone
GKM = {"grade3": 16, "grade4": 28}   # Glewwe, Kremer & Moulin (2009), Table 11: median pupils
                                     # who could read the English textbook, Kenya
BOOK_COLUMNS = ["id", "iso3", "language", "grade", "subject_group", "line", "title", "windows",
                "outside_1000", "outside_2000", "fk", "spache", "sentence_words", "harder",
                "measures_disagree"]


def make_texts(root: Path) -> Texts:
    """The scored books' texts, from the search's and the corpus build's caches."""
    return Texts(root / "build" / "search-texts", root / "build" / "corpus" / "cache.sqlite",
                 root / "data" / "corpus" / "books.csv")


@dataclass(frozen=True)
class ExtraBook:
    """A book in another language than the site's (extra_books.csv), as `in_scope` reads one."""
    id: str
    iso3: str
    country: str
    grade: int | None
    subject_group: str
    title: str
    language: str
    text: str                 # its text file, relative to the root (in build/, outside git)


def extra_books(root: Path) -> list[ExtraBook]:
    path = Path(root) / EXTRA
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [ExtraBook(r["id"], r["iso3"], r["country"], int(r["grade"]) if r["grade"] else None,
                          r["subject_group"], r["title"], r["language"], r["text"])
                for r in csv.DictReader(fh)]


def in_scope(book, lines: set[tuple[str, str]], lang: str = "en") -> str | None:
    """"reading" for a language book of Grades 1-6 with a line (a usable figure for its country
    in its language), "other" for another subject at those grades, else None."""
    if (book.iso3, lang) not in lines or book.grade not in GRADES:
        return None
    return "reading" if book.subject_group == "Language" else "other"


def yardsticks_by_line(root: Path) -> dict[tuple[str, str], dict]:
    """(iso3, language) -> {"figure": the main reading row, "by_grade": {grade: row}, "other": row
    | None, "yardstick": its scores}, for the lines whose figure has a passage in that language (a
    figure pooling Bangla and English bounds English books only once there is an English
    passage). A passage that is listed but not scored stops the run."""
    chosen = reading.choose(reading.load_reading(root / READING))
    sticks = {y["id"]: y for y in reading.load_yardsticks(root / YARDSTICKS)}
    out = {}
    for (iso3, lang), c in chosen.items():
        ids = [i.strip() for i in c["main"]["yardstick"].split(";") if i.strip()]
        mine = [i for i in ids if i in sticks and reading.yardstick_language(sticks[i]) == lang]
        if not mine:
            continue
        y = sticks[mine[0]]
        if y["outside_2000"] is None:
            raise ValueError(f"{YARDSTICKS}: no scores for yardstick {y['id']!r} ({iso3}, {lang}); "
                             "run reading.score_yardsticks")
        out[(iso3, lang)] = {"figure": c["main"], "by_grade": c["by_grade"], "other": c["other"],
                             "yardstick": y}
    return out


def grade_figure(grades: list[int], grade: int) -> int | None:
    """The grade whose figure a book of `grade` is set against: the next grade's, else the
    nearest above that, else None. Children in the next grade have all finished the book's
    grade, so a ceiling from them holds wherever in the school year the test was given (Lee,
    2026-11-01; most of these surveys test mid-year)."""
    above = [g for g in grades if g > grade]
    return min(above) if above else None


def _fmt(x: float | None) -> str:
    return "" if x is None else f"{x:.2f}"


def measure(root: Path, out: Path) -> int:
    """Write books.csv for the books in scope; return how many rows it has."""
    root = Path(root)
    lines = yardsticks_by_line(root)
    sticks = reading.load_yardsticks(root / YARDSTICKS)
    texts = make_texts(root)
    todo = [(bf.book, "en", lambda bf=bf: "\n".join(texts.text(f) or "" for f in bf.files))
            for bf in national_books(root)]
    for e in extra_books(root):
        path = root / e.text
        todo.append((e, e.language, lambda path=path: path.read_text(encoding="utf-8")
                     if path.exists() else ""))
    rows = []
    for b, lang, read in todo:
        line = in_scope(b, set(lines), lang)
        if line is None:
            continue
        y = lines[(b.iso3, lang)]["yardstick"]
        s = measures.score_text(read(), lang=lang)
        row = {"id": b.id, "iso3": b.iso3, "language": lang, "grade": b.grade,
               "subject_group": b.subject_group, "line": line, "title": b.title, "windows": 0,
               "harder": "", "measures_disagree": ""}
        if s is not None:
            try:
                sbar = threshold(sticks, y["id"], "sentence_words")
            except ValueError:
                sbar = None
            book = {"outside_2000": s["outside_2000"], "sentence_words": s["sentence_words"]}
            harder = is_harder(book, threshold(sticks, y["id"]), sbar)
            # whether Flesch-Kincaid ranks the book against the story as rare words alone do
            words = is_harder(book, threshold(sticks, y["id"]), sbar, sentences=False)
            disagree = "" if s["fk"] is None or y["fk"] is None else \
                "yes" if (s["fk"] > y["fk"]) != words else "no"
            row.update(windows=s["windows"], outside_1000=_fmt(s["outside_1000"]),
                       outside_2000=_fmt(s["outside_2000"]), fk=_fmt(s["fk"]),
                       spache=_fmt(s["spache"]), sentence_words=_fmt(s["sentence_words"]),
                       harder="yes" if harder else "no",
                       measures_disagree=disagree)
        rows.append(row)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BOOK_COLUMNS)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in BOOK_COLUMNS} for r in rows)
    return len(rows)


def _versions_key(yardstick_id: str) -> str:
    """'aser-pakistan-english-2025-b' -> 'aser-pakistan-english-2025': one round's test versions."""
    return re.sub(r"-[a-z]$", "", yardstick_id)


def threshold(sticks: list[dict], yardstick_id: str, measure: str = "outside_2000") -> float:
    """The `measure` a book must exceed to count as harder: the hardest version of the same
    test (one survey round in one country), plus MARGIN for outside_2000. One easy version cannot
    lower the bar, and a book is never called harder than a version some children were given
    (Lee, 2026-11-01, replacing the story plus the spread between versions)."""
    key = _versions_key(yardstick_id)
    vals = [y[measure] for y in sticks if _versions_key(y["id"]) == key
            and y.get(measure) is not None]
    return max(vals) + (MARGIN if measure == "outside_2000" else 0.0)


def is_harder(book: dict, word_bar: float, sentence_bar: float | None,
              sentences: bool = True) -> bool:
    """A book is harder than the test when more of its words are rare (outside_2000 above
    word_bar) and, with `sentences`, its sentences are longer too (median sentence_words above
    sentence_bar). Lee, 2026-11-01: a book counts only when it is harder on both, so the ceiling
    does not rest on word counts alone; a book with too few finished sentences to measure, or a
    test with no sentence length, is not called harder."""
    if not float(book["outside_2000"]) > word_bar:
        return False
    if not sentences:
        return True
    return sentence_bar is not None and bool(book.get("sentence_words")) and \
        float(book["sentence_words"]) > sentence_bar


def pass_rate_se(row: dict) -> float | None:
    """A figure's standard error in points: the report's (`se`), else from the children tested
    with a design effect of DEFF (sqrt(DEFF * p(1-p) / n)), else None (taken as exact)."""
    se = str(row.get("se") or "").strip()
    if se:
        return float(se)
    n = str(row.get("n_tested") or "").strip()
    if n.isdigit() and int(n) > 0:
        p = row["share"] / 100
        return 100 * math.sqrt(DEFF * p * (1 - p) / int(n))
    return None


def _pass_rate_draw(rng: random.Random, row: dict):
    """A function drawing the figure's pass rate (0-1): a Beta with its mean and standard error
    (an effective sample of p(1-p)/se^2 children), or the figure itself when it has no error."""
    p = row["share"] / 100
    se = pass_rate_se(row)
    n = str(row.get("n_tested") or "").strip()
    if se and 0 < p < 1:
        n_eff = p * (1 - p) / (se / 100) ** 2
    elif n.isdigit() and int(n) > 0:          # a share of 0 or 100: the children tested
        n_eff = int(n) / DEFF
    else:
        return lambda: p
    a, b = p * n_eff + 0.5, (1 - p) * n_eff + 0.5
    return lambda: rng.betavariate(a, b)


def ceiling(groups: list[tuple[int, int, dict]]) -> tuple[float, float, float]:
    """The most children (per cent) who could read a book drawn at random, from (books, harder
    books, figure row) per grade figure, and its 90% interval: (point, low, high)."""
    total = sum(n for n, _, _ in groups)
    point = sum(k * row["share"] + (n - k) * 100 for n, k, row in groups) / total
    rng = random.Random(SEED)
    pass_rate = [_pass_rate_draw(rng, row) for _, _, row in groups]
    draws = []
    for _ in range(DRAWS):
        v = 0.0
        for (n, k, _), p in zip(groups, pass_rate):
            h = rng.betavariate(k + 0.5, n - k + 0.5)
            v += n * (1 - h * (1 - p()))
        draws.append(100 * v / total)
    draws.sort()
    lo, hi = (draws[min(DRAWS - 1, int(q * DRAWS))] for q in INTERVAL)
    # where no book (or every book) is harder, the prior pulls every draw off the observed share;
    # the interval is stretched to hold it, as with the Jeffreys interval for a binomial share
    # (Brown, Cai and DasGupta 2001)
    return round(point, 1), round(min(lo, point), 1), round(max(hi, point), 1)


def mark_secondary(countries: list[dict]) -> None:
    """Set each line's "secondary": True for a line of a country that also has a line in the
    first language its figure names (the one most children were tested in), when this line is
    in another. Bangladesh's English line is secondary to its Bangla one (Lee, 2026-10-27)."""
    from tgs.difficulty.reading import languages

    langs: dict[str, set[str]] = {}
    for c in countries:
        langs.setdefault(c["iso3"], set()).add(c["language"])
    for c in countries:
        first = languages({"language": c["tested_in"]})[0]
        c["secondary"] = (c["language"] != first and first in langs[c["iso3"]]) or \
            c.get("secondary_figure", False)


def estimate(root: Path, out: Path) -> dict:
    """Per country with at least MIN_BOOKS scored books: the reading figure, its books' gap
    above the story, the share of books harder by the margin, and the ceiling with its interval
    (see `ceiling`). Writes results.json."""
    root = Path(root)
    lines = yardsticks_by_line(root)
    sticks = reading.load_yardsticks(root / YARDSTICKS)
    extras = extra_books(root)
    names = {bf.book.iso3: bf.book.country for bf in national_books(root)}
    names.update({e.iso3: e.country for e in extras if e.iso3 not in names})
    with open(root / BOOKS, newline="", encoding="utf-8") as fh:
        all_rows = list(csv.DictReader(fh))
    for r in all_rows:
        r["language"] = r.get("language") or "en"
    # the comparative judgement run (tgs.difficulty.cjrun), where it has been done
    cj_harder = {}
    if (root / CJ_BOOKS).exists():
        with open(root / CJ_BOOKS, newline="", encoding="utf-8") as fh:
            cj_harder = {r["id"]: r["harder"] == "yes" for r in csv.DictReader(fh)}
    countries, left_out = [], []
    for iso3, lang in sorted(lines):
        c = lines[(iso3, lang)]
        rows = [r for r in all_rows if r["language"] == lang]
        f, y = c["figure"], c["yardstick"]
        # each book against the next grade's figure or, without one, the nearest grade above
        # that (a younger child reads no better); books at or above the highest grade with a
        # figure are out:
        # a Grade 3 child is not meant to read a Grade 6 book (the review, 2026-10-20;
        # Lee, 2026-10-21). A figure for an age band stands for the grade it corresponds to.
        grades = sorted(c.get("by_grade") or {}) or [max(1, int(reading._grade(f) or 3))]
        figure_of = {g: grade_figure(grades, g) for g in range(1, 7)}
        scored = [r for r in rows if r["iso3"] == iso3 and r["outside_2000"]
                  and figure_of.get(int(r["grade"])) is not None]
        top_grade = max(int(r["grade"]) for r in scored) if scored else grades[-1] - 1
        if len(scored) < MIN_BOOKS:
            left_out.append({"iso3": iso3, "language": lang,
                             "why": f"{len(scored)} scored books (minimum {MIN_BOOKS})"})
            continue
        bar = threshold(sticks, y["id"])
        try:
            sbar = threshold(sticks, y["id"], "sentence_words")
        except ValueError:
            sbar = None
        o2000 = [float(r["outside_2000"]) for r in scored]

        def tally(flags, books=None):
            by_grade, groups = [], []
            for g in grades:
                mine = [h for r, h in zip(books or scored, flags)
                        if figure_of[int(r["grade"])] == g]
                if mine:
                    row = (c.get("by_grade") or {}).get(g, f)
                    by_grade.append({"grade": g, "share": row["share"],
                                     "books": len(mine), "harder_books": sum(mine),
                                     "harder_share": round(sum(mine) / len(mine), 4)})
                    groups.append((len(mine), sum(mine), row))
            return by_grade, groups

        flags = [is_harder(r, bar, sbar) for r in scored]
        harder = sum(flags) / len(flags)
        by_grade, groups = tally(flags)
        point, low, high = ceiling(groups)
        words_flags = [is_harder(r, bar, sbar, sentences=False) for r in scored]
        w_point, w_low, w_high = ceiling(tally(words_flags)[1])
        comparative = None
        judged = [(r, cj_harder[r["id"]]) for r in scored if r["id"] in cj_harder]
        if judged:
            sub = [h for _, h in judged]
            c_point, c_low, c_high = ceiling(tally(sub, [r for r, _ in judged])[1])
            comparative = {"books": len(sub), "harder_books": sum(sub), "ceiling": c_point,
                           "ceiling_low": c_low, "ceiling_high": c_high}
        sentence_rows = [float(r["sentence_words"]) for r in scored if r.get("sentence_words")]
        errors = {"se" if str(row.get("se") or "").strip() else
                  "children tested" if pass_rate_se(row) is not None else "none"
                  for _, _, row in groups}
        other = c["other"]
        countries.append({
            "iso3": iso3, "language": lang, "country": names.get(iso3, iso3), "source": f["source"],
            "year": f["year"], "grade": f["grade"], "age": f["age"], "share": f["share"],
            "other": {"source": other["source"], "share": other["share"]} if other else None,
            "books": len(scored), "book_grades": f"1-{top_grade}", "by_grade": by_grade,
            "caveat": (f.get("caveat") or "").strip(), "tested_in": f["language"],
            "scope": (f.get("scope") or "all-english").strip(),
            "reading_books": sum(r["line"] == "reading" for r in scored),
            "harder_share": round(harder, 4), "harder_books": sum(flags),
            "words_only": {"harder_books": sum(words_flags), "ceiling": w_point,
                           "ceiling_low": w_low, "ceiling_high": w_high},
            "comparative": comparative,
            "sentence_bar": sbar, "books_with_sentences": len(sentence_rows),
            "sentence_gap": round(statistics.median(sentence_rows) - sbar, 2)
            if sentence_rows and sbar is not None else None,
            "gap": round(statistics.median(o2000) - y["outside_2000"], 2),
            "fk_gap": round(statistics.median(float(r["fk"]) for r in scored) - y["fk"], 2)
            if y.get("fk") is not None and all(r.get("fk") for r in scored) else None,
            "spache_gap": round(statistics.median(float(r["spache"]) for r in scored)
                                - y["spache"], 2)
            if y.get("spache") is not None and all(r.get("spache") for r in scored) else None,
            "ceiling": point, "ceiling_low": low, "ceiling_high": high,
            "pass_rate_error": errors.pop() if len(errors) == 1 else "partly",
            "secondary_figure": str(f.get("secondary") or "").strip().lower() == "yes"})
    mark_secondary(countries)
    for c in countries:
        c.pop("secondary_figure", None)
    ken = lines.get(("KEN", "en"))
    uwezo = None
    if ken:
        for row in (ken["figure"], ken["other"]):
            if row and row["source"] == "Uwezo":
                uwezo = row["share"]
                break
    extra_ids = {e.id for e in extras}
    result = {"made": time.strftime("%Y-%m-%d"),
              "books": [r["id"] for r in all_rows if r["id"] not in extra_ids],
              "extra_books": [r["id"] for r in all_rows if r["id"] in extra_ids],
              "countries": countries, "left_out": left_out,
              "kenya_check": {"uwezo_share": uwezo, "gkm": GKM} if uwezo is not None else None}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
