"""Books judged harder than their country's test, by the book's grade (Lee, 2026-11-03).

Reads research/difficulty/cj_books.csv (tgs.difficulty.cjrun), books.csv and extra_books.csv for
each book's grade, and results.json for which lines are on the chart (not secondary). Writes
research/difficulty/cj_by_grade.csv: one row per grade with the books, the harder books and the
countries, plus a row per country for Grades 1 and 2 together.

Run: python3 scripts/cj_by_grade.py
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research/difficulty"


def main() -> None:
    r = json.loads((D / "results.json").read_text())
    lines = {(c["iso3"], c["language"]): c["country"] for c in r["countries"] if not c["secondary"]}
    grade = {b["id"]: int(b["grade"]) for b in csv.DictReader(open(D / "books.csv"))}
    for e in csv.DictReader(open(D / "extra_books.csv")):
        if e["grade"]:
            grade.setdefault(e["id"], int(e["grade"]))
    by_grade = defaultdict(lambda: [0, 0, set()])
    early = defaultdict(lambda: [0, 0])
    for b in csv.DictReader(open(D / "cj_books.csv")):
        key = (b["iso3"], b["language"])
        g = grade.get(b["id"])
        if key not in lines or g is None:
            continue
        hard = b["harder"] == "yes"
        by_grade[g][0] += 1
        by_grade[g][1] += hard
        by_grade[g][2].add(lines[key])
        if g in (1, 2):
            early[key][0] += 1
            early[key][1] += hard
    rows = [{"group": f"grade {g}", "books": n, "harder": k, "share": round(k / n, 3),
             "countries": len(cs)} for g, (n, k, cs) in sorted(by_grade.items())]
    rows += [{"group": f"grades 1-2, {lines[key]}", "books": n, "harder": k,
              "share": round(k / n, 3), "countries": 1}
             for key, (n, k) in sorted(early.items(), key=lambda x: lines[x[0]])]
    with open(D / "cj_by_grade.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
