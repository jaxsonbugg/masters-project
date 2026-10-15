# Benchmark generation prompt, version 6

This file is the prompt that asks Claude to write ONE benchmark question at a time. The same file is used for the 20-question trial and for the full 1,000-question benchmark, so the trial tests exactly what the big run will send. The script `code/generation/generate_benchmark.py` reads the sections below, fills in the `{placeholders}` for each item, and records this file's SHA-256 hash in every run log so we always know which prompt wrote which questions.

How to read it: the parts between `<<<MARKER>>>` lines are the text sent to the model. Anything above the first marker (like this note) is for humans and is never sent. If you change any wording, copy the file to `benchmark_generation_v7.md` instead of editing v6, so old runs stay explainable.

**What changed from v1 to v2 and why.** The first trial (2026-10-07) found that 3 of 8 numerical answer keys were wrong, and one R check tested nothing. In v2 the model must (1) write out its calculation in a new `working` field BEFORE it writes the key, and (2) write `r_solution`, R code that recomputes every number. We then run that R code ourselves (`generate_benchmark.py verify`); if R and the key disagree, the item is flagged. The model's typed number is no longer trusted on its own, because in one case the model's own explanation contained the arithmetic slip.

**What changed from v2 to v3 and why.** The second trial (prompt v2) showed a rounding problem. BM0001 asked for the probability of exactly 2 heads in 5 fair coin tosses; the exact value is 0.3125. The model's key was 0.313 (the usual rule: round half up), but its `r_solution` wrapped the answer in `round(x, 3)`, and R rounds 0.3125 to 0.312, so the key and R disagreed even though nothing was wrong. In v3 (1) `r_solution` prints the UNROUNDED number, so R is compared with the key before any rounding, (2) every number question must say how to round and the key must be written with exactly that many decimals (BM0005 asked for 3 decimals but its key was `0.74`), and (3) for a rounded answer the allowed error `answer_tolerance` must be at least half of the last decimal place, so a student who rounds a tie the other way is not marked wrong. Everything else is unchanged from v2.

**What changed from v3 to v6 and why (v4 and v5 were tried in between and set aside).** v3 was the best of the first three prompts, but its trial still had two problems R cannot see: BM0015's question text thought aloud ("...must be... no: exactly 2 statisticians..."), and BM0017, a multiple-choice question whose answer key was wrong (no choice was fully correct). v4 tried to fix this by making the model write its `working` field FIRST and judge every answer choice true or false inside it; the API then refused all 20 requests, most likely because a reasoning field written before the answer looks like a request to reveal the model's reasoning (the refusal category was not recorded, so this is a likely cause, not proven). v5 removed the `working` field entirely; it was accepted by the API but did worse (a wrong key, and two questions that thought aloud and gave up). v6 therefore goes back to v3 exactly (the `working` field stays AFTER the question, which v3 never had refused) and adds only three content rules, worded so that none of them tells the model to reason, design or judge anything in its reply: (1) the question field must be final text with no self-corrections or trailing "..." (rule 2a); (2) multiple choice must have exactly one fully true choice and three clearly false ones (rule 8, extended); (3) numbers printed in a question as software output must agree with each other (rule 8a). Separately from this prompt, the script now takes the answer key for number questions from R's own output instead of the model's typed number, and regenerates any item that fails the automatic checks.

<<<SYSTEM>>>
You write exam questions for a held-out benchmark that measures how well small language models (70 million to 1 billion parameters) handle statistics and the R programming language. The questions will be shown to those small models, and their answers will be graded automatically: the first line of each answer is compared with the answer key you provide, or, for R questions, the code is run. So every question must have exactly one correct answer that is short and checkable.

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

Set the category, subtopic, difficulty and answer_type fields in your output to exactly these values: category "{category}", subtopic "{subtopic}", difficulty "{difficulty}", answer_type "{answer_type}".

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
