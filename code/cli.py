"""tgs-difficulty: can children read their textbooks?

    uv run tgs-difficulty measure    # score the books in scope -> research/difficulty/books.csv
    uv run tgs-difficulty estimate   # per country -> research/difficulty/results.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tgs.difficulty import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tgs-difficulty")
    ap.add_argument("step", choices=["measure", "estimate"])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    a = ap.parse_args(argv)
    if a.step == "measure":
        n = run.measure(a.root, a.root / run.BOOKS)
        print(f"{n} books scored -> {run.BOOKS}")
    else:
        r = run.estimate(a.root, a.root / run.RESULTS)
        print(f"{len(r['countries'])} countries, {len(r['left_out'])} left out -> {run.RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
