"""Strip page clutter from a scanned book's text and cut passages of running prose.

Lee, 2026-11-02, after the messiness check: page clutter (running heads, page numbers, exercise
labels, lines broken mid-sentence) made a test story look harder to the judge. The judge should
read the book's prose as a child would meet it.

`paragraphs(text)` drops clutter line by line:
  dropped      page numbers, and running heads or footers (short unfinished lines that recur on
               at least RUNNING pages, digits ignored); a story continues across them;
  breaks       headings and labels (UNIT 4, Exercise 3, a short Title Case or capitals line), and
               lines that are mostly not words (sums, tables, number lists); a passage never
               runs across one;
  mended       lines within a paragraph are joined, a word hyphenated at a line end rejoined,
               and item markers (1. a) (iii) Q2 and bullets) stripped from the line's start.
`prose_passages(text)` cuts runs of whole finished sentences of at least `size` words (at most
2 x size) from consecutive paragraphs; an unfinished piece (a word list, a label) ends a run, and
a run never starts with a lowercase piece (the end of a sentence begun before a page break).
"""
from __future__ import annotations

import re
from collections import Counter

from tgs.difficulty import measures as m

RUNNING = 3            # a short unfinished line on this many pages is a running head or footer
SHORT = 60             # characters: longer lines are never running heads
HEADING_WORDS = 6      # a heading has at most this many words
MIN_WORDS = 0.5        # a line where fewer tokens than this share are words is a table or sum
TOLERANCE = 0.15       # a passage is within this share of the target length ...
MIN_SLACK = 2          # ... or this many words, whichever is more

_PAGE_NUMBER = re.compile(r"^\W*(?:page\s*)?(?:\d{1,4}|[ivxlc]{1,6})\W*$", re.IGNORECASE)
_LABEL = re.compile(
    r"^\W*(?:unit|lesson|chapter|exercise|activity|activities|section|part|theme|week|term|"
    r"module|topic|practice|task|step|revision|test|assessment|project|worksheet|page)\b"
    r"[\s\d.:)\-–—A-Za-z]{0,24}$", re.IGNORECASE)
_MARKER = re.compile(r"^\s*(?:\(?\d{1,2}[.)]|\(?[a-h]\)|\([ivx]{1,4}\)|[ivx]{1,4}\)|[a-h]\.(?=\s)|"
                     r"Q\.?\s?\d{1,2}[.:)]?|[•▪●◦*·\-–—])\s+")
_SMALL = frozenset("a an and as at by for from in into of on or the to with".split())


def _key(line: str) -> str:
    return " ".join(re.sub(r"[\d\W_]+", " ", line.lower()).split())


def _finished(line: str) -> bool:
    return bool(m._FINISHED.search(line.strip()))


def _running(pages: list[list[str]]) -> set[str]:
    seen = Counter()
    for lines in pages:
        seen.update({_key(l) for l in lines if l.strip() and len(l.strip()) <= SHORT
                     and not _finished(l)} - {""})
    if len(pages) == 1:                       # no page breaks: count lines instead
        seen = Counter(_key(l) for l in pages[0] if l.strip() and len(l.strip()) <= SHORT
                       and not _finished(l))
        seen.pop("", None)
    return {k for k, n in seen.items() if n >= RUNNING}


def _heading(line: str, nxt: str) -> bool:
    s = line.strip()
    if _LABEL.match(s):
        return True
    words = s.split()
    if len(words) > HEADING_WORDS or _finished(s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 3 and all(c.isupper() for c in letters if c.lower() != c.upper()) \
            and any(c.lower() != c.upper() for c in letters):
        return True
    alpha = [w for w in words if w[:1].isalpha()]
    title = alpha and alpha[0][0].isupper() and \
        all(w[0].isupper() or w.lower() in _SMALL for w in alpha)
    nxt = nxt.strip()
    return bool(title) and (not nxt or nxt[0].isupper() or not nxt[0].isalpha())


def _not_words(line: str) -> bool:
    toks = line.split()
    return bool(toks) and sum(m._is_word(t) for t in toks) < MIN_WORDS * len(toks)


def paragraphs(text: str) -> list[str | None]:
    """The text's prose paragraphs in order, None where a heading, label or table broke it.
    Leading, trailing and repeated breaks are collapsed."""
    pages = [p.split("\n") for p in text.split("\f")]
    running = _running(pages)
    out: list[str | None] = []
    cur: list[str] = []

    def close(brk: bool):
        if cur:
            out.append(" ".join(cur))
            cur.clear()
        if brk and out and out[-1] is not None:
            out.append(None)

    for lines in pages:
        lines = [l for l in lines if not (l.strip() and (_PAGE_NUMBER.match(l.strip()) or
                                                        _key(l) in running and not _finished(l)))]
        for n, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                close(False)
                continue
            nxt = next((l for l in lines[n + 1:] if l.strip()), "")
            if _heading(line, nxt) or _not_words(line):
                close(True)
                continue
            line = _MARKER.sub("", line, count=1).strip()
            if not line:
                continue
            if cur and re.search(r"\w-$", cur[-1]) and line[:1].islower():
                cur[-1] = cur[-1][:-1] + line.split(" ", 1)[0]
                rest = line.split(" ", 1)[1:]
                if rest:
                    cur.append(rest[0])
            else:
                cur.append(line)
    close(False)
    while out and out[-1] is None:
        out.pop()
    return [p for p in out]


def prose_passages(text: str, size: int = m.WINDOW, tol: float = TOLERANCE) -> list[str]:
    """Runs of whole finished sentences from consecutive paragraphs, each within `tol` x size
    words (at least MIN_SLACK words) of `size`, so a book's passage is as long as the test it is
    set against (Lee, 2026-11-02). Within a run, each passage starts where the last ended and
    ends at the sentence that brings it closest to `size`; where none comes close enough, the
    start moves on a sentence. A heading or an unfinished piece ends a run, and a run never
    starts with a lowercase piece (the end of a sentence begun before a page break). Passages
    that are mostly not words or are imprint boilerplate are left out."""
    slack = max(tol * size, MIN_SLACK)
    out: list[str] = []
    for run_ in _runs(text):
        lens = [len(s.split()) for s in run_]
        i = 0
        while i < len(run_):
            n, best, best_j = 0, None, None
            for j in range(i, len(run_)):
                n += lens[j]
                if best is None or abs(n - size) < abs(best - size):
                    best, best_j = n, j
                if n > size + slack:
                    break
            if best is not None and abs(best - size) <= slack:
                p = " ".join(run_[i:best_j + 1])
                toks = p.split()
                if sum(m._is_word(t) for t in toks) >= m.MIN_ALPHA * len(toks) \
                        and not m.BOILERPLATE.search(p):
                    out.append(p)
                i = best_j + 1
            else:
                i += 1
    return out


def _runs(text: str) -> list[list[str]]:
    """Runs of consecutive finished sentences; a heading or an unfinished piece ends one."""
    runs: list[list[str]] = []
    cur: list[str] = []

    def end():
        nonlocal cur
        if cur:
            runs.append(cur)
        cur = []

    for para in paragraphs(text):
        if para is None:
            end()
            continue
        for piece in m._END.split(para):
            piece = piece.strip()
            if not piece:
                continue
            if not _finished(piece):          # a paragraph's unfinished tail: a label, a list
                end()
                continue
            if not cur and piece[:1].islower():   # the end of a sentence begun before a break
                continue
            cur.append(piece)
    end()
    return runs


def paragraphs_text(text: str) -> str:
    """The cleaned text, its paragraphs and breaks as blank lines."""
    return "\n\n".join(p for p in paragraphs(text) if p is not None)
