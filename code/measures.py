"""How hard a text is to read, for a child reading in a second language.

A text is scored as passages of about the length of the Grade 2 stories children are tested on
(WINDOW running words): consecutive windows of the raw text, keeping only those that are mostly
words (tables, exercises and badly read scans are not). Each passage gets the share of its words
outside the 1,000 and the 2,000 most frequent English words (vocabulary coverage, the measure
second-language reading research ties to comprehension: Hu and Nation 2000; Laufer and
Ravenhorst-Kalovski 2010) and its Flesch-Kincaid grade; a book is the median of its passages.
The frequency list is wordfreq's general English, weighted towards adult text ("cat" ranks 1,712),
so the shares are higher than a children's list would give; books and the test stories are scored
on the same list, and only the gap between them is used.
A text in another language (Bangladesh's Bangla-medium books against its Bangla MICS story; Lee,
2026-10-27) is scored on wordfreq's list for that language in the same way, where wordfreq has
one; the grade formulas are English-only, and names are only found in English.
Design: docs/superpowers/specs/2026-10-20-textbook-difficulty-design.md.
"""
from __future__ import annotations

import re
import statistics
from functools import lru_cache

WINDOW = 70          # running words in a passage: about the length of the MICS Grade 2 story
MIN_ALPHA = 0.6      # a passage is prose when at least this share of its tokens are words
MIN_WINDOWS = 3      # a book with fewer prose passages is not scored (210 words; Lee, 2026-10-21)
TOPS = (1000, 2000)  # the frequency lists' lengths
MIN_ENGLISH = 0.7    # a text is English when at least this share of its words are known English
                     # words (wordfreq's 50,000 most frequent): a Marathi or Urdu language book in
                     # an English-medium set, or a badly extracted text, is not
KNOWN = 50_000
SPACHE_EASY = "build/difficulty/spache_easy.txt"   # made by scripts/spache_words.py; not in git
# a copyright, licence or imprint passage, not the book's text: the short USAID readers (Kenya,
# Nigeria) have a licence page as long as a fifth of the book (2026-10-21)
BOILERPLATE = re.compile(
    r"copyright|licen[cs]ed?\b|creative ?commons|all rights reserved|\bisbn\b|attribution|"
    r"no part of this (?:publication|book)|may be reproduced|published by|printed (?:in|by)|"
    r"trademark|third[- ]part|"
    r"সর্বস্বত্ব|প্রকাশক|মুদ্রণে|মুদ্রিত", re.IGNORECASE)   # Bangla: all rights reserved, publisher,
                                                         # printed

_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
_SENTENCE = re.compile(r"[.!?]+")
_VOWELS = re.compile(r"[aeiouy]+")


def tokens(text: str) -> list[str]:
    """Lower-case word tokens (letters, with an inner apostrophe), in order."""
    return _WORD.findall(text.lower())


_DIGIT = re.compile(r"\d")
_LATIN = re.compile(r"[a-z]")


def word_tokens(text: str, lang: str = "en") -> list[str]:
    """Word tokens, in order. English: `tokens`. Another language: wordfreq's tokenizer (so
    words are normalised as its list is), keeping tokens with a letter and no digit, and, in a
    language not written in Latin script, none in Latin letters (OCR fragments of pictures)."""
    if lang == "en":
        return tokens(text)
    import wordfreq

    latin = lang in LATIN_SCRIPT
    return [t for t in wordfreq.tokenize(text, lang)
            if any(c.isalpha() for c in t) and not _DIGIT.search(t)
            and (latin or not _LATIN.search(t))]


LATIN_SCRIPT = {"en", "sw", "fr", "pt", "es", "ha", "ig", "yo", "om", "ny", "st", "sn", "nd",
                "gil", "rw", "lg", "id", "tr", "az", "et", "laj", "ach", "luo", "nyn", "xog"}


@lru_cache(maxsize=None)
def _top(n: int, lang: str = "en") -> frozenset[str]:
    """wordfreq's `n` most frequent words of `lang`; empty where it has no list for the language
    (it would silently give English: Kiswahili, Hausa, Nepali)."""
    import wordfreq

    if lang not in wordfreq.available_languages("best"):
        return frozenset()
    return frozenset(wordfreq.top_n_list(lang, n))


def outside_share(words: list[str], top: int, lang: str = "en") -> float:
    """The per cent of `words` not among the `top` most frequent words of the language
    (wordfreq)."""
    if not words:
        return 0.0
    common = _top(top, lang)
    return 100 * sum(w not in common for w in words) / len(words)


_ANY_WORD = re.compile(r"[^\s\d.,;:!?\"'()\[\]{}<>|/\\%&*+=#@~`_\u2018\u2019\u201c\u201d-]{3,}")


def english_share(text: str) -> float:
    """The share of the text's words of three letters or more, in any script, that are known
    English words. Shorter words are left out: English OCR of another script (an Urdu or Sindhi
    scan) yields many short fragments that happen to be English ("be", "we", "ale")."""
    words = _ANY_WORD.findall(text.lower())
    if not words:
        return 0.0
    known = _top(KNOWN)
    return sum(w in known for w in words) / len(words)


def known_share(text: str, lang: str = "en") -> float:
    """The share of the text's words that are known words of the language (wordfreq's KNOWN most
    frequent): `english_share` for English; 0 when it has no words in the language, or wordfreq
    has no list for it."""
    if lang == "en":
        return english_share(text)
    words = word_tokens(text, lang)
    known = _top(KNOWN, lang) if words else frozenset()
    if not known:
        return 0.0
    return sum(w in known for w in words) / len(words)


def _is_word(raw: str) -> bool:
    return any(c.isalpha() for c in raw) and not any(c.isdigit() for c in raw)


def passages(text: str, size: int = WINDOW) -> list[str]:
    """Consecutive, non-overlapping windows of `size` whitespace-separated tokens of `text` (an
    incomplete last window is dropped), keeping those whose tokens are at least MIN_ALPHA words
    and that are not a copyright, licence or imprint passage (BOILERPLATE)."""
    raw = text.split()
    out = []
    for i in range(0, len(raw) - size + 1, size):
        chunk = raw[i:i + size]
        p = " ".join(chunk)
        if sum(_is_word(t) for t in chunk) >= MIN_ALPHA * size and not BOILERPLATE.search(p):
            out.append(p)
    return out


def _syllables(word: str) -> int:
    n = len(_VOWELS.findall(word))
    if word.endswith("e") and not word.endswith("le") and n > 1:
        n -= 1                                   # a silent final e
    return max(n, 1)


def fk_grade(text: str) -> float:
    """Flesch-Kincaid grade level: 0.39 (words / sentences) + 11.8 (syllables / words) - 15.59.
    Syllables are counted as vowel groups, a silent final e dropped, at least one a word."""
    words = tokens(text)
    if not words:
        return 0.0
    sentences = max(len([s for s in _SENTENCE.split(text) if tokens(s)]), 1)
    syllables = sum(_syllables(w) for w in words)
    return 0.39 * len(words) / sentences + 11.8 * syllables / len(words) - 15.59


@lru_cache(maxsize=1)
def spache_easy() -> frozenset[str]:
    """The revised Spache list of familiar words (Spache 1974), as the common English words whose
    Porter stem is on it (scripts/spache_words.py writes SPACHE_EASY)."""
    from pathlib import Path

    path = Path(SPACHE_EASY)
    if not path.exists():
        raise FileNotFoundError(f"{path}: run scripts/spache_words.py (see its docstring)")
    return frozenset(path.read_text(encoding="utf-8").split())


def spache_grade(text: str, skip: frozenset[str] = frozenset()) -> float:
    """Revised Spache grade (Spache 1974), built for Grades 1-3: 0.121 (words / sentences) +
    0.082 (per cent of words that are unfamiliar, each counted once) + 0.659. Words in `skip`
    (names) count as familiar, and are kept in the word count."""
    words = tokens(text)
    if not words:
        return 0.0
    sentences = max(len([s for s in _SENTENCE.split(text) if tokens(s)]), 1)
    easy = spache_easy()
    hard = {w for w in words if w not in easy and w not in skip}
    return 0.121 * len(words) / sentences + 0.082 * 100 * len(hard) / len(words) + 0.659


MIN_SENTENCE = 3     # words: a shorter piece ending in a full stop is a label or an answer, not a sentence
MIN_SENTENCES = 10   # finished sentences a book needs for a sentence length
MAX_FRAGMENTS = 0.2  # an English sentence with more of its words one- or two-letter fragments is a
                     # bad scan or a jumbled layout, not a sentence
MIN_KNOWN = 0.8      # nor is one with fewer of its words known words of the language
_PARAGRAPH = re.compile(r"\n\s*\n")
_END = re.compile(r"(?<=[.!?\u0964])[\"'\u2019\u201d)\]]*\s+")
_FINISHED = re.compile(r"[.!?\u0964][\"'\u2019\u201d)\]]*$")
_SHORT_WORDS = frozenset("a i an am as at be by do go he if in is it me my no of oh ok on or so to "
                         "up us we".split())


def _clean_sentence(words: list[str], lang: str) -> bool:
    if len(words) < MIN_SENTENCE:
        return False
    if lang == "en" and sum(len(w) <= 2 and w not in _SHORT_WORDS for w in words) > \
            MAX_FRAGMENTS * len(words):
        return False
    known = _top(KNOWN, lang)
    return not known or sum(w in known for w in words) >= MIN_KNOWN * len(words)


def sentence_lengths(text: str, lang: str = "en") -> list[int]:
    """Words in each finished sentence of `text`, in order. Lines within a paragraph are joined (a
    sentence wraps over lines); a sentence ends at . ! ? or the Bangla dari, and a paragraph's
    unfinished last piece (a heading, a label, an exercise line) is not a sentence. Pieces under
    MIN_SENTENCE words, and garbled ones (`_clean_sentence`), are left out. Lee, 2026-11-01:
    sentence length is the second measure, in every language."""
    out = []
    for para in _PARAGRAPH.split(text):
        pieces = _END.split(" ".join(para.split()))
        for piece in pieces:
            if not _FINISHED.search(piece):
                continue
            words = word_tokens(piece, lang)
            if _clean_sentence(words, lang):
                out.append(len(words))
    return out


def sentence_words(text: str, lang: str = "en", whole: bool = False) -> float | None:
    """The median words per finished sentence; None for a book with fewer than MIN_SENTENCES
    (a story, `whole`, needs one)."""
    lengths = sentence_lengths(text, lang)
    if len(lengths) < (1 if whole else MIN_SENTENCES):
        return None
    return statistics.median(lengths)


AOA = "build/difficulty/aoa_kuperman.csv"   # Kuperman, Stadthagen-Gonzalez & Brysbaert (2012),
                                            # 31,104 lemmas; not in git (Lee, 2026-11-01 trial)
AOA_LATE = 8.0   # years: a word most children learn after about age 8, past a Grade 2 reader's age
_SUFFIXES = (("ies", "y"), ("ied", "y"), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
             ("es", ""), ("s", ""), ("er", ""), ("est", ""), ("ly", ""), ("'s", ""))


@lru_cache(maxsize=None)
def aoa_ratings() -> dict[str, float]:
    """Age-of-acquisition ratings in years, by lower-case lemma."""
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / AOA
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["word"]: float(r["aoa"]) for r in csv.DictReader(fh)}


def aoa_of(word: str) -> float | None:
    """A word's rating, or its stem's after one common English ending is taken off (doubled
    consonants undone: running -> run); None when neither is rated."""
    ratings = aoa_ratings()
    if word in ratings:
        return ratings[word]
    for end, add in _SUFFIXES:
        if word.endswith(end) and len(word) > len(end) + 2:
            stem = word[: -len(end)] + add
            if stem in ratings:
                return ratings[stem]
            if len(stem) > 2 and stem[-1] == stem[-2] and stem[:-1] in ratings:
                return ratings[stem[:-1]]
    return None


def aoa_scores(words: list[str]) -> dict:
    """The mean rating of the rated words and the per cent of them rated AOA_LATE or later."""
    rated = [a for a in map(aoa_of, words) if a is not None]
    if not rated:
        return {"aoa_mean": None, "aoa_late": None}
    return {"aoa_mean": round(statistics.mean(rated), 2),
            "aoa_late": round(100 * sum(a >= AOA_LATE for a in rated) / len(rated), 2)}


_RAW = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


def names(text: str) -> frozenset[str]:
    """Words the text only ever writes capitalised and that are not among the 2,000 most frequent
    English words: the names of people and places ("Moses", "Kofi"), which are not vocabulary a
    child must know. Common words that only begin sentences ("He", "The") are kept."""
    raw = _RAW.findall(text)
    caps = {w.lower() for w in raw if w[0].isupper()}
    lower = {w for w in raw if w[0].islower()}
    common = _top(2000)
    return frozenset(w for w in caps - lower if w not in common)


def score_text(text: str, *, whole: bool = False, lang: str = "en") -> dict | None:
    """The medians over the text's passages of each measure, names left out of the word counts
    (`names`, found over the whole text): {"windows", "outside_1000",
    "outside_2000", "fk", "spache", "sentence_words"}. With `whole`, the text is one passage (a test story). None when the
    text has fewer than MIN_WINDOWS prose passages, or is not English (english_share below
    MIN_ENGLISH), and is not scored whole. With another `lang` (a wordfreq code): that
    language's list, the same known-word rule (known_share), no names and no grade formulas
    (fk, spache None)."""
    windows = [text] if whole else passages(text)
    known = known_share(text, lang)
    if not whole and (len(windows) < MIN_WINDOWS or known < MIN_ENGLISH):
        return None
    out = {"windows": len(windows)}
    skip = names(text) if lang == "en" else frozenset()
    words = [[t for t in word_tokens(w, lang) if t not in skip] for w in windows]
    for top in TOPS:
        out[f"outside_{top}"] = statistics.median(outside_share(ws, top, lang) for ws in words)
    out["sentence_words"] = sentence_words(text, lang, whole)
    if lang != "en":
        return {**out, "fk": None, "spache": None}
    out["fk"] = statistics.median(fk_grade(w) for w in windows)
    out["spache"] = statistics.median(spache_grade(w, skip) for w in windows)
    return out
