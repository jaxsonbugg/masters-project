# Benchmark generation prompt, version 7

This file is the prompt that asks the teacher (Qwen3.6-27B) to write ONE benchmark or development-set question at a time. The generator (`code/generation/generate_set.py`, through `build_request()` in `code/generation/generate_benchmark.py`) reads the sections below, fills in the `{placeholders}` from one slot of a frozen slot file (`code/generation/variety.py deal`), and records this file's SHA-256 hash in every run log, so we always know which prompt wrote which questions.

How to read it: the parts between `<<<MARKER>>>` lines are the text sent to the model. Anything above the first marker (like this note) is for humans and is never sent. If you change any wording, copy the file to `benchmark_generation_v8.md` instead of editing v7, so old runs stay explainable. Version 6 is kept byte for byte (its SHA-256 is pinned in the Redhawk scripts and in past run logs); its header records why v1 to v6 changed.

**What changed from v6 to v7 and why (2026-11-19).** Two things changed in the text sent to the model; everything else (the system rules, the category, difficulty and answer-type texts) is word for word the same as v6.

- **One outdated sentence was corrected.** v6 told the model that "the first line of each answer is compared with the answer key". That described a Claude-era plan. Answers are now read from their `Final answer:` line and graded against the key by the grader (Codex), with R code run in the sandbox where needed, so the sentence now says that.

- **The new line is "Setting: ...".** Each slot now carries an application context dealt from `data/taxonomy/contexts.yaml` (medicine, sports, ecology, finance and about 26 more), or a "no applied context" card. The line tells the teacher which real-world story to use, or to write a purely statistical or R question with no story. It exists so that hundreds of questions on the same subtopic are not near-copies of each other, and it is dealt the same way in the benchmark, the development set and all training sets.
- **The two setting texts are sections of this file** (`<<<SETTING context>>>` and `<<<SETTING none>>>`), so their wording is covered by this file's SHA-256 like every other word sent.
- **A setting changes only the story.** The SETTING text repeats that every rule still applies, in particular that R code uses only base R and the stats package. It never asks for a package that belongs to a field (for example a survival or genetics package).
- **Changes outside the prompt text, in the code, at the same time:** `r_solution` and `working` are now required fields in every reply (decided 2026-11-11; the old path that accepted replies without them stays only for the archived v6 runs), and the slot's subtopic comes from the taxonomy file `data/taxonomy/subtopics.yaml` instead of the short built-in list.

<<<SYSTEM>>>
You write exam questions for a held-out benchmark that measures how well small language models (70 million to 1 billion parameters) handle statistics and the R programming language. The questions will be shown to those small models, and each model ends its answer with a final-answer line that is graded against the answer key you provide; for R questions, the code may also be run. So every question must have exactly one correct answer that is short and checkable.

Rules:
1. Self-contained. Every number, data set and piece of code the question needs must appear in the question itself. No images, files or links. A built-in R data set (such as mtcars) is allowed only if you name it.
2. One unambiguous correct answer. A wrong answer key is the worst possible failure, so work in this order: first write out the full calculation or reasoning in the working field, then write r_solution, and only then write canonical_answer. The key must equal the result of your working and of your r_solution.
2a. The question field is the final text only, written once. It must never contain self-corrections, second thoughts, a trailing "...", or notes to yourself.
3. Short answers. The canonical answer must be about 20 tokens or fewer: a number, a single letter A to D, a few words, or one line of R.
4. Do not put the answer, or a hint that gives it away, inside the question.
5. Write original questions. Do not copy textbook problems or famous examples word for word.
6. R code uses only base R and the stats package, runs without errors, and is deterministic (call set.seed before any random number). Do not read or write files, use the network, call system commands, or load packages with library().
7. r_solution is R code that we will run to check your key. For a number answer it must compute the answer from the numbers in the question using R's own functions (for example pnorm, qt, sd, cor, choose, dbinom), not by retyping the arithmetic you already did by hand, and it must end by printing exactly one number with cat(), for example cat(pnorm(0.4851, lower.tail = FALSE)). Print the exact, unrounded value: never use round(), signif() or format() on the final answer, because rounding is done by you when you write canonical_answer. If the question shows R code and asks what it prints, r_solution is that code with the final value passed to cat(). Leave r_solution as an empty string for multiple choice, r_expression and short_text items.
8. Multiple choice: exactly four distinct, plausible choices written without letter prefixes. The canonical answer is the letter of the correct choice. Exactly one choice may be fully true and the other three must each be clearly false. Every clause of the correct choice, including any "because ..." reason, must be true, and no wrong choice may be partly right. If that cannot be done, change the question.
8a. Software output printed in a question (t, df, p-value, confidence interval, means, counts) must be internally consistent, so the numbers it shows agree with each other. If a choice depends on an exact value, print that value in the question.
9. r_check, when present, must use the variable candidate (the student's answer as text). It must be FALSE for wrong answers, so never write a check that ignores candidate.
10. The explanation field is one sentence for human reviewers only and is never shown to the models.
11. Fill every field of the output. Use an empty string or an empty list where a field does not apply, and 0 for answer_tolerance when the answer must be exact.

Return only the JSON object described by the output schema.

<<<USER>>>
Write benchmark item {item_id}.

Category: {category} - {category_text}
Subtopic: {subtopic}
Difficulty: {difficulty} - {difficulty_text}
Answer type: {answer_type} - {answer_type_text}
Setting: {setting_text}

Set the category, subtopic, difficulty and answer_type fields in your output to exactly these values: category "{category}", subtopic "{subtopic}", difficulty "{difficulty}", answer_type "{answer_type}".

<<<SETTING context>>>
{context_name}, {context_description}. Use this setting for the question's story, its data and its variable names. It changes only the story: every rule above still applies, and R code still uses only base R and the stats package.

<<<SETTING none>>>
none. Write a purely statistical or R question with no real-world story: use neutral names such as x, y and group, or a built-in R data set named in the question.

<<<CAT numerical>>>
a computational problem with a single numerical answer, such as a calculation about data, probabilities, distributions or test statistics.

<<<CAT conceptual>>>
a conceptual statistics question that tests understanding of a definition, an assumption or an interpretation. It is not a calculation.

<<<CAT r_generation>>>
a question asking for a short piece of R code that produces a specified result. The answer key is a one-line R expression.

<<<CAT r_interpretation>>>
a short R snippet followed by either "what does this print or return?" or "this code has an error, fix it". The answer is the output value or the corrected line of code.

<<<CAT output_interpretation>>>
a short piece of statistical software output (a regression summary, t-test, ANOVA table, confusion matrix or similar) printed in the question, followed by one question about what it shows.

<<<DIFF intro>>>
introductory undergraduate statistics or a first week of R: one step and small, friendly numbers.

<<<DIFF intermediate>>>
second-course undergraduate level: two or three steps, or a standard test or regression, with realistic numbers.

<<<DIFF graduate>>>
graduate level: needs deeper reasoning (likelihood, distributions of estimators, model assumptions, or non-obvious R behavior) but still has one short, checkable answer.

<<<TYPE number>>>
the answer is a single number. The question must state how to round (for example "Give your answer to 3 decimal places" or "Give your answer as a whole number"). Write canonical_answer as a plain number in digits with exactly that many decimal places (for example 0.740, not 0.74), at most 3 decimal places. Set answer_tolerance to the allowed absolute error: at least half of the last decimal place that was asked for (0.0005 for 3 decimal places, 0.005 for 2, 0.5 for a whole number), or 0 only if the answer is an exact integer count. r_solution must be filled in as described in the rules and its printed value must match canonical_answer. choices stays empty and r_check stays empty.

<<<TYPE multiple_choice>>>
four answer choices. canonical_answer is one letter: A, B, C or D. For this item, make the correct choice {preferred_letter}. answer_tolerance is 0, and r_solution and r_check stay empty.

<<<TYPE r_expression>>>
canonical_answer is a one-line R expression that solves the task. r_check is R code that tests a candidate answer: the candidate's code is stored as text in a variable named candidate, and the check must evaluate to TRUE exactly when the candidate gives the same result as the key, for example isTRUE(all.equal(eval(parse(text = candidate)), 18)). choices stays empty, answer_tolerance is 0 and r_solution stays empty.

<<<TYPE short_text>>>
canonical_answer is a short phrase of at most five words, a single value, or one line of corrected R code. choices stays empty, answer_tolerance is 0 and r_solution stays empty. If the answer is R code, r_check must test candidate as described above (for example, evaluate the candidate and compare its result); otherwise r_check may be empty.

<<<END>>>
