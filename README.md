# The textbooks are still too hard: method

Lee Crawfurd, November 2026. This page explains the method behind the blog post *The textbooks are still too hard*: the data, how book and test difficulty were compared, the checks, and the full results.

## The question

Can most children read the textbooks they are given? We cannot test children on their textbooks directly. National reading assessments do test children on a short passage, so the method compares the books with that passage:

- **If a book is harder than the test passage,** a child who fails the test probably cannot read the book. So the share of children who pass the test is a ceiling on the share who can read the book.
- **For a whole country,** the question is: at most, how many children could read a textbook picked at random from its set?
- **Each book is compared with children one grade above it.** A Grade 4 book is set against the pass rate of children tested in Grade 5, who have all finished Grade 4. So the comparison holds whatever point in the school year the survey was done. Where there is no figure for the next grade, the nearest grade above is used.
- **A book that is harder than the test** is readable by at most that pass rate. **A book that is not harder** is counted as readable by every child. Both choices are generous, so the result stays an upper bound.

## Data

**Books.** 433 primary textbooks for Grades 1 to 6 from 11 countries, in all subjects. Bangladesh's books are in Bangla; all others are in English.

- **Sources.** Most are official copies from ministry or curriculum-board websites. Some are from donor archives (USAID's Development Experience Clearinghouse) or unofficial mirrors (Tanzania, Uganda).
- **Uganda's books** are the government's 2020 home-study books from the school closures, not its regular textbooks.
- **Dates.** The year is the latest one on each book's imprint, copyright or edition lines, so it is often a reprint year.
- **Copyright.** The book texts are not published.

**Reading assessments.**

| Assessment | Countries | What children read |
|---|---|---|
| UNICEF MICS6 foundational learning module | Bangladesh 2019, Guyana 2019, Kiribati 2018, Malawi 2019, Nigeria 2021 | A story of about 70 words, with comprehension questions |
| ASER | India 2022 (rural), Pakistan 2025 (provisional) | The top level of the English test: a few short sentences (17 to 24 words) |
| Uwezo | Kenya 2015, Tanzania 2017, Uganda 2024 | A short English story (64 to 79 words) |
| PIRLS 2021 | South Africa (children taught in English from Grade 1) | Two released passages of 656 and 763 words; the pass mark is the Low international benchmark |

Note: Pass rates are by grade. MICS pass rates and their standard errors are computed from the child microdata, using the survey design (strata and clusters). For ASER, Uwezo and PIRLS, standard errors come from the number of children tested, with a design effect of 2.

**How representative the samples are.**
- MICS and Uwezo are nationally representative household surveys.
- ASER covers rural children only.
- The South African figure covers only children taught in English from Grade 1.
- Kenya's and Tanzania's tests are older than most of their books.

## Measuring difficulty: comparative judgement

**The method.** Comparative judgement is used to mark essays. People, and AI models, are poor at giving a text an absolute difficulty score, but good at saying which of two texts is harder. Many such pairwise judgements place every text on one scale.

**The judge.** TypeSafe's Jev model (jev-1.13.0) was used because it is fast, cheap and reliable enough for tens of thousands of comparisons. It was asked:

> Which passage is harder for a child of about 9 to read and understand, where the child is a beginning reader who may be reading in a second language? Weigh unfamiliar words, sentence length and structure, how abstract the ideas are or how much background knowledge they need, and how the text is organised. Do not count a passage as harder just because it is longer. Some passages are messy text from scanned textbooks; judge the reading the child would face and ignore obvious extraction noise.

- **Each pair is asked in both orders,** and the two answers are averaged to remove any bias towards the first option.
- **The result for each pair** is the probability that one passage is harder than the other.

**Cleaning the books.** Text extracted from scanned books carries page clutter, which a judge might read as difficulty. Before any judging, each book is cleaned ([`code/clean.py`](code/clean.py)):

- page numbers, and running heads and footers that repeat across pages, are removed;
- headings, exercise labels ("UNIT 4", "Exercise 3") and tables or sums are treated as breaks in the text;
- lines broken mid-sentence are rejoined, and words hyphenated at a line end are mended;
- list markers ("1.", "(a)") are stripped, but the item's text is kept.

**Extracts the same length as the test.** Each book is cut into extracts of whole sentences, as long as its country's test passage:

| Country | Words per extract |
|---|---|
| India | 17 |
| Pakistan | 22 |
| Most other countries | 64 to 79 |
| South Africa | about 710 |

Note: Each extract is within 15% of the target length, or within 2 words for very short tests.

- **Number of extracts.** Each book gives 2 to 6 extracts, enough to cover about 140 words.
- **Books left out.** A book with no stretch of continuous prose that long has no extract: 5 books in Guyana and 6 of the 14 in South Africa.

**Building the scale.**
- **The pool.** 2,321 passages: the test passages, every book extract, and the checks below. English and Bangla passages are judged in separate pools.
- **The comparisons.** Each passage is compared with about 10 others, at least 3 of them test passages, for 15,710 pairs in all.
- **The fit.** A Bradley-Terry model places every passage on one difficulty scale.

**The rule.** A book counts as harder than its country's test when its median extract sits above the hardest version of the test passage. Where a country used several versions of the test, using the hardest one gives the books the benefit of the doubt.

**Cost.** The final run used about 11 million input tokens and cost $0.47.

## Checks

**1. Does the judge agree with children?** The check used 25 pairs of test passages read by the same children (Uwezo, ASER, PIRLS), where we know which passage fewer children passed.

| Measure | Right | Tie | Wrong |
|---|---|---|---|
| Jev, side by side | 24 | 0 | 1 |
| Sentence length (median words per sentence) | 15 | 10 | 0 |
| Flesch-Kincaid grade | 9 | 0 | 6 |
| Rare words (share outside the 2,000 most common) | 8 | 2 | 7 |

Note: Each pair is two passages read by the same children. "Right" means the measure rates harder the passage that fewer children passed.

- Jev got wrong only a PIRLS pair, where pass rates also depend on how hard the questions are.
- In most pairs children read the story only after passing an easier paragraph, so these are not close calls.

**2. Does the scale follow reading level?** The pool included 40 clean excerpts from the CLEAR corpus, which have known reading levels (Lexile bands), as anchors.

| Excerpts | Median position on the scale | Share above the hardest MICS-type story |
|---|---|---|
| About Grade 1 (Lexile 100–300) | −0.5 | 40% |
| About Grade 2–3 (Lexile 410–600) | 0.3 | 73% |
| About Grade 3–4 (Lexile 700) | 1.1 | 100% |

Note: The scale is centred on the average passage; higher means harder. On this scale the test stories have a median of −2.8, and the hardest is −0.3.

**3. Does clutter drive the result?**
- **Adding clutter.** A running head, a page number and an exercise label were added to 10 test stories. This raised them by a median of 1.0 on the scale.
- **Cleaning books changed nothing.** Before and after cleaning, book passages sat the same distance above the hardest test story: 1.9 before, 2.0 after.

**4. A simpler measure as a cross-check.** A book counts as harder only if it has both more rare words and longer sentences than the hardest test version. This works in any language with a good word list.
- In most countries it finds fewer books harder than the side-by-side judgement, so its ceilings are higher.
- It is shown as open circles in the blog's chart.

## Ceilings: the uncertainty

The ceiling combines the share of books that are harder at each grade with that grade's pass rate. The 90% interval comes from 20,000 simulated draws that combine two sources of error:

- **the share of a country's books that are harder at each grade,** from a Beta posterior with a Jeffreys prior, since the books found may not be the full set;
- **the pass rate,** from its sampling error.

**The judge's own noise is left out of the interval, because it barely matters.** Across 200 bootstrap resamples of the judgements, only 5 of 426 books ever switch between harder and not harder: 2 in Uganda, 2 in South Africa and 1 in Tanzania.

## Results

**Table 1. At most this share of children could read a textbook picked at random**

| Country | Assessment | Books harder | Ceiling, % (90% interval) | Word-and-sentence-count ceiling, % |
|---|---|---|---|---|
| Kenya | Uwezo 2015 | 3 of 5 | 75 (59–92) | 100 |
| Guyana | MICS 2019 | 30 of 30 | 67 (65–74) | 80 |
| Bangladesh (Bangla) | MICS 2019 | 47 of 47 | 64 (64–69) | 75 |
| South Africa | PIRLS 2021 | 6 of 8 | 56 (46–73) | 100 |
| Pakistan | ASER 2025 | 31 of 31 | 44 (44–54) | 63 |
| Uganda | Uwezo 2024 | 15 of 18 | 42 (36–57) | 38 |
| Nigeria | MICS 2021 | 11 of 11 | 37 (36–52) | 83 |
| Tanzania | Uwezo 2017 | 12 of 13 | 33 (30–51) | 69 |
| Kiribati | MICS 2018 | 16 of 16 | 30 (28–45) | 35 |
| India | ASER 2022 | 238 of 238 | 23 (23–25) | 23 |
| Malawi | MICS 2019 | 5 of 5 | 17 (17–53) | 67 |

Note: "Books harder" counts the books judged harder than the hardest version of the test passage, out of the books with an extract. The ceiling counts each harder book as readable by at most the share of children in the next grade with a figure who passed the test, and every other book as readable by all children. The 90% interval combines error from the sample of books and from the survey. The last column applies the simpler rule: more rare words and longer sentences than the test. Countries with at least five scored books are shown.

**Table 2. Pass rates used, by grade tested**

| Country | Share passing the test, by grade (number of books set against it) |
|---|---|
| India | G2 6% (34), G3 11% (27), G4 17% (49), G5 25% (41), G6 32% (35), G7 40% (52) |
| Pakistan | G2 2% (3), G3 10% (3), G4 16% (3), G5 54% (7), G6 54% (7), G7 66% (8) |
| Bangladesh | G2 16% (2), G3 33% (2), G4 45% (9), G5 64% (9), G6 74% (9), G7 80% (16) |
| Guyana | G2 51% (11), G3 75% (5), G4 79% (6), G5 65% (5), G6 62% (4), G7 72% (4) |
| Malawi | G3 16% (2), G4 18% (1), G5 14% (1), G7 22% (1) |
| Nigeria | G2 37% (8), G3 38% (2), G4 40% (1) |
| Kiribati | G5 26% (3), G6 22% (7), G7 40% (6) |
| Tanzania | G3 15% (6), G5 33% (4), G6 40% (3) |
| Uganda | G3 7% (6), G4 22% (3), G5 36% (5), G6 53% (4) |
| Kenya | G3 40% (4), G8 96% (1) |
| South Africa | G4 49% (3), G6 42% (11) |

Note: Each book is set against the next grade with a figure, or failing that the nearest grade above.

**Other lines, left off the chart.**
- **Rwanda:** EGRA 2011, Grade 6. No child reached 80% comprehension. 45 of 49 books are harder, so the ceiling is 8% (4–16). The test predates the 2015 curriculum.
- **South Sudan:** EGRA 2016, in 25 chosen schools. The MICS story stands in for the unpublished passage. All 10 books are harder, so the ceiling is 2% (1–19).
- **Bangladesh's English-language books:** all 29 are harder, so the ceiling is 75% (75–78).

## Caveats

- **A ceiling, not an estimate.** Children who fail the test probably cannot read a harder book, but not every child who passes can. The true share is probably well below these figures.
- **One model is the main judge.** It agrees with children's pass rates and with known reading levels in English. It has not been checked against Bangla texts of known level, and no second model has judged the same pairs.
- **The books may not be typical.** Some countries' sets are incomplete; Kenya and Malawi have five books each.
- **Books without long prose are left out** of the side-by-side measure, mostly maths workbooks.
- **Test and book years differ** in some countries; see Data.

## Code and results

The code is in [`code/`](code). It is copied from the private research repository it runs in, so it will not run on its own: it expects that repository's book texts and helpers.

| Step | File |
|---|---|
| Cleaning and extracts | [`clean.py`](code/clean.py) |
| The comparative judgement run | [`cjrun.py`](code/cjrun.py) |
| The Bradley-Terry fit and the comparison design | [`cj.py`](code/cj.py) |
| Ceilings and intervals | [`run.py`](code/run.py), run through [`cli.py`](code/cli.py) |
| Reading-test passages and pass rates | [`reading.py`](code/reading.py) |
| Word and sentence measures | [`measures.py`](code/measures.py) |

The results, without any book or test text, are in [`results/`](results):
- [`results.json`](results/results.json): the ceilings by country;
- [`cj_books.csv`](results/cj_books.csv): one row per book;
- [`cj_passages.csv`](results/cj_passages.csv): every passage's place on the scale;
- [`cj_run.json`](results/cj_run.json): the run's settings and checks;
- [`validation-log.md`](results/validation-log.md): the working log of every check and earlier run.

Book texts, test passages and the CLEAR corpus are not redistributed.
