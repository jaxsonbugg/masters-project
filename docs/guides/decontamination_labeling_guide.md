# Labeling guide for decontamination pairs (2026-11-19; approved by Jaxson 2026-11-19)

This guide is for the person who labels question pairs by hand (Jaxson). The labels decide the thresholds that the decontamination code (`code/verification/decontaminate.py`) uses to remove training examples. The method is described in `docs/methodology/workflow.md` Section 4, safeguard 5; this file covers only how to label.

## Why labels are needed

**Decontamination** means keeping the training data from containing the test questions. If a student model trains on a copy of a benchmark question, a correct answer on that question may be memory, not skill, and the benchmark score would overstate what the student learned. The same idea applied inside the training data is **duplicate removal**: if the training set holds near-copies of one problem, the student sees that problem many times and fewer different problems.

The code cannot decide on its own what counts as a "copy". It computes similarity scores for pairs of questions:

- **shared 8-word runs:** whether the two texts share any sequence of 8 or more words in a row, as written or with every number replaced by a placeholder (`#`);
- **template similarity:** how much of the wording is the same once the numbers are masked, from 0 (nothing shared) to 1 (identical apart from numbers);
- **embedding similarity:** a small language model (`all-MiniLM-L6-v2`) turns each question into a list of 384 numbers that summarize its meaning; the cosine similarity of the two lists runs from about 0 (unrelated) to 1 (the same meaning), and it stays high when the same problem is reworded.

These scores only **nominate** pairs: a high score means "a person should look at this", not "this is a copy". Questions in this project share a lot of vocabulary by design (every binomial question says "probability", "trials" and "success"), so many high-scoring pairs are distinct problems. Your labels show where, on each score, real copies stop and distinct problems start. The removal rule is then chosen from your labels, and you approve it before it is applied.

## The three labels

Read both questions (with their answer choices, if any) and pick one label.

**1. Duplicate or paraphrase (`duplicate`).** The same problem: the same setup, the same numbers (or numbers that make no difference), and the same question asked, so the answer to one is the answer to the other, or follows from it trivially. The wording may be completely different.

> A: "A fair die is rolled 4 times. What is the probability of getting exactly two sixes? Give your answer to 3 decimal places."
> B: "In four rolls of a fair six-sided die, find P(two sixes exactly), to 3 decimals."
> Label: **duplicate**. Same experiment, same numbers, same question; only the wording changed. Both answers are 0.116.

**2. Template variant (`template`).** The same wording and setup, with only the numbers (or the names of things) changed. Someone who memorized one has seen the exact recipe for the other.

> A: "A fair die is rolled 4 times. What is the probability of getting exactly two sixes?"
> B: "A fair die is rolled 7 times. What is the probability of getting exactly three sixes?"
> Label: **template**. The recipe (binomial with p = 1/6, "exactly k") and the sentence are the same; only n and k changed.

> A: "x <- c(4, 8, 15); mean(x) — what does this print?"
> B: "y <- c(2, 9, 10); mean(y) — what does this print?"
> Label: **template**. The same code with different numbers and a different variable name.

**3. Distinct (`distinct`).** The same concept or the same topic, but a genuinely different problem: a different setup, a different quantity asked for, or a different step needed to solve it. Knowing the answer to one does not give the answer to the other.

> A: "A fair die is rolled 4 times. What is the probability of getting exactly two sixes?"
> B: "A fair die is rolled 4 times. What is the expected number of sixes?"
> Label: **distinct**. Same experiment, but B asks for an expected value (n × p = 0.667), a different calculation from A's probability.

> A: "Which call gives the mean of mpg for each number of cylinders in mtcars? (tapply)"
> B: "Write one line of R that gives the mean of mpg for each number of cylinders in mtcars, as a data frame. (aggregate)"
> Label: **distinct**. The same goal, but B asks for a different function and output shape, so the answer to A does not answer B.

## Rules for hard cases

- **Look at what is asked, not at the vocabulary.** Two questions that both mention "p-value", "t-test" and "sample of 25" may still ask different things. Same question asked about the same setup means duplicate; same recipe with new numbers means template; anything that needs a different step means distinct.
- **A changed story with the same numbers and question is a duplicate.** "Patients' recovery times" versus "machines' repair times" with the same five numbers and the same "find the sample standard deviation" is the same problem in a new costume.
- **A changed story AND changed numbers, same recipe and question, is a template variant.**
- **Answer choices count.** Two multiple-choice questions with the same stem but different choices, where a different choice is correct for a different reason, are distinct. With the same stem and the same correct statement among reworded choices, they are duplicates.
- **R code:** the same code with only literals or variable names changed is a template variant. Code that calls a different function, or the same function with arguments that change what it does (for example `sd(x)` versus `sd(x, na.rm = TRUE)` when `x` has an `NA`), is distinct.
- **When unsure between two labels, pick the less severe one** (template over duplicate, distinct over template) and tick the "unsure" box. Unsure pairs are counted and reported separately; they show where the boundary itself is unclear.
- **Do not look up which question is from which set,** and do not try to guess the scores. The sheet hides them on purpose (below).

## How a labeling session works

1. The code draws the pairs and writes a sheet (`labeling_sheet.csv`) with one row per pair: a random pair number, question 1 and question 2 (each with its choices), and empty columns `label` (`duplicate`, `template` or `distinct`), `unsure` (`yes` or empty) and `note`.
2. **The sheet is blind.** The scores, the check that nominated the pair, and the IDs of the two questions are kept in a separate key file you do not open while labeling. The rows are in random order, and which question is "question 1" is random too. This keeps the labels from being pulled toward the scores they are meant to test.
3. You fill in `label` for every row (and `unsure` or `note` where useful). About 150 to 200 pairs take roughly two to three hours.
4. The code joins your labels to the key file and reports, for each score, how the three labels spread across score bands. For example: "of 40 pairs with embedding similarity above 0.95, 31 were duplicate, 6 template and 3 distinct".
5. A removal rule is proposed from that table and shown to you with its estimated precision (of the pairs the rule removes, the share that truly are copies) and recall (of the true copies among the labeled pairs, the share the rule removes), each with a 95% confidence interval. **You approve the rule before it touches any data.**

## Which pairs are labeled (and which are not)

- **Calibration pairs** come only from an early training batch compared with the **development set**, never with the benchmark, so the benchmark plays no part in choosing the thresholds. They are drawn across score bands and across the check that nominated them, so you see both clear and borderline cases.
- **Synthetic hard pairs (about 80).** After the development set exists, I write two kinds of pairs from development questions, and you review them before use: *hard duplicates* (heavy rewordings, renamed variables, reordered sentences, or template variants with new numbers) and *hard distinct pairs* (same concept, different problem, across numerical and R questions, such as the die examples above). These test whether the checks find copies at all ("retrieval") and whether the rule keeps distinct pairs. Because I write them, their labels are known in advance, so you review them rather than label them blind.
- **An audit of pairs the checks did not nominate (about 100).** For a random sample of training examples, the closest development question by embedding similarity is put on a sheet even if no check flagged it. Your labels estimate how many copies slip past the checks entirely.
- **After the real run,** a sample of kept pairs just below the thresholds is labeled to estimate how much leakage remains.

## What the labels can and cannot tell us

The labeled pairs measure how well the rule **classifies** pairs that the checks found. They do not, by themselves, show how many copies the checks never found; the synthetic pairs and the audit estimate that. Together they give an estimate, with confidence intervals, of how much leakage is removed and how much may remain. **Decontamination reduces leakage; it cannot prove that none remains,** and the report says so.

## Default decisions per label (to confirm when the rule is fixed)

| Pair | Duplicate | Template variant | Distinct |
|---|---|---|---|
| Training example against a benchmark or development question | remove the training example | remove the training example | keep |
| Training example against an earlier training example | remove the later one | keep both (practice on the same recipe with new numbers) | keep both |

The benchmark is never changed because of an overlap; it is frozen before any training data is generated, and an overlap is always resolved by removing the training example.
