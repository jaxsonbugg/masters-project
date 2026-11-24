# The benchmark audit (drawn 2026-11-24)

**What it is.** R checks number keys and grading checks, and Codex screens every question for clarity, but nothing so far
checks whether a multiple-choice or short-text key is actually right (Codex never sees the keys). The audit is that human
check, on a random sample, so the report can state an estimated key-error rate with a confidence interval
(docs/methodology/workflow.md, Section 4, safeguard 6d).

**The sample.** 150 questions drawn from the final 1,000 (`2026-11-24_assembly2/positions.jsonl`) by a seeded random draw
(seed `audit-2026-11-24`), stratified by category in the benchmark's own mix: numerical 45, conceptual 30, R generation 30,
output interpretation 23, R interpretation 22. Draw details: `audit_draw.json`.

**The targeted section (33 rows).** Questions Jaxson edited, chose by hand, kept against a Codex screen flag, or kept with a
subtopic verdict, that are not already in the random sample (10 more such questions are in the random sample, marked in
`why_targeted`). Reported separately and never mixed into the error rate. Questions accepted only at their intended
difficulty are not targeted (they passed every check; decision of 2026-11-22).

**What to fill in, per row:**
- `key_correct (yes/no/unsure)`: is the key the right answer to the question as written?
- `question_sound (yes/no/unsure)`: is the question clear, answerable and correctly worded (one correct option for multiple
  choice)?
- `owner_note`: a short reason for any "no" or "unsure".

**How it is used.** The error rate is the share of "no" for `key_correct` in the random 150, with a 95 percent exact
(Clopper-Pearson) interval; for example 3 of 150 is 2.0 percent (0.4 to 5.7 percent). Any question marked "no" is fixed or
replaced before the freeze, and the fix is logged; the error rate still describes the benchmark as it stood when drawn.
