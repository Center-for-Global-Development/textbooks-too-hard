"""The comparative judgement run: every scored book's passages against the test passages.

Lee, 2026-11-01 (after the pilot, scripts/cj_pilot.py). Pools are judged within a language:
English (the survey stories, the paired test passages, every English-line book) and Bangla. Each
book gives PER_BOOK 70-word passages (all it has when fewer). Each passage is judged by Jev
against at least 3 test passages and about 10 passages in all; both option orders are asked and
averaged; judgements are cached (build/difficulty/cj/judgements.jsonl), so a rerun only asks
what is missing. A Bradley-Terry fit (tgs.difficulty.cj) puts every passage on one scale; a book
is harder than its country's test when the median theta of its passages is above the hardest
version of that test (as in run.threshold). Intervals: BOOT bootstrap resamples of the
judgements.

Two checks ride along in the English pool (the messiness check):
  anchors  clean CLEAR excerpts of known level (Lexile 100-300, about Grade 1; 410-600 and 500,
           about Grade 2-3; 700, about Grade 3-4), cut to about 70 words at a sentence end;
  noisy    copies of English test stories with textbook-scan noise added (a running head, a
           page number, an exercise number, a line broken mid-sentence), to see whether noise
           alone raises a passage.

Writes research/difficulty/cj_books.csv (one row per book: median theta, harder), cj_passages.csv
(no text) and cj_run.json. Mango Tree books are never included (their text never goes to a model).
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tgs.difficulty import cj, clean, measures as m, reading, run

PER_BOOK = 2
BOOK_WORDS = 140             # where the test is short, a book gives enough passages to cover
MAX_PER_BOOK = 6             # about this many words, but at most MAX_PER_BOOK (Lee, 2026-11-02)
PER = 10
MIN_TESTS = 3
BOOT = 200
SEED = 20261103
THREADS = 8
PRICE = 0.042 / 1e6          # dollars per input token (docs.typesafe.ai/models, 2026-11-01)
INSTRUCTIONS = (
    "Which passage is harder for a child of about 9 to read and understand, where the child "
    "is a beginning reader who may be reading in a second language? Weigh unfamiliar words, "
    "sentence length and structure, how abstract the ideas are or how much background "
    "knowledge they need, and how the text is organised. Do not count a passage as harder just "
    "because it is longer. Some passages are messy text from scanned textbooks; judge the "
    "reading the child would face and ignore obvious extraction noise.")
ANCHOR_BANDS = {"100": "G1", "300": "G1", "410L - 600L": "G2-3", "410L-600L": "G2-3",
                "500": "G2-3", "700": "G3-4"}
ANCHORS_PER = {"G1": 15, "G2-3": 15, "G3-4": 10}
NOISY = 10
CLEAN = True                 # book passages from tgs.difficulty.clean (Lee, 2026-11-02); the run
                             # before cleaning is kept as cj_*_raw.*
CJ_BOOKS = Path("research/difficulty/cj_books.csv")
CACHE = Path("build/difficulty/cj/run_judgements.jsonl")


def _hash(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode()).hexdigest()[:16]


def _lang_of(stem: str) -> str | None:
    if "bangla" in stem or "bengali" in stem:
        return "bn"
    if "english" in stem or stem.startswith("egra-") or "pirls" in stem:
        return "en"
    return None


def test_passages(root: Path) -> list[dict]:
    """The survey stories first, then the paired test passages; a text seen already is dropped."""
    out, seen = [], set()
    for folder in ("yardsticks", "validation"):
        for f in sorted((root / "build/difficulty" / folder).glob("*.txt")):
            text = f.read_text("utf-8").strip()
            lang = _lang_of(f.stem)
            h = hashlib.sha1(" ".join(text.split()).encode()).hexdigest()
            if lang is None or h in seen:
                continue
            seen.add(h)
            out.append({"pid": f.stem, "kind": "test", "lang": lang, "text": text})
    return out


def cut(text: str, size: int = m.WINDOW) -> str:
    """The text's opening, ended at the first sentence end at or after `size` words."""
    words = text.split()
    for n in range(min(size, len(words)), len(words)):
        if words[n - 1][-1:] in ".!?\"'”":
            return " ".join(words[:n])
    return " ".join(words[:size])


def anchors(root: Path, rng: random.Random) -> list[dict]:
    rows = list(csv.DictReader(open(root / "build/difficulty/clear.csv", encoding="utf-8")))
    out = []
    for level, n in ANCHORS_PER.items():
        pool = [r for r in rows if ANCHOR_BANDS.get(r["Lexile Band"].strip()) == level]
        for r in rng.sample(pool, min(n, len(pool))):
            out.append({"pid": f"clear-{r['ID']}", "kind": "anchor", "lang": "en", "level": level,
                        "text": cut(r["Excerpt"])})
    return out


def add_noise(text: str, rng: random.Random) -> str:
    words = text.split()
    k = len(words) // 2
    body = " ".join(words[:k]) + "\n" + " ".join(words[k:])
    return (f"UNIT {rng.randint(2, 9)}  Reading\n{rng.randint(10, 99)}\n"
            f"Exercise {rng.randint(1, 6)}.\n{body}\nAnswer the questions.")


def noisy(tests: list[dict], rng: random.Random) -> list[dict]:
    stories = [t for t in tests if t["lang"] == "en" and "pirls" not in t["pid"]]
    return [{"pid": f"noisy-{t['pid']}", "kind": "noisy", "lang": "en", "of": t["pid"],
             "text": add_noise(t["text"], rng)} for t in rng.sample(stories, min(NOISY, len(stories)))]


def cleaned(noisies: list[dict]) -> list[dict]:
    """The noisy stories run through the cleaner: is the noise taken off again?"""
    return [{"pid": f"cleaned-{n['of']}", "kind": "cleaned", "lang": "en", "of": n["of"],
             "text": clean.paragraphs_text(n["text"])} for n in noisies]


def test_lengths(root: Path, lines: dict, sticks: list[dict]) -> dict:
    """(iso3, language) -> the mean length in words of the line's test versions: a book's
    passages are cut to this length (Lee, 2026-11-02)."""
    out = {}
    for key, c in lines.items():
        ns = [len(f.read_text("utf-8").split()) for v in versions(sticks, c["yardstick"]["id"])
              for f in [root / "build/difficulty/yardsticks" / f"{v}.txt"] if f.exists()]
        if ns:
            out[key] = round(sum(ns) / len(ns))
    return out


def per_book(size: int) -> int:
    return max(PER_BOOK, min(MAX_PER_BOOK, -(-BOOK_WORDS // size)))


def book_passages(root: Path, rng: random.Random, lines: dict,
                  no_prose: list | None = None, sizes: dict | None = None) -> list[dict]:
    books = list(csv.DictReader(open(root / run.BOOKS, encoding="utf-8")))
    corpus = {r["id"]: r for r in csv.DictReader(open(root / "data/corpus/books.csv",
                                                      encoding="utf-8"))}
    files = {bf.book.id: bf for bf in run.national_books(root)}
    extras = {e.id: e for e in run.extra_books(root)}
    texts = run.make_texts(root)
    out = []
    for b in books:
        lang = b["language"] or "en"
        if (b["iso3"], lang) not in lines or not b["outside_2000"] or int(b["grade"]) > 7:
            continue
        if "mango" in (corpus.get(b["id"], {}).get("publisher") or "").lower():
            continue
        if b["id"] in files:
            text = "\n".join(texts.text(f) or "" for f in files[b["id"]].files)
        elif b["id"] in extras:
            text = (root / extras[b["id"]].text).read_text("utf-8")
        else:
            continue
        size = (sizes or {}).get((b["iso3"], lang), m.WINDOW)
        ps = clean.prose_passages(text, size) if CLEAN else m.passages(text)
        if not ps and no_prose is not None:
            no_prose.append((b["iso3"], lang, b["id"]))
        for k, p in enumerate(rng.sample(ps, min(per_book(size) if sizes else PER_BOOK, len(ps)))):
            out.append({"pid": f"{b['id']}#{k}", "kind": "book", "lang": lang, "iso3": b["iso3"],
                        "book": b["id"], "grade": b["grade"], "text": p})
    return out


def _payload(model: str, a: str, b: str) -> dict:
    x, y = "The passage in `passage_x`", "The passage in `passage_y`"
    return {"model": model, "state": {"passage_x": a, "passage_y": b}, "questions": {
        "xy": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": {"x": x, "y": y}},
        "yx": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": {"y": y, "x": x}}}}


def p_first_harder(answers: dict) -> float:
    """P(passage_x is harder), averaged over the two option orders."""
    px = [float((answers.get(q) or {}).get("probabilities", {}).get("x", 0.5))
          for q in ("xy", "yx")]
    return sum(px) / 2


def versions(sticks: list[dict], yardstick_id: str) -> list[str]:
    key = run._versions_key(yardstick_id)
    return [y["id"] for y in sticks if run._versions_key(y["id"]) == key]


def main(root: Path, client=None) -> dict:
    root = Path(root)
    rng = random.Random(SEED)
    lines = run.yardsticks_by_line(root)
    sticks = reading.load_yardsticks(root / run.YARDSTICKS)
    tests = test_passages(root)
    noisies = noisy(tests, rng)
    no_prose: list = []
    sizes = test_lengths(root, lines, sticks) if CLEAN else None
    items = (tests + anchors(root, rng) + noisies + (cleaned(noisies) if CLEAN else [])
             + book_passages(root, rng, lines, no_prose, sizes))
    by_pid = {it["pid"]: it for it in items}
    cache_f = root / CACHE
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    h = {pid: _hash(it["text"]) for pid, it in by_pid.items()}
    seen = {}                                   # judgements by the texts' hashes, not ids
    if cache_f.exists():
        for line in cache_f.read_text().splitlines():
            r = json.loads(line)
            seen[(r["ha"], r["hb"])] = r["p"]
            seen[(r["hb"], r["ha"])] = 1 - r["p"]
    cache = {}
    pairs = []
    for lang in ("en", "bn"):
        ids = [it["pid"] for it in items if it["lang"] == lang]
        pairs += cj.design(ids, {p: by_pid[p]["kind"] == "test" for p in ids}, per=PER,
                           min_tests=MIN_TESTS, rng=random.Random(f"{SEED}-{lang}"))
    for a, b in pairs:
        if (h[a], h[b]) in seen:
            cache[(a, b)] = seen[(h[a], h[b])]
    todo = [p for p in pairs if p not in cache]
    print(f"{len(items)} passages, {len(pairs)} pairs, {len(todo)} to ask", flush=True)
    tokens = 0
    if todo:
        from tgs.review.typesafe import DEFAULT_MODEL, TypeSafe
        client = client or TypeSafe(DEFAULT_MODEL)
        client.info()

        def one(pair):
            a, b = pair
            return pair, p_first_harder(client.ask(_payload(client.model, by_pid[a]["text"],
                                                            by_pid[b]["text"])).get("answers") or {})

        with ThreadPoolExecutor(THREADS) as pool, open(cache_f, "a") as fh:
            for n, ((a, b), p) in enumerate(pool.map(one, todo), start=1):
                cache[(a, b)] = p
                fh.write(json.dumps({"a": a, "b": b, "ha": h[a], "hb": h[b], "p": p,
                                     "model": client.reported_model}) + "\n")
                if n % 500 == 0:
                    fh.flush()
                    print(f"  {n} of {len(todo)}", flush=True)
        tokens = client.input_tokens
    result = {"made": __import__("time").strftime("%Y-%m-%d"), "per_book": PER_BOOK,
              "passages": len(items), "pairs": len(pairs), "new_input_tokens": tokens,
              "new_cost_usd": round(tokens * PRICE, 4), "clean": CLEAN,
              "passage_words": {f"{i}-{l}": n for (i, l), n in sorted((sizes or {}).items())},
              "books_without_prose": {f"{i}-{l}": sum(1 for x in no_prose if x[:2] == (i, l))
                                      for i, l in sorted({x[:2] for x in no_prose})},
              "lines": {}, "checks": {}}
    prow, brow = [], []
    for lang in ("en", "bn"):
        ids = [it["pid"] for it in items if it["lang"] == lang]
        index = {p: n for n, p in enumerate(ids)}
        judged = [(index[a], index[b], cache[(a, b)]) for a, b in pairs if a in index and b in index]
        theta = cj.fit(len(ids), judged)
        brng = random.Random(f"{SEED}-boot-{lang}")
        boot = [cj.fit(len(ids), [judged[brng.randrange(len(judged))] for _ in judged])
                for _ in range(BOOT)]
        for p in ids:
            it = by_pid[p]
            prow.append({"pid": p, "kind": it["kind"], "lang": lang, "iso3": it.get("iso3", ""),
                         "book": it.get("book", ""), "grade": it.get("grade", ""),
                         "level": it.get("level", ""), "of": it.get("of", ""),
                         "theta": round(theta[index[p]], 3)})
        book_ids = {}
        for p in ids:
            if by_pid[p].get("book"):
                book_ids.setdefault(by_pid[p]["book"], []).append(index[p])
        for (iso3, l), c in sorted(lines.items()):
            if l != lang:
                continue
            vs = [v for v in versions(sticks, c["yardstick"]["id"]) if v in index]
            mine = sorted(b for b in book_ids if by_pid[ids[book_ids[b][0]]]["iso3"] == iso3)
            if not vs or not mine:
                continue

            def flags(th):
                bar = max(th[index[v]] for v in vs)
                return [statistics.median(th[i] for i in book_ids[b]) > bar for b in mine]

            f0 = flags(theta)
            fb = [flags(t) for t in boot]
            for n, (b, hard) in enumerate(zip(mine, f0)):
                brow.append({"id": b, "iso3": iso3, "language": lang,
                             "median_theta": round(statistics.median(theta[i] for i in book_ids[b]), 3),
                             "bar": round(max(theta[index[v]] for v in vs), 3),
                             "harder": "yes" if hard else "no",
                             "harder_in_boot": round(sum(f[n] for f in fb) / BOOT, 3)})
            dist = sorted(sum(f) / len(mine) for f in fb)
            result["lines"][f"{iso3}-{lang}"] = {
                "tests": vs, "books": len(mine), "harder_books": sum(f0),
                "harder_share": round(sum(f0) / len(mine), 3),
                "harder_share_90": [round(dist[int(0.05 * BOOT)], 3),
                                    round(dist[int(0.95 * BOOT) - 1], 3)]}
        if lang == "en":
            th = {p: theta[index[p]] for p in ids}
            stories = [th[p] for p in ids if by_pid[p]["kind"] == "test" and "pirls" not in p]
            books_en = [th[p] for p in ids if by_pid[p]["kind"] == "book"]
            result["checks"]["anchors"] = {
                lv: {"n": len(v), "median_theta": round(statistics.median(v), 3),
                     "share_above_hardest_grade2_story": round(
                         sum(x > max(stories) for x in v) / len(v), 3),
                     "share_above_median_story": round(
                         sum(x > statistics.median(stories) for x in v) / len(v), 3)}
                for lv in ANCHORS_PER
                for v in [[th[p] for p in ids if by_pid[p].get("level") == lv]] if v}
            result["checks"]["test_stories"] = {"n": len(stories),
                                                "median_theta": round(statistics.median(stories), 3),
                                                "max_theta": round(max(stories), 3)}
            result["checks"]["books"] = {"n": len(books_en),
                                         "median_theta": round(statistics.median(books_en), 3)}
            lifts = [th[p] - th[by_pid[p]["of"]] for p in ids if by_pid[p]["kind"] == "noisy"]
            result["checks"]["noise_lift"] = {"n": len(lifts),
                                              "median": round(statistics.median(lifts), 3),
                                              "min": round(min(lifts), 3), "max": round(max(lifts), 3)}
            back = [th[p] - th[by_pid[p]["of"]] for p in ids if by_pid[p]["kind"] == "cleaned"]
            if back:
                result["checks"]["cleaned_lift"] = {
                    "n": len(back), "median": round(statistics.median(back), 3),
                    "min": round(min(back), 3), "max": round(max(back), 3)}
    for name, rows in (("cj_passages.csv", prow), ("cj_books.csv", brow)):
        with open(root / "research/difficulty" / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    (root / "research/difficulty/cj_run.json").write_text(json.dumps(result, indent=1) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(main(Path(".")), indent=1))
