# Do the difficulty measures rank passages the way children's results do?

Lee, 2026-11-01 (step 4 of the difficulty upgrade). Run: `uv run --no-sync python scripts/validate_measures.py`.

**Data.** `validation_passages.csv` lists 39 test passages that the same children were given, each with the share who passed it, and a page reference.

- **Sources.**
  - Uwezo Kenya 2012 (English and Kiswahili).
  - Uwezo Uganda 2012, 2013, 2015 and 2018 (English, plus Luganda in 2013).
  - Uwezo Uganda 2024 (English and Leblango, two samples). The shares come from the public child microdata, so each child is matched to the exact sample they read.
  - ASER India 2022 (Hindi and Bengali, from the state pages).
  - PIRLS 2021 South Africa, Grade 6 (two released passages).
- **Texts.** The passages are in `build/difficulty/validation/`, not in git because they are copyrighted.
- **What a pair is.** A pair is two passages given to the same children. The one fewer children passed should score as harder.

**Result** (25 distinct passage pairs; `validation.csv` repeats a pair once for each grade with a figure):

| Measure | Right | Tie | Wrong | Pairs it can score |
|---|---|---|---|---|
| Sentence length (median words per sentence) | 15 | 10 | 0 | 25 |
| Rare words (share outside the 2,000 most common) | 8 | 2 | 7 | 17 |
| Flesch-Kincaid | 9 | 0 | 6 | 15 |
| Spache | 8 | 0 | 7 | 15 |

- **Sentence length never ranks a pair the wrong way.** Rare words, Flesch-Kincaid and Spache do little better than chance on these pairs.
- **The rare-word share is noisy on short passages.** The paragraphs run 20 to 40 words, so one or two uncommon words move the share by 5 to 10 points.
- **Test designers grade passages by length and sentence structure.** They keep the vocabulary familiar, so rare words barely separate a paragraph from a story.
- **Books are less noisy than test passages.** A book's score is the median of many 70-word passages, but the test story is a single passage. Using the hardest version of a test as the bar guards against one easy version.
- **Rare words cannot be scored in Kiswahili, Luganda or Leblango**, because the frequency source has no word list for them. Sentence length works in all six languages.

**Limits.**

- **The pairs are nested.** In Uwezo and ASER, a child reads the story only after passing the paragraph, so the story's pass share is lower by construction. These pairs therefore test whether a measure ranks the story above the paragraph, as the designers intended, and are not close calls.
- **Only PIRLS is an independent pair**, and every measure misses or ties on it. Its pass shares also reflect how hard the questions are.
- **Before 2024, a printed sample stands for several test versions.** Uwezo printed one sample test, but the shares pool all the versions children were given.
- **The Hindi and Bengali texts were transcribed from images** and should be checked by a reader of those scripts.
- **More notes** on each row are in the `note` column of `validation_passages.csv`.

**Use in the ceiling.** Since 2560c79, a book counts as harder only when it beats the hardest test version on both rare words and sentence length. `results.json` also keeps the ceiling on rare words alone under `words_only`.

## Trial of steps 2 and 3 (Lee, 2026-11-01)

**Step 2: age of acquisition.** This uses the Kuperman, Stadthagen-Gonzalez and Brysbaert (2012) ratings of the age at which 31,104 English words are learnt. They come from the Springer erratum's supplement and are kept in `build/difficulty/aoa_kuperman.csv`, not in git. The code is `measures.aoa_scores`, which returns two numbers:
- `aoa_mean`: the mean rated age of a passage's words.
- `aoa_late`: the share of those words learnt at age 8 or later.

**Step 3: a model's judgement.** Claude Sonnet 5.5 read each pair of passages and said which is harder for a 9-year-old beginning reader to read and understand. It ran as four subagents in a Claude Code session, with no API key. The passage order was randomised, and the judges saw no scores and no answers.

- Items: `scripts/judge_items.py`.
- Scoring: `scripts/judge_score.py`.
- Results: `judge_trial.csv` (no text).

**The CLEAR corpus.** This holds 4,724 excerpts for Grades 3 to 12 (Crossley et al. 2022; CC BY-NC-SA; `scripts/clear_check.py`, scores in `clear_scores.csv`). Each excerpt has an ease score built from teachers' paired judgements.

How strongly each measure tracks the teachers' ease score, over all 4,724 excerpts (Spearman correlation; more negative is better):

| Measure | Correlation |
|---|---|
| Rare words | −0.40 |
| Sentence length | −0.36 |
| Flesch-Kincaid | −0.52 |
| Age of acquisition (`aoa_mean` or `aoa_late`) | −0.59 |

Share of 60 random CLEAR pairs ordered as the teachers order them. There were 20 pairs in each band of gap in ease.

| Gap in ease | Model's judgement | Age of acquisition | Flesch-Kincaid | Rare words | Sentence length |
|---|---|---|---|---|---|
| Small (< 0.5) | 14/20 | 13 | 14 | 11 | 13 |
| Middling (0.5–1) | 12/20 | 15 | 12 | 10 | 12 |
| Large (> 1) | 19/20 | 18 | 16 | 17 | 11 |
| All | 45/60 (75%) | 46 (77%) | 42 (70%) | 38 (63%) | 36 (60%) |

**The 25 pairs of test passages.**
- The model's judgement orders 23 of them correctly.
- It misses the PIRLS pair, where children's scores also depend on the questions.
- It misses one Luganda pair.
- Sentence length orders 15 correctly and ties 10. Age of acquisition orders 9 correctly, ties 2 and gets 4 wrong.

**48 textbook passages set against their country's hardest test story.** There were 16 each for India, Uganda and Guyana.

- **The model calls almost every passage harder than the story:** India 16 of 16, Guyana 15 of 16 and Uganda 11 of 16.
- **It agrees with the two-measure rule on 38 of 48.**
- **Uganda.** The 5 passages the model calls easier are all set against the 2024 eclipse story, which it finds harder than a simple exercise or song.
- **Guyana.** The model calls 5 passages harder that the rule does not. Some of these are maths worksheets or credits pages: scan text the model reads as hard.

**Reading.**
- **On teachers' ratings, the model is no better than age of acquisition** on 60 pairs, so a larger sample is needed to tell them apart.
- **On the test passages, the model is the only measure that is both often right and rarely wrong.**
- **On books, it supports the ceiling.** In India and Guyana nearly every passage is harder than the story.
- **The Uganda result depends on which test version is the bar.** Under the hardest version, the eclipse story, the model calls 5 of 16 passages easier.
- **Not yet done:**
  - a second judge model (Opus) to check consistency;
  - a larger CLEAR sample;
  - book-level passages for more countries.

## Comparative judgement over every scored book (Lee, 2026-11-01)

**The run.** Code is `tgs.difficulty.cjrun`; output is in `cj_run.json`, `cj_books.csv` and `cj_passages.csv` (no text). Each `results.json` country now has a `comparative` field.

- **The pool.** 1,200 passages:
  - 40 test passages;
  - 40 clean CLEAR excerpts of known level;
  - 10 test stories with scan noise added;
  - 1,110 textbook passages, two per scored book. The English and Bangla pools are judged separately.
- **The judgements.** Jev (jev-1.13.0) judged 7,976 pairs. Each pair was asked in both option orders and the two answers averaged. The run used 6.48 million input tokens, which cost $0.27.
- **The scale.** A Bradley-Terry fit puts every passage on one difficulty scale.
- **The rule.** A book counts as harder when its median passage sits above the hardest version of its country's test.
- **Intervals.** They come from 200 bootstrap resamples of the judgements.

**Messiness check (English pool).**

Clean texts of known level fall in the expected order:

| Clean CLEAR excerpts | Median position on the scale | Share above the hardest Grade 2 test story |
|---|---|---|
| About Grade 1 (Lexile 100–300) | −2.6 | 13% |
| About Grade 2–3 (Lexile 410–600, 500) | −1.2 | 73% |
| About Grade 3–4 (Lexile 700) | 0.0 | 100% |

- **The test stories sit low.** Their median is −3.8 and the hardest is −1.8.
- **Textbook passages sit with Grade 3–4 texts.** Their median is +0.1.
- **Scan noise does raise a passage.** Adding a running head, a page number, an exercise number and a broken line lifted a story by a median of +0.84 (range −0.07 to +1.36). That is less than half the gap between textbook passages and the hardest test story.

**How many books stay harder after taking off the noise lift:**

| Line | Median lift (0.84) taken off | Largest lift (1.36) taken off |
|---|---|---|
| India | 238/238 | 238/238 |
| Pakistan | 31/31 | 31/31 |
| Bangladesh (Bangla) | 47/47 | 47/47 |
| Tanzania | 13/13 | 13/13 |
| Kiribati | 16/16 | 16/16 |
| Guyana | 33/35 | 31/35 |
| Uganda | 13/18 | 7/18 |
| Nigeria | 9/11 | 6/11 |
| Kenya | 3/5 | 1/5 |
| South Africa | 6/19 | 2/19 |

The Bangla pool had no noise check.

**Ceilings (% who could at most read a book drawn at random, with 90% interval).** These are on the books that have a ceiling; `results.json` gives every line.

| Country | Rare words only | Rare words and sentence length | Comparative judgement |
|---|---|---|---|
| India | 23 | 23 | 23 (23–25), 238/238 harder |
| Malawi | 50 | 67 | 17 (17–53), 5/5 |
| Tanzania | 62 | 69 | 26 (26–42), 13/13 |
| Kiribati | 35 | 35 | 30 (28–45), 16/16 |
| Uganda | 28 | 38 | 33 (31–49), 17/18 |
| Nigeria | 66 | 83 | 37 (36–52), 11/11 |
| Pakistan | 60 | 63 | 44 (44–54), 31/31 |
| South Africa | 100 | 100 | 63 (55–73), 9/14 |
| Kenya | 100 | 100 | 63 (54–83), 4/5 |
| Bangladesh (Bangla) | 68 | 75 | 64 (64–69), 47/47 |
| Guyana | 73 | 80 | 65 (62–72), 35/35 |

**Reading.**

- **On Jev's reading, nearly every book is harder than the test passage**, so most ceilings fall to the pass rate itself.
- **The anchors show the scale tracks reading level on clean text.** The noise check shows that messiness explains only part of the gap.
- **Where the gap is small, the result rests on the noise correction.** This is so for Uganda, Nigeria, Kenya and South Africa.
- **Not yet done:**
  - a check of the Bangla pool against clean Bangla texts of known level;
  - a second judge for the same pairs.

## Cleaned, length-matched passages (Lee, 2026-11-02)

**What changed.** Book passages are now cut by `tgs.difficulty.clean` and not as blind 70-word windows.

- **Cleaning.** Page numbers and running heads or footers are dropped. Headings, labels and tables break the text. Lines are rejoined and hyphenated words mended.
- **Passages.** Each is a run of whole sentences, as long as its line's test passage (within 15% or 2 words): IND 17 words, PAK 22, TZA 64, RWA 68, UGA 74, KEN 79, ZAF 710, the rest 72.
- **Passages per book.** Each book gives enough passages to cover about 140 words: 2 to 6.
- **Books left out.** A book with no stretch of prose that long is left out: 5 in Guyana, 7 in South Africa (6 of them in the scored 14).

The earlier runs are kept for comparison:
- `cj_*_raw.*`: uncleaned 70-word windows;
- `cj_*_clean70.*`: cleaned passages of 70 to 140 words.

**Cleaning alone (clean70 run).** Book passages still sit about 2.0 above the hardest test story on the fitted scale, against 1.9 before cleaning. So clutter was not driving the gap. Cleaning the noise-added test stories took their median lift from 1.06 to 0.55. The rest is mostly the added instruction line ("Answer the questions."), which the cleaner keeps as text a child reads.

**Length-matched run.** 2,321 passages and 15,710 pairs; $0.47.

| Country | Raw | Cleaned | Cleaned and length-matched |
|---|---|---|---|
| Malawi | 17.2, 5/5 | 17.2, 5/5 | 17.2 (17.2–52.7), 5/5 |
| India | 23.1, 238/238 | 23.1, 238/238 | 23.1 (23.1–25.1), 238/238 |
| Kiribati | 29.9, 16/16 | 29.9, 16/16 | 29.9 (27.8–45.0), 16/16 |
| Tanzania | 26.3, 13/13 | 26.3, 13/13 | 32.8 (29.5–51.0), 12/13 |
| Nigeria | 37.1, 11/11 | 37.1, 11/11 | 37.1 (35.7–51.9), 11/11 |
| Uganda | 33.0, 17/18 | 34.5, 16/17 | 41.7 (36.1–57.0), 15/18 |
| Pakistan | 44.0, 31/31 | 44.0, 31/31 | 44.0 (44.0–53.9), 31/31 |
| South Africa | 62.6, 9/14 | 87.5, 3/14 | 56.3 (46.3–73.1), 6/8 |
| Bangladesh (Bangla) | 64.4, 47/47 | 64.4, 47/47 | 64.4 (64.4–69.2), 47/47 |
| Guyana | 64.8, 35/35 | 66.8, 29/29 | 67.0 (65.4–73.9), 30/30 |
| Kenya | 63.2, 4/5 | 75.2, 3/5 | 75.2 (59.2–91.5), 3/5 |

**Reading.**
- **The strong cases do not move.** India's books are harder even as 17-word extracts set against the 17-word ASER test.
- **South Africa swings with the passage length.** Against 700-word PIRLS passages, 6 of the 8 books with prose that long are harder. Its result rests on few books.
- **Kenya, Uganda and Tanzania loosen slightly.**
